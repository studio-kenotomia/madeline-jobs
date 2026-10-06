"""Commands that arrive as GitHub issues from the phone or the Mac dashboard."""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Dict, List

STATUSES = {"saved", "prepared", "submitted", "interview", "offer", "rejected", "withdrawn", "skipped", "none"}
FEEDBACK = {"more", "less", "too_customer", "too_sales", "too_senior", "greek_too_strong", "remote_bad", "great_company", "great_work", "pay_low", "other"}
FACTS = {"role2_end", "travel_weeks", "us_night_hours", "r1_tech_claims", "salary_floor_eur_month", "notice_period", "start_date"}


def _api(path: str, method: str = "GET", payload=None):
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return None
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{path}", method=method, data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "madeline-job-radar", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode()
        return json.loads(body) if body else {}


def pending() -> List[Dict]:
    try:
        issues = _api("/issues?state=open&per_page=50") or []
    except Exception:
        return []
    owner = (os.environ.get("GITHUB_REPOSITORY") or "/").split("/")[0].lower()
    commands = []
    for issue in issues:
        if issue.get("pull_request"):
            continue
        login = ((issue.get("user") or {}).get("login") or "").lower()
        if login != owner and issue.get("author_association") not in ("OWNER",):
            continue
        commands.append({"number": issue["number"], "title": (issue.get("title") or "").strip(), "body": issue.get("body") or ""})
    return commands


def close(number: int, note: str) -> None:
    try:
        _api(f"/issues/{number}/comments", "POST", {"body": note})
        _api(f"/issues/{number}", "PATCH", {"state": "closed"})
    except Exception:
        pass


def apply(state: Dict, command: Dict) -> str:
    title = command["title"]
    parts = title.split()
    if not parts:
        return "Empty command."
    verb = parts[0].lower()
    if verb == "status" and len(parts) >= 3 and parts[2] in STATUSES:
        job = state["jobs"].get(parts[1])
        if not job:
            return f"No job {parts[1]}."
        job["application_status"] = parts[2]
        job.setdefault("status_history", []).append({"status": parts[2], "at": command.get("at")})
        if parts[2] == "submitted":
            job["frozen"] = {"at": command.get("at"), "cv_model": job.get("cv_model"), "cover_model": job.get("cover_model"), "job_snapshot": {k: job.get(k) for k in ("title", "company", "location_raw", "canonical_url", "description_text", "content_hash")}}
            job["doc_status"] = "frozen_submitted_version"
        if parts[2] in ("saved", "prepared", "submitted", "interview", "offer"):
            state.setdefault("learned", {}).setdefault("liked_families", {})
            family = (job.get("analysis") or {}).get("family")
            if family:
                state["learned"]["liked_families"][family] = state["learned"]["liked_families"].get(family, 0) + 1
        return f"{job['title']} marked {parts[2]}."
    if verb == "feedback" and len(parts) >= 3 and parts[2] in FEEDBACK:
        job = state["jobs"].get(parts[1])
        state.setdefault("feedback", []).append({"id": parts[1], "reason": parts[2], "at": command.get("at"), "family": ((job or {}).get("analysis") or {}).get("family"), "company": (job or {}).get("company")})
        return f"Feedback {parts[2]} saved."
    if verb == "facts" and len(parts) >= 2 and "=" in parts[1]:
        key, _, value = parts[1].partition("=")
        if key in FACTS:
            state.setdefault("confirmations", {})[key] = value
            return f"{key} set to {value}."
        return f"Unknown fact {key}."
    if verb == "prepare" and len(parts) >= 2:
        state.setdefault("queue", [])
        if not any(item["id"] == parts[1] for item in state["queue"]):
            state["queue"].append({"id": parts[1], "action": "prepare", "at": command.get("at")})
        return "Queued for the Mac apply bridge."
    if verb == "import" and len(parts) >= 2 and re.match(r"https?://", parts[1]):
        state.setdefault("imports", []).append({"url": parts[1], "at": command.get("at")})
        return "URL queued for import."
    return "Command not recognised."


def soft_weights(state: Dict) -> Dict:
    weights: Dict[str, float] = {}
    for item in state.get("feedback", [])[-200:]:
        family, company = item.get("family"), (item.get("company") or "").lower()
        delta = {"more": 2, "great_work": 2, "great_company": 1.5, "less": -2, "too_customer": -2, "too_sales": -2, "too_senior": -1.5, "greek_too_strong": -1, "remote_bad": -1}.get(item["reason"], 0)
        if family:
            weights[f"family:{family}"] = weights.get(f"family:{family}", 0) + delta * 0.5
        if company and item["reason"] in ("great_company", "less"):
            weights[f"company:{company}"] = weights.get(f"company:{company}", 0) + delta
    for family, count in (state.get("learned", {}).get("liked_families") or {}).items():
        weights[f"family:{family}"] = weights.get(f"family:{family}", 0) + min(3.0, count * 0.5)
    return {k: max(-8.0, min(8.0, v)) for k, v in weights.items()}
