import sqlite3
import os
import glob
from datetime import datetime
from mootdx.reader import Reader

TDX_DIR = r"C:\new_haitong"
DB_PATH = "stocks.db"

BLOCK_FILES = {
    "concept": os.path.join(TDX_DIR, "T0002", "hq_cache", "block_gn.dat"),
    "style": os.path.join(TDX_DIR, "T0002", "hq_cache", "block_fg.dat"),
    "index": os.path.join(TDX_DIR, "T0002", "hq_cache", "block_zs.dat"),
}


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS stocks (
            code TEXT PRIMARY KEY,
            name TEXT,
            industry TEXT,
            concepts TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_stocks(stocks):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for s in stocks.values():
        c.execute("""
            INSERT INTO stocks (code, name, industry, concepts, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                industry=excluded.industry,
                concepts=excluded.concepts,
                updated_at=excluded.updated_at
        """, (s["code"], s["name"], s["industry"], s["concepts"], now))
    conn.commit()
    conn.close()


def scan_stock_codes():
    """扫描 vipdoc 下所有 .day 文件，提取A股代码"""
    codes = set()
    vipdoc = os.path.join(TDX_DIR, "vipdoc")

    market_rules = {
        "sh": ["60", "68"],
        "sz": ["00", "30"],
        "bj": ["43", "83", "87", "92"],
    }

    for market, prefixes in market_rules.items():
        path = os.path.join(vipdoc, market, "lday", "*.day")
        for file in glob.glob(path):
            filename = os.path.basename(file)
            code = filename.split(".")[0][2:]   # 去掉 sh/sz/bj 前缀
            if len(code) == 6 and code.isdigit() and code[:2] in prefixes:
                codes.add(code)
    return codes


def parse_block_file(reader, filepath):
    """解析一个板块文件，返回 {block_name: [codes]}"""
    result = {}
    try:
        df = reader.block(symbol=filepath, group=True)
    except Exception as e:
        print(f"    读取失败：{e}")
        return result

    if df is None or df.empty:
        return result

    for _, row in df.iterrows():
        block_name = row["blockname"]
        code_str = row["code_list"]
        if not code_str:
            continue
        codes = [x.strip() for x in code_str.split(",") if x.strip()]
        result[block_name] = codes
    return result


def build_full_database():
    init_db()
    reader = Reader.factory(market="std", tdxdir=TDX_DIR)

    print("正在扫描本地A股代码...")
    codes = scan_stock_codes()
    print(f"共发现 {len(codes)} 只股票")

    stocks = {code: {"code": code, "name": "", "industry": "", "concepts": ""} for code in codes}

    print("\n正在解析板块文件...")
    for block_type, filepath in BLOCK_FILES.items():
        print(f"  {block_type}：{os.path.basename(filepath)}")
        blocks = parse_block_file(reader, filepath)
        print(f"    解析出 {len(blocks)} 个板块")

        for block_name, block_codes in blocks.items():
            for code in block_codes:
                if code not in stocks:
                    continue
                if block_type == "concept":
                    existing = stocks[code]["concepts"]
                    stocks[code]["concepts"] = existing + "," + block_name if existing else block_name
                elif block_type == "style":
                    existing = stocks[code]["concepts"]
                    stocks[code]["concepts"] = existing + "," + block_name if existing else block_name
                elif block_type == "index":
                    if not stocks[code]["industry"]:
                        stocks[code]["industry"] = block_name

    print("\n正在保存到数据库...")
    save_stocks(stocks)

    # 统计
    with_industry = sum(1 for s in stocks.values() if s["industry"])
    with_concepts = sum(1 for s in stocks.values() if s["concepts"])
    print(f"完成！共保存 {len(stocks)} 只股票")
    print(f"  有行业信息：{with_industry} 只")
    print(f"  有概念板块：{with_concepts} 只")


if __name__ == "__main__":
    build_full_database()