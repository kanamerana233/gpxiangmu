import os
os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
# ===== 自动启动 china-finance-rss 后台服务 =====
from cn_rss_integration import start_cn_rss_server
start_cn_rss_server()
# ==============================================
from db import init_db, get_cached, save_article, db_stats, cleanup_old
init_db()
import streamlit as st
import os
import re
import json
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from utils import (
    is_blacklisted, match_keywords, parse_time,
    fetch_rss, fetch_eastmoney, fetch_cftc_data,
    analyze_with_ai, quick_filter, translate_keyword,
    render_item as _render_item,
)
from stock_picker import run_stock_picker

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



init_db()


# ============ 加载配置 ============
import json

with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

BLACKLIST = CONFIG["blacklist"]
DOMAIN_KEYWORDS = CONFIG["domain_keywords"]
DOMAIN_MUST_HAVE = CONFIG["domain_must_have"]
SOURCE_LIST = CONFIG["source_list"]

# 自动给每个 domain 挂上对应的 keywords
for domain in SOURCE_LIST:
    domain["keywords"] = DOMAIN_KEYWORDS.get(domain["domain"])

# ============ 工具函数 ============

# ============ 模式切换 ============
def render_item(item, idx):
    _render_item(st, item, idx)
mode = st.radio("模式", ["清单模式", "关键词模式", "选股模式"], horizontal=True)


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
                    if is_blacklisted(item, BLACKLIST):
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
                        cn_title, cn_summary, ai_summary, ai_category = analyze_with_ai(client, 
                            item["title"], item["summary"], item["lang"]
                        )
                        new_item["cn_title"] = cn_title
                        new_item["cn_summary"] = cn_summary
                        new_item["ai_summary"] = ai_summary
                        new_item["ai_category"] = ai_category
                        save_article(new_item, domain["domain"])

                    elif i < ai_full + ai_quick:
                        status.write(f"AI 快速过滤：{source['name']} 第 {i+1} 条...")
                        if not quick_filter(client,item["title"], item["summary"], domain["domain"]):
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


# ============ 选股模式 ============
elif mode == "选股模式":
    st.write("输入一个问题，从本地 A 股数据库里找出相关股票，AI 按相关度打分排序。")

    # ===== 数据管理 =====
    with st.expander("📊 数据管理（点击展开）", expanded=False):
        from update_db import (
            update_stock_list, update_industry_concepts,
            get_db_stats, get_pending_zyjs_count
        )

        stats = get_db_stats()
        st.caption(
            f"股票总数：{stats['total']} 只　|　"
            f"有名称/主营：{stats['has_zyjs']} 只　|　"
            f"有行业：{stats['has_industry']} 只　|　"
            f"有概念：{stats['has_concepts']} 只"
        )

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if st.button("更新股票列表",
                         help="扫描通达信本地 .day 文件，发现新股自动加入数据库。秒级完成。"):
                with st.spinner("扫描中..."):
                    added, total = update_stock_list()
                if added > 0:
                    st.success(f"新增 {added} 只股票，本地共 {total} 只")
                else:
                    st.info(f"没有新股，本地共 {total} 只")

        with col2:
            if st.button("更新行业概念",
                         help="重新解析通达信板块文件，刷新每只股票的行业和概念。秒级完成。"):
                with st.spinner("解析板块文件..."):
                    ind_count, con_count = update_industry_concepts()
                st.success(f"更新完成：{ind_count} 只行业，{con_count} 只概念")

        with col3:
            if st.button("更新主营业务",
                         help="只抓还没有主营业务的股票（新股）。耗时较长，建议在终端运行。"):
                pending = get_pending_zyjs_count()
                if pending == 0:
                    st.info("所有股票都有主营业务了")
                else:
                    st.warning(
                        f"还有 {pending} 只没有主营业务。\n\n"
                        f"请在终端运行：\n\n"
                        f"`python fetch_zyjs.py`"
                    )

        with col4:
            if st.button("全量重建",
                         help="清空数据库后从零重建。耗时 3-4 小时。"):
                st.warning(
                    "全量重建需要 3-4 小时。\n\n"
                    "请在终端依次运行：\n\n"
                    "`python build_stock_db.py`\n\n"
                    "`python fill_names.py`\n\n"
                    "`python fetch_zyjs.py`"
                )

    st.divider()

    # ===== 选股输入 =====
    col_a, col_b = st.columns([3, 1])
    with col_a:
        question = st.text_input("输入你的问题，例如：锂电池产业链相关股票", "")
    with col_b:
        use_cache = st.checkbox("使用缓存", value=True, help="勾选后，相同问题会直接返回上次结果，节省 AI 费用。")

    if st.button("开始选股", key="picker_run"):
        if not question.strip():
            st.warning("请先输入问题")
        else:
            status = st.empty()
            status.write("准备中...")

            try:
                matched_count, keywords, ranked, from_cache = run_stock_picker(
                    client, question,
                    progress_callback=lambda msg: status.write(msg),
                    use_cache=use_cache
                )
                status.empty()

                if from_cache:
                    st.info("⚡ 命中缓存，未消耗 AI 费用")
                st.info(f"搜索关键词：{' / '.join(keywords)}")
                st.success(f"粗筛出 {matched_count} 只，展示相关度最高的 {len(ranked)} 只")

                if not ranked:
                    st.warning("没有找到相关股票，换个问法试试。")
                elif "error" in ranked[0]:
                    st.error(f"AI 打分失败：{ranked[0]['error']}")
                else:
                    # 导出按钮
                    import pandas as pd
                    export_data = []
                    for s in ranked:
                        export_data.append({
                            "代码": s["code"],
                            "名称": s["name"],
                            "相关度": s.get("score", 0),
                            "关联原因": s.get("reason", ""),
                            "行业": s["industry"],
                            "主营业务": s["main_business"][:200],
                            "概念": s["concepts"][:200],
                        })
                    df = pd.DataFrame(export_data)
                    csv = df.to_csv(index=False).encode("utf-8-sig")
                    st.download_button(
                        label="📥 下载 CSV",
                        data=csv,
                        file_name=f"选股结果_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                        mime="text/csv",
                    )

                    st.divider()

                    # 按分数区间分组
                    high = [s for s in ranked if s.get("score", 0) >= 80]
                    mid = [s for s in ranked if 60 <= s.get("score", 0) < 80]
                    low = [s for s in ranked if s.get("score", 0) < 60]

                    def render_stock_list(items, label):
                        if not items:
                            return
                        st.markdown(f"### {label}（{len(items)} 只）")
                        for i, s in enumerate(items, 1):
                            score = s.get("score", 0)
                            st.markdown(f"**{i}. {s['name']}（{s['code']}）— {score} 分**")
                            st.caption(f"行业：{s['industry'] or '未分类'}")
                            if s.get("main_business"):
                                st.caption(f"主营业务：{s['main_business'][:120]}")
                            st.caption(f"概念：{s['concepts'][:200]}")
                            st.info(f"关联原因：{s['reason']}")
                            st.divider()

                    render_stock_list(high, "🔥 高相关（80 分以上）")
                    render_stock_list(mid, "✅ 中等相关（60-79 分）")
                    render_stock_list(low, "⚪ 低相关（60 分以下）")

            except Exception as e:
                status.empty()
                st.error(f"选股失败：{e}")


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

        all_items = [x for x in all_items if not is_blacklisted(x, BLACKLIST)]
        all_items.sort(key=lambda x: 0 if x["lang"] == "en" else 1)

        st.success(f"共抓到 {len(all_items)} 条")

        if keyword.strip():
            with st.spinner("正在翻译关键词..."):
                keywords = translate_keyword(client, keyword)
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
                    client,item["title"], item["summary"], item["lang"]
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