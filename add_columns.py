import sqlite3

conn = sqlite3.connect("stocks.db")
c = conn.cursor()

# 检查现有列
c.execute("PRAGMA table_info(stocks)")
columns = [row[1] for row in c.fetchall()]
print("现有列：", columns)

# 加新列
new_cols = {
    "main_business": "TEXT",
    "product_type": "TEXT",
    "product_name": "TEXT",
    "business_scope": "TEXT",
    "zyjs_updated": "TEXT",
}

for col, col_type in new_cols.items():
    if col not in columns:
        c.execute(f"ALTER TABLE stocks ADD COLUMN {col} {col_type}")
        print(f"  已加列：{col}")
    else:
        print(f"  已存在：{col}")

conn.commit()
conn.close()
print("完成")