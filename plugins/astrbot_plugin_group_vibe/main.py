"""群聊氛围：低概率接话、@必回、固定上下文窗口、敏感话题收敛。"""

import asyncio
import random
import time
from collections import deque
from datetime import datetime

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Plain
from astrbot.api.star import Context, Star, register
from astrbot.core.message.message_event_result import MessageChain

JOIN_PROMPT = """下面是群里最近的对话：

{recent}

你刚看到这些，想插一句嘴。规则：
- 只说你真的感兴趣的那件事，别总结、别逐条回应
- 一句话，不超过 25 字，口语，像群里随口接一句
- 不要 @ 任何人，不要问"你们在聊什么"
- 如果不感兴趣就只输出一个短横线 "-"
- 不要解释你在干什么"""

DECLINE_HINT = (
    "\n\n【群聊规则】这是群聊，不是一对一。"
    "不接作业、论文、代写、复杂技术方案这类请求，用一句口语岔开就行，别展开讲。"
)


@register(
    "astrbot_plugin_group_vibe",
    "dyy-2503",
    "群聊氛围控制",
    "0.1.0",
)
class Main(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self.buffers: dict[str, deque] = {}
        self.last_join: float = 0.0
        self.join_times: deque = deque(maxlen=64)
        self.replies: dict = {}
        self.at_hits: dict = {}
        self.at_cooldown: dict = {}

    def _groups(self) -> list[str]:
        g = self.config.get("groups", [])
        if isinstance(g, str):
            g = [g]
        return g

    def _buf(self, umo: str) -> deque:
        n = int(self.config.get("context_window", 12))
        if umo not in self.buffers:
            self.buffers[umo] = deque(maxlen=n)
        return self.buffers[umo]

    @staticmethod
    def _nick(event: AstrMessageEvent) -> str:
        try:
            return event.message_obj.sender.nickname or str(event.get_sender_id())
        except Exception:
            return str(event.get_sender_id())

    @staticmethod
    def _mentions_me(event: AstrMessageEvent) -> bool:
        me = str(event.get_self_id())
        for c in event.get_messages():
            if isinstance(c, At) and str(c.qq) == me:
                return True
        return False

    # ---------- 监听群消息 ----------
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        text = (event.message_str or "").strip()
        if not text:
            return

        sender = str(event.get_sender_id())
        now_ts = time.time()
        is_admin = sender in [str(u) for u in (self.config.get("admin_users") or ["<QQ>"])] \
            or getattr(event, "role", "") == "admin"

        # ① 静默名单：所有群都生效（管理员不受限）
        mute = [str(u) for u in (self.config.get("mute_users") or [])]
        if sender in mute and not is_admin:
            logger.info(f"[group] 静默名单 {sender}，不接话")
            event.stop_event()
            return

        # ② 被 @ 冷却：同一个人短时间内反复 @ 就静默他（管理员豁免）
        if self._mentions_me(event) and not is_admin:
            k = (umo, sender)
            hits = [t for t in self.at_hits.get(k, []) if now_ts - t < 120]
            hits.append(now_ts)
            self.at_hits[k] = hits
            until = self.at_cooldown.get(k, 0)
            if until > now_ts:
                logger.info(f"[group] {sender} 处于 @ 冷却中，忽略")
                event.stop_event()
                return
            if len(hits) >= int(self.config.get("max_at_per_120s", 5)):
                mins = int(self.config.get("at_cooldown_minutes", 3))
                self.at_cooldown[k] = now_ts + mins * 60
                logger.warning(
                    f"[group] {sender} 120 秒内 @ 了 {len(hits)} 次，静默 {mins} 分钟"
                )
                await self._say(event, f"你@我太勤了，先歇 {mins} 分钟。")
                event.stop_event()
                return

        # 不在氛围配置里的群，到这里就结束（守卫仍然生效）
        if umo not in self._groups():
            return

        # ③ 回复次数冷却（统计自 on_decorating_result；管理员豁免）
        if not is_admin:
            key = (umo, sender)
            recent = [t for t in self.replies.get(key, []) if now_ts - t < 300]
            self.replies[key] = recent
            if len(recent) >= int(self.config.get("max_replies_per_sender", 8)):
                logger.warning(f"[group] {sender} 5 分钟内已回 {len(recent)} 次，冷却中")
                event.stop_event()
                return

        # 屏蔽词：直接婉拒，不再往下走
        for w in self.config.get("block_words") or []:
            if w and w in text:
                await self._say(event, self.config.get("block_reply", "这个我不写哦，换个话题吧。"))
                event.stop_event()
                return

        self._buf(umo).append((self._nick(event), text[:200], time.time()))

        if text.startswith(("/", "／")):
            return
        if self._mentions_me(event):
            return  # 被 @ 的走正常链路，100% 回

        if random.random() >= float(self.config.get("join_probability", 0.03)):
            return

        now = time.time()
        if now - self.last_join < int(self.config.get("join_min_interval_sec", 180)):
            return
        recent = [t for t in self.join_times if now - t < 3600]
        if len(recent) >= int(self.config.get("join_max_per_hour", 6)):
            return

        self.last_join = now
        self.join_times.append(now)
        asyncio.create_task(self._join(umo, event))

    async def _join(self, umo: str, event: AstrMessageEvent):
        try:
            import json as _json
            from pathlib import Path as _Path

            st = _Path("data/plugin_data/mute/state.json")
            if st.exists():
                until = _json.loads(st.read_text(encoding="utf-8")).get(umo, 0)
                if until > time.time():
                    logger.info("[group] 静音中，跳过主动接话")
                    return
        except Exception:
            pass
        try:
            recent = "\n".join(f"{n}: {t}" for n, t, _ in self._buf(umo))
            pid = await self._provider_id(umo)
            resp = await self.context.llm_generate(
                chat_provider_id=pid,
                prompt=JOIN_PROMPT.format(recent=recent),
                system_prompt=await self._persona(),
                max_tokens=80,
            )
            text = (resp.completion_text or "").strip().strip('"“”')
            if not text or text in ("-", "—"):
                logger.info("[group] 判定不感兴趣，不接话")
                return
            text = text.split("\n")[0][:40]
            await self.context.send_message(umo, MessageChain([Plain(text)]))
            logger.info(f"[group] 主动接话: {text}")
        except Exception:
            logger.exception("[group] 接话失败")

    async def _say(self, event: AstrMessageEvent, text: str):
        try:
            await self.context.send_message(
                event.unified_msg_origin, MessageChain([Plain(text)])
            )
        except Exception as e:
            logger.warning(f"[group] 发送失败: {e}")

    async def _persona(self) -> str:
        try:
            p = await self.context.persona_manager.get_persona("default")
            return getattr(p, "system_prompt", "") or ""
        except Exception:
            return ""

    async def _provider_id(self, umo: str) -> str:
        try:
            return await self.context.get_current_chat_provider_id(umo)
        except Exception:
            return "deepseek-chat"

    # ---------- 固定上下文窗口 ----------
    @filter.on_llm_request()
    async def inject_context(self, event: AstrMessageEvent, req):
        umo = event.unified_msg_origin
        if umo not in self._groups():
            return
        n = int(self.config.get("context_window", 12))
        buf = list(self._buf(umo))[-n:]

        # 只看最近 n 条：裁掉更早的
        if isinstance(req.contexts, list) and len(req.contexts) > n:
            req.contexts = req.contexts[-n:]

        if buf:
            lines = "\n".join(f"{nick}: {text}" for nick, text, _ in buf)
            last_nick = buf[-1][0]
            req.system_prompt += (
                f"\n\n【群里最近 {len(buf)} 条消息】\n{lines}\n"
                f"只结合这些，不要提更早的事。\n"
                f"【回应对象】最后开口的是「{last_nick}」，优先回应这个人；"
                f"可以直呼对方昵称，别答非所问，也别把别人的话算在他头上。"
            )

        if self.config.get("decline_complex", True):
            req.system_prompt += DECLINE_HINT

    # ---------- 记录回复次数（刷屏冷却用）----------
    @filter.on_decorating_result()
    async def _count_reply(self, event: AstrMessageEvent):
        """用 on_decorating_result 计数，比 after_message_sent 更可靠。"""
        umo = event.unified_msg_origin
        result = event.get_result()
        if not result or not getattr(result, "chain", None):
            return
        key = (umo, str(event.get_sender_id()))
        self.replies.setdefault(key, []).append(time.time())
