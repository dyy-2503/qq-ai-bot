import json, io

p = r"<INSTALL_DIR>\astrbot\data\cmd_config.json"
c = json.load(io.open(p, encoding="utf-8-sig"))
wl = c["platform_settings"]["id_whitelist"]
for sid in ("qq:FriendMessage:<OWNER_QQ>", "qq:FriendMessage:<FRIEND_QQ>"):
    if sid not in wl:
        wl.append(sid)
c["platform_settings"]["id_whitelist"] = wl
json.dump(c, io.open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("whitelist:", wl)
