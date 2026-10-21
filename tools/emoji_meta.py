import sqlite3, json

db = r"<INSTALL_DIR>\astrbot\data\plugin_data\astrbot_plugin_stealer\cache\emoji.db"
c = sqlite3.connect(db)

for row in c.execute("select path, category, desc, overlay_text, emotions_json, created_at from emoji order by created_at"):
    path, cat, desc, overlay, emo, ts = row
    tags = [r[0] for r in c.execute("select tag from emoji_tag where path=?", (path,))]
    scenes = [r[0] for r in c.execute("select scene from emoji_scene where path=?", (path,))]
    print(f"\n分类: {cat}")
    print(f"  描述: {desc}")
    print(f"  图内文字: {overlay}")
    print(f"  标签: {tags}")
    print(f"  场景: {scenes}")
    print(f"  情绪: {emo}")
c.close()
