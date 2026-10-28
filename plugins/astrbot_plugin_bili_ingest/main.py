"""阶段一：谷时自动刷 B 站，判定入库（不发任何消息）。"""

import asyncio
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .core.client import BiliClient
from .core.db import BiliDB
from .core.pipeline import Pipeline

DB_PATH = "data/plugin_data/bili_ingest/bili.db"
JOB_NAME = "bili_ingest_hourly"


@register(
    "astrbot_plugin_bili_ingest",
    "dyy-2503",
    "谷时刷B站并入库",
    "0.1.0",
)
class Main(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self.db = BiliDB(DB_PATH)
        self.client = BiliClient(
            sessdata=self.config.get("sessdata", ""),
            bili_jct=self.config.get("bili_jct", ""),
        )
        self.pipeline = Pipeline(self.config, self.db, self.client, self._llm)
        self._running = False

    async def initialize(self):
        if not self.config.get("enable", True):
            return
        try:
            for job in await self.context.cron_manager.list_jobs("basic"):
                if job.name == JOB_NAME:
                    await self.context.cron_manager.delete_job(job.job_id)
            await self.context.cron_manager.add_basic_job(
                name=JOB_NAME,
                cron_expression="7 * * * *",
                handler=self._job,
                description="B站：每小时检查谷时并刷一轮",
                timezone="Asia/Shanghai",
                persistent=False,
            )
            logger.info("[bili] 定时任务已注册（每小时 :07）")
        except Exception as e:
            logger.error(f"[bili] 注册定时任务失败: {e}")

    async def terminate(self):
        try:
            self.db.close()
        except Exception:
            pass

    # ---------- LLM ----------
    async def _llm(self, prompt: str) -> str:
        pid = (self.config.get("judge_provider_id") or "").strip()
        if not pid:
            try:
                cfg = self.context.get_config() or {}
                pid = (cfg.get("agent_runner", {}).get("config", {})
                       .get("model", {}).get("provider_id") or "deepseek-chat")
            except Exception:
                pid = "deepseek-chat"
        resp = await self.context.llm_generate(
            chat_provider_id=pid,
            prompt=prompt,
            system_prompt="你是一个严格的视频筛选器，只输出 JSON。",
            max_tokens=400,
        )
        return resp.completion_text or ""

    # ---------- 定时 ----------
    async def _job(self):
        if self._running:
            return
        self._running = True
        try:
            summary = await self.pipeline.run_round()
            logger.info(f"[bili] 本轮结束 {summary}")
        finally:
            self._running = False

    # ---------- 命令 ----------
    @filter.command("bili")
    async def bili_cmd(self, event: AstrMessageEvent):
        args = (event.message_str or "").strip()
        if "run" in args.lower() or "刷" in args:
            n = 2
            for token in args.split():
                if token.isdigit():
                    n = int(token)
            yield event.plain_result(f"开始跑一轮（最多 {n} 条）…")
            summary = await self.pipeline.run_round(n)
            yield event.plain_result(
                f"候选 {summary.get('candidates', 0)}｜检查 {summary.get('seen', 0)}｜"
                f"无字幕 {summary.get('nosub', 0)}｜入库 {summary.get('accept', 0)}｜"
                f"跳过 {summary.get('skip', 0)}｜错误 {summary.get('error', 0)}"
                + (f"｜{summary['skipped']}" if summary.get("skipped") else "")
            )
            return

        s = self.db.stats()
        lines = [
            f"库存 {s['videos']} 条｜候选池 {s['candidates']}｜今日入库 {s['today']}",
            f"谷时：{'是' if self.pipeline.in_offpeak() else '否（现在不跑）'}",
            f"SESSDATA：{'已配置' if self.client.sessdata else '未配置（拿不到字幕）'}",
        ]
        for v in s["latest"]:
            lines.append(f"· [{v['category']}] {v['strength']} {v['title'][:24]}")
        yield event.plain_result("\n".join(lines))
