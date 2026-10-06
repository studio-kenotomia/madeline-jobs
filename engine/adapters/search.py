"""Optional web-search discovery. Search results are leads, never confirmed openings."""

from __future__ import annotations

import os
import urllib.parse
from typing import Dict, List

from .. import http

QUERIES = [
    '"Thessaloniki" "project assistant"', '"Thessaloniki" "programme assistant"', '"Thessaloniki" "administrative coordinator"',
    '"Thessaloniki" "operations coordinator" English', '"Thessaloniki" "environmental project" careers', '"Thessaloniki" "research assistant" project',
    '"Θεσσαλονίκη" "διοικητική υποστήριξη" Αγγλικά', '"Θεσσαλονίκη" "βοηθός έργου"', '"Θεσσαλονίκη" "ευρωπαϊκά προγράμματα" θέση',
    '"Θεσσαλονίκη" "ερευνητικό έργο" θέση εργασίας', '"remote Europe" Dutch immigration coordinator', '"remote EMEA" executive assistant',
    '"remote" "Greece" "project coordinator" sustainability', 'site:boards.greenhouse.io Thessaloniki', 'site:jobs.lever.co Thessaloniki',
    'site:jobs.ashbyhq.com Greece remote operations', 'site:apply.workable.com Thessaloniki assistant',
]


def enabled() -> bool:
    return bool(os.environ.get("BRAVE_API_KEY"))


def brave(limit_queries: int = 6, offset: int = 0) -> List[Dict]:
    key = os.environ.get("BRAVE_API_KEY")
    if not key:
        return []
    leads = []
    chosen = QUERIES[offset % len(QUERIES):] + QUERIES[: offset % len(QUERIES)]
    for query in chosen[:limit_queries]:
        url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode({"q": query, "count": 10, "freshness": "pw"})
        data = http.get_json(url, headers={"X-Subscription-Token": key, "Accept": "application/json"}, check_robots=False)
        for result in (data.get("web") or {}).get("results") or []:
            leads.append({"url": result.get("url"), "title": result.get("title"), "query": query, "snippet": result.get("description", "")})
    return leads
