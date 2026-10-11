from utils import fetch_cls, fetch_jin10, is_blacklisted, match_keywords
import json

# 加载配置
with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

BLACKLIST = CONFIG["blacklist"]
DOMAIN_KEYWORDS = CONFIG["domain_keywords"]
DOMAIN_MUST_HAVE = CONFIG["domain_must_have"]

# 测试央行政策
print("=" * 60)
print("测试：央行政策 - 财联社")
print("=" * 60)

items = fetch_cls(30)
print(f"财联社原始：{len(items)} 条")
print()

keywords = DOMAIN_KEYWORDS["央行政策"]
must_have = DOMAIN_MUST_HAVE.get("央行政策")

print(f"关键词：{keywords}")
print(f"must_have：{must_have}")
print()

print("前 10 条数据：")
for i, item in enumerate(items[:10], 1):
    title = item.get("title", "")[:50]
    summary = item.get("summary", "")[:80]
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()

    # 检查关键词匹配
    kw_hit = [kw for kw in keywords if kw.lower() in text]
    mh_hit = []
    if must_have:
        mh_hit = [kw for kw in must_have if kw.lower() in text]

    print(f"\n{i}. 标题：{title}")
    print(f"   摘要：{summary}")
    print(f"   命中关键词：{kw_hit}")
    print(f"   命中 must_have：{mh_hit}")
    print(f"   标题原始类型：{type(item.get('title'))}，摘要原始类型：{type(item.get('summary'))}")