import sqlite3, io, re

ADD = ("【表情包·已修复】表情包功能已经修好，可以正常发图。你之前说过\"发不了图\"\"没接上表情包\"，那是旧故障，现在是错的。"
       "对方要图时你必须真的去发：① 调用 search_meme（query 写情绪或画面词）② 用返回的编号调用 send_meme。"
       "不要用文字画表情代替，也不要再说\"没接上\"。")

DB = r"<INSTALL_DIR>\astrbot\data\data_v4.db"
c = sqlite3.connect(DB)
p = c.execute("select system_prompt from personas where persona_id='default'").fetchone()[0]

# 去掉上一轮那条较弱的约束，换成更强的
p = re.sub(r"【工具】[^\n]*\n?", "", p)
if ADD not in p:
    p = p.rstrip() + "\n" + ADD + "\n"

c.execute("update personas set system_prompt=? where persona_id='default'", (p,))
c.commit()
print("chars:", len(p))
c.close()

with io.open(r"<INSTALL_DIR>\persona_大肥鱼.txt", "w", encoding="utf-8") as f:
    f.write(p + "\n")
