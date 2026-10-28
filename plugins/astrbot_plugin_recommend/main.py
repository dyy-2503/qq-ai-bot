"""阶段二：从 B 站库存里挑一条没推过的，用她的话说一句，附链接发出去。"""

import random
import sqlite3
import time

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Plain
from astrbot.api.star import Context, Star, register
from astrbot.core.message.message_event_result import MessageChain

JOB = "video_recommend"

PROMPT = """你在给朋友推荐一个 B 站视频。素材：

【标题】{title}
【UP主】{up}
【你当时的判断】{summary}

用你自己的口吻说一两句话把这个视频推给对方。要求：
- 不超过 40 字
- 说清楚"这视频讲什么 + 你为什么会点开"，不要写"强烈推荐""值得一看"这种空话
- 不要放链接（链接会另外附上）
- 不要用引号包住整段话
- 只输出这句话"""


@register("astrbot_plugin_recommend", "dyy-2503", "视频推荐", "0.1.0")
class Main(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}

    async def initialize(self):
        if not self.config.get("enable", True):
            return
        try:
            for job in await self.context.cron_manager.list_jobs("basic"):
                if job.name == JOB:
                    await self.context.cron_manager.delete_job(job.job_id)
            await self.context.cron_manager.add_basic_job(
                name=JOB,
                cron_expression=self.config.get("cron", "0 20 * * *"),
                handler=self._job,
                description="每天挑一条 B 站库存推荐",
                timezone="Asia/Shanghai",
                persistent=False,
            )
            logger.info("[rec] 定时任务已注册")
        except Exception as e:
            logger.error(f"[rec] 注册失败: {e}")

    # ---------- 数据 ----------
    def _pick(self) -> dict | None:
        db = self.config.get("bili_db", "")
        days = int(self.config.get("max_age_days", 7))
        min_s = float(self.config.get("min_strength", 0.6))
        try:
            c = sqlite3.connect(db)
            c.row_factory = sqlite3.Row
            row = c.execute(
                "SELECT bvid,title,up_name,summary,strength FROM video"
                " WHERE pushed_at IS NULL AND strength >= ? AND ingested_at >= ?"
                " ORDER BY strength DESC, ingested_at DESC LIMIT 1",
                (min_s, int(time.time()) - days * 86400),
            ).fetchone()
            c.close()
            return dict(row) if row else None
        except Exception as e:
            logger.warning(f"[rec] 读库存失败: {e}")
            return None

    def _mark(self, bvid: str):
        try:
            c = sqlite3.connect(self.config.get("bili_db", ""))
            c.execute(
                "UPDATE video SET pushed_at=?, push_count=push_count+1 WHERE bvid=?",
                (int(time.time()), bvid),
            )
            c.commit()
            c.close()
        except Exception as e:
            logger.warning(f"[rec] 标记失败: {e}")

    async def _persona(self) -> str:
        try:
            p = await self.context.persona_manager.get_persona("default")
            return getattr(p, "system_prompt", "") or ""
        except Exception:
            return ""

    async def _provider(self) -> str:
        try:
            cfg = self.context.get_config() or {}
            return (
                cfg.get("agent_runner", {}).get("config", {}).get("model", {}).get("provider_id")
                or "deepseek-chat"
            )
        except Exception:
            return "deepseek-chat"

    async def _compose(self, v: dict) -> str:
        prompt = PROMPT.format(
            title=v["title"][:80], up=v.get("up_name", ""), summary=v.get("summary", "")
        )
        resp = await self.context.llm_generate(
            chat_provider_id=await self._provider(),
            prompt=prompt,
            system_prompt=(await self._persona()) + "\n\n只输出一句话。",
            max_tokens=120,
        )
        text = (resp.completion_text or "").strip().strip('"“”')
        return text[:60] if text else v.get("summary", v["title"])[:60]

    # ---------- 生成 ----------
    async def _build(self) -> tuple[dict | None, str]:
        v = self._pick()
        if not v:
            return None, "库存里没有可推的视频（要么都推过了，要么还没攒够）"
        line = await self._compose(v)
        msg = line
        if self.config.get("with_link", True):
            msg += f"\nhttps://www.bilibili.com/video/{v['bvid']}"
        return v, msg

    async def _job(self):
        try:
            v, msg = await self._build()
            if not v:
                logger.info(f"[rec] {msg}")
                return
            umo = self.config.get("target_umo", "")
            await self.context.send_message(umo, MessageChain([Plain(msg)]))
            self._mark(v["bvid"])
            logger.info(f"[rec] 已推送 {v['bvid']} → {umo}")
        except Exception:
            logger.exception("[rec] 推荐出错")

    # ---------- 命令 ----------
    @filter.command("推荐")
    async def rec_now(self, event: AstrMessageEvent):
        if str(event.get_sender_id()) not in ("<QQ>",):
            yield event.plain_result("这个命令只有主人能用。")
            return
        v, msg = await self._build()
        if v:
            self._mark(v["bvid"])
            logger.info(f"[rec] 手动推送 {v['bvid']}")
        yield event.plain_result(msg)
