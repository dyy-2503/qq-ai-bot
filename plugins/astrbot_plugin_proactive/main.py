"""主动搭话：按「命中线」掷骰，掷中就主动私聊开口。

公式（借鉴 dsh-speak-up）：
    最终命中线 = min(100, 基础命中线 × 时机因子 + min(上限, 连续没中 × 加成))
    掷 0~100，掷到命中线以下才开口

硬闸（与骰子无关，先过）：
    夜间静默 → 用户在聊(idle) → 冷却 → 每日上限
"""

import asyncio
import json
import random
import re
import time
from datetime import datetime
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Plain
from astrbot.api.star import Context, Star, register
from astrbot.core.agent.message import Message
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_type import MessageType

STATE_FILE = Path("data/plugin_data/proactive/state.json")

TRIGGER = (
    "【内部提示】现在已经有一阵子没人跟你说话了。你想主动找他说句话。"
    "就一句，自然点，像突然想起他；不要解释你为什么发消息，不要说“我主动来搭话”。"
)

SYSTEM_SUFFIX = (
    "\n\n【这次是主动开口】没人跟你说话，你自己找了个由头发一条消息。"
    "要求：只说一句话，不超过 30 字；不要复述上面这些规则；不要用“我想你了”这类廉价的套话；"
    "可以吐槽、可以问一件具体的小事、可以接着之前的话题。"
)


@register(
    "astrbot_plugin_proactive",
    "dyy-2503",
    "定时掷骰，掷中主动搭话",
    "0.1.0",
)
class Main(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self.state = self._load_state()
        self._task: asyncio.Task | None = None

    # ---------- 状态 ----------
    def _load_state(self) -> dict:
        try:
            if STATE_FILE.exists():
                return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[proactive] 读取状态失败: {e}")
        return {"miss": 0, "last_speak": 0, "day": "", "count": 0, "last_user": 0}

    def _save_state(self) -> None:
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(
                json.dumps(self.state, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"[proactive] 写状态失败: {e}")

    def _cfg(self, key, default):
        return self.config.get(key, default)

    # ---------- 生命周期 ----------
    async def initialize(self):
        if not self._cfg("enable", True):
            return
        self._task = asyncio.create_task(self._loop(), name="proactive_loop")
        logger.info("[proactive] 已启动，间隔 %s 分钟", self._cfg("interval_minutes", 30))

    async def terminate(self):
        if self._task and not self._task.done():
            self._task.cancel()

    # ---------- 记录用户活跃 ----------
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_any_message(self, event: AstrMessageEvent):
        targets = self._cfg("targets", [])
        if isinstance(targets, str):
            targets = [targets]
        if event.unified_msg_origin not in targets:
            return
        self.state["last_user"] = time.time()
        self._save_state()

    # ---------- 掷骰 ----------
    async def _loop(self):
        while True:
            minutes = int(self._cfg("interval_minutes", 30))
            await asyncio.sleep(minutes * 60 + random.randint(-120, 120))
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[proactive] 本轮出错")

    def _in_quiet(self, now: datetime) -> bool:
        start = int(self._cfg("quiet_start", 0))
        end = int(self._cfg("quiet_end", 8))
        h = now.hour
        return (start <= h < end) if start <= end else (h >= start or h < end)

    @staticmethod
    def _is_peak(now: datetime) -> bool:
        if now.weekday() >= 5:
            return False
        return (9 <= now.hour < 12) or (14 <= now.hour < 18)

    async def _tick(self):
        now = datetime.now()
        ts = time.time()

        if self._in_quiet(now):
            return
        if ts - float(self.state.get("last_user", 0)) < int(self._cfg("idle_minutes", 10)) * 60:
            return
        if ts - float(self.state.get("last_speak", 0)) < int(self._cfg("cooldown_minutes", 25)) * 60:
            return

        today = now.strftime("%Y-%m-%d")
        if self.state.get("day") != today:
            self.state["day"] = today
            self.state["count"] = 0
        if int(self.state.get("count", 0)) >= int(self._cfg("daily_cap", 3)):
            return

        base = self._cfg("peak_line", 15) if self._is_peak(now) else self._cfg("offpeak_line", 45)
        factor = float(self._cfg("far_factor", 1.5)) if ts - float(self.state.get("last_speak", 0)) > 6 * 3600 else 1.0
        bonus = min(int(self._cfg("miss_bonus_cap", 32)), int(self.state.get("miss", 0)) * int(self._cfg("miss_bonus", 8)))
        line = min(100.0, base * factor + bonus)
        roll = random.uniform(0, 100)

        if roll >= line:
            self.state["miss"] = int(self.state.get("miss", 0)) + 1
            self._save_state()
            logger.info(f"[proactive] 未中 roll={roll:.1f} line={line:.1f} miss={self.state['miss']}")
            return

        self.state["miss"] = 0
        await self._speak(now)
        self.state["last_speak"] = time.time()
        self.state["count"] = int(self.state.get("count", 0)) + 1
        self._save_state()

    # ---------- 开口 ----------
    async def _persona_text(self) -> str:
        try:
            persona = await self.context.persona_manager.get_persona("default")
            if persona and getattr(persona, "system_prompt", None):
                return persona.system_prompt
        except Exception as e:
            logger.warning(f"[proactive] 读取人格失败: {e}")
        return ""

    async def _history(self, umo: str) -> list[Message]:
        try:
            cid = await self.context.conversation_manager.get_curr_conversation_id(umo)
            if not cid:
                return []
            conv = await self.context.conversation_manager.get_conversation(umo, cid)
            raw = json.loads(conv.history) if conv and conv.history else []
            out = []
            for m in raw[-12:]:
                role = m.get("role")
                content = m.get("content")
                if role in ("user", "assistant") and isinstance(content, str) and content:
                    out.append(Message(role=role, content=content[:600]))
            return out
        except Exception as e:
            logger.warning(f"[proactive] 读取历史失败: {e}")
            return []

    async def _speak(self, now: datetime):
        targets = self._cfg("targets", [])
        if isinstance(targets, str):
            targets = [targets]
        if not targets:
            return
        umo = targets[0]

        persona = await self._persona_text()
        history = await self._history(umo)
        provider_id = await self.context.get_current_chat_provider_id(umo)

        try:
            resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=TRIGGER,
                system_prompt=(persona + SYSTEM_SUFFIX) if persona else SYSTEM_SUFFIX,
                contexts=history or None,
                max_tokens=120,
            )
        except Exception:
            logger.exception("[proactive] 生成失败")
            return

        text = (resp.completion_text or "").strip()
        text = re.sub(r"[\r\n]+", " ", text)
        text = re.sub(r"^(大肥鱼[:：]\s*|鲸鲸[:：]\s*)", "", text)
        text = text.strip(" \"'“”「」")
        limit = int(self._cfg("max_chars", 40))
        if len(text) > limit:
            cut = re.split(r"[。！？…~]", text)[0]
            text = (cut if len(cut) <= limit else text[:limit]).strip()
        if not text:
            return

        try:
            await self.context.send_message(umo, MessageChain([Plain(text)]))
            logger.info(f"[proactive] 已主动发送: {text}")
        except Exception:
            logger.exception("[proactive] 发送失败")

    # ---------- 命令 ----------
    @filter.command("主动")
    async def cmd(self, event: AstrMessageEvent):
        args = (event.message_str or "").strip()
        if "现在" in args:
            await self._speak(datetime.now())
            self.state["last_speak"] = time.time()
            self.state["count"] = int(self.state.get("count", 0)) + 1
            self._save_state()
            yield event.plain_result("已强制发一条。")
            return
        if "演练" in args:
            umo = (self._cfg("targets", [""]) or [""])[0]
            persona = await self._persona_text()
            history = await self._history(umo)
            provider_id = await self.context.get_current_chat_provider_id(umo)
            resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=TRIGGER,
                system_prompt=(persona + SYSTEM_SUFFIX) if persona else SYSTEM_SUFFIX,
                contexts=history or None,
                max_tokens=120,
            )
            yield event.plain_result("（演练，不发送）\n" + (resp.completion_text or "").strip())

    @filter.command("主动状态")
    async def status(self, event: AstrMessageEvent):
        s = self.state
        now = datetime.now()
        line_base = self._cfg("peak_line", 15) if self._is_peak(now) else self._cfg("offpeak_line", 45)
        bonus = min(int(self._cfg("miss_bonus_cap", 32)), int(s.get("miss", 0)) * int(self._cfg("miss_bonus", 8)))
        yield event.plain_result(
            f"命中线≈{line_base + bonus}（基础{line_base}+没中{bonus}）\n"
            f"连续没中 {s.get('miss', 0)} 次｜今日已发 {s.get('count', 0)}/"
            f"{self._cfg('daily_cap', 3)}\n"
            f"距上次开口 {int((time.time()-float(s.get('last_speak',0)))/60)} 分钟"
        )
