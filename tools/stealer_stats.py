import sqlite3, os

db = r"<INSTALL_DIR>\astrbot\data\plugin_data\astrbot_plugin_stealer\cache\emoji.db"
print("db exists:", os.path.exists(db))
c = sqlite3.connect(db)
tables = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
for t in tables:
    try:
        n = c.execute(f"select count(*) from {t}").fetchone()[0]
        print(f"  {t}: {n}")
    except Exception as e:
        print(f"  {t}: err {e}")
c.close()
