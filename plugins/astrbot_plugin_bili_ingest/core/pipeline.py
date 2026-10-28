"""阶段一流水线：发现 → 去重 → 字幕 → 判定 → 入库。"""

import asyncio
import time
from datetime import datetime

from astrbot.api import logger

from . import judge as judge_mod
from .client import BiliClient
from .db import BiliDB


class Pipeline:
    def __init__(self, cfg: dict, db: BiliDB, client: BiliClient, llm_call):
        self.cfg = cfg
        self.db = db
        self.client = client
        self.llm_call = llm_call  # async (prompt) -> str

    # ---------- 时段 ----------
    @staticmethod
    def in_offpeak(now: datetime | None = None) -> bool:
        now = now or datetime.now()
        if now.weekday() >= 5:
            return True
        return not ((9 <= now.hour < 12) or (14 <= now.hour < 18))

    def quota_left(self) -> int:
        return int(self.cfg.get("daily_quota", 8)) - self.db.count_today()

    # ---------- 发现 ----------
    async def discover(self) -> list[dict]:
        source = self.cfg.get("source", "popular")
        items: list[dict] = []
        if source == "search":
            kws = self.cfg.get("keywords") or []
            if not kws:
                kws = ["科技", "游戏"]
            for k in kws:
                try:
                    items.extend(await self.client.search(k, 10))
                except Exception as e:
                    logger.warning(f"[bili] 搜索 {k} 失败: {e}")
                await asyncio.sleep(1.2)
        else:
            pn = int(self.db.get_meta("popular_pn", "1") or 1)
            try:
                items = await self.client.popular(page=pn, size=20)
                self.db.set_meta("popular_pn", str(pn % 10 + 1))
            except Exception as e:
                logger.warning(f"[bili] 热门流失败: {e}")
        return items

    def _pass_gate(self, v: dict) -> bool:
        if not v.get("bvid"):
            return False
        if int(v.get("view") or 0) < int(self.cfg.get("min_views", 50000)):
            return False
        age_days = (time.time() - int(v.get("pubdate") or 0)) / 86400
        if age_days < float(self.cfg.get("min_age_days", 1)):
            return False
        return True

    # ---------- 主流程 ----------
    async def run_round(self, limit: int | None = None) -> dict:
        started = time.time()
        summary = {"seen": 0, "nosub": 0, "accept": 0, "skip": 0, "error": 0, "candidates": 0}

        if self.cfg.get("offpeak_only", True) and not self.in_offpeak():
            summary["skipped"] = "peak_hours"
            return summary
        if self.quota_left() <= 0:
            summary["skipped"] = "quota"
            return summary

        items = await self.discover()
        summary["candidates"] = len(items)
        todo = []
        for v in items:
            if not self._pass_gate(v):
                continue
            prev = self.db.candidate(v["bvid"])
            if prev:
                # 无字幕的隔 7 天再试（有些视频后来才补上 AI 字幕）；其它结论不再重试
                stale_nosub = (
                    prev.get("decision") == "nosub"
                    and time.time() - (prev.get("judged_at") or 0) > 7 * 86400
                )
                stuck = (
                    not prev.get("decision")
                    and time.time() - (prev.get("first_seen_at") or 0) < 86400
                )
                if not stale_nosub or stuck:
                    continue
            todo.append(v)

        budget = limit or int(self.cfg.get("per_run", 3))
        max_chars = int(self.cfg.get("max_subtitle_chars", 8000))
        threshold = float(self.cfg.get("strength_threshold", 0.6))

        for v in todo[: max(budget, 0)]:
            if self.quota_left() <= 0:
                break
            bvid = v["bvid"]
            self.db.add_candidate(bvid, v.get("title", ""), v.get("up_name", ""),
                                  int(v.get("view") or 0), int(v.get("pubdate") or 0))
            summary["seen"] += 1
            try:
                info = await self.client.info(bvid)
            except Exception as e:
                logger.warning(f"[bili] {bvid} 详情失败: {e}")
                self.db.decide(bvid, "error", f"view: {e}")
                summary["error"] += 1
                continue

            await asyncio.sleep(1.5)
            try:
                sub = await self.client.subtitle(bvid, info.get("cid"))
            except Exception as e:
                logger.warning(f"[bili] {bvid} 字幕失败: {e}")
                sub = ""

            if not sub or len(sub) < 80:
                self.db.decide(bvid, "nosub", "无字幕或字幕过短")
                summary["nosub"] += 1
                logger.info(f"[bili] 跳过（无字幕）{bvid} {info.get('title','')[:24]}")
                continue

            prompt = judge_mod.build_prompt(info, sub, max_chars)
            try:
                raw = await self.llm_call(prompt)
            except Exception as e:
                logger.warning(f"[bili] {bvid} 判定调用失败: {e}")
                self.db.decide(bvid, "error", f"judge: {e}")
                summary["error"] += 1
                continue

            verdict = judge_mod.parse(raw)
            if not verdict:
                self.db.decide(bvid, "error", "判定输出无法解析")
                summary["error"] += 1
                continue

            if verdict["verdict"] == "skip" or verdict["strength"] < threshold:
                self.db.decide(bvid, "rejected", verdict["reason"] or "强度不足")
                summary["skip"] += 1
                logger.info(f"[bili] 不收 {bvid} strength={verdict['strength']}")
                continue

            ok = self.db.add_video(
                bvid=bvid,
                title=info.get("title", "")[:120],
                up_name=info.get("up_name", "")[:40],
                cover_url=info.get("cover", ""),
                duration=int(info.get("duration") or 0),
                pubdate=int(info.get("pubdate") or 0),
                category=verdict["category"],
                strength=verdict["strength"],
                summary=verdict["summary"],
                subtitle_head=sub[:2000],
                ingested_at=int(time.time()),
            )
            if ok:
                self.db.decide(bvid, "accepted", verdict["reason"])
                summary["accept"] += 1
                logger.info(
                    f"[bili] 入库 {bvid} [{verdict['category']}] "
                    f"{verdict['strength']} {verdict['summary']}"
                )
            else:
                self.db.decide(bvid, "error", "写入失败")

        summary["elapsed"] = round(time.time() - started, 1)
        return summary
