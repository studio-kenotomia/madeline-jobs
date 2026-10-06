"""One discovery cycle: due sources, merge, close, rank, radar, documents, alerts, site."""

from __future__ import annotations

import concurrent.futures as futures
import json
import os
import re
import time
import traceback
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from . import crypto, documents, evidence, http, inbox, model, notify, rank, registry
from .adapters import ats, greek, pages, radar as radar_signals, search

ROOT = Path(__file__).resolve().parent.parent
SOURCE_RANK = {"ats": 4, "page": 3, "public_registry": 3, "jsonld": 3, "board": 2, "manual": 4}
VISIBLE = ("exceptional", "apply", "worth", "verify")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def empty_state() -> Dict:
    return {"version": 2, "jobs": {}, "fingerprints": {}, "seen_detail": {}, "sources": {}, "runs": [], "alerts": {}, "digests": [],
            "companies": {}, "radar": [], "feedback": [], "learned": {}, "queue": [], "confirmations": {}, "imports": [], "rejected_examples": []}


def load_state(path: Path, key: str) -> Dict:
    if path.exists() and key:
        try:
            state = crypto.decrypt_json(key, path.read_text())
            for name, value in empty_state().items():
                state.setdefault(name, value)
            return state
        except Exception:
            traceback.print_exc()
            raise SystemExit("State exists but cannot be decrypted. Refusing to overwrite it.")
    return empty_state()


def save_state(path: Path, key: str, state: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(crypto.encrypt_json(key, state))
    tmp.replace(path)


def migrate_sqlite(state: Dict, db_path: Path) -> int:
    """Carry statuses from the first prototype so applied/saved/skipped history survives."""
    if not db_path.exists() or state.get("migrated_sqlite"):
        return 0
    import sqlite3
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    moved = 0
    for row in connection.execute("SELECT * FROM jobs"):
        job = model.make_job(source=row["source"] or "legacy", source_type="board", title=row["title"] or "", company=row["company"] or "", url=row["url"] or "",
                             location=row["location"] or "", description_text=row["description"] or "")
        status = {"applied": "submitted", "saved": "saved", "skipped": "skipped"}.get(row["status"], "none")
        state["legacy_status"] = state.get("legacy_status", {})
        state["legacy_status"][model.fingerprint(job)] = status
        moved += 1
    connection.close()
    state["migrated_sqlite"] = True
    return moved


def due_sources(state: Dict, now: datetime, only: Optional[List[str]] = None, force: bool = False) -> List[Dict]:
    chosen = []
    for source in registry.build():
        if only and source["id"] not in only:
            continue
        health = state["sources"].get(source["id"], {})
        last = health.get("last_attempt")
        failures = health.get("consecutive_failures", 0)
        interval = source["interval"] * (2 ** min(failures, 4))
        if force or not last or now - datetime.fromisoformat(last) >= timedelta(minutes=interval - 2):
            chosen.append(source)
    return chosen


def run_sources(state: Dict, sources: List[Dict], now: datetime) -> Dict[str, Dict]:
    results: Dict[str, Dict] = {}

    def work(source):
        started = time.time()
        context = {"known": set(state["seen_detail"].get(source["id"], []))}
        try:
            jobs = source["fn"](context)
            return source, jobs, None, time.time() - started
        except Exception as error:
            return source, [], f"{type(error).__name__}: {str(error)[:200]}", time.time() - started

    with futures.ThreadPoolExecutor(max_workers=10) as pool:
        for source, jobs, error, duration in pool.map(work, sources):
            health = state["sources"].setdefault(source["id"], {"label": source["label"], "history": []})
            health.update({"label": source["label"], "kind": source["kind"], "interval": source["interval"], "note": source.get("note", ""), "last_attempt": now.isoformat(), "duration": round(duration, 1)})
            if error:
                health["consecutive_failures"] = health.get("consecutive_failures", 0) + 1
                health["status"] = "failing" if health["consecutive_failures"] >= 3 else "degraded"
                health["error"] = error
            else:
                previous = [h for h in health.get("history", []) if h > 0]
                health.update({"last_success": now.isoformat(), "consecutive_failures": 0, "status": "healthy", "error": "", "items": len(jobs)})
                health["history"] = (health.get("history", []) + [len(jobs)])[-12:]
                missing = [j for j in jobs if not j.get("title") or not j.get("canonical_url")]
                if jobs and len(missing) > len(jobs) * 0.3:
                    health["status"] = "degraded"
                    health["warning"] = f"{len(missing)} of {len(jobs)} items have no title or link. The page layout may have changed."
                elif not jobs and previous and sum(previous) / len(previous) >= 2:
                    health["status"] = "degraded"
                    health["warning"] = "Returned nothing, though it normally has listings. Check whether the site changed."
                else:
                    health["warning"] = ""
                if source["id"] in ("kariera", "euraxess"):
                    seen = state["seen_detail"].setdefault(source["id"], [])
                    for job in jobs:
                        board_id = str(job.get("extra", {}).get("board_id") or job.get("source_job_id") or "")
                        if board_id and board_id not in seen:
                            seen.append(board_id)
                    state["seen_detail"][source["id"]] = seen[-4000:]
            health["next_run"] = (now + timedelta(minutes=source["interval"] * (2 ** min(health.get("consecutive_failures", 0), 4)))).isoformat()
            results[source["id"]] = {"jobs": jobs, "error": error}
    return results


def merge(state: Dict, results: Dict[str, Dict], now: datetime, rejections: Counter) -> List[str]:
    new_ids: List[str] = []
    weights = inbox.soft_weights(state)
    for source_id, result in results.items():
        if result["error"]:
            continue
        present = set()
        for job in result["jobs"]:
            if not job.get("title") or job["title"] == "(outside Greece)":
                rejections["geography"] += 1
                continue
            analysis = rank.evaluate(job, first_seen=now.isoformat(), soft_weights=weights)
            if analysis["rejection"]:
                rejections[analysis["rejection"]] += 1
                state["rejected_examples"] = (state["rejected_examples"] + [{"title": job["title"][:120], "company": job["company"][:60], "source": source_id, "reason": analysis["rejection"], "url": job["canonical_url"], "at": now.isoformat()}])[-400:]
                continue
            fp = model.fingerprint(job)
            target_id = job["id"] if job["id"] in state["jobs"] else state["fingerprints"].get(fp, job["id"])
            existing = state["jobs"].get(target_id)
            present.add(target_id)
            if existing:
                if job["canonical_url"] not in existing.get("secondary_sources", []) and job["canonical_url"] != existing["canonical_url"]:
                    if SOURCE_RANK.get(job["source_type"], 1) > SOURCE_RANK.get(existing["source_type"], 1):
                        existing.setdefault("secondary_sources", []).append(existing["canonical_url"])
                        for field in ("canonical_url", "application_url", "source", "source_type", "description_text", "description_html", "location_raw", "date_posted", "valid_through", "salary", "work_mode", "remote_regions", "extra"):
                            if job.get(field):
                                existing[field] = job[field]
                        existing.setdefault("discovery", {})["direct_seen_at"] = now.isoformat()
                    else:
                        existing.setdefault("secondary_sources", []).append(job["canonical_url"])
                if job["source"] == existing["source"] and job["content_hash"] != existing.get("content_hash"):
                    existing.setdefault("versions", []).append({"at": now.isoformat(), "hash": existing.get("content_hash"), "title": existing.get("title"), "location": existing.get("location_raw"), "valid_through": existing.get("valid_through")})
                    existing["versions"] = existing["versions"][-10:]
                    for field in ("title", "description_text", "description_html", "location_raw", "valid_through", "salary", "remote_regions", "work_mode"):
                        existing[field] = job[field]
                    existing["content_hash"] = job["content_hash"]
                    existing["last_changed"] = now.isoformat()
                    existing.setdefault("badges_extra", []).append("Description changed")
                if existing.get("open_status") == "closed":
                    existing["open_status"] = "open"
                    existing.setdefault("badges_extra", []).append("Reopened")
                existing["last_seen"] = now.isoformat()
                existing["missing_runs"] = 0
                existing.setdefault("sources_seen", [])
                if source_id not in existing["sources_seen"]:
                    existing["sources_seen"].append(source_id)
            else:
                record = dict(job)
                record.update({"first_seen": now.isoformat(), "last_seen": now.isoformat(), "last_changed": now.isoformat(), "open_status": "open", "missing_runs": 0,
                               "application_status": state.get("legacy_status", {}).get(fp, "none"), "doc_status": "not_generated", "sources_seen": [source_id], "versions": [], "secondary_sources": []})
                state["jobs"][record["id"]] = record
                state["fingerprints"][fp] = record["id"]
                new_ids.append(record["id"])
                present.add(record["id"])
        for job_id, job in state["jobs"].items():
            if job_id in present or job.get("open_status") == "closed":
                continue
            if source_id in job.get("sources_seen", [job.get("source")]) and len(job.get("sources_seen", [])) <= 1:
                job["missing_runs"] = job.get("missing_runs", 0) + 1
                if job["missing_runs"] >= 2:
                    job["open_status"] = "closed"
                    job["closed_at"] = now.isoformat()
                    job["closed_reason"] = "No longer listed by its source."
    return new_ids


def expire(state: Dict, now: datetime) -> None:
    today = now.date().isoformat()
    for job in state["jobs"].values():
        if job.get("open_status") != "closed" and job.get("valid_through") and job["valid_through"] < today:
            job["open_status"] = "closed"
            job["closed_at"] = now.isoformat()
            job["closed_reason"] = "Deadline passed."
        if job.get("open_status") == "open":
            last_seen = datetime.fromisoformat(job["last_seen"])
            if now - last_seen > timedelta(days=4):
                job["open_status"] = "stale"
    cutoff = (now - timedelta(days=75)).isoformat()
    for job_id in [k for k, v in state["jobs"].items() if v.get("open_status") == "closed" and v.get("closed_at", "") < cutoff and v.get("application_status") in ("none", "skipped")]:
        state["jobs"].pop(job_id, None)


def rerank(state: Dict, now: datetime) -> None:
    weights = inbox.soft_weights(state)
    for job in state["jobs"].values():
        analysis = rank.evaluate(job, first_seen=job.get("first_seen", ""), soft_weights=weights)
        if analysis.get("rejection"):
            analysis.update({"tier": "archive", "score": 0, "reasons": [], "gaps": [f"Now rejected: {analysis['rejection']}"], "blockers": [], "unknowns": []})
        if job.get("open_status") == "stale" and analysis.get("tier") in VISIBLE:
            analysis.setdefault("unknowns", []).insert(0, "Not reconfirmed by its source for a few days.")
            analysis["score"] = max(0, analysis["score"] - 8)
        job["analysis"] = {k: v for k, v in analysis.items()}
        job["analysis"]["badges"] = analysis.get("freshness", {}).get("badges", []) + job.get("badges_extra", [])[-2:]


def update_companies(state: Dict, now: datetime, run_radar: bool) -> None:
    graph = state["companies"]
    for seed in registry.companies():
        node = graph.setdefault(seed["name"], {"name": seed["name"], "history": [], "signals": {}})
        node.update({k: seed.get(k) for k in ("domain", "ats", "token", "tags", "thessaloniki", "speculative_cv", "note", "remote_policy") if seed.get(k) is not None})
        node.setdefault("origins", ["seed list"])
    for job in state["jobs"].values():
        name = job.get("company") or ""
        if not name:
            continue
        node = graph.setdefault(name, {"name": name, "history": [], "signals": {}, "origins": [job.get("source", "")]})
        if job.get("extra", {}).get("company_website") and not node.get("domain"):
            node["domain"] = re.sub(r"^https?://(www\.)?|/.*$", "", job["extra"]["company_website"])
        a = job.get("analysis") or {}
        if job["id"] not in [h["id"] for h in node["history"]]:
            node["history"].append({"id": job["id"], "title": job["title"][:100], "first_seen": job["first_seen"], "tier": a.get("tier"), "family": a.get("family")})
            node["history"] = node["history"][-40:]
        if rank.geography(job).get("thessaloniki"):
            node["thessaloniki"] = True
    if run_radar:
        try:
            employers = greek.dypa_career_day_employers()
            for employer in employers:
                office = [r for r in employer["roles"] if re.search(r"διοικητ|γραφείου|γραμματ|project|υπάλληλ|hr|ανθρώπινου|περιβάλλ|marketing|λογιστ", r, re.I)]
                node = graph.setdefault(employer["name"], {"name": employer["name"], "history": [], "signals": {}, "origins": []})
                node["thessaloniki"] = True
                if "DYPA Thessaloniki Career Day, Sept 2026" not in node.setdefault("origins", []):
                    node["origins"].append("DYPA Thessaloniki Career Day, Sept 2026")
                node["signals"]["dypa_career_day"] = {"at": now.isoformat(), "office_roles": office[:6], "all_roles": employer["roles"][:12]}
            state["radar_meta"] = {"dypa_employers": len(employers), "at": now.isoformat()}
        except Exception as error:
            state.setdefault("radar_meta", {})["dypa_error"] = str(error)[:200]
        try:
            terms = [n["name"] for n in graph.values() if n.get("thessaloniki") and any(t in (n.get("tags") or []) for t in ("environment", "eu_projects", "research"))][:8]
            for term, hits in radar_signals.eu_projects(terms).items():
                graph[term]["signals"]["eu_funding"] = {"at": now.isoformat(), "hits": hits[:5]}
        except Exception as error:
            state.setdefault("radar_meta", {})["eu_error"] = str(error)[:200]
        checked = 0
        for node in graph.values():
            domain = node.get("domain")
            if checked >= 15 or not domain or not node.get("thessaloniki") or node.get("ats_checked"):
                continue
            if node.get("ats") in (None, "board", "workable-search"):
                checked += 1
                try:
                    found = ats.detect(domain)
                    node["ats_detected"] = found
                except Exception:
                    node["ats_detected"] = []
                node["ats_checked"] = now.isoformat()
    for node in graph.values():
        relevant_history = [h for h in node.get("history", []) if h.get("tier") in ("exceptional", "apply", "worth", "stretch", "verify")]
        signals = []
        if node.get("speculative_cv"):
            signals.append("The company explicitly accepts speculative CVs.")
        if node.get("thessaloniki"):
            signals.append("Has a Thessaloniki presence.")
        if any(t in (node.get("tags") or []) for t in ("environment", "eu_projects", "mobility", "english_first", "research", "international_school")):
            signals.append("Works in a domain that fits her degrees or casework.")
        if len(relevant_history) >= 2:
            signals.append(f"Has posted {len(relevant_history)} relevant roles while watched.")
        dypa = node.get("signals", {}).get("dypa_career_day")
        if dypa and dypa.get("office_roles"):
            signals.append("Recruited for office roles at DYPA's Thessaloniki Career Day: " + ", ".join(dypa["office_roles"][:3]).lower() + ".")
        if node.get("signals", {}).get("eu_funding"):
            signals.append("Appears in recent EU funding or tender records.")
        node["radar_signals"] = signals
        open_relevant = [j for j in state["jobs"].values() if j.get("company") == node["name"] and j.get("open_status") == "open" and (j.get("analysis") or {}).get("tier") in VISIBLE]
        node["has_open_match"] = bool(open_relevant)
        strength = len(signals) + (2 if node.get("speculative_cv") else 0)
        node["radar_score"] = strength
    candidates = [n for n in graph.values() if not n["has_open_match"] and (len(n["radar_signals"]) >= 3 or (n.get("speculative_cv") and len(n["radar_signals"]) >= 2))]
    candidates.sort(key=lambda n: -n["radar_score"])
    state["radar"] = [{
        "company": n["name"], "domain": n.get("domain", ""), "label": "No confirmed opening", "why": " ".join(n["radar_signals"][:3]),
        "signals": n["radar_signals"], "angle": angle_for(n), "confidence": "medium-high" if n["radar_score"] >= 5 else "medium",
        "url": f"https://{n['domain']}" if n.get("domain") else "", "last_checked": now.isoformat(), "note": n.get("note", ""),
    } for n in candidates[:3]]


def angle_for(node: Dict) -> str:
    tags = node.get("tags") or []
    if "environment" in tags or "eu_projects" in tags:
        return "Junior project, documentation or grant-support operations, leading with the MSc and the casework. Not a scientist or experienced grant writer."
    if "international_school" in tags or "university" in tags:
        return "Administrative officer, admissions or student services, in English."
    if "mobility" in tags:
        return "Immigration or relocation coordination, leading with real Dutch IND casework."
    return "Office or operations coordination in English."


def build_documents(state: Dict, now: datetime) -> None:
    ranked = sorted([j for j in state["jobs"].values() if j.get("open_status") != "closed"], key=lambda j: -(j.get("analysis") or {}).get("score", 0))
    targets = [j for j in ranked if (j.get("analysis") or {}).get("tier") in VISIBLE][:12]
    targets += [j for j in state["jobs"].values() if j.get("application_status") in ("saved", "prepared") and j not in targets]
    for job in targets:
        if job.get("doc_status") == "frozen_submitted_version":
            continue
        analysis = job["analysis"]
        signature = f"{job.get('content_hash')}|{analysis.get('variant')}|{evidence.profile().get('version')}|{json.dumps(evidence.profile().get('preferences'), sort_keys=True)}"
        if job.get("doc_signature") == signature and job.get("cv_model"):
            continue
        cv = documents.cv_model(job, analysis)
        cover = documents.cover_model(job, analysis)
        job["cv_model"], job["cover_model"] = cv, cover
        job["cv_model_2"] = documents.cv_model(job, analysis, pages=2)
        job["lint"] = documents.lint_model(cv) + documents.lint_model(cover)
        job["doc_status"] = "draft" if not any(p["severity"] == "critical" for p in job["lint"]) else "needs_fix"
        job["doc_signature"] = signature
        job["doc_generated_at"] = now.isoformat()


def file_targets(state: Dict, limit: int = 8) -> List[Dict]:
    ranked = sorted([j for j in state["jobs"].values() if j.get("open_status") != "closed" and j.get("cv_model")], key=lambda j: -(j.get("analysis") or {}).get("score", 0))
    chosen = [j for j in ranked if (j.get("analysis") or {}).get("tier") in ("exceptional", "apply", "worth")][:limit]
    chosen += [j for j in state["jobs"].values() if j.get("cv_model") and j.get("application_status") in ("saved", "prepared", "submitted") and j not in chosen]
    return chosen


def render_files(job: Dict) -> Dict[str, Optional[bytes]]:
    source = job.get("frozen") or job
    cv, cover = source.get("cv_model"), source.get("cover_model")
    if not cv or not cover:
        return {}
    return {
        "cv_docx": documents.docx_bytes(cv),
        "cover_docx": documents.cover_docx_bytes(cover, job),
        "cv_pdf": documents.pdf_bytes(documents.cv_html(cv)),
        "cover_pdf": documents.pdf_bytes(documents.cover_html(cover, job)),
    }


def notify_cycle(state: Dict, now: datetime, new_ids: List[str], primary: bool) -> List[str]:
    log = []
    if not primary:
        return ["Not the primary scheduler, so no email was sent."]
    if not notify.configured():
        return ["RESEND_API_KEY is not set, so no email was sent."]
    if not notify.RECIPIENTS:
        notify.RECIPIENTS.extend(evidence.profile()["identity"].get("alert_to") or [evidence.profile()["identity"]["email"]])
    for job_id in new_ids:
        job = state["jobs"].get(job_id)
        if not job or (job.get("analysis") or {}).get("tier") != "exceptional":
            continue
        key = f"exceptional:{job_id}"
        if key in state["alerts"]:
            continue
        mail = notify.exceptional_email(job)
        result = notify.send(mail["subject"], mail["html"], mail["text"], idempotency_key=f"madeline-{key}")
        state["alerts"][key] = {"at": now.isoformat(), **result}
        log.append(f"Exceptional alert for {job['title']}: {result}")
    due = notify.due_digest(now, state["digests"])
    if due:
        last = max([d.get("sent_at", "") for d in state["digests"] if d.get("ok")] or [(now - timedelta(days=3)).isoformat()])
        mailed = {i for d in state["digests"] for i in d.get("ids", [])}
        fresh = [j for j in state["jobs"].values() if j.get("first_seen", "") > last and j["id"] not in mailed and j.get("open_status") != "closed" and (j.get("analysis") or {}).get("tier") in ("exceptional", "apply", "worth")]
        fresh.sort(key=lambda j: -j["analysis"]["score"])
        runs = [r for r in state["runs"] if r.get("at", "") > last]
        stats = {"raw": sum(r.get("raw", 0) for r in runs), "sources": len(state["sources"]), "rejections": sum((Counter(r.get("rejections", {})) for r in runs), Counter())}
        mailed_radar = {c for d in state["digests"] for c in d.get("radar", [])}
        radar_items = [r for r in state["radar"] if r["company"] not in mailed_radar][:3]
        mail = notify.digest_email(fresh[:3], radar_items, stats, last[:10])
        result = notify.send(mail["subject"], mail["html"], mail["text"], idempotency_key=f"madeline-digest-{due}")
        state["digests"].append({"due": due, "sent_at": now.isoformat(), "ids": [j["id"] for j in fresh[:3]], "radar": [r["company"] for r in radar_items], **result})
        log.append(f"Digest for {due}: {result}")
    return log


def process_imports(state: Dict, now: datetime, results: Dict[str, Dict]) -> None:
    pending = state.get("imports", [])
    state["imports"] = []
    jobs = []
    for item in pending[:10]:
        url = item["url"]
        if not http.public_url(url):
            continue
        try:
            page = http.text(url)
        except Exception:
            continue
        postings = model.jobpostings_from_html(page)
        if postings:
            job = model.job_from_jsonld(postings[0], source="manual", url=url)
        else:
            title = re.search(r"<title>(.*?)</title>", page, re.S)
            job = model.make_job(source="manual", source_type="manual", title=model.strip_html(title.group(1)) if title else url, company="", url=url, description_html=page)
        job["source_type"] = "manual"
        jobs.append(job)
    if jobs:
        results["manual-import"] = {"jobs": jobs, "error": None}


def site_payload(state: Dict, now: datetime, cycle: Dict) -> Dict:
    def card(job: Dict, full: bool) -> Dict:
        a = job.get("analysis") or {}
        out = {
            "id": job["id"], "title": job["title"], "company": job["company"], "location": job.get("location_raw"), "url": job.get("canonical_url"),
            "apply_url": job.get("application_url") or job.get("canonical_url"), "source": job.get("source"), "source_type": job.get("source_type"),
            "score": a.get("score"), "tier": a.get("tier"), "eligibility": a.get("eligibility"), "reasons": a.get("reasons", []), "gaps": a.get("gaps", []),
            "blockers": a.get("blockers", []), "unknowns": a.get("unknowns", []), "badges": a.get("badges", []), "urgency": a.get("urgency"),
            "greece_remote": (a.get("geo") or {}).get("greece_remote"), "remote_evidence": (a.get("geo") or {}).get("evidence"), "work_mode": (a.get("geo") or {}).get("work_mode"),
            "posted": job.get("date_posted"), "first_seen": job.get("first_seen"), "deadline": job.get("valid_through"), "salary": job.get("salary") or {},
            "ai_policy": a.get("ai_policy"), "ai_policy_evidence": a.get("ai_policy_evidence"), "status": job.get("application_status"), "open_status": job.get("open_status"),
            "doc_status": job.get("doc_status"), "family": a.get("family"), "language": job.get("language"), "secondary_sources": job.get("secondary_sources", [])[:4],
        }
        if full:
            out.update({
                "components": a.get("components"), "matrix": a.get("matrix", []), "greek_gist": a.get("greek_gist", []), "description": (job.get("description_text") or "")[:12000],
                "cv_model": job.get("cv_model"), "cv_model_2": job.get("cv_model_2"), "cover_model": job.get("cover_model"), "lint": job.get("lint", []), "frozen": bool(job.get("frozen")),
                "versions": job.get("versions", [])[-3:], "scam_signals": a.get("scam_signals", []), "has_files": job.get("rendered_files", []),
            })
        return out

    active = [j for j in state["jobs"].values() if j.get("open_status") != "closed" and j.get("application_status") not in ("skipped", "submitted", "rejected", "withdrawn")]
    active.sort(key=lambda j: (-(j.get("analysis") or {}).get("score", 0), j.get("first_seen", "")))
    tiers = {t: [j for j in active if (j.get("analysis") or {}).get("tier") == t] for t in ("exceptional", "apply", "worth", "verify", "stretch")}
    shown = tiers["exceptional"][:2] + tiers["apply"][:3] + tiers["worth"][:3] + tiers["verify"][:3] + tiers["stretch"][:12]
    tracked = [j for j in state["jobs"].values() if j.get("application_status") not in ("none", None)]
    full_ids = {j["id"] for j in shown + tracked}
    archive = [card(j, False) for j in sorted(state["jobs"].values(), key=lambda j: -(j.get("analysis") or {}).get("score", 0)) if j["id"] not in full_ids][:500]
    last_runs = state["runs"][-72:]
    day_ago = (now - timedelta(hours=24)).isoformat()
    day_runs = [r for r in state["runs"] if r.get("at", "") > day_ago]
    sources_view = []
    for source in registry.build():
        h = state["sources"].get(source["id"], {})
        sources_view.append({"id": source["id"], "label": source["label"], "kind": source["kind"], "status": h.get("status", "pending"), "last_success": h.get("last_success"),
                             "last_attempt": h.get("last_attempt"), "items": h.get("items"), "error": h.get("error"), "warning": h.get("warning"), "next_run": h.get("next_run"),
                             "interval": source["interval"], "note": source.get("note", ""), "duration": h.get("duration")})
    healthy = sum(1 for s in sources_view if s["status"] == "healthy")
    prefs = dict(evidence.profile()["preferences"])
    prefs.update(state.get("confirmations", {}))
    radar_view = []
    for item in state["radar"]:
        pseudo_job = {"title": "a junior project, documentation or administrative role", "company": item["company"], "description_text": item["angle"], "id": "radar"}
        family = "environment" if re.search(r"environment|grant|project", item["angle"], re.I) else "education_admin" if "student" in item["angle"] else "mobility" if "immigration" in item["angle"].lower() else "operations"
        pseudo = {"variant": family, "matrix": [], "geo": {"greece_remote": "onsite"}, "ai_policy": "unknown"}
        cover = documents.cover_model(pseudo_job, pseudo)
        cover["paragraphs"][0]["text"] = (
            f"I am writing to ask whether {item['company']} expects to need help with {item['angle'].split('.')[0].lower()}. "
            "I could not find a matching advertised vacancy, so I am sending this speculatively and will not follow up repeatedly."
        )
        radar_view.append({**item, "cv_model": documents.cv_model(pseudo_job, pseudo), "cover_model": cover})
    return {
        "generated_at": now.isoformat(),
        "cycle": cycle,
        "tiers": {k: [card(j, True) for j in v[: {"exceptional": 2, "apply": 3, "worth": 3, "verify": 3, "stretch": 12}[k]]] for k, v in tiers.items()},
        "tracked": [card(j, True) for j in tracked],
        "archive": archive,
        "radar": radar_view,
        "sources": sources_view,
        "manual": registry.MANUAL_WATCHES,
        "health": {"healthy": healthy, "total": len(sources_view), "last_cycle": state["runs"][-1]["at"] if state["runs"] else None,
                   "next_digest": notify.next_digest(now, state["digests"]), "email": notify.configured(), "search_api": search.enabled(),
                   "bridge": state.get("bridge", {}), "queue": state.get("queue", [])},
        "why_not": {"day": dict(sum((Counter(r.get("rejections", {})) for r in day_runs), Counter())), "raw_day": sum(r.get("raw", 0) for r in day_runs),
                    "ranked_day": sum(r.get("ranked", 0) for r in day_runs), "examples": state["rejected_examples"][-60:]},
        "runs": last_runs[-30:],
        "facts": prefs,
        "profile": {"name": evidence.profile()["identity"]["name"], "email": evidence.profile()["identity"]["email"], "phone": evidence.profile()["identity"]["phone"],
                    "phone_confirmed": evidence.profile()["identity"].get("phone_confirmed", False), "evidence": evidence.profile()["evidence"],
                    "experience": [{k: r.get(k) for k in ("id", "employer", "title", "dates")} for r in evidence.profile()["experience"]]},
        "companies": sorted([{"name": n["name"], "domain": n.get("domain"), "thessaloniki": n.get("thessaloniki"), "signals": n.get("radar_signals", []), "history": len(n.get("history", [])), "ats": n.get("ats") or (n.get("ats_detected") or [{}])[0].get("ats") if n.get("ats_detected") else n.get("ats")} for n in state["companies"].values()], key=lambda n: (-(len(n["signals"])), n["name"]))[:200],
        "digests": state["digests"][-5:],
        "alerts": list(state["alerts"].values())[-10:],
        "templates": {k: v["label"] for k, v in documents.TEMPLATES.items()},
    }


def write_site(out: Path, key: str, state: Dict, now: datetime, cycle: Dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    files = out / "files"
    files.mkdir(exist_ok=True)
    for old in files.glob("*.enc"):
        old.unlink()
    if documents.PHOTO.exists():
        (files / "photo.enc").write_text(crypto.encrypt_bytes(key, documents.PHOTO.read_bytes()))
    for job in state["jobs"].values():
        job["rendered_files"] = []
    for job in file_targets(state):
        try:
            rendered = render_files(job)
        except Exception as error:
            job["file_error"] = f"{type(error).__name__}: {error}"
            continue
        for name, blob in rendered.items():
            if blob:
                (files / f"{job['id']}-{name}.enc").write_text(crypto.encrypt_bytes(key, blob))
                job["rendered_files"].append(name)
    (out / "payload.enc").write_text(crypto.encrypt_json(key, site_payload(state, now, cycle)))


def run(*, state_path: Path, site_out: Optional[Path], key: str, primary: bool, mode: str = "full", only: Optional[List[str]] = None, force: bool = False) -> Dict:
    started = time.time()
    now = utcnow()
    state = load_state(state_path, key)
    migrated = migrate_sqlite(state, ROOT / "data" / "jobs.sqlite")
    for command in inbox.pending():
        command["at"] = now.isoformat()
        note = inbox.apply(state, command)
        inbox.close(command["number"], note)
    if state.get("confirmations"):
        overrides = ROOT / "data" / "confirmations.json"
        overrides.parent.mkdir(exist_ok=True)
        overrides.write_text(json.dumps(state["confirmations"]))
        evidence.reset()
    rejections: Counter = Counter()
    results: Dict[str, Dict] = {}
    chosen: List[Dict] = []
    if mode == "full":
        chosen = due_sources(state, now, only, force)
        results = run_sources(state, chosen, now)
    process_imports(state, now, results)
    raw = sum(len(r["jobs"]) for r in results.values())
    new_ids = merge(state, results, now, rejections)
    expire(state, now)
    rerank(state, now)
    run_radar = mode == "full" and (not state.get("radar_meta") or now - datetime.fromisoformat(state["radar_meta"].get("at", "2000-01-01T00:00:00+00:00")) > timedelta(hours=20))
    update_companies(state, now, run_radar)
    build_documents(state, now)
    mail_log = notify_cycle(state, now, new_ids, primary) if mode == "full" else []
    ranked = sum(1 for j in state["jobs"].values() if (j.get("analysis") or {}).get("tier") in VISIBLE)
    cycle = {"at": now.isoformat(), "mode": mode, "sources": [s["id"] for s in chosen], "raw": raw, "new": len(new_ids), "ranked": ranked,
             "rejections": dict(rejections), "duration": round(time.time() - started, 1), "mail": mail_log, "migrated": migrated}
    state["runs"] = (state["runs"] + [cycle])[-300:]
    if site_out:
        write_site(site_out, key, state, now, cycle)
    save_state(state_path, key, state)
    return cycle
