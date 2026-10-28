"""B站数据访问：发现候选、取详情、取字幕。"""

import asyncio
import json
import time
from typing import Any

import httpx

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
}


class BiliClient:
    def __init__(self, sessdata: str = "", bili_jct: str = ""):
        self.sessdata = sessdata
        self.bili_jct = bili_jct
        self._credential = None

    # ---------- 凭证 ----------
    def _cred(self):
        if self._credential is None:
            from bilibili_api import Credential

            self._credential = Credential(
                sessdata=self.sessdata, bili_jct=self.bili_jct
            )
        return self._credential

    # ---------- 风控 cookie ----------
    async def _buvid(self) -> str:
        """数据中心 IP 不带 buvid 会被 412，先取一对缓存起来。"""
        if getattr(self, "_buvid_cache", ""):
            return self._buvid_cache
        try:
            async with httpx.AsyncClient(timeout=15, headers=UA) as c:
                r = await c.get("https://api.bilibili.com/x/frontend/finger/spi")
                d = (r.json() or {}).get("data") or {}
            b3, b4 = d.get("b_3", ""), d.get("b_4", "")
            self._buvid_cache = f"buvid3={b3}; buvid4={b4}"
            if self.sessdata:
                self._buvid_cache += f"; SESSDATA={self.sessdata}"
        except Exception:
            self._buvid_cache = f"SESSDATA={self.sessdata}" if self.sessdata else ""
        return self._buvid_cache

    # ---------- 发现 ----------
    async def popular(self, page: int = 1, size: int = 20) -> list[dict]:
        url = "https://api.bilibili.com/x/web-interface/popular"
        headers = dict(UA)
        cookie = await self._buvid()
        if cookie:
            headers["Cookie"] = cookie
        async with httpx.AsyncClient(timeout=20, headers=headers) as c:
            r = await c.get(url, params={"ps": size, "pn": page})
            data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"popular 失败: {data.get('code')} {data.get('message')}")
        out = []
        for v in (data.get("data") or {}).get("list") or []:
            out.append({
                "bvid": v.get("bvid"),
                "title": v.get("title", ""),
                "up_name": (v.get("owner") or {}).get("name", ""),
                "view": (v.get("stat") or {}).get("view", 0),
                "pubdate": v.get("pubdate", 0),
                "duration": v.get("duration", 0),
                "cover": v.get("pic", ""),
            })
        return out

    async def search(self, keyword: str, limit: int = 10) -> list[dict]:
        from bilibili_api import search

        res = await search.search_by_type(
            keyword, search_type=search.SearchObjectType.VIDEO, page=1
        )
        out = []
        for v in (res.get("result") or [])[:limit]:
            out.append({
                "bvid": v.get("bvid"),
                "title": (v.get("title") or "").replace('<em class="keyword">', "").replace("</em>", ""),
                "up_name": v.get("author", ""),
                "view": v.get("play", 0),
                "pubdate": v.get("pubdate", 0),
                "duration": _parse_duration(v.get("duration", "")),
                "cover": _fix_url(v.get("pic", "")),
            })
        return out

    # ---------- 详情 ----------
    async def info(self, bvid: str) -> dict:
        url = "https://api.bilibili.com/x/web-interface/view"
        headers = dict(UA)
        cookie = await self._buvid()
        if cookie:
            headers["Cookie"] = cookie
        try:
            async with httpx.AsyncClient(timeout=20, headers=headers) as c:
                r = await c.get(url, params={"bvid": bvid})
                data = r.json()
            if data.get("code") != 0:
                raise RuntimeError(f"view 失败: {data.get('code')}")
            d = data["data"]
        except Exception:
            # 数据中心 IP 被 412 时退回官方库（它自己维护 buvid）
            from bilibili_api import video

            d = await video.Video(bvid=bvid, credential=self._cred()).get_info()
        return {
            "bvid": bvid,
            "title": d.get("title", ""),
            "desc": d.get("desc", ""),
            "cid": d.get("cid"),
            "duration": d.get("duration", 0),
            "pubdate": d.get("pubdate", 0),
            "cover": d.get("pic", ""),
            "up_name": (d.get("owner") or {}).get("name", ""),
        }

    # ---------- 字幕 ----------
    async def subtitle(self, bvid: str, cid: int) -> str:
        """返回拼接后的字幕文本；无字幕返回空串。"""
        if not self.sessdata:
            return ""
        from bilibili_api import video

        v = video.Video(bvid=bvid, credential=self._cred())
        try:
            data = await v.get_subtitle(cid)
        except Exception:
            return ""
        subs = (data or {}).get("subtitles") or []
        if not subs:
            return ""

        pick = None
        for lan in ("ai-zh", "zh-CN", "zh-Hans", "zh"):
            for s in subs:
                if s.get("lan") == lan:
                    pick = s
                    break
            if pick:
                break
        pick = pick or subs[0]

        url = pick.get("subtitle_url", "")
        if url.startswith("//"):
            url = "https:" + url
        if not url:
            return ""
        await asyncio.sleep(0.8)
        async with httpx.AsyncClient(timeout=30, headers=UA) as c:
            r = await c.get(url)
            body = r.json()
        lines = [b.get("content", "") for b in (body.get("body") or [])]
        text = "\n".join(x for x in lines if x)
        return text.strip()


def _fix_url(u: str) -> str:
    return ("https:" + u) if u.startswith("//") else u


def _parse_duration(s: str) -> int:
    try:
        parts = [int(x) for x in str(s).split(":")]
        sec = 0
        for p in parts:
            sec = sec * 60 + p
        return sec
    except Exception:
        return 0
