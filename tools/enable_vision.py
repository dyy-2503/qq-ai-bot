import json, io

p = r"<INSTALL_DIR>\astrbot\data\cmd_config.json"
c = json.load(io.open(p, encoding="utf-8-sig"))
for prov in c["provider"]:
    if prov.get("id") == "deepseek-chat":
        prov["modalities"] = ["text", "image"]
json.dump(c, io.open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("modalities:", [x.get("modalities") for x in c["provider"]])
