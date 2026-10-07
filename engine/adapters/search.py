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


GREECE_QUERIES = [
    '"Θεσσαλονίκη" (γραμματεία OR "διοικητική υποστήριξη" OR "βοηθός έργου") -site:facebook.com -site:instagram.com -site:youtube.com',
    '"Thessaloniki" ("project assistant" OR "administrative assistant" OR "office administrator") (vacancy OR hiring) -site:facebook.com -site:instagram.com -site:linkedin.com',
    'site:skywalker.gr Θεσσαλονίκη (assistant OR coordinator OR γραμματεία OR διοικητικ)',
    'site:kariera.gr Θεσσαλονίκη (assistant OR coordinator OR γραμματεία OR operations)',
    '"Θεσσαλονίκη" "πρόσκληση εκδήλωσης ενδιαφέροντος" (διοικητικ OR έργου OR γραμματεία) 2026 -site:facebook.com',
]


def enabled() -> bool:
    return bool(os.environ.get("SERPER_API_KEY") or os.environ.get("BRAVE_API_KEY"))


def serper(limit_queries: int = 2, offset: int = 0) -> List[Dict]:
    """Google results via Serper. Each query costs one credit, so callers stay at a couple per half day."""
    key = os.environ.get("SERPER_API_KEY")
    if not key:
        return []
    leads = []
    chosen = GREECE_QUERIES[offset % len(GREECE_QUERIES):] + GREECE_QUERIES[: offset % len(GREECE_QUERIES)]
    for query in chosen[:limit_queries]:
        data = http.post_json(
            "https://google.serper.dev/search",
            {"q": query, "gl": "gr", "hl": "el", "num": 8, "tbs": "qdr:m"},
            headers={"X-API-KEY": key}, check_robots=False,
        )
        for result in data.get("organic") or []:
            leads.append({"url": result.get("link"), "title": result.get("title"), "query": query, "snippet": result.get("snippet", "")})
    return leads


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
