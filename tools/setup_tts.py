import json, io

CFG = r"<INSTALL_DIR>\astrbot\data\cmd_config.json"
c = json.load(io.open(CFG, encoding="utf-8-sig"))

src_id = "edge_tts"
tip_id = "tts_edge"

sources = [s for s in c.get("provider_sources", []) if s.get("id") != src_id]
sources.append({
    "id": src_id,
    "provider": "microsoft",
    "type": "edge_tts",
    "provider_type": "text_to_speech",
    "enable": True,
    "edge-tts-voice": "zh-CN-XiaoyiNeural",
    "rate": "-4%",
    "volume": "+0%",
    "pitch": "+15Hz",
    "timeout": 20,
})
c["provider_sources"] = sources

provs = [p for p in c.get("provider", []) if p.get("id") != tip_id]
provs.append({
    "id": tip_id,
    "provider_source_id": src_id,
    "enable": True,
})
c["provider"] = provs

tts = c.setdefault("provider_tts_settings", {})
tts["enable"] = False          # 交给 voice_reply 插件控制，内建管线不自动转
tts["provider_id"] = tip_id
tts["dual_output"] = False
tts["trigger_probability"] = 1.0

json.dump(c, io.open(CFG, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("sources:", [s["id"] for s in c["provider_sources"]])
print("providers:", [(p["id"], p.get("provider_source_id")) for p in c["provider"]])
print("tts settings:", tts)
