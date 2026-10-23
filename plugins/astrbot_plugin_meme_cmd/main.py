"""表情包命令 + DSML 兜底过滤。

两个作用：
1. `/表情 <关键词>`：直接查表情包库并发送，不依赖模型是否肯调工具。
2. `on_decorating_result`：把模型偶尔泄漏的 `<||DSML||...>` 协议文本清掉，
   避免协议原文被当成回复发出去。
"""

import random
import re
import sqlite3
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Plain
from astrbot.api.star import Context, Star, register

DSML_BLOCK = re.compile(r"<\|+\s*DSML\s*\|+[^>]*>.*?(?:</\|+\s*DSML\s*\|+[^>]*>|$)", re.S)
DSML_TAG = re.compile(r"</?\|+\s*DSML\s*\|+[^>]*>")


@register(
    "astrbot_plugin_meme_cmd",
    "dyy-2503",
    "/表情 命令与 DSML 兜底",
    "0.1.0",
)
class Main(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}

    def _db(self) -> Path:
        return Path(self.config.get("emoji_db", "")).expanduser()

    # ---------- 查询 ----------
    def _search(self, keyword: str) -> list[str]:
        db = self._db()
        if not db.exists():
            logger.warning(f"[meme] 数据库不存在: {db}")
            return []
        like = f"%{keyword}%"
        sql = """
        SELECT DISTINCT e.path FROM emoji e
        LEFT JOIN emoji_tag t ON t.path = e.path
        LEFT JOIN emoji_scene s ON s.path = e.path
        WHERE e.path LIKE '%.jpg' OR e.path LIKE '%.png' OR e.path LIKE '%.gif'
            OR e.path LIKE '%.jpeg' OR e.path LIKE '%.webp'
        """
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
            rows = conn.execute(
                """
                SELECT DISTINCT e.path FROM emoji e
                LEFT JOIN emoji_tag t ON t.path = e.path
                LEFT JOIN emoji_scene s ON s.path = e.path
                WHERE e.desc LIKE ?
                   OR e.overlay_text LIKE ?
                   OR t.tag LIKE ?
                   OR s.scene LIKE ?
                   OR e.category LIKE ?
                """,
                (like, like, like, like, like),
            ).fetchall()
            conn.close()
        except Exception as e:
            logger.error(f"[meme] 查询失败: {e}")
            return []
        paths = []
        for (p,) in rows:
            if p and Path(p).exists():
                paths.append(p)
        random.shuffle(paths)
        return paths[: int(self.config.get("max_candidates", 20))]

    # ---------- 命令 ----------
    @filter.command("表情")
    async def meme_cmd(self, event: AstrMessageEvent):
        if not self.config.get("enable", True):
            return
        keyword = (event.message_str or "").strip()
        # 平台层可能已经吃掉 "/"，也可能保留，两种都兜住
        keyword = re.sub(r"^[\/／]\s*", "", keyword)
        if keyword.startswith("表情"):
            keyword = keyword[2:]
        keyword = keyword.strip()
        if not keyword:
            yield event.plain_result("用法：/表情 开心｜摆烂｜嘲讽")
            return

        paths = self._search(keyword)
        if not paths:
            yield event.plain_result(f"库里没找到跟「{keyword}」相关的，换个词试试？")
            return

        path = paths[0]
        logger.info(f"[meme] /表情 {keyword} -> {path}")
        yield event.chain_result([Image.fromFileSystem(path)])

    # ---------- DSML 兜底 ----------
    @filter.on_decorating_result()
    async def strip_dsml(self, event: AstrMessageEvent):
        if not self.config.get("strip_dsml", True):
            return
        result = event.get_result()
        if not result or not result.chain:
            return

        changed = False
        new_chain = []
        for comp in result.chain:
            if isinstance(comp, Plain) and comp.text and "DSML" in comp.text:
                cleaned = DSML_BLOCK.sub("", comp.text)
                cleaned = DSML_TAG.sub("", cleaned).strip()
                changed = True
                if cleaned:
                    new_chain.append(Plain(cleaned))
                continue
            new_chain.append(comp)

        if changed:
            result.chain = new_chain or [Plain("……")]
            logger.warning("[meme] 已拦截模型输出的 DSML 协议文本")
