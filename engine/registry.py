"""Every automated source, how often it runs, and how it is called."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List

from . import crypto, http
from .adapters import ats, boards, greek, pages, search

ROOT = Path(__file__).resolve().parent.parent
RELAY_URL = "https://raw.githubusercontent.com/studio-kenotomia/madeline-jobs/mac-relay/feed.enc"


def relay() -> List[Dict]:
    """Jobs the Mac fetched from sites that refuse GitHub's servers. Stale feeds raise so nothing gets closed."""
    blob = http.text(RELAY_URL + f"?t={datetime.now().timestamp():.0f}", check_robots=False)
    feed = crypto.decrypt_json(os.environ.get("DASH_KEY", ""), blob)
    at = datetime.fromisoformat(feed["at"])
    if datetime.now(timezone.utc) - at > timedelta(hours=6):
        raise RuntimeError(f"Mac relay is stale (last update {feed['at'][:16]} UTC). The Mac has been off or asleep.")
    return feed["jobs"]


def companies() -> List[Dict]:
    return json.loads((ROOT / "data" / "companies.json").read_text())


def build() -> List[Dict]:
    sources: List[Dict] = []

    def add(source_id: str, label: str, minutes: int, fn: Callable, kind: str = "ats", note: str = "") -> None:
        sources.append({"id": source_id, "label": label, "interval": minutes, "fn": fn, "kind": kind, "note": note})

    for company in companies():
        kind, token, name = company["ats"], company["token"], company["name"]
        if kind == "greenhouse":
            add(f"greenhouse:{token}", name, 20, lambda ctx, t=token, n=name: ats.greenhouse(t, n))
        elif kind == "lever":
            add(f"lever:{token}", name, 40 if token == "jobgether" else 20, lambda ctx, t=token, n=name: ats.lever(t, n))
        elif kind == "ashby":
            add(f"ashby:{token}", name, 20, lambda ctx, t=token, n=name: ats.ashby(t, n))
        elif kind == "smartrecruiters":
            add(f"smartrecruiters:{token}", name, 20, lambda ctx, t=token, n=name: ats.smartrecruiters(t, n))
        elif kind == "workday":
            add(f"workday:{token}", name, 60, lambda ctx, c=company: ats.workday(c["token"], c["site"], c["host"], c["name"], c.get("search", "")))
        elif kind == "manatal":
            add(f"manatal:{token}", name, 60, lambda ctx, c=company: ats.manatal(c["token"], c["name"], c.get("location", "Thessaloniki, Greece")), kind="page")

    add("workable-search", "Workable job search (Thessaloniki, Greece, remote)", 20, lambda ctx: boards.workable_search(), kind="board")
    add("remotive", "Remotive", 60, lambda ctx: boards.remotive(), kind="board")
    add("jobicy", "Jobicy", 60, lambda ctx: boards.jobicy(), kind="board")
    add("arbeitnow", "Arbeitnow", 120, lambda ctx: boards.arbeitnow(), kind="board")
    add("remoteok", "Remote OK", 60, lambda ctx: boards.remoteok(), kind="board")
    add("himalayas", "Himalayas", 60, lambda ctx: boards.himalayas(), kind="board")
    add("weworkremotely", "We Work Remotely", 60, lambda ctx: boards.weworkremotely(), kind="board")
    add("workingnomads", "Working Nomads", 120, lambda ctx: boards.workingnomads(), kind="board")
    add("kariera", "Kariera.gr (office categories)", 40, lambda ctx: greek.kariera(ctx.get("known", set())), kind="board")
    if os.environ.get("RADAR_HOST") == "mac":
        add("skywalker", "Skywalker.gr", 40, lambda ctx: greek.skywalker(), kind="board", note="Listing pages only. Full ads block automated reading.")
    add("mac-relay", "Mac relay (Skywalker and DYPA, which block GitHub's servers)", 20, lambda ctx: relay(), kind="relay", note="Fresh only while the Mac is on.")
    add("dypa", "DYPA Hot Jobs (public employment service)", 180, lambda ctx: greek.dypa_hotjobs(), kind="public", note="Often times out from GitHub's servers; the Mac relay also reads it.")
    add("diavgeia", "Diavgeia public notices (Thessaloniki universities, CERTH, region, city)", 180, lambda ctx: greek.diavgeia(), kind="public")
    add("cedefop", "Cedefop, EU agency in Thessaloniki", 120, lambda ctx: pages.cedefop(), kind="page")
    add("euraxess", "EURAXESS research jobs in Greece", 180, lambda ctx: pages.euraxess(ctx.get("known", set())), kind="page")
    add("bstdb", "Black Sea Trade and Development Bank", 180, lambda ctx: pages.bstdb(), kind="page")
    add("certh", "CERTH project positions", 180, lambda ctx: pages.certh(), kind="page")
    add("draxis", "DRAXIS careers page", 120, lambda ctx: pages.draxis(), kind="page")
    add("isea", "iSea careers", 120, lambda ctx: pages.isea(), kind="page")
    add("ekby", "EKBY calls", 180, lambda ctx: pages.html_announcements("ekby", "EKBY / Goulandris", "https://ekby.gr/news/prokirikseis-proskliseis/", "Thermi, Thessaloniki", r"prosklisi|proslipsi|θέσ"), kind="page")
    add("afs", "American Farm School / Perrotis", 180, lambda ctx: pages.html_announcements("afs", "American Farm School", "https://afs.edu.gr/en/human-resources/", "Thessaloniki, Greece", r"opening|position|vacanc|θέση|officer|assistant|coordinator", r"faculty|lecturer|teacher|professor"), kind="page")
    if search.enabled():
        add("web-search", "Web search discovery (Brave)", 180, lambda ctx: web_search(ctx), kind="search", note="Search results are verified on the original page before they count.")
    return sources


def web_search(ctx: Dict) -> List[Dict]:
    from .model import job_from_jsonld, jobpostings_from_html
    offset = int(datetime.now(timezone.utc).timestamp() // 10800)
    jobs = []
    for lead in search.brave(limit_queries=6, offset=offset * 6):
        url = lead.get("url") or ""
        if not url or not http.public_url(url):
            continue
        try:
            page = http.text(url, timeout=20)
        except Exception:
            continue
        for item in jobpostings_from_html(page)[:1]:
            job = job_from_jsonld(item, source="web-search", url=url)
            job["extra"]["found_by_query"] = lead.get("query")
            jobs.append(job)
    return jobs


MANUAL_WATCHES = [
    {"name": "LinkedIn, Thessaloniki office roles", "url": "https://www.linkedin.com/jobs/search/?keywords=%22project%20assistant%22%20OR%20%22administrative%22%20OR%20%22coordinator%22%20OR%20%22executive%20assistant%22&location=Thessaloniki%2C%20Greece&f_TPR=r86400", "why": "LinkedIn's robots.txt blocks crawlers, so this is a one-tap search."},
    {"name": "LinkedIn, remote Europe", "url": "https://www.linkedin.com/jobs/search/?keywords=%22executive%20assistant%22%20OR%20%22operations%20coordinator%22%20OR%20%22immigration%20coordinator%22&location=European%20Economic%20Area&f_WT=2&f_TPR=r86400", "why": "Check that Greece is allowed before applying."},
    {"name": "Indeed Greece", "url": "https://gr.indeed.com/jobs?q=administrator+OR+coordinator+OR+%22project+assistant%22&l=Thessaloniki&fromage=1", "why": "Indeed blocks automated readers with a bot wall."},
    {"name": "Glassdoor", "url": "https://www.glassdoor.com/Job/thessaloniki-administrative-assistant-jobs-SRCH_IL.0,12_IC2516514_KO13,38.htm", "why": "Login wall."},
    {"name": "JobFind", "url": "https://www.jobfind.gr/", "why": "No stable public listing format."},
    {"name": "UN Jobs, Thessaloniki", "url": "https://unjobs.org/duty_stations/thessaloniki", "why": "Its robots.txt disallows crawlers."},
    {"name": "IOM Greece vacancies", "url": "https://greece.iom.int/vacancies", "why": "The site blocks automated access."},
    {"name": "Elevate Greece startup registry", "url": "https://elevategreece.gov.gr/the-startup-database/", "why": "No public data feed. Browse for Central Macedonia startups."},
    {"name": "Climatebase, Europe", "url": "https://climatebase.org/jobs?l=Europe&q=assistant", "why": "No public API."},
    {"name": "Conservation Careers", "url": "https://www.conservation-careers.com/job-search/?search_keywords=assistant&search_location=europe", "why": "No public API."},
    {"name": "EU Careers (EPSO)", "url": "https://eu-careers.europa.eu/en/job-opportunities", "why": "Mostly Brussels and Luxembourg. Cedefop in Thessaloniki is automated separately."},
]
