import sqlite3, json, io, re

DB = r"<INSTALL_DIR>\astrbot\data\data_v4.db"
c = sqlite3.connect(DB)
p = c.execute("select system_prompt from personas where persona_id='default'").fetchone()[0]

# 旧规则：告诉她收不到图（已过时，导致她对着真实图片也嘴硬说看不到）
old = re.compile(r"【图片】[^\n]*")
new_rule = ("【图片】你能看到对方发来的图片和表情包内容，直接针对画面回应，不要说自己看不到图、也不要让对方描述。"
            "只有在消息里确实只有占位符、没有画面时，才说明看不到。")

if old.search(p):
    p = old.sub(new_rule, p, count=1)
else:
    p = p.rstrip() + "\n" + new_rule + "\n"

c.execute("update personas set system_prompt=? where persona_id='default'", (p,))
c.commit()
print("persona chars:", len(p))
print("new rule applied:", new_rule[:20] in p)
c.close()

with io.open(r"<INSTALL_DIR>\persona_大肥鱼.txt", "w", encoding="utf-8") as f:
    f.write(p + "\n")

# 日志降回 INFO
CFG = r"<INSTALL_DIR>\astrbot\data\cmd_config.json"
cfg = json.load(io.open(CFG, encoding="utf-8-sig"))
cfg["log_level"] = "INFO"
json.dump(cfg, io.open(CFG, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("log_level:", cfg["log_level"])
