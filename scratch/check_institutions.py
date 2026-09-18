import sqlite3

conn = sqlite3.connect('data/atomos.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute('SELECT id, name, code FROM institutions')
rows = cur.fetchall()
print(f"Total institutions in DB: {len(rows)}")
for r in rows[:60]:
    print(f"[{r['id']}] code={r['code']} name={repr(r['name'])}")
