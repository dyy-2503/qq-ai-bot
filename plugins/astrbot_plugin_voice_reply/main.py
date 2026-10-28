"""短回复按概率转语音（只发语音）。

设计要点：
- 只处理私聊（可配）、只处理短句（<= max_chars）
- 命中后把整条回复的文本组件替换成一条 Record（语音），不保留文字
- 冷却与每日上限写本地 json，避免连续语音
- 任何异常/超时都退回文字，绝不让 TTS 把回复吞掉
"""

import json
import random
import re
import time
from datetime import datetime
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Plain, Record
from astrbot.api.star import Context, Star, register
from astrbot.core.platform.message_type import MessageType

STATE_FILE = Path("data/plugin_data/voice_reply/state.json")

# 不适合读出来的内容
SKIP_PATTERNS = re.compile(r"https?://|\[图片\]|\[CQ:|```|^\s*/")


@register(
    "astrbot_plugin_voice_reply",
    "dyy-2503",
    "短回复按概率转语音",
    "0.1.0",
)
class Main(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self.state = self._load_state()

    # ---------- 状态 ----------
    def _load_state(self) -> dict:
        try:
            if STATE_FILE.exists():
                return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[voice] 读取状态失败: {e}")
        return {}

    def _save_state(self) -> None:
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(
                json.dumps(self.state, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"[voice] 写状态失败: {e}")

    def _quota_ok(self) -> bool:
        today = datetime.now().strftime("%Y-%m-%d")
        if self.state.get("day") != today:
            self.state["day"] = today
            self.state["count"] = 0
        cap = int(self.config.get("daily_cap", 40))
        return int(self.state.get("count", 0)) < cap

    def _cooldown_ok(self) -> bool:
        gap = int(self.config.get("min_interval_sec", 180))
        return (time.time() - float(self.state.get("last_ts", 0))) >= gap

    # ---------- 主钩子 ----------
    @filter.on_decorating_result()
    async def on_decorating(self, event: AstrMessageEvent):
        if not self.config.get("enable", True):
            return
        if self.config.get("private_only", True):
            if event.get_message_type() != MessageType.FRIEND_MESSAGE:
                return

        # 命令的回复不转语音：用户敲的是命令，期待的是文字反馈
        if event.get_extra("parsed_params") is not None:
            return
        raw = "".join(
            c.text for c in event.get_messages() if isinstance(c, Plain) and c.text
        ).strip()
        if raw.startswith(("/", "／")):
            return
        first = raw.split()[0] if raw else ""
        prefixes = self.config.get("command_prefixes") or []
        if first in prefixes or first.lstrip("/") in prefixes:
            return

        result = event.get_result()
        if not result or not result.chain:
            return

        texts = [c.text for c in result.chain if isinstance(c, Plain) and c.text]
        if len(texts) != len(result.chain):
            return  # 含图片/At 等非文本组件，不转
        text = "".join(texts).strip()

        max_chars = int(self.config.get("max_chars", 30))
        if not (2 <= len(text) <= max_chars):
            return
        if SKIP_PATTERNS.search(text):
            return
        if random.random() > float(self.config.get("probability", 0.25)):
            return
        if not self._cooldown_ok() or not self._quota_ok():
            return

        try:
            tts = await self.context.get_using_tts_provider_async(
                event.unified_msg_origin
            )
            if not tts:
                logger.warning("[voice] 没有可用的 TTS provider，退回文字")
                return
            audio_path = await tts.get_audio(text)
            if not audio_path:
                logger.warning("[voice] TTS 返回空音频，退回文字")
                return
        except Exception as e:
            logger.error(f"[voice] TTS 失败，退回文字: {e}")
            return

        result.chain = [Record(file=audio_path, text=text)]

        self.state["last_ts"] = time.time()
        self.state["count"] = int(self.state.get("count", 0)) + 1
        self._save_state()
        logger.info(f"[voice] 已转语音({len(text)}字): {text}")
