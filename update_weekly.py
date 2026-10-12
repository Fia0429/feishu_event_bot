#!/usr/bin/env python3
"""Refresh weekly merchant recommendations from the full merchant catalog.

Uses Google News RSS as a zero-key public information source.  It scans the
complete catalog locally, builds a shortlist from merchant quality/category
fit, then looks for recent promotion, product, earnings and seasonal signals.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "data" / "merchant_catalog.csv"
OUTPUT = ROOT / "data" / "weekly_top10.json"
TZ_CN = timezone(timedelta(hours=8))

PRIMARY = {"时尚服饰", "旅游出行", "家居生活", "家用电器和智能设备"}
SECONDARY = {"美妆日化", "集合折扣店", "食品饮品", "运动健康"}

SIGNALS = {
    "促销": (22, ("sale", "deal", "discount", "promotion", "coupon", "offer", "save")),
    "新品": (20, ("launch", "new product", "unveil", "release", "collection", "debut")),
    "财报": (18, ("earnings", "revenue", "profit", "results", "forecast", "guidance")),
    "节庆": (16, ("halloween", "holiday", "christmas", "black friday", "gift", "season")),
    "赛事": (14, ("marathon", "nba", "nfl", "race", "tournament", "championship", "sports")),
}

CATEGORY_RULES = [
    ("旅游出行", ("hotel", "travel", "air", "flight", "booking", "rental car", "cruise", "tour")),
    ("时尚服饰", ("fashion", "apparel", "clothing", "shoes", "jewelry", "watch", "bag", "lingerie")),
    ("家用电器和智能设备", ("electronics", "computer", "laptop", "phone", "camera", "appliance", "robot", "smart")),
    ("家居生活", ("home", "furniture", "mattress", "kitchen", "garden", "decor", "lighting")),
    ("美妆日化", ("beauty", "cosmetic", "skincare", "makeup", "fragrance", "hair")),
    ("运动健康", ("sport", "fitness", "health", "vitamin", "supplement", "running", "outdoor")),
    ("食品饮品", ("food", "coffee", "tea", "wine", "snack", "grocery", "drink")),
    ("集合折扣店", ("marketplace", "department store", "shop", "mall", "outlet")),
]


def category_for(name: str) -> str:
    low = name.lower()
    for category, words in CATEGORY_RULES:
        if any(word in low for word in words):
            return category
    return "其他"


def quality_score(m: dict) -> float:
    order = max(0.0, min(1.0, float(m.get("order_valid_rate") or 0)))
    commission = max(0.0, min(1.0, float(m.get("commission_valid_rate") or 0)))
    revenue = max(0.0, float(m.get("sales") or 0))
    category = m.get("category") or category_for(m["name"])
    category_weight = 10 if category in PRIMARY else 6 if category in SECONDARY else 0
    return order * 12 + commission * 13 + min(15, math.log10(revenue + 1) * 2) + category_weight


def fetch_news(name: str, days: int = 14) -> list[dict]:
    query = f'"{name}" (sale OR launch OR earnings OR holiday OR promotion) when:{days}d'
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 weekly-opportunity-bot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            root = ET.fromstring(resp.read())
    except Exception as exc:
        print(f"WARN {name}: {exc}")
        return []
    out = []
    for item in root.findall("./channel/item")[:5]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = item.findtext("pubDate") or ""
        try:
            published = parsedate_to_datetime(pub).astimezone(TZ_CN).date().isoformat()
        except Exception:
            published = ""
        out.append({"title": title, "url": link, "published": published})
    return out


def signal_score(items: list[dict]) -> tuple[int, list[str]]:
    text = " ".join(i["title"].lower() for i in items)
    found, points = [], 0
    for label, (weight, words) in SIGNALS.items():
        if any(word in text for word in words):
            found.append(label)
            points += weight
    if len(found) >= 2:
        points += 10
    return min(65, points), found


def reason(name: str, category: str, signals: list[str], headline: str) -> str:
    labels = "、".join(signals) if signals else "季节需求"
    headline = re.sub(r"\s+-\s+[^-]{1,80}$", "", headline).strip()
    return (
        f"本周检测到与{name}相关的{labels}信号。公开信息重点为“{headline}”。"
        f"结合{category}进入四季度消费窗口，建议优先制作活动解读、选购指南和价格对比内容；"
        "上线前由运营复核活动地区、库存与有效期。"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--shortlist", type=int, default=120)
    parser.add_argument("--delay", type=float, default=0.35)
    args = parser.parse_args()

    now = datetime.now(TZ_CN)
    week_start = now.date()
    week_end = week_start + timedelta(days=6)
    with CATALOG.open(encoding="utf-8-sig", newline="") as handle:
        catalog = list(csv.DictReader(handle))

    for m in catalog:
        m["category"] = m.get("category") or category_for(m["name"])
        m["base_score"] = quality_score(m)
    shortlist = sorted(catalog, key=lambda x: x["base_score"], reverse=True)[: args.shortlist]

    candidates = []
    for idx, m in enumerate(shortlist, 1):
        items = fetch_news(m["name"])
        info_points, signals = signal_score(items)
        if not items or not signals:
            continue
        total = min(100, round(35 + m["base_score"] + info_points * 0.55))
        candidates.append({**m, "items": items, "signals": signals, "score": total})
        print(f"{idx}/{len(shortlist)} {m['name']}: {total} {','.join(signals)}")
        time.sleep(args.delay)

    candidates.sort(key=lambda x: x["score"], reverse=True)
    selected, category_counts = [], {}
    max_per_category = max(1, math.floor(args.limit * 0.8))
    for m in candidates:
        cat = m["category"]
        if category_counts.get(cat, 0) >= max_per_category:
            continue
        selected.append(m)
        category_counts[cat] = category_counts.get(cat, 0) + 1
        if len(selected) == args.limit:
            break
    if len(selected) < args.limit:
        raise RuntimeError(f"Only {len(selected)} evidence-backed merchants found; refusing to send.")

    merchants = []
    for rank, m in enumerate(selected, 1):
        top = m["items"][0]
        merchants.append({
            "rank": rank,
            "name": m["name"],
            "merchant_id": str(m["merchant_id"]),
            "score": m["score"],
            "info_score": max(0, m["score"] - int(m.get("website_score", 0))),
            "website_score": int(m.get("website_score", 0)),
            "website_metric": m.get("website_metric") or "公开自然搜索与可靠品类排名暂不可用 0/10",
            "reason": reason(m["name"], m["category"], m["signals"], top["title"]),
            "source_url": top["url"],
            "affiliate": m.get("affiliate") or "待确认",
            "category": m["category"],
            "brand_key": re.sub(r"[^a-z0-9]+", "-", m["name"].lower()).strip("-"),
            "evidence_date": top["published"] or week_start.isoformat(),
        })

    payload = {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "expected_count": args.limit,
        "generated_at": now.isoformat(timespec="seconds"),
        "generation_method": "public-news-rss-v1",
        "merchants": merchants,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {OUTPUT} with {len(merchants)} merchants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
