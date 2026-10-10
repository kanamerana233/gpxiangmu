import sqlite3

conn = sqlite3.connect("stocks.db")
c = conn.cursor()

# 总数统计
c.execute("SELECT COUNT(*) FROM stocks")
total = c.fetchone()[0]

c.execute("SELECT COUNT(*) FROM stocks WHERE main_business != '' AND main_business IS NOT NULL")
has_zyjs = c.fetchone()[0]

print(f"股票总数：{total}")
print(f"有主营业务：{has_zyjs}")
print(f"缺失：{total - has_zyjs}")

# 查看失败的
print("\n缺失主营业务的股票（前 20 只）：")
c.execute("""
    SELECT code, name FROM stocks
    WHERE main_business IS NULL OR main_business = ''
    LIMIT 20
""")
for row in c.fetchall():
    print(f"  {row[0]} {row[1]}")

# 抽样验证
print("\n抽样验证（随机 5 只）：")
c.execute("""
    SELECT code, name, main_business
    FROM stocks
    WHERE main_business != ''
    ORDER BY RANDOM()
    LIMIT 5
""")
for row in c.fetchall():
    print(f"\n  {row[0]} {row[1]}")
    print(f"    主营业务：{row[2][:100]}")

conn.close()