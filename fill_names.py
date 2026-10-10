import sqlite3
import akshare as ak

DB_PATH = "stocks.db"


def fill_names():
    print("正在从 akshare 抓取股票名称...")
    df = ak.stock_info_a_code_name()
    print(f"抓到 {len(df)} 条")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    updated = 0
    for _, row in df.iterrows():
        code = str(row["code"]).zfill(6)
        name = row["name"]
        c.execute("UPDATE stocks SET name = ? WHERE code = ?", (name, code))
        if c.rowcount > 0:
            updated += 1

    conn.commit()
    conn.close()
    print(f"更新了 {updated} 只股票的名称")


if __name__ == "__main__":
    fill_names()