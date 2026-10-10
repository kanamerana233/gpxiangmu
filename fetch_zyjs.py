import sqlite3
import akshare as ak
import time
import random
from datetime import datetime

DB_PATH = "stocks.db"
BATCH_SIZE = 500          # 每批处理多少只
SLEEP_MIN = 1.5           # 每只之间最小延迟
SLEEP_MAX = 3.0           # 最大延迟


def get_pending_codes():
    """获取还没抓主营业务的股票"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT code FROM stocks
        WHERE (zyjs_updated IS NULL OR zyjs_updated = '')
        ORDER BY code
    """)
    codes = [row[0] for row in c.fetchall()]
    conn.close()
    return codes


def save_zyjs(code, data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        UPDATE stocks SET
            main_business = ?,
            product_type = ?,
            product_name = ?,
            business_scope = ?,
            zyjs_updated = ?
        WHERE code = ?
    """, (
        data.get("main_business", ""),
        data.get("product_type", ""),
        data.get("product_name", ""),
        data.get("business_scope", ""),
        now,
        code,
    ))
    conn.commit()
    conn.close()


def fetch_one(code):
    """抓一只股票的主营业务"""
    df = ak.stock_zyjs_ths(symbol=code)
    if df is None or df.empty:
        return None
    row = df.iloc[0]

    def get_val(col):
        v = row.get(col, "")
        if v is None:
            return ""
        return str(v).strip()

    return {
        "main_business": get_val("主营业务"),
        "product_type": get_val("产品类型"),
        "product_name": get_val("产品名称"),
        "business_scope": get_val("经营范围"),
    }


def main():
    codes = get_pending_codes()
    total = len(codes)
    print(f"还有 {total} 只股票需要抓取主营业务\n")

    if total == 0:
        print("全部已抓完，无需继续。")
        return

    success = 0
    fail = 0
    start_time = time.time()

    for i, code in enumerate(codes, 1):
        try:
            data = fetch_one(code)
            if data:
                save_zyjs(code, data)
                success += 1
                status = "OK"
            else:
                fail += 1
                status = "空"
        except Exception as e:
            fail += 1
            status = f"失败：{type(e).__name__}"

        elapsed = time.time() - start_time
        avg = elapsed / i
        remain = avg * (total - i)

        print(f"[{i}/{total}] {code}  {status}  "
              f"成功 {success} 失败 {fail}  "
              f"已用 {elapsed/60:.1f}分  预计剩余 {remain/60:.1f}分")

        time.sleep(SLEEP_MIN + random.random() * (SLEEP_MAX - SLEEP_MIN))

        # 每 100 只暂停一下，降低被限流风险
        if i % 100 == 0:
            print(f"\n--- 已处理 {i} 只，暂停 10 秒 ---\n")
            time.sleep(10)

    print(f"\n完成！成功 {success}，失败 {fail}")


if __name__ == "__main__":
    main()