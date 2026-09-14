#!/usr/bin/env python3
"""Build and send Feishu affiliate-opportunity cards."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
BEIJING = ZoneInfo("Asia/Shanghai")


def load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def weekly_card(now: datetime) -> dict:
    merchants = load_json(ROOT / "data" / "weekly_top10.json")
    elements = [
        {
            "tag": "markdown",
            "content": (
                "**评分口径：信息机会信号 90分 + 官网自然搜索 5分 + 品类排名 5分 = 100分**\n"
                "官网数据来自公开页面估算；自然搜索量按月访问量 × 自然搜索占比计算。"
            ),
        },
        {"tag": "hr"},
    ]
    for index, merchant in enumerate(merchants):
        content = (
            f"**#{merchant['rank']}  {merchant['name']}｜{merchant['score']}/100**\n"
            f"商家ID：{merchant['merchant_id']}　｜　所属联盟：{merchant['affiliate']}　｜　"
            f"信息信号：{merchant['info_score']}/90　｜　"
            f"网站模块：{merchant['website_score']}/10\n"
            f"**官网表现：** {merchant['website_metric']}\n"
            f"**推荐理由：** {merchant['reason']}\n"
            f"[查看相关信息]({merchant['source_url']})"
        )
        elements.append({"tag": "markdown", "content": content})
        if index < len(merchants) - 1:
            elements.append({"tag": "hr"})
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "orange",
            "title": {
                "tag": "plain_text",
                "content": f"海外商家机会 TOP10｜Ver 1.0（{now:%Y.%m.%d}）",
            },
        },
        "elements": elements,
    }


def monthly_card(now: datetime) -> dict:
    events = load_json(ROOT / "data" / "marketing_calendar.json")
    current = [item for item in events if item["month"] == now.month]
    elements = [
        {
            "tag": "markdown",
            "content": "面向海外市场筛选的本月重点节日、销售季和营销节点。日期可能因国家或平台政策调整，请在执行前复核活动页面。",
        },
        {"tag": "hr"},
    ]
    for index, event in enumerate(current):
        merchant_text = "、".join(
            f"{merchant['id']} {merchant['name']}" for merchant in event["merchants"]
        )
        content = (
            f"**{event['date']}｜{event['name']}**\n"
            f"重点市场：{event['markets']}\n"
            f"机会品类：{event['categories']}\n"
            f"相关商家：{merchant_text}"
        )
        elements.append({"tag": "markdown", "content": content})
        if index < len(current) - 1:
            elements.append({"tag": "hr"})
    if not current:
        elements.append({"tag": "markdown", "content": "本月暂无已录入的重点营销节点。"})
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {
                "tag": "plain_text",
                "content": f"{now:%Y年%m月}海外营销日历｜Ver 1.0",
            },
        },
        "elements": elements,
    }


def send(webhook: str, card: dict) -> None:
    payload = json.dumps({"msg_type": "interactive", "card": card}, ensure_ascii=False).encode()
    request = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode())
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Feishu request failed: {exc}") from exc
    if body.get("code", body.get("StatusCode")) != 0:
        raise RuntimeError(f"Feishu rejected the card: {body}")
    print("Feishu card sent successfully.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("card", choices=("weekly", "monthly"))
    parser.add_argument("--preview", action="store_true", help="Print JSON without sending")
    args = parser.parse_args()
    now = datetime.now(BEIJING)
    card = weekly_card(now) if args.card == "weekly" else monthly_card(now)
    if args.preview:
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return 0
    webhook = os.environ.get("FEISHU_WEBHOOK", "").strip()
    if not webhook:
        print("FEISHU_WEBHOOK is not configured.", file=sys.stderr)
        return 2
    send(webhook, card)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
