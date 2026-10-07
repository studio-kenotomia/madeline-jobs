"""Revisit the listings that matter and report removed, filled or changed postings."""

from __future__ import annotations

import re
import urllib.error
from datetime import datetime, timedelta
from typing import Dict, List

from . import http

CLOSED_TEXT = [
    r"no longer (available|accepting|active|open)", r"(position|role|vacancy|job) (has been |is )?(filled|closed|expired)", r"job (has )?expired",
    r"this (job|posting|listing|vacancy) (is )?(closed|no longer)", r"applications? (are |is )?(now )?closed", r"we('re| are) no longer accepting",
    r"the job you are looking for", r"page not found", r"δεν είναι πλέον διαθέσιμη", r"η αγγελία (έχει )?λήξει", r"έχει λήξει",
]


def targets(state: Dict, limit: int = 40) -> List[Dict]:
    chosen = [j for j in state["jobs"].values() if j.get("swipe") in ("like", "superlike", "applied") or j.get("application_status") in ("saved", "prepared", "submitted", "interview")]
    ranked = sorted([j for j in state["jobs"].values() if j.get("open_status") != "closed" and (j.get("analysis") or {}).get("tier") in ("exceptional", "apply", "worth")],
                    key=lambda j: -(j.get("analysis") or {}).get("score", 0))
    for job in ranked:
        if job not in chosen:
            chosen.append(job)
    return chosen[:limit]


def check(state: Dict, now: datetime, limit: int = 40) -> Dict[str, int]:
    stats = {"checked": 0, "removed": 0, "ok": 0}
    for job in targets(state, limit):
        last = job.get("rechecked_at")
        if last and now - datetime.fromisoformat(last) < timedelta(hours=8):
            continue
        url = job.get("canonical_url") or ""
        if not url.startswith("http") or "#" in url.split("/")[-1]:
            continue
        stats["checked"] += 1
        job["rechecked_at"] = now.isoformat()
        try:
            status, _, blob = http.fetch(url, timeout=20, retries=1)
            page = blob.decode("utf-8", "replace")
        except http.Blocked:
            continue
        except urllib.error.HTTPError as error:
            if error.code in (404, 410):
                _close(job, now, "Listing removed by the employer (the page now returns not found).")
                stats["removed"] += 1
            continue
        except Exception:
            continue
        body = re.sub(r"(?is)<(script|style).*?</\1>", " ", page)
        body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).lower()[:20000]
        head = body[:6000]
        hit = next((p for p in CLOSED_TEXT if re.search(p, head)), None)
        title_present = (job.get("title") or "").lower()[:40] in body
        strong = re.search(r"no longer accepting|position (has been )?filled|job (has )?expired|applications? (are |is )?(now )?closed|η αγγελία (έχει )?λήξει", head)
        if hit and (not title_present or strong):
            _close(job, now, "The listing says it is closed or filled.")
            stats["removed"] += 1
        else:
            stats["ok"] += 1
            job["confirmed_open_at"] = now.isoformat()
    return stats


def _close(job: Dict, now: datetime, reason: str) -> None:
    if job.get("open_status") != "closed":
        job["open_status"] = "closed"
        job["closed_at"] = now.isoformat()
        job["closed_reason"] = reason
