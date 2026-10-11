import re
import feedparser
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
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
def fetch_cls(limit=30):
    """财联社电报（用 last_time 翻页抓多条）"""
    url = "https://www.cls.cn/api/cache"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Referer": "https://www.cls.cn/telegraph",
    }

    results = []
    seen_ids = set()
    last_time = ""

    max_pages = 5
    for page in range(max_pages):
        params = {
            "app": "CailianpressWeb",
            "name": "telegraph",
            "os": "web",
            "sv": "8.7.9",
            "rn": "20",
        }
        if last_time:
            params["last_time"] = last_time

        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            data = r.json()
            items = data.get("data", {}).get("roll_data", [])
        except Exception:
            break

        if not items:
            break

        new_count = 0
        for item in items:
            item_id = item.get("id", "")
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            new_count += 1

            title = item.get("title", "") or item.get("brief", "")[:60]
            brief = item.get("brief", "") or item.get("content", "")
            ctime = item.get("ctime", "")
            try:
                from datetime import datetime, timezone, timedelta
                dt = datetime.fromtimestamp(ctime, tz=timezone(timedelta(hours=8)))
                time_str = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                time_str = str(ctime)

            results.append({
                "title": title,
                "link": f"https://www.cls.cn/detail/{item_id}",
                "time": time_str,
                "media": "财联社",
                "summary": brief,
                "lang": "zh",
            })

        # 如果这一页没有新内容，停止
        if new_count == 0:
            break

        # 取最后一页的 ctime 作为下一页的 last_time
        last_item = items[-1]
        last_time = str(last_item.get("ctime", ""))

        if len(results) >= limit:
            break

    return results[:limit]


def fetch_jin10(limit=30):
    """金十数据快讯"""
    url = "https://flash-api.jin10.com/get_flash_list"
    params = {"channel": "-8200", "vip": "1"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Referer": "https://www.jin10.com/",
        "Origin": "https://www.jin10.com",
        "x-app-id": "bVBF4FyRTn5NJF5n",
        "x-version": "1.0.0",
    }
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        data = r.json()
        items = data.get("data", [])
    except Exception:
        return []

    results = []
    for item in items[:limit]:
        content = item.get("data", {}).get("content", "")
        if not content:
            continue
        title = content[:60] + ("..." if len(content) > 60 else "")

        # 金十的时间是 id 里前 14 位：20261010152506
        item_id = item.get("id", "")
        time_str = ""
        if len(item_id) >= 14:
            try:
                dt_str = item_id[:14]
                from datetime import datetime
                dt = datetime.strptime(dt_str, "%Y%m%d%H%M%S")
                time_str = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                time_str = ""

        results.append({
            "title": title,
            "link": f"https://flash.jin10.com/detail/{item_id}",
            "time": time_str,
            "media": "金十数据",
            "summary": content,
            "lang": "zh",
        })
    return results
def fetch_ths(limit=30):
    """同花顺快讯"""
    url = "https://news.10jqka.com.cn/tapp/news/push/stock/"
    params = {"page": "1", "tag": "", "track": "website", "pagesize": str(limit)}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Referer": "https://news.10jqka.com.cn/",
    }
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        data = r.json()
        items = data.get("data", {}).get("list", [])
    except Exception:
        return []

    results = []
    for item in items[:limit]:
        title = item.get("title", "")
        digest = item.get("digest", "")
        link = item.get("url", "")
        ctime = item.get("rtime") or item.get("ctime") or item.get("time", "")
        try:
            from datetime import datetime, timezone, timedelta
            dt = datetime.fromtimestamp(int(ctime), tz=timezone(timedelta(hours=8)))
            time_str = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            time_str = str(ctime)

        results.append({
            "title": title,
            "link": link,
            "time": time_str,
            "media": "同花顺",
            "summary": digest,
            "lang": "zh",
        })
    return results


def fetch_wscn(limit=30, channel="global-channel"):
    """华尔街见闻快讯"""
    url = "https://api-one-wscn.awtmt.com/apiv1/content/lives"
    params = {"channel": channel, "client": "pc", "limit": str(limit)}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Referer": "https://wallstreetcn.com/",
    }
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        data = r.json()
        items = data.get("data", {}).get("items", [])
    except Exception:
        return []

    results = []
    for item in items[:limit]:
        content = item.get("content", "")
        content = re.sub(r"<[^>]+>", "", content).strip()
        if not content:
            continue
        title = content[:60] + ("..." if len(content) > 60 else "")

        display_time = item.get("display_time", 0)
        try:
            from datetime import datetime, timezone, timedelta
            dt = datetime.fromtimestamp(int(display_time), tz=timezone(timedelta(hours=8)))
            time_str = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            time_str = ""

        item_id = item.get("id", "")

        results.append({
            "title": title,
            "link": f"https://wallstreetcn.com/livenews/{item_id}",
            "time": time_str,
            "media": "华尔街见闻",
            "summary": content,
            "lang": "zh",
        })
    return results


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

def filter_by_time(items, max_days=3):
    """过滤掉超过 max_days 天的旧新闻"""
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=max_days)
    result = []
    for item in items:
        time_str = item.get("time", "")
        if not time_str:
            result.append(item)  # 没时间的保留
            continue
        try:
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
            if dt >= cutoff:
                result.append(item)
        except Exception:
            result.append(item)  # 时间格式不对的保留
    return result
def batch_quick_filter(client, items, domain, batch_size=20):
    """批量判断一批新闻是否属于某领域。返回相关的 item 列表。"""
    if not items:
        return []

    relevant = []
    total = len(items)

    for start in range(0, total, batch_size):
        batch = items[start:start + batch_size]

        lines = []
        for i, item in enumerate(batch, 1):
            title = item.get("title", "")[:60]
            summary = item.get("summary", "")[:120]
            lines.append(f"{i}. {title} | {summary}")
        text = "\n".join(lines)

        prompt = f"""下面是 {len(batch)} 条财经新闻，请判断每条是否与「{domain}」领域直接相关。

{text}

严格按以下格式输出，只列出相关的序号，用逗号分隔：
相关序号：1,3,5

如果都不相关，输出：
相关序号：无

不要其他内容。"""

        try:
            response = client.chat.completions.create(
                model="deepseek-flash",
                messages=[
                    {"role": "system", "content": "你是财经新闻分类助手，只输出相关序号。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            result_text = response.choices[0].message.content.strip()

            match = re.search(r"相关序号[：:]\s*(.+)", result_text)
            if match:
                nums_str = match.group(1).strip()
                if "无" in nums_str:
                    continue
                nums = [int(x.strip()) for x in nums_str.split(",") if x.strip().isdigit()]
                for n in nums:
                    if 1 <= n <= len(batch):
                        relevant.append(batch[n - 1])
            else:
                # AI 返回格式不对，保留这一批全部，避免误杀
                relevant.extend(batch)
        except Exception:
            # 出错就保留这一批全部
            relevant.extend(batch)

    return relevant
def fetch_pbc(limit=10):
    """抓取央行新闻发布页"""
    url = "https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.pbc.gov.cn/",
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.encoding = r.apparent_encoding
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"[PBC] 抓取失败：{e}")
        return []

    results = []
    seen_titles = set()

    for a in soup.find_all("a"):
        href = a.get("href", "")
        if not href:
            continue
        # 只保留 /goutongjiaoliu/113456/113469/ 开头的新闻详情页
        if "/goutongjiaoliu/113456/113469/" not in href:
            continue

        title = a.get("title") or a.text.strip()
        if not title or len(title) < 8:
            continue
        if title in seen_titles:
            continue

        seen_titles.add(title)
        full_link = urljoin("https://www.pbc.gov.cn/", href)

        # 从 URL 里提取日期：/2026101011293518009/
        time_str = ""
        match = re.search(r"/(\d{14})", href)
        if match:
            ts = match.group(1)
            try:
                dt = datetime.strptime(ts[:8], "%Y%m%d")
                time_str = dt.strftime("%Y-%m-%d")
            except Exception:
                pass

        results.append({
            "title": title,
            "link": full_link,
            "time": time_str,
            "media": "央行官网",
            "summary": title,
            "lang": "zh",
        })
        if len(results) >= limit:
            break

    return results


def fetch_csrc(limit=10):
    """抓取证监会新闻发布页"""
    url = "https://www.csrc.gov.cn/csrc/xwfb/index.shtml"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.csrc.gov.cn/",
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.encoding = r.apparent_encoding
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"[CSRC] 抓取失败：{e}")
        return []

    results = []
    seen_titles = set()

    for a in soup.find_all("a"):
        href = a.get("href", "")
        if not href:
            continue
        if "content.shtml" not in href:
            continue
        # 只保留 c100028 和 c106311 两个栏目（新闻发布、新闻发言人）
        if "c100028" not in href and "c106311" not in href:
            continue
        # 跳过旧栏目
        if "c100029" in href:
            continue

        title = a.get("title") or a.text.strip()
        if not title or len(title) < 8:
            continue
        if title in seen_titles:
            continue

        seen_titles.add(title)
        full_link = urljoin("https://www.csrc.gov.cn/", href)

        results.append({
            "title": title,
            "link": full_link,
            "time": "",
            "media": "证监会官网",
            "summary": title,
            "lang": "zh",
        })
        if len(results) >= limit:
            break

    return results