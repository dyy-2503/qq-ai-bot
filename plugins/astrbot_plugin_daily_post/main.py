"""每晚生成一条说说草稿，写进 QQ 空间插件的待审队列。

素材来自两处：
- B 站视频库（今天入库的高强度视频）
- 今天的聊天记录（最近若干条）
"""

import glob
import json
import random
import re
import sqlite3
import time
from datetime import datetime

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Plain
from astrbot.api.star import Context, Star, register
from astrbot.core.agent.message import Message
from astrbot.core.message.message_event_result import MessageChain

PROMPT = """你是「大肥鱼」，一只拟人化的鲸鱼娘：软萌、傲娇、贪吃、爱躺平。

现在是晚上，你要发一条 QQ 空间说说。素材如下：

【今天刷到的视频】
{videos}

【今天和人聊到的事】
{chat}

从下面三种里**只选一种**来写：
A. 聊今天刷到的一个视频（可以吐槽、可以推荐，但别说"推荐"两个字）
B. 总结今天干了什么（挑一件具体的，别流水账）
C. 纯日常感慨（吃的、懒、天气都行）

要求：
- 1~2 句，总共不超过 {max_chars} 字
- 第一人称，口语，像真的在自言自语
- 不要提"素材""视频库""聊天记录"这些词
- 不要用"今天又是元气满满的一天"这类模板句
- 不要堆表情符号
- 只输出说说正文，不要引号、不要解释"""


@register(
    "astrbot_plugin_daily_post",
    "dyy-2503",
    "每日说说草稿",
    "0.1.0",
)
class Main(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self._last_gen = 0

    async def initialize(self):
        if not self.config.get("enable", True):
            return
        try:
            for job in await self.context.cron_manager.list_jobs("basic"):
                if job.name == "daily_post":
                    await self.context.cron_manager.delete_job(job.job_id)
            cron = self.config.get("cron", "20 23 * * *")
            await self.context.cron_manager.add_basic_job(
                name="daily_post",
                cron_expression=cron,
                handler=self._job,
                description="每晚生成说说草稿",
                timezone="Asia/Shanghai",
                persistent=False,
            )
            logger.info(f"[daily] 定时任务已注册（{cron}）")
        except Exception as e:
            logger.error(f"[daily] 注册定时任务失败: {e}")

    # ---------- 素材 ----------
    def _videos(self) -> list[dict]:
        path = self.config.get("bili_db", "")
        try:
            c = sqlite3.connect(path)
            c.row_factory = sqlite3.Row
            rows = c.execute(
                "SELECT title,summary,strength FROM video"
                " WHERE ingested_at >= ? ORDER BY strength DESC LIMIT 3",
                (int(time.time()) - 86400,),
            ).fetchall()
            c.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"[daily] 读视频库失败: {e}")
            return []

    async def _chat(self, umo: str) -> str:
        try:
            cid = await self.context.conversation_manager.get_curr_conversation_id(umo)
            if not cid:
                return ""
            conv = await self.context.conversation_manager.get_conversation(umo, cid)
            raw = json.loads(conv.history) if conv and conv.history else []
            lines = []
            for m in raw[-16:]:
                role = m.get("role")
                content = m.get("content")
                if role in ("user", "assistant") and isinstance(content, str):
                    content = content.strip().replace("\n", " ")
                    if content:
                        lines.append(("我" if role == "assistant" else "他") + "：" + content[:80])
            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"[daily] 读聊天记录失败: {e}")
            return ""

    async def _persona(self) -> str:
        try:
            p = await self.context.persona_manager.get_persona("default")
            return getattr(p, "system_prompt", "") or ""
        except Exception:
            return ""

    # ---------- 生成 ----------
    async def _compose(self, umo: str) -> str:
        videos = self._videos()
        chat = await self._chat(umo)

        w_v = float(self.config.get("video_weight", 0.4))
        w_l = float(self.config.get("life_weight", 0.4))
        r = random.random()
        if r < w_v and videos:
            mode = "video"
            hint = "这次优先写视频（A）。"
        elif r < w_v + w_l:
            mode = "life"
            hint = "这次优先写今天的事（B）。"
        else:
            mode = "emotion"
            hint = "这次写日常感慨（C）。"
        logger.info(f"[daily] 本次类型={mode} (r={r:.2f}, 视频数={len(videos)})")

        vtext = "\n".join(
            f"- {v['title']}（{v['strength']}）：{v['summary']}" for v in videos
        ) or "（今天没有）"

        prompt = PROMPT.format(
            videos=vtext,
            chat=chat or "（今天没怎么聊）",
            max_chars=int(self.config.get("max_chars", 60)),
        ) + "\n\n" + hint

        pid = ""
        try:
            cfg = self.context.get_config() or {}
            pid = (cfg.get("agent_runner", {}).get("config", {})
                   .get("model", {}).get("provider_id") or "deepseek-chat")
        except Exception:
            pid = "deepseek-chat"

        persona = await self._persona()
        resp = await self.context.llm_generate(
            chat_provider_id=pid,
            prompt=prompt,
            system_prompt=(persona + "\n\n只输出说说正文。") if persona else "只输出说说正文。",
            max_tokens=200,
        )
        text = (resp.completion_text or "").strip()
        text = re.sub(r"^[\"'“”「」]+|[\"'“”「」]+$", "", text)
        text = re.sub(r"\s+", " ", text)
        limit = int(self.config.get("max_chars", 60))
        if len(text) > limit:
            text = text[:limit]
        return text

    # ---------- 落库 ----------
    def _save_draft(self, text: str) -> int | None:
        pattern = self.config.get("qzone_db_glob", "")
        files = sorted(glob.glob(pattern))
        if not files:
            logger.error(f"[daily] 找不到 QQ 空间待审库: {pattern}")
            return None
        path = files[0]
        try:
            c = sqlite3.connect(path)
            cur = c.execute(
                "INSERT INTO posts(uin,name,gin,text,images,videos,anon,status,"
                "create_time,rt_con,comments) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                ("<QQ>", "", "0", text, "[]", "[]", "0", "pending",
                 str(int(time.time())), "", "[]"),
            )
            c.commit()
            pid = cur.lastrowid
            c.close()
            return pid
        except Exception as e:
            logger.error(f"[daily] 写草稿失败: {e}")
            return None

    # ---------- 发布 ----------
    async def _publish(self, text: str) -> bool:
        """直接调用 QQ 空间插件的发布能力；失败再退回私聊。"""
        try:
            from astrbot.core.star.star import star_map

            qz = None
            for path, md in star_map.items():
                if "astrbot_plugin_qzone" in path and getattr(md, "star_cls", None):
                    qz = md.star_cls
                    break
            if qz is None or not getattr(qz, "service", None):
                raise RuntimeError("找不到 QQ 空间插件实例")

            await qz.service.publish_post(text=text)
            logger.info(f"[daily] 已自动发布说说: {text}")
            return True
        except Exception as e:
            logger.error(f"[daily] 发布失败: {type(e).__name__} {e}")
            return False

    async def _notify(self, text: str, pid: int | None):
        umo = self.config.get("admin_umo", "")
        if not umo:
            return
        msg = f"今晚的说说草稿（#{pid}）：\n{text}\n\n/过稿 {pid} 发布｜/拒稿 {pid} 不要"
        try:
            await self.context.send_message(umo, MessageChain([Plain(msg)]))
        except Exception as e:
            logger.warning(f"[daily] 通知失败: {e}")

    # ---------- 定时 ----------
    async def _job(self):
        try:
            umo = self.config.get("admin_umo", "")
            text = await self._compose(umo)
            if not text:
                logger.warning("[daily] 生成内容为空")
                return
            ok = await self._publish(text)
            if not ok:
                pid = self._save_draft(text)
                await self._notify(text, pid)
                logger.warning(f"[daily] 自动发布失败，已存草稿 #{pid}")
            else:
                logger.info(f"[daily] 已发布: {text}")
        except Exception:
            logger.exception("[daily] 生成说说出错")

    # ---------- 命令 ----------
    @filter.command("说说草稿")
    async def draft_now(self, event: AstrMessageEvent):
        text = await self._compose(event.unified_msg_origin)
        pid = self._save_draft(text)
        yield event.plain_result(f"草稿 #{pid}：\n{text}\n\n/过稿 {pid} 发布｜/拒稿 {pid} 不要")
