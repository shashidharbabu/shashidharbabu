#!/usr/bin/env python3
"""Scrape the public contribution calendar and write data/contributions.json.

No GitHub token and no GraphQL API: github.com/users/<user>/contributions is
the same public HTML fragment the profile page itself renders.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

USERNAME = os.environ.get("GITHUB_USERNAME", "shashidharbabu")
URL = f"https://github.com/users/{USERNAME}/contributions"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "contributions.json"

HEADERS = {
    # GitHub serves a stripped page to unknown agents; look like a browser.
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "X-Requested-With": "XMLHttpRequest",
}

# "12 contributions on August 17th." / "No contributions on August 17th."
COUNT_RE = re.compile(r"^\s*(No|[\d,]+)\s+contribution", re.IGNORECASE)


def fetch_html(url: str, attempts: int = 3) -> str:
    last = None
    for i in range(attempts):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:  # noqa: BLE001 - retry on any transport error
            last = exc
            print(f"  attempt {i + 1}/{attempts} failed: {exc}", file=sys.stderr)
    raise SystemExit(f"could not fetch {url}: {last}")


def parse_days(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")

    # Counts live in sibling <tool-tip for="<td id>"> nodes, not on the td.
    tips: dict[str, int] = {}
    for tip in soup.find_all("tool-tip"):
        target = tip.get("for")
        if not target:
            continue
        m = COUNT_RE.match(tip.get_text(" ", strip=True))
        if not m:
            continue
        raw = m.group(1)
        tips[target] = 0 if raw.lower() == "no" else int(raw.replace(",", ""))

    days: dict[str, dict] = {}
    for td in soup.select("td.ContributionCalendar-day"):
        iso = td.get("data-date")
        if not iso:
            continue
        # data-count exists on some renders; tool-tip is the reliable source.
        count = td.get("data-count")
        count = int(count) if count and count.isdigit() else tips.get(td.get("id", ""), 0)
        days[iso] = {
            "date": iso,
            "count": count,
            "level": int(td.get("data-level") or 0),
        }

    if not days:
        raise SystemExit(
            "parsed 0 day cells - GitHub markup changed or the profile is private"
        )
    return [days[k] for k in sorted(days)]


def compute_stats(days: list[dict]) -> dict:
    counts = {d["date"]: d["count"] for d in days}
    total = sum(counts.values())
    active = [d for d in days if d["count"] > 0]

    # Longest streak over the whole window.
    longest = run = 0
    longest_end = None
    prev: date | None = None
    for d in days:
        cur = date.fromisoformat(d["date"])
        if d["count"] > 0 and prev is not None and cur - prev == timedelta(days=1):
            run += 1
        elif d["count"] > 0:
            run = 1
        else:
            run = 0
        if run > longest:
            longest, longest_end = run, cur
        prev = cur

    # Current streak: walk backwards. Today being empty doesn't break it yet,
    # since the day isn't over - that matches how GitHub presents it.
    ordered = list(reversed(days))
    idx = 0
    if ordered and ordered[0]["count"] == 0:
        idx = 1
    current = 0
    for d in ordered[idx:]:
        if d["count"] == 0:
            break
        current += 1

    best = max(days, key=lambda d: d["count"])

    monthly: "OrderedDict[str, int]" = OrderedDict()
    for d in days:
        monthly[d["date"][:7]] = monthly.get(d["date"][:7], 0) + d["count"]

    return {
        "total": total,
        "active_days": len(active),
        "max_count": best["count"],
        "best_day": {"date": best["date"], "count": best["count"]},
        "current_streak": current,
        "longest_streak": longest,
        "longest_streak_end": longest_end.isoformat() if longest_end else None,
        "daily_average": round(total / len(days), 2) if days else 0,
        "monthly": monthly,
    }


def main() -> None:
    print(f"fetching {URL}")
    days = parse_days(fetch_html(URL))
    stats = compute_stats(days)

    payload = {
        "username": USERNAME,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "range": {"start": days[0]["date"], "end": days[-1]["date"]},
        "stats": stats,
        "days": days,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {OUT.relative_to(ROOT)}")
    print(
        f"  {len(days)} days | {stats['total']:,} contributions | "
        f"streak {stats['current_streak']}d (best {stats['longest_streak']}d) | "
        f"peak {stats['max_count']} on {stats['best_day']['date']}"
    )


if __name__ == "__main__":
    main()
