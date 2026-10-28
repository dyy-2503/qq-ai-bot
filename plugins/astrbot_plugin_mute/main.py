"""闭嘴：管理员让机器人在某个会话静默一段时间。

状态写在 data/plugin_data/mute/state.json，group_vibe 也会读它，
避免"闭嘴期间还在 3% 自动接话"。
"""

import json
import time
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

STATE = Path("data/plugin_data/mute/state.json")


@register("astrbot_plugin_mute", "dyy-2503", "会话静音", "0.1.0")
class Main(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self.muted: dict[str, float] = {}
        self._load()

    # ---------- 状态 ----------
    def _load(self):
        try:
            if STATE.exists():
                raw = json.loads(STATE.read_text(encoding="utf-8"))
                now = time.time()
                self.muted = {k: v for k, v in raw.items() if v > now}
        except Exception:
            self.muted = {}

    def _save(self):
        try:
            STATE.parent.mkdir(parents=True, exist_ok=True)
            STATE.write_text(json.dumps(self.muted, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning(f"[mute] 保存失败: {e}")

    def _until(self, umo: str) -> float:
        v = self.muted.get(umo, 0)
        return v if v > time.time() else 0

    def _is_admin(self, event: AstrMessageEvent) -> bool:
        if str(event.get_sender_id()) in [str(u) for u in self.config.get("allowed_users", [])]:
            return True
        try:
            return getattr(event, "role", "") == "admin"
        except Exception:
            return False

    # ---------- 拦截发送 ----------
    @filter.on_decorating_result()
    async def block(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        if self._until(umo) <= 0:
            return
        result = event.get_result()
        if result and getattr(result, "chain", None):
            result.chain.clear()

    # ---------- 命令 ----------
    @filter.command("闭嘴")
    async def mute(self, event: AstrMessageEvent, minutes: int = 0):
        if not self._is_admin(event):
            yield event.plain_result("这个命令只有主人能用。")
            return

        m = minutes or int(self.config.get("default_minutes", 30))
        m = max(1, min(m, int(self.config.get("max_minutes", 720))))
        until = time.time() + m * 60
        umo = event.unified_msg_origin

        # 先放行这条回复，再把状态写进去
        yield event.plain_result(f"好，我闭嘴 {m} 分钟。")
        self.muted[umo] = until
        self._save()
        logger.info(f"[mute] {umo} 静音到 {time.strftime('%H:%M:%S', time.localtime(until))}")

    @filter.command("开口")
    async def unmute(self, event: AstrMessageEvent):
        if not self._is_admin(event):
            yield event.plain_result("这个命令只有主人能用。")
            return
        umo = event.unified_msg_origin
        self.muted.pop(umo, None)
        self._save()
        yield event.plain_result("可以说话了。")

    @filter.command("静音状态")
    async def status(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        until = self._until(umo)
        if until <= 0:
            yield event.plain_result("当前没有静音。")
        else:
            left = int((until - time.time()) / 60) + 1
            yield event.plain_result(f"本会话还会静音约 {left} 分钟。")
