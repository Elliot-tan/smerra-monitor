#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Actions 云端空房监测脚本（不依赖本地电脑）

每个定时任务运行一次：
1. 抓取四个公寓预订页面的 iframe HTML
2. 解析每个房型的状态徽章（Complet / A venir / Disponible）
3. 对比上一次状态（state.json），只对"新出现 Disponible"的房型
   通过 ntfy 推送通知到手机，避免重复轰炸
4. 把最新状态写回 state.json，由 workflow 提交回仓库

用法:
    NTFY_TOPIC=<话题名> python3 check.py          # 正常检查
    python3 check.py --dry-run                    # 只检查不推送不写状态
    NTFY_TOPIC=<话题名> python3 check.py --test-notify   # 发一条测试推送
"""

import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE_DIR, "state.json")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

RESIDENCES = [
    {
        "name": "Simone de Beauvoir",
        "url": "https://logement.smerra.fr/residence-etudiante/fac-habitat-simone-de-beauvoir/",
        "iframe_url": "https://w2.Fac-Habitat.com/Simone-de-Beauvoir/p/4/20/28/version=iframe_reservation",
    },
    {
        "name": "Magellan",
        "url": "https://logement.smerra.fr/residence-etudiante/fac-habitat-magellan/",
        "iframe_url": "https://w2.Fac-Habitat.com/Magellan/p/4/20/9633/version=iframe_reservation",
    },
    {
        "name": "Auguste Rodin",
        "url": "https://logement.smerra.fr/residence-etudiante/fac-habitat-auguste-rodin/",
        "iframe_url": "https://w2.Fac-Habitat.com/Auguste-Rodin/p/4/21/33/version=iframe_reservation/new",
    },
    {
        "name": "Adelaide",
        "url": "https://logement.smerra.fr/residence-etudiante/fac-habitat-adelaide/",
        "iframe_url": "https://w2.Fac-Habitat.com/Adelaide/p/4/20/15409/version=iframe_reservation/new/",
    },
]

SECTION_RE = re.compile(
    r'<section class="rounded[^"]*"[^>]*>(.*?)</section>', re.S
)
ROOM_RE = re.compile(
    r'<span class="fw-bold me-1">([^<]+)</span>\s*'
    r'<span class="badge([^"]*)"[^>]*>([^<]+)</span>'
)
PRICE_RE = re.compile(
    r'<span class="fw-medium">À partir de</span>\s*'
    r'<span class="fw-bold">([^<]+)</span>'
)


def now_str():
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def fetch(url):
    """优先用 urllib；个别环境（如 macOS 系统 Python）证书库缺失时退回 curl。"""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
                "Referer": "https://logement.smerra.fr/",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", "replace")
    except Exception:
        result = subprocess.run(
            [
                "curl",
                "-sL",
                "--max-time",
                "30",
                "-A",
                USER_AGENT,
                "-H",
                "Accept-Language: fr-FR,fr;q=0.9,en;q=0.8",
                "-H",
                "Referer: https://logement.smerra.fr/",
                "-w",
                "\n%{http_code}",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=40,
        )
        body, _, status = result.stdout.rpartition("\n")
        if result.returncode != 0 or not status.startswith("2"):
            raise RuntimeError(f"HTTP {status or result.returncode}: {result.stderr.strip()[:200]}")
        return body


def parse_rooms(html):
    rooms = []
    for section in SECTION_RE.findall(html):
        m = ROOM_RE.search(section)
        if not m:
            continue
        room_type = m.group(1).strip()
        badge_class = m.group(2)
        badge_text = m.group(3).strip()
        price_m = PRICE_RE.search(section)
        rooms.append(
            {
                "type": room_type,
                "badge": badge_text,
                "disponible": badge_text.strip().lower() == "disponible"
                or "text-bg-success" in badge_class,
                "price": price_m.group(1).strip() if price_m else "",
            }
        )
    return rooms


def ntfy_notify(topic, title, message):
    data = json.dumps(
        {
            "topic": topic,
            "title": title,
            "message": message,
            "priority": 5,
            "tags": ["house"],
        }
    )
    try:
        req = urllib.request.Request(
            "https://ntfy.sh",
            data=data.encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status
    except Exception:
        result = subprocess.run(
            [
                "curl",
                "-s",
                "--max-time",
                "15",
                "-H",
                "Content-Type: application/json; charset=utf-8",
                "-d",
                data,
                "https://ntfy.sh",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip()[:200])
        return 200


def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def main():
    dry_run = "--dry-run" in sys.argv
    test_notify = "--test-notify" in sys.argv
    topic = os.environ.get("NTFY_TOPIC", "").strip()

    if test_notify:
        if not topic:
            print("错误：请设置 NTFY_TOPIC 环境变量", file=sys.stderr)
            return 2
        ntfy_notify(
            topic,
            "Smerra 云端监测 测试",
            "云端推送通道正常 ✅ 以后有空房时，你会收到这样的通知。",
        )
        print("测试推送已发送")
        return 0

    if not topic:
        print("错误：请设置 NTFY_TOPIC 环境变量", file=sys.stderr)
        return 2

    state = load_state()
    new_state = dict(state)
    summary = {"checked_at": now_str(), "residences": []}
    any_error = False

    for res in RESIDENCES:
        name = res["name"]
        entry = {"name": name, "url": res["url"], "rooms": [], "error": None}
        try:
            rooms = parse_rooms(fetch(res["iframe_url"]))
            if not rooms:
                raise RuntimeError("未解析到任何房型区块（页面结构可能变化）")
            entry["rooms"] = [
                {
                    "type": r["type"],
                    "badge": r["badge"],
                    "disponible": r["disponible"],
                    "price": r["price"],
                }
                for r in rooms
            ]
            print(f"{name}: " + ", ".join(f"{r['type']}={r['badge']}" for r in rooms))
        except Exception as exc:  # noqa: BLE001
            any_error = True
            entry["error"] = str(exc)
            print(f"{name}: 抓取/解析失败 - {exc}", file=sys.stderr)
            continue

        summary["residences"].append(entry)

        prev_available = set(state.get(name, {}).get("available", []))
        now_available = [r["type"] for r in rooms if r["disponible"]]
        newly = [t for t in now_available if t not in prev_available]

        if not dry_run:
            new_state[name] = {"available": sorted(now_available), "rooms": entry["rooms"]}

        if newly:
            details = ", ".join(
                f"{r['type']} ({r['price']})"
                for r in rooms
                if r["disponible"] and r["type"] in newly
            )
            title = f"🏠 {name} 有空房了！"
            message = f"新出现 Disponible: {details}\n{res['url']}"
            print(f"新空房: {name} - {details}")
            if dry_run:
                print("(dry-run，不推送)")
            else:
                ntfy_notify(topic, title, message)
                print("已推送 ntfy")
        else:
            status = "有 Disponible" if now_available else "无 Disponible"
            print(f"{name}: {status}（无新增）")

    if not dry_run:
        save_state(new_state)

    print(json.dumps(summary, ensure_ascii=False))
    return 1 if any_error else 0


if __name__ == "__main__":
    sys.exit(main())
