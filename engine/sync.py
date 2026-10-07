"""Swipes and settings from the job-radar edge function, applied to the cloud state."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Dict, List

ENDPOINT = os.environ.get("RADAR_SYNC_URL", "https://sekrgfspurktfnryfaif.supabase.co/functions/v1/job-radar")
STATUS = {"like": "saved", "superlike": "saved", "pass": "skipped", "applied": "submitted", "interview": "interview", "offer": "offer", "rejected": "rejected", "withdrawn": "withdrawn"}


def token() -> str:
    return os.environ.get("RADAR_SYNC_TOKEN", "")


def pull() -> Dict:
    if not token():
        return {}
    request = urllib.request.Request(ENDPOINT, headers={"x-radar-token": token(), "User-Agent": "job-radar-cycle"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode())


def apply(state: Dict, remote: Dict) -> Dict[str, int]:
    counts = {"swipes": 0, "facts": 0, "feedback": 0, "imports": 0, "prepare": 0}
    if not remote:
        return counts
    seen = {}
    for swipe in remote.get("swipes", []):
        seen[swipe["job_id"]] = swipe
        job = state["jobs"].get(swipe["job_id"])
        if not job:
            continue
        status = STATUS.get(swipe["decision"], "none")
        if job.get("application_status") != status:
            job["application_status"] = status
            job.setdefault("status_history", []).append({"status": status, "at": swipe["at"], "via": "swipe"})
            if status == "submitted" and not job.get("frozen"):
                job["frozen"] = {"at": swipe["at"], "cv_model": job.get("cv_model"), "cover_model": job.get("cover_model")}
                job["doc_status"] = "frozen_submitted_version"
            counts["swipes"] += 1
        job["swipe"] = swipe["decision"]
        job["superlike"] = swipe["decision"] == "superlike"
    for job_id, job in state["jobs"].items():
        if job.get("swipe") and job_id not in seen:
            job.pop("swipe", None)
            if job.get("application_status") in ("saved", "skipped") and not job.get("status_history", [{}])[-1].get("via") == "issue":
                job["application_status"] = "none"
    for fact in remote.get("facts", []):
        if state.setdefault("confirmations", {}).get(fact["key"]) != fact["value"]:
            state["confirmations"][fact["key"]] = fact["value"]
            counts["facts"] += 1
    known_events = set(state.setdefault("synced_events", []))
    for event in remote.get("events", []):
        marker = f"{event['kind']}|{event.get('job_id')}|{event['at']}"
        if marker in known_events:
            continue
        known_events.add(marker)
        payload = event.get("payload") or {}
        if event["kind"] == "feedback" and payload.get("reason"):
            job = state["jobs"].get(event.get("job_id") or "") or {}
            state.setdefault("feedback", []).append({"id": event.get("job_id"), "reason": payload["reason"], "at": event["at"], "family": (job.get("analysis") or {}).get("family"), "company": job.get("company")})
            counts["feedback"] += 1
        elif event["kind"] == "import" and payload.get("url"):
            state.setdefault("imports", []).append({"url": payload["url"], "at": event["at"]})
            counts["imports"] += 1
        elif event["kind"] == "prepare" and event.get("job_id"):
            state.setdefault("queue", [])
            if not any(item["id"] == event["job_id"] for item in state["queue"]):
                state["queue"].append({"id": event["job_id"], "action": "prepare", "at": event["at"]})
            counts["prepare"] += 1
    state["synced_events"] = sorted(known_events)[-2000:]
    passes = [s for s in remote.get("swipes", []) if s["decision"] == "pass"]
    likes = [s for s in remote.get("swipes", []) if s["decision"] in ("like", "superlike", "applied")]
    families: Dict[str, float] = {}
    for swipe in passes:
        family = ((state["jobs"].get(swipe["job_id"]) or {}).get("analysis") or {}).get("family")
        if family:
            families[family] = families.get(family, 0) - 0.3
    for swipe in likes:
        family = ((state["jobs"].get(swipe["job_id"]) or {}).get("analysis") or {}).get("family")
        if family:
            families[family] = families.get(family, 0) + 0.6
    state.setdefault("learned", {})["swipe_families"] = families
    return counts
