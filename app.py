# ===== 自动启动 china-finance-rss 后台服务 =====
from cn_rss_integration import start_cn_rss_server
start_cn_rss_server()
# ==============================================
import streamlit as st
import requests
import os
import re
import sqlite3
import feedparser
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from openai import OpenAI

# 本地读取 .env
load_dotenv()

# 云端兼容：如果 st.secrets 里有 Key，覆盖环境变量
try:
    if "DEEPSEEK_API_KEY" in st.secrets:
        os.environ["DEEPSEEK_API_KEY"] = st.secrets["DEEPSEEK_API_KEY"]
except Exception:
    pass

# 启动 china-finance-rss（云端自动跳过）
# try:
#     from cn_rss_integration import start_cn_rss_server
#     start_cn_rss_server()
# except Exception as e:
#     print(f"[启动] 跳过 cn_rss：{e}")

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)


st.set_page_config(page_title="股市信息程序", layout="wide")
st.markdown("""
<style>
@media (max-width: 600px) {
    .stMarkdown { font-size: 0.9rem !important; }
    .stButton > button { min-height: 44px !important; }
    .stCaption { font-size: 0.75rem !important; }
}
.main .block-container { max-width: 900px !important; }
</style>
""", unsafe_allow_html=True)
st.title("股市信息程序")


# ============ 数据库 ============
# 数据库路径：本地和云端都用相对路径
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


init_db()


# ============ 黑名单 ============
BLACKLIST = [
    "开通会员", "PLUS会员", "尊享", "立即购买", "立即登录",
    "优惠礼包", "专属客服", "专属微标", "独享小程序", "专享日报",
    "VIP", "订阅会员", "升级会员", "点击查看", "限时优惠",
    "扫码关注", "下载APP", "广告", "赞助",
]


# ============ 领域关键词 ============
DOMAIN_KEYWORDS = {
    "地缘/能源/黄金": [
        "地缘", "战争", "冲突", "制裁", "谈判", "外交", "军事",
        "俄乌", "中东", "以色列", "伊朗", "朝鲜", "台海", "南海",
        "原油", "石油", "电力", "天然气", "煤炭", "新能源", "油气",
        "OPEC", "油价", "LNG", "页岩油",
        "黄金", "金价", "贵金属", "避险",
    ],
    "央行政策": [
        "央行", "人民银行", "降准", "降息", "LPR", "逆回购",
        "MLF", "货币政策", "流动性", "公开市场", "存款准备金",
    ],
    "证监会政策": [
        "证监会", "证券监管", "交易所", "上市公司监管",
        "并购重组", "IPO", "退市", "股票发行", "信息披露",
        "注册制", "北交所", "科创板",
    ],
    "国内政策/快讯": [
        "国务院", "发改委", "财政部", "国常会", "人民银行", "央行",
        "政策", "通知", "意见", "办法", "规划", "方案",
        "降准", "降息", "LPR", "专项债", "减税", "降费",
        "经济", "财政", "货币",
    ],
    "国内科技": [
        "半导体", "芯片", "人工智能", "软件", "云计算", "大数据", "量子",
        "生物医药", "创新药", "疫苗", "基因", "医疗器械",
        "新能源", "光伏", "锂电", "储能", "风电", "氢能", "电动车",
        "新材料", "碳纤维", "石墨烯", "稀土",
        "高端装备", "工业母机", "机器人", "数控机床",
        "航空航天", "卫星", "商业航天", "船舶", "海洋工程",
        "环保", "碳中和", "碳达峰", "节能",
        "农业", "种业", "农机", "生物育种",
        "可控核聚变", "脑机接口", "6G",
    ],
    "A股": [
        "A股", "沪指", "上证", "深证", "创业板", "科创板", "北交所", "沪深",
    ],
    "美股": [
        "美股", "纳斯达克", "道琼斯", "标普", "S&P",
        "NYSE", "Nasdaq", "Dow", "Wall Street",
        "Tesla", "Apple", "Nvidia", "Microsoft", "Google", "Amazon", "Meta",
        "特斯拉", "苹果", "英伟达", "微软", "谷歌", "亚马逊",
    ],
    "能源供需": [
        "OPEC", "欧佩克", "石油输出国组织", "月报", "供需", "需求", "产量",
        "原油", "石油", "库存", "减产", "增产", "IEA", "国际能源署",
        "EIA", "美国能源信息署", "钻井", "页岩油", "炼油",
    ],
    "美国立法行政": [
        "国会", "参议院", "众议院", "参众两院", "议员", "法案", "议案",
        "白宫", "总统", "行政令", "特朗普", "拜登",
        "通过", "表决", "投票", "签署", "否决", "听证会", "提交",
        "拨款", "支出", "税改", "债务上限", "制裁", "关税",
        "芯片", "生物安全", "TikTok", "国防授权",
    ],
}


DOMAIN_MUST_HAVE = {
    "国内政策/快讯": ["中国", "国内", "我国", "国务院", "发改委", "财政部", "央行", "国常会", "人民币"],
    "国内科技": ["中国", "国内", "国产", "我国", "中芯", "华为", "比亚迪", "宁德时代", "大疆", "京东方"],
}


SOURCE_LIST = [
    {
        "domain": "地缘/能源/黄金",
        "keywords": DOMAIN_KEYWORDS["地缘/能源/黄金"],
        "sources": [
            {"name": "金十数据", "type": "rss", "url": "http://localhost:8053/jin10/flash", "limit": 15, "lang": "zh"},
            {"name": "CNBC", "type": "rss", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "limit": 10, "lang": "en"},
        ]
    },
    {
        "domain": "央行政策",
        "keywords": DOMAIN_KEYWORDS["央行政策"],
        "sources": [
            {"name": "财联社", "type": "rss", "url": "http://localhost:8053/cls/telegraph", "limit": 30, "lang": "zh"},
        ]
    },
    {
        "domain": "美联储政策",
        "keywords": None,
        "sources": [
            {"name": "美联储", "type": "rss", "url": "https://www.federalreserve.gov/feeds/press_all.xml", "limit": 5, "lang": "en"},
        ]
    },
    {
        "domain": "证监会政策",
        "keywords": DOMAIN_KEYWORDS["证监会政策"],
        "sources": [
            {"name": "财联社", "type": "rss", "url": "http://localhost:8053/cls/telegraph", "limit": 30, "lang": "zh"},
        ]
    },
    {
        "domain": "能源供需",
        "keywords": DOMAIN_KEYWORDS["能源供需"],
        "sources": [
            {"name": "财联社", "type": "rss", "url": "http://localhost:8053/cls/telegraph", "limit": 30, "lang": "zh"},
            {"name": "金十数据", "type": "rss", "url": "http://localhost:8053/jin10/flash", "limit": 30, "lang": "zh"},
        ]
    },
    {
        "domain": "大宗商品持仓",
        "keywords": None,
        "sources": [
            {"name": "CFTC", "type": "cftc", "limit": 10, "lang": "zh"},
        ]
    },
    {
        "domain": "美国立法行政",
        "keywords": DOMAIN_KEYWORDS["美国立法行政"],
        "sources": [
            {"name": "财联社", "type": "rss", "url": "http://localhost:8053/cls/telegraph", "limit": 30, "lang": "zh"},
            {"name": "金十数据", "type": "rss", "url": "http://localhost:8053/jin10/flash", "limit": 30, "lang": "zh"},
        ]
    },
    {
        "domain": "美股",
        "keywords": DOMAIN_KEYWORDS["美股"],
        "sources": [
            {"name": "CNBC-财经", "type": "rss", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", "limit": 10, "lang": "en"},
            {"name": "华尔街日报-市场", "type": "rss", "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "limit": 10, "lang": "en"},
            {"name": "MarketWatch", "type": "rss", "url": "https://feeds.marketwatch.com/marketwatch/topstories/", "limit": 10, "lang": "en"},
            {"name": "Seeking Alpha", "type": "rss", "url": "https://seekingalpha.com/market_currents.xml", "limit": 10, "lang": "en"},
        ]
    },
    {
        "domain": "官方监管",
        "keywords": None,
        "sources": [
            {"name": "美国SEC", "type": "rss", "url": "https://www.sec.gov/news/pressreleases.rss", "limit": 5, "lang": "en"},
        ]
    },
    {
        "domain": "国内政策/快讯",
        "keywords": DOMAIN_KEYWORDS["国内政策/快讯"],
        "sources": [
            {"name": "财联社", "type": "rss", "url": "http://localhost:8053/cls/telegraph", "limit": 30, "lang": "zh"},
        ]
    },
    {
        "domain": "国内科技",
        "keywords": DOMAIN_KEYWORDS["国内科技"],
        "sources": [
            {"name": "同花顺", "type": "rss", "url": "http://localhost:8053/ths/kuaixun", "limit": 30, "lang": "zh"},
        ]
    },
    {
        "domain": "海外科技",
        "keywords": None,
        "sources": [
            {"name": "TechCrunch", "type": "rss", "url": "https://techcrunch.com/feed/", "limit": 5, "lang": "en"},
            {"name": "The Verge", "type": "rss", "url": "https://www.theverge.com/rss/index.xml", "limit": 5, "lang": "en"},
        ]
    },
    {
        "domain": "A股",
        "keywords": DOMAIN_KEYWORDS["A股"],
        "sources": [
            {"name": "东方财富", "type": "api", "url": "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns", "limit": 30, "lang": "zh"},
        ]
    },
]


# ============ 工具函数 ============

def is_blacklisted(item):
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()
    return any(word.lower() in text for word in BLACKLIST)


def match_keywords(item, keywords, must_have=None):
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()
    if must_have:
        if not any(kw.lower() in text for kw in must_have):
            return False
    if not keywords:
        return True
    return any(kw.lower() in text for kw in keywords)


def parse_time(published):
    if not published:
        return ""
    formats = [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(published, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone(timezone(timedelta(hours=8)))
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            continue
    return published


def fetch_rss(name, url, limit=5, lang="en"):
    try:
        feed = feedparser.parse(url)
    except Exception:
        return []

    results = []
    for entry in feed.entries[:limit]:
        summary = entry.get("summary", "")
        summary = re.sub(r"<[^>]+>", "", summary).strip()
        published = entry.get("published", "") or entry.get("updated", "")
        results.append({
            "title": entry.get("title", ""),
            "link": entry.get("link", ""),
            "time": parse_time(published),
            "media": name,
            "summary": summary,
            "lang": lang,
        })
    return results


def fetch_eastmoney(limit=5):
    url = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
    params = {
        "client": "web", "biz": "web_news_col", "column": "346",
        "order": "1", "needInteractData": "0", "page_index": "1",
        "page_size": str(limit), "req_trace": "1",
        "fields": "code,showTime,title,mediaName,summary,url,uniqueUrl",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        items = data.get("data", {}).get("list", [])
    except Exception:
        return []

    return [{
        "title": item.get("title", ""),
        "link": item.get("uniqueUrl") or item.get("url", ""),
        "time": item.get("showTime", ""),
        "media": item.get("mediaName", "东方财富"),
        "summary": item.get("summary", ""),
        "lang": "zh",
    } for item in items]


def fetch_cftc_data():
    try:
        from cftc_cot import cot_download_year
    except ImportError:
        return []
    try:
        df = cot_download_year(year=datetime.now().year, cot_report_type="disaggregated_fut", store_zip=False)
    except Exception:
        return []

    target_markets = ["CRUDE OIL", "GOLD", "COPPER", "SILVER", "NATURAL GAS"]
    long_col = "M_Money_Positions_Long_All"
    short_col = "M_Money_Positions_Short_All"
    date_col = "Report_Date_as_YYYY-MM-DD"
    market_col = "Market_and_Exchange_Names"

    results = []
    for market in target_markets:
        try:
            sub = df[df[market_col].str.contains(market, case=False, na=False)]
            if sub.empty:
                continue
            latest = sub.sort_values(date_col, ascending=False).iloc[0]
            long_val = latest[long_col]
            short_val = latest[short_col]
            net = long_val - short_val
            results.append({
                "title": f"{market} 非商业净持仓：{net:+,.0f} 张",
                "link": f"https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm#{market.lower().replace(' ', '-')}",
                "time": str(latest[date_col]),
                "media": "CFTC",
                "summary": f"多头：{long_val:,.0f} 张　空头：{short_val:,.0f} 张　净持仓：{net:+,.0f} 张",
                "lang": "zh",
                "skip_ai": True,
            })
        except Exception:
            continue
    return results


def analyze_with_ai(title, summary, lang):
    if lang == "en":
        system_content = """你是财经信息整理助手。用户会给你一段英文新闻。
你必须输出四行，一行都不能少：
标题：把标题翻译成简洁的中文
内容：把内容翻译成1-2句中文
摘要：用一句话（不超过40字）概括核心内容
分类：从「金融直接相关 / 无关但有用 / 噪音」中选一个

严格按下面格式输出，不要加多余内容：
标题：xxx
内容：xxx
摘要：xxx
分类：xxx
"""
    else:
        system_content = """你是财经信息整理助手。用户会给你一段新闻。
你必须输出两行，一行都不能少：
摘要：用一句话（不超过40字）概括核心内容
分类：从「金融直接相关 / 无关但有用 / 噪音」中选一个

严格按下面格式输出，不要加多余内容：
摘要：xxx
分类：xxx
"""

    if lang == "en":
        user_content = f"请翻译并分析下面这条英文新闻。必须输出标题、内容、摘要、分类四行。\n\n新闻标题：{title}\n新闻内容：{summary}\n"
    else:
        user_content = f"请分析下面这条新闻。必须输出摘要、分类两行。\n\n新闻标题：{title}\n新闻内容：{summary}\n"

    try:
        response = client.chat.completions.create(
            model="deepseek-flash",
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ],
            temperature=0.3
        )
        text = response.choices[0].message.content

        def extract(label):
            m = re.search(rf"{label}[：:]\s*(.+)", text)
            return m.group(1).strip() if m else None

        cn_title = extract("标题")
        cn_summary = extract("内容")
        ai_summary = extract("摘要")
        ai_category = extract("分类") or "未分类"

        if lang == "en" and not cn_title and ai_summary:
            cn_title = ai_summary

        return cn_title, cn_summary, ai_summary, ai_category
    except Exception as e:
        return None, None, None, f"分析失败：{e}"


def quick_filter(title, summary, domain):
    prompt = f"""判断下面这条新闻是否与「{domain}」领域直接相关。
只回答"相关"或"不相关"，不要其他内容。

新闻标题：{title}
新闻内容：{summary}
"""
    try:
        response = client.chat.completions.create(
            model="deepseek-flash",
            messages=[
                {"role": "system", "content": "你是财经信息分类助手，只回答'相关'或'不相关'。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        text = response.choices[0].message.content.strip()
        return "不相关" not in text
    except Exception:
        return True


def translate_keyword(keyword):
    if not keyword.strip():
        return []
    if re.match(r"^[a-zA-Z0-9\s\-]+$", keyword):
        return [keyword]
    try:
        response = client.chat.completions.create(
            model="deepseek-flash",
            messages=[
                {"role": "system", "content": "你是翻译助手。把用户输入的中文关键词翻译成英文，只输出翻译结果，不要解释，不要标点，不要引号。"},
                {"role": "user", "content": keyword}
            ],
            temperature=0.1
        )
        en_keyword = response.choices[0].message.content.strip()
        return [keyword, en_keyword]
    except Exception:
        return [keyword]


def render_item(item, idx):
    if item.get("cn_title"):
        st.markdown(f"**{idx}. {item['cn_title']}**")
        st.caption(f"原文：{item['title']}")
    else:
        st.markdown(f"**{idx}. {item['title']}**")

    st.caption(f"来源：{item.get('media', '')}　|　时间：{item.get('time', '')}")

    if item.get("cn_summary"):
        st.write(item["cn_summary"])
        if item.get("summary"):
            st.caption(f"原文：{item['summary'][:200]}")
    elif item.get("summary"):
        st.write(item["summary"])

    if item.get("ai_summary"):
        st.info(f"AI 摘要：{item['ai_summary']}")

    if item.get("link"):
        st.markdown(f"[原文链接]({item['link']})")


# ============ 模式切换 ============
mode = st.radio("模式", ["清单模式", "关键词模式"], horizontal=True)


# ============ 清单模式 ============
if mode == "清单模式":
    st.write("按领域展示各信息源的最新内容。已分析过的自动从数据库读取，不重复花钱。")

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("清理 7 天前数据"):
            deleted = cleanup_old(7)
            st.success(f"已删除 {deleted} 条旧记录")

    total, analyzed = db_stats()
    st.caption(f"数据库：共 {total} 条，已分析 {analyzed} 条")

    ai_full = st.slider("每个源完整分析的条数", 0, 5, 3, key="list_full")
    ai_quick = st.slider("每个源快速过滤的条数", 0, 5, 2, key="list_quick")

    if st.button("开始抓取", key="list_fetch"):
        all_data = []
        total_sources = sum(len(d["sources"]) for d in SOURCE_LIST)
        current = 0
        progress = st.progress(0)
        status = st.empty()

        cache_hit = 0  # 命中缓存的条数

        for domain in SOURCE_LIST:
            domain_data = {"domain": domain["domain"], "sources": []}
            must_have = DOMAIN_MUST_HAVE.get(domain["domain"])

            for source in domain["sources"]:
                status.write(f"正在抓取：{source['name']}...")

                if source["type"] == "rss":
                    raw_items = fetch_rss(source["name"], source["url"], source["limit"], source["lang"])
                elif source["type"] == "api":
                    raw_items = fetch_eastmoney(source["limit"])
                elif source["type"] == "cftc":
                    raw_items = fetch_cftc_data()
                else:
                    raw_items = []

                filtered = []
                for item in raw_items:
                    if is_blacklisted(item):
                        continue
                    if not match_keywords(item, domain["keywords"], must_have):
                        continue
                    filtered.append(item)

                filtered = filtered[:5]

                analyzed_items = []
                for i, item in enumerate(filtered):
                    new_item = dict(item)
                    new_item["cn_title"] = None
                    new_item["cn_summary"] = None
                    new_item["ai_summary"] = None
                    new_item["ai_category"] = None

                    if item.get("skip_ai"):
                        analyzed_items.append(new_item)
                        save_article(new_item, domain["domain"])
                        continue

                    # 先查数据库
                    cached = get_cached(item.get("link", ""))
                    if cached and cached[0]:
                        new_item["cn_title"] = cached[0]
                        new_item["cn_summary"] = cached[1]
                        new_item["ai_summary"] = cached[2]
                        new_item["ai_category"] = cached[3]
                        cache_hit += 1
                        analyzed_items.append(new_item)
                        continue

                    # 没缓存，调 AI
                    if i < ai_full:
                        status.write(f"AI 完整分析：{source['name']} 第 {i+1} 条...")
                        cn_title, cn_summary, ai_summary, ai_category = analyze_with_ai(
                            item["title"], item["summary"], item["lang"]
                        )
                        new_item["cn_title"] = cn_title
                        new_item["cn_summary"] = cn_summary
                        new_item["ai_summary"] = ai_summary
                        new_item["ai_category"] = ai_category
                        save_article(new_item, domain["domain"])

                    elif i < ai_full + ai_quick:
                        status.write(f"AI 快速过滤：{source['name']} 第 {i+1} 条...")
                        if not quick_filter(item["title"], item["summary"], domain["domain"]):
                            continue
                        save_article(new_item, domain["domain"])

                    else:
                        save_article(new_item, domain["domain"])

                    analyzed_items.append(new_item)

                domain_data["sources"].append({
                    "name": source["name"],
                    "items": analyzed_items,
                })
                current += 1
                progress.progress(current / total_sources)

            all_data.append(domain_data)

        progress.empty()
        status.empty()
        st.session_state["list_data"] = all_data
        st.success(f"抓取完成！命中缓存 {cache_hit} 条，本次新分析 {analyzed + 0} 条。")

    if "list_data" in st.session_state:
        for domain_data in st.session_state["list_data"]:
            total = sum(len(s["items"]) for s in domain_data["sources"])
            header = f"{domain_data['domain']}（{total} 条）" if total else f"{domain_data['domain']}（无新消息）"

            with st.expander(header, expanded=False):
                if total == 0:
                    st.write("无新消息")
                    continue

                for source in domain_data["sources"]:
                    if not source["items"]:
                        continue
                    st.markdown(f"#### {source['name']}")
                    for i, item in enumerate(source["items"], 1):
                        render_item(item, i)
                        st.divider()
    else:
        st.info("点击上方「开始抓取」按钮获取最新信息。")


# ============ 关键词模式 ============
else:
    st.write("输入关键词，跨所有信息源搜索。")

    keyword = st.text_input("输入关键词（留空则不过滤）", "")
    ai_count = st.slider("对前几条调用 AI 分析", 0, 40, 12, key="kw_ai")

    if st.button("开始搜集", key="kw_fetch"):
        all_items = []
        progress = st.progress(0)

        for domain in SOURCE_LIST:
            for source in domain["sources"]:
                if source["type"] == "rss":
                    items = fetch_rss(source["name"], source["url"], 8, source["lang"])
                elif source["type"] == "api":
                    items = fetch_eastmoney(8)
                elif source["type"] == "cftc":
                    items = fetch_cftc_data()
                else:
                    items = []
                all_items.extend(items)

        seen = set()
        unique_items = []
        for item in all_items:
            link = item.get("link", "")
            if link and link not in seen:
                seen.add(link)
                unique_items.append(item)
        all_items = unique_items

        progress.progress(1.0)
        progress.empty()

        all_items = [x for x in all_items if not is_blacklisted(x)]
        all_items.sort(key=lambda x: 0 if x["lang"] == "en" else 1)

        st.success(f"共抓到 {len(all_items)} 条")

        if keyword.strip():
            with st.spinner("正在翻译关键词..."):
                keywords = translate_keyword(keyword)
            st.info(f"搜索关键词：{' / '.join(keywords)}")

            filtered = []
            for x in all_items:
                title_lower = x.get("title", "").lower()
                summary_lower = x.get("summary", "").lower()
                for kw in keywords:
                    kw_lower = kw.lower()
                    if kw_lower in title_lower or kw_lower in summary_lower:
                        filtered.append(x)
                        break

            if not filtered:
                st.info(f"没有包含「{keyword}」的内容，下面是全部。")
                filtered = all_items
        else:
            filtered = all_items

        filtered = filtered[:60]

        results = []
        for i, item in enumerate(filtered, 1):
            row = dict(item)
            row["cn_title"] = None
            row["cn_summary"] = None
            row["ai_summary"] = None
            row["ai_category"] = "未分析"

            if item.get("skip_ai"):
                results.append(row)
                continue

            cached = get_cached(item.get("link", ""))
            if cached and cached[0]:
                row["cn_title"] = cached[0]
                row["cn_summary"] = cached[1]
                row["ai_summary"] = cached[2]
                row["ai_category"] = cached[3]
                results.append(row)
                continue

            if i <= ai_count:
                cn_title, cn_summary, ai_summary, ai_category = analyze_with_ai(
                    item["title"], item["summary"], item["lang"]
                )
                row["cn_title"] = cn_title
                row["cn_summary"] = cn_summary
                row["ai_summary"] = ai_summary
                row["ai_category"] = ai_category
                save_article(row, "关键词搜索")

            results.append(row)

        groups = {"金融直接相关": [], "无关但有用": [], "噪音": [], "未分类": [], "未分析": []}
        for row in results:
            cat = row["ai_category"]
            groups[cat if cat in groups else "未分类"].append(row)

        for group_name in ["金融直接相关", "无关但有用", "噪音", "未分类", "未分析"]:
            rows = groups.get(group_name, [])
            if not rows:
                continue
            st.markdown(f"## {group_name}（{len(rows)} 条）")
            for i, row in enumerate(rows, 1):
                render_item(row, i)
                st.divider()