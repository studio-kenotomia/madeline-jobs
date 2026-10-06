"""Hiring-probability signals for companies with no confirmed opening."""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import Dict, List

from .. import http


def eu_projects(organisation_terms: List[str]) -> Dict[str, List[Dict]]:
    """EU Funding & Tenders search: recent calls and projects naming Thessaloniki organisations."""
    signals: Dict[str, List[Dict]] = {}
    for term in organisation_terms:
        url = "https://api.tech.ec.europa.eu/search-api/prod/rest/search?" + urllib.parse.urlencode(
            {"apiKey": "SEDIA", "text": f'"{term}"', "pageSize": 10, "pageNumber": 1}
        )
        data = http.fetch(url, data=b"", method="POST", check_robots=False)[2].decode("utf-8", "replace")
        try:
            results = json.loads(data).get("results") or []
        except ValueError:
            results = []
        hits = []
        for item in results[:10]:
            meta = item.get("metadata") or {}
            title = (meta.get("title") or [item.get("title") or ""])[0] if isinstance(meta.get("title"), list) else (item.get("title") or "")
            hits.append({"title": str(title)[:160], "url": item.get("url") or "", "date": (meta.get("startDate") or meta.get("deadlineDate") or [""])[0] if isinstance(meta.get("startDate") or meta.get("deadlineDate"), list) else ""})
        if hits:
            signals[term] = hits
    return signals


def page_fingerprint(url: str) -> str:
    import hashlib
    page = http.text(url)
    body = re.sub(r"(?is)<(script|style).*?</\1>", "", page)
    body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))
    return hashlib.sha256(body.encode()).hexdigest()[:16]
