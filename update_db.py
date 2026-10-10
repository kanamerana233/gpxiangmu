import sqlite3
import os
import glob
from datetime import datetime
from mootdx.reader import Reader

DB_PATH = "stocks.db"
TDX_DIR = r"C:\new_haitong"

BLOCK_FILES = {
    "concept": os.path.join(TDX_DIR, "T0002", "hq_cache", "block_gn.dat"),
    "style": os.path.join(TDX_DIR, "T0002", "hq_cache", "block_fg.dat"),
    "index": os.path.join(TDX_DIR, "T0002", "hq_cache", "block_zs.dat"),
}


def connect_db():
    """统一连接函数，加超时和 WAL 模式，防止锁库"""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def scan_stock_codes():
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
            code = filename.split(".")[0][2:]
            if len(code) == 6 and code.isdigit() and code[:2] in prefixes:
                codes.add(code)
    return codes


def update_stock_list():
    codes = scan_stock_codes()
    conn = connect_db()
    c = conn.cursor()

    c.execute("SELECT code FROM stocks")
    existing = {row[0] for row in c.fetchall()}

    new_codes = codes - existing

    if new_codes:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for code in new_codes:
            c.execute("""
                INSERT INTO stocks (code, name, industry, concepts, updated_at)
                VALUES (?, '', '', '', ?)
            """, (code, now))
        conn.commit()

    conn.close()
    return len(new_codes), len(codes)


def parse_block_file(reader, filepath):
    result = {}
    try:
        df = reader.block(symbol=filepath, group=True)
    except Exception:
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


def update_industry_concepts():
    """重解析板块文件，更新行业和概念。全部在一个连接里完成。"""
    reader = Reader.factory(market="std", tdxdir=TDX_DIR)

    industry_map = {}
    concept_map = {}

    for block_type, filepath in BLOCK_FILES.items():
        blocks = parse_block_file(reader, filepath)
        for block_name, codes in blocks.items():
            for code in codes:
                if block_type in ("concept", "style"):
                    concept_map.setdefault(code, []).append(block_name)
                elif block_type == "index":
                    if code not in industry_map:
                        industry_map[code] = block_name

    # 一个连接搞定所有写入
    conn = connect_db()
    c = conn.cursor()

    # 清空
    c.execute("UPDATE stocks SET industry = '', concepts = ''")

    # 批量更新
    c.executemany(
        "UPDATE stocks SET industry = ? WHERE code = ?",
        [(ind, code) for code, ind in industry_map.items()]
    )
    c.executemany(
        "UPDATE stocks SET concepts = ? WHERE code = ?",
        [(",".join(cons), code) for code, cons in concept_map.items()]
    )

    conn.commit()
    conn.close()

    return len(industry_map), len(concept_map)


def get_pending_zyjs_count():
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM stocks WHERE main_business IS NULL OR main_business = ''")
    count = c.fetchone()[0]
    conn.close()
    return count


def get_db_stats():
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM stocks")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM stocks WHERE main_business != '' AND main_business IS NOT NULL")
    has_zyjs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM stocks WHERE industry != '' AND industry IS NOT NULL")
    has_industry = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM stocks WHERE concepts != '' AND concepts IS NOT NULL")
    has_concepts = c.fetchone()[0]
    conn.close()
    return {
        "total": total,
        "has_zyjs": has_zyjs,
        "has_industry": has_industry,
        "has_concepts": has_concepts,
    }