import sqlite3
import os
from datetime import datetime, timezone, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stock_ai.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link TEXT UNIQUE,
            title TEXT,
            summary TEXT,
            media TEXT,
            time TEXT,
            lang TEXT,
            domain TEXT,
            cn_title TEXT,
            cn_summary TEXT,
            ai_summary TEXT,
            ai_category TEXT,
            first_seen TEXT,
            last_updated TEXT
        )
    """)
    conn.commit()
    conn.close()


def get_cached(link):
    """查数据库，返回已分析的结果"""
    if not link:
        return None
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT cn_title, cn_summary, ai_summary, ai_category FROM articles WHERE link = ?",
        (link,)
    )
    row = c.fetchone()
    conn.close()
    return row if row else None


def save_article(item, domain):
    """保存或更新一条文章"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT id FROM articles WHERE link = ?", (item.get("link", ""),))
    existing = c.fetchone()

    if existing:
        c.execute("""
            UPDATE articles SET
                cn_title = ?, cn_summary = ?, ai_summary = ?, ai_category = ?, last_updated = ?
            WHERE link = ?
        """, (
            item.get("cn_title"), item.get("cn_summary"),
            item.get("ai_summary"), item.get("ai_category"),
            now, item.get("link")
        ))
    else:
        c.execute("""
            INSERT INTO articles
            (link, title, summary, media, time, lang, domain,
             cn_title, cn_summary, ai_summary, ai_category, first_seen, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.get("link", ""), item.get("title", ""), item.get("summary", ""),
            item.get("media", ""), item.get("time", ""), item.get("lang", ""),
            domain, item.get("cn_title"), item.get("cn_summary"),
            item.get("ai_summary"), item.get("ai_category"),
            now, now
        ))
    conn.commit()
    conn.close()


def db_stats():
    """返回数据库统计"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM articles")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM articles WHERE ai_summary IS NOT NULL")
    analyzed = c.fetchone()[0]
    conn.close()
    return total, analyzed

def cleanup_old(days=7):
    """删除 N 天前的记录"""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM articles WHERE first_seen < ?", (cutoff,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted