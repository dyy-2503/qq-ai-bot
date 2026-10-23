import sqlite3
import io

ADD = ("【语音】你说话是能变成语音条的：短句有时会被系统自动转成语音发出去，你不需要做任何操作。"
       "所以不要说\"发不了语音\"\"只能打字\"这类话，那是错的。")

DB = r"<INSTALL_DIR>\astrbot\data\data_v4.db"
c = sqlite3.connect(DB)
p = c.execute("select system_prompt from personas where persona_id='default'").fetchone()[0]

if "【语音】" in p:
    # 替换旧的语音段
    import re
    p = re.sub(r"【语音】[^\n]*\n?", "", p)

p = p.rstrip() + "\n" + ADD + "\n"
c.execute("update personas set system_prompt=? where persona_id='default'", (p,))
c.commit()
print("chars:", len(p))
c.close()

io.open(r"<INSTALL_DIR>\persona_大肥鱼.txt", "w", encoding="utf-8").write(p + "\n")
