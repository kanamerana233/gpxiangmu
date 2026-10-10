import sqlite3
import re
import json
import os
import hashlib
from datetime import datetime

DB_PATH = "stocks.db"
CACHE_DB = "picker_cache.db"


def init_cache_db():
    conn = sqlite3.connect(CACHE_DB, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS picker_cache (
            cache_key TEXT PRIMARY KEY,
            question TEXT,
            result_json TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def make_cache_key(question, db_hash):
    """生成缓存键：问题 + 数据库状态"""
    raw = f"{question}|{db_hash}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def get_db_hash():
    """用数据库文件大小+修改时间做简易指纹"""
    if not os.path.exists(DB_PATH):
        return "none"
    stat = os.stat(DB_PATH)
    return f"{stat.st_size}_{int(stat.st_mtime)}"


def get_cached_result(cache_key):
    init_cache_db()
    conn = sqlite3.connect(CACHE_DB, timeout=30)
    c = conn.cursor()
    c.execute("SELECT result_json FROM picker_cache WHERE cache_key = ?", (cache_key,))
    row = c.fetchone()
    conn.close()
    return json.loads(row[0]) if row else None


def save_cached_result(cache_key, question, result):
    init_cache_db()
    conn = sqlite3.connect(CACHE_DB, timeout=30)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT OR REPLACE INTO picker_cache (cache_key, question, result_json, created_at)
        VALUES (?, ?, ?, ?)
    """, (cache_key, question, json.dumps(result, ensure_ascii=False), now))
    conn.commit()
    conn.close()


def get_all_stocks():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    c = conn.cursor()
    c.execute("SELECT code, name, industry, concepts, main_business FROM stocks")
    rows = c.fetchall()
    conn.close()
    return [{
        "code": r[0],
        "name": r[1],
        "industry": r[2] or "",
        "concepts": r[3] or "",
        "main_business": r[4] or "",
    } for r in rows]


def extract_keywords(client, question):
    prompt = f"""用户想找A股股票，问题是：{question}

请提取出用于搜索的关键词，返回JSON数组格式。
例如：["锂电池", "正极材料", "电解液", "隔膜"]

要求：
- 关键词要具体，便于匹配股票概念、行业和主营业务
- 5-15 个关键词
- 只输出 JSON 数组，不要解释
"""
    try:
        response = client.chat.completions.create(
            model="deepseek-flash",
            messages=[
                {"role": "system", "content": "你是A股股票搜索助手，只输出JSON数组。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        text = response.choices[0].message.content.strip()
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    except Exception:
        pass
    return [question]


def coarse_filter(stocks, keywords):
    matched = []
    for s in stocks:
        text = (s["name"] + " " + s["industry"] + " " +
                s["concepts"] + " " + s["main_business"])
        hits = [kw for kw in keywords if kw in text]
        if hits:
            s["hit_count"] = len(hits)
            s["hit_words"] = hits
            matched.append(s)
    matched.sort(key=lambda x: -x["hit_count"])
    return matched


def ai_rank(client, question, stocks):
    if not stocks:
        return []

    candidates = stocks[:80]

    lines = []
    for i, s in enumerate(candidates, 1):
        mb = s["main_business"][:150] if s["main_business"] else "（暂无）"
        lines.append(
            f"{i}. {s['code']} {s['name']}\n"
            f"   行业：{s['industry'] or '未分类'}\n"
            f"   主营业务：{mb}\n"
            f"   概念：{s['concepts'][:100]}"
        )
    stocks_text = "\n".join(lines)

    prompt = f"""用户问题：{question}

下面是候选股票：
{stocks_text}

请根据用户问题，对每只股票的相关度打分（0-100分），并给出简短的关联原因。

严格按以下格式输出，每行一只，共 {len(candidates)} 行：
序号|分数|关联原因

例如：
1|95|锂电池正极材料龙头，直接受益
2|60|涉及锂电池概念，但主业非核心

要求：
- 分数 0-100，越相关越高
- 关联原因不超过 30 字
- 只输出这些行，不要其他内容
"""

    try:
        response = client.chat.completions.create(
            model="deepseek-flash",
            messages=[
                {"role": "system", "content": "你是A股投资研究助手，严格按格式输出。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        text = response.choices[0].message.content.strip()
    except Exception as e:
        return [{"error": str(e)}]

    result = {}
    for line in text.split("\n"):
        parts = line.split("|")
        if len(parts) >= 3:
            try:
                idx = int(parts[0].strip()) - 1
                score = int(parts[1].strip())
                reason = parts[2].strip()
                result[idx] = (score, reason)
            except Exception:
                continue

    ranked = []
    for i, s in enumerate(candidates):
        if i in result:
            s["score"] = result[i][0]
            s["reason"] = result[i][1]
            ranked.append(s)

    ranked.sort(key=lambda x: -x["score"])
    return ranked


def run_stock_picker(client, question, progress_callback=None, use_cache=True):
    """返回 (matched_count, keywords, ranked, from_cache)"""
    db_hash = get_db_hash()
    cache_key = make_cache_key(question, db_hash)

    if use_cache:
        cached = get_cached_result(cache_key)
        if cached:
            if progress_callback:
                progress_callback("命中缓存，直接返回上次结果")
            return cached["matched_count"], cached["keywords"], cached["ranked"], True

    if progress_callback:
        progress_callback("正在读取本地股票数据库...")
    stocks = get_all_stocks()

    if progress_callback:
        progress_callback("AI 正在提取搜索关键词...")
    keywords = extract_keywords(client, question)

    if progress_callback:
        progress_callback(f"关键词：{' / '.join(keywords)}，正在粗筛...")
    matched = coarse_filter(stocks, keywords)

    if not matched:
        return 0, keywords, [], False

    if progress_callback:
        progress_callback(f"粗筛出 {len(matched)} 只，AI 正在精排打分...")
    ranked = ai_rank(client, question, matched)

    result = {
        "matched_count": len(matched),
        "keywords": keywords,
        "ranked": ranked,
    }
    save_cached_result(cache_key, question, result)

    return len(matched), keywords, ranked, False