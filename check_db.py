import sqlite3

conn = sqlite3.connect("stocks.db")
c = conn.cursor()

# 总数
c.execute("SELECT COUNT(*) FROM stocks")
print(f"股票总数：{c.fetchone()[0]}")

# 有名称的
c.execute("SELECT COUNT(*) FROM stocks WHERE name != ''")
print(f"有名称：{c.fetchone()[0]}")

# 有概念的
c.execute("SELECT COUNT(*) FROM stocks WHERE concepts != ''")
print(f"有概念：{c.fetchone()[0]}")

# 有行业的
c.execute("SELECT COUNT(*) FROM stocks WHERE industry != ''")
print(f"有行业：{c.fetchone()[0]}")

# 查锂电池相关
print("\n锂电相关：")
c.execute("SELECT code, name, concepts FROM stocks WHERE concepts LIKE ? LIMIT 10", ("%锂%",))
for row in c.fetchall():
    print(f"  {row[0]} {row[1]}  概念：{row[2][:80]}")

conn.close()