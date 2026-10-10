import re
import feedparser
import requests
from datetime import datetime, timezone, timedelta


def is_blacklisted(item, blacklist):
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()
    return any(word.lower() in text for word in blacklist)


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
        df = cot_download_year(
            year=datetime.now().year,
            cot_report_type="disaggregated_fut",
            store_zip=False
        )
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
                "link": "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm",
                "time": str(latest[date_col]),
                "media": "CFTC",
                "summary": f"多头：{long_val:,.0f} 张　空头：{short_val:,.0f} 张　净持仓：{net:+,.0f} 张",
                "lang": "zh",
                "skip_ai": True,
            })
        except Exception:
            continue
    return results


def analyze_with_ai(client, title, summary, lang):
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


def quick_filter(client, title, summary, domain):
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


def translate_keyword(client, keyword):
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


def render_item(st, item, idx):
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