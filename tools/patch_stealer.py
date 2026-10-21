import json, io

p = r"<INSTALL_DIR>\astrbot\data\config\astrbot_plugin_stealer_config.json"
c = json.load(io.open(p, encoding="utf-8-sig"))

c["steal_meme"] = True
c["audit_required"] = False
c["vision_provider_id"] = "deepseek-chat"
c["emotion_analysis_provider_id"] = "deepseek-chat"
c["enable_embedding_search"] = False
c["auto_send_meme"] = True
c["meme_chance"] = 0.2
c["max_reg_num"] = 100

json.dump(c, io.open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

for k in ("steal_meme", "audit_required", "vision_provider_id",
          "emotion_analysis_provider_id", "auto_send_meme", "meme_chance"):
    print(k, "=", c[k])
