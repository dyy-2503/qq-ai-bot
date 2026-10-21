import json, io, os

CFG = r"<INSTALL_DIR>\astrbot\data\cmd_config.json"
with io.open(CFG, "r", encoding="utf-8-sig") as f:
    cfg = json.load(f)

cfg["platform"] = [
    {
        "id": "qq",
        "type": "aiocqhttp",
        "enable": True,
        "ws_reverse_host": "0.0.0.0",
        "ws_reverse_port": 6199,
        "ws_reverse_token": "<YOUR_WS_TOKEN>",
    }
]

cfg["provider_sources"] = [
    {
        "id": "deepseek",
        "provider": "deepseek",
        "type": "openai_chat_completion",
        "provider_type": "chat_completion",
        "enable": True,
        "key": ["$DEEPSEEK_API_KEY"],
        "api_base": "https://api.deepseek.com/v1",
        "timeout": 120,
        "proxy": "",
        "custom_headers": {},
    }
]

cfg["provider"] = [
    {
        "id": "deepseek-chat",
        "provider_source_id": "deepseek",
        "model": "deepseek-chat",
        "modalities": ["text"],
        "enable": True,
    }
]

ar = cfg.setdefault("agent_runner", {})
arc = ar.setdefault("config", {})
arc.setdefault("model", {})["provider_id"] = "deepseek-chat"
comp = arc.setdefault("compression", {})
comp["max_turns"] = -1
comp["fallback_max_tokens"] = 100000000
arc.setdefault("persona", {})["persona_id"] = "default"

ps = cfg.setdefault("platform_settings", {})
ps["enable_id_white_list"] = True
ps["id_whitelist"] = ["<OWNER_QQ>"]
seg = ps.setdefault("segmented_reply", {})
seg["enable"] = True
seg["only_llm_result"] = True
seg["interval_method"] = "random"
seg["interval"] = "1.5,3.5"
seg["words_count_threshold"] = 40
seg["split_mode"] = "regex"

cfg.setdefault("provider_settings", {})["streaming_response"] = False

with io.open(CFG, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)

print("platform:", json.dumps(cfg["platform"], ensure_ascii=False))
print("provider_source key placeholder:", cfg["provider_sources"][0]["key"])
print("model provider_id:", arc["model"]["provider_id"])
print("whitelist:", ps["id_whitelist"], "segmented:", seg["enable"], seg["words_count_threshold"])
