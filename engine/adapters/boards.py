"""Job boards and remote-job feeds with public machine-readable endpoints."""

from __future__ import annotations

import re
import urllib.parse
from typing import Dict, List

from .. import http
from ..model import make_job, strip_html

WORKABLE_QUERIES = [
    {"location": "Thessaloniki"},
    {"location": "Thessaloniki", "query": "assistant"},
    {"location": "Thessaloniki", "query": "coordinator"},
    {"location": "Greece", "workplace": "remote"},
    {"location": "Greece", "query": "project"},
    {"location": "Greece", "query": "sustainability"},
    {"location": "Greece", "query": "environment"},
    {"location": "Greece", "query": "research"},
    {"query": "dutch", "workplace": "remote"},
    {"query": "immigration", "workplace": "remote"},
    {"query": "executive assistant", "workplace": "remote"},
    {"query": "operations coordinator", "workplace": "remote"},
    {"query": "project coordinator", "workplace": "remote"},
    {"query": "esg", "workplace": "remote"},
]


def workable_search(max_pages: int = 6) -> List[Dict]:
    jobs: Dict[str, Dict] = {}
    for query in WORKABLE_QUERIES:
        token = ""
        for _ in range(max_pages):
            params = dict(query)
            if token:
                params["pageToken"] = token
            data = http.get_json("https://jobs.workable.com/api/v1/jobs?" + urllib.parse.urlencode(params))
            for item in data.get("jobs") or []:
                company = item.get("company") or {}
                location = item.get("location") or {}
                locations = item.get("locations") or []
                loc = "; ".join(locations) or ", ".join(x for x in (location.get("city"), location.get("subregion"), location.get("countryName")) if x)
                body = strip_html(item.get("description") or "") + "\n" + strip_html(item.get("requirementsSection") or "") + "\n" + strip_html(item.get("benefitsSection") or "")
                job = make_job(
                    source="workable-search", source_type="board", title=item.get("title") or "", company=company.get("title") or "",
                    url=item.get("url") or "", location=loc, description_text=body, source_job_id=item.get("id") or "",
                    date_posted=item.get("created"), employment_type=item.get("employmentType") or "",
                    work_mode={"on_site": "onsite"}.get(item.get("workplace") or "", item.get("workplace") or ""),
                    extra={"company_website": company.get("website") or "", "ats": "workable", "logo": company.get("image") or ""},
                )
                jobs[job["id"]] = job
            token = data.get("nextPageToken") or ""
            if not token:
                break
    return list(jobs.values())


def remotive() -> List[Dict]:
    jobs = {}
    for term in ("", "assistant", "operations", "coordinator", "sustainability", "immigration", "project", "research"):
        url = "https://remotive.com/api/remote-jobs" + (f"?search={urllib.parse.quote(term)}" if term else "")
        for item in http.get_json(url).get("jobs") or []:
            job = make_job(
                source="remotive", source_type="board", title=item.get("title") or "", company=item.get("company_name") or "",
                url=item.get("url") or "", location=item.get("candidate_required_location") or "", description_html=item.get("description") or "",
                source_job_id=str(item.get("id") or ""), date_posted=item.get("publication_date"), work_mode="remote",
            )
            jobs[job["id"]] = job
    return list(jobs.values())


def jobicy() -> List[Dict]:
    jobs = {}
    for params in ("geo=emea", "geo=europe", "geo=greece", "industry=admin", "industry=management", "tag=sustainability", "tag=operations"):
        data = http.get_json(f"https://jobicy.com/api/v2/remote-jobs?count=100&{params}")
        for item in data.get("jobs") or []:
            job = make_job(
                source="jobicy", source_type="board", title=item.get("jobTitle") or "", company=item.get("companyName") or "",
                url=item.get("url") or "", location=item.get("jobGeo") or "", description_html=item.get("jobDescription") or item.get("jobExcerpt") or "",
                source_job_id=str(item.get("id") or ""), date_posted=item.get("pubDate"), work_mode="remote", extra={"logo": item.get("companyLogo") or ""},
                salary={"min": item.get("salaryMin"), "max": item.get("salaryMax"), "currency": item.get("salaryCurrency"), "period": item.get("salaryPeriod"), "published": True} if item.get("salaryMin") else {},
            )
            jobs[job["id"]] = job
    return list(jobs.values())


def arbeitnow() -> List[Dict]:
    jobs = []
    for item in http.get_json("https://www.arbeitnow.com/api/job-board-api").get("data") or []:
        location = item.get("location")
        jobs.append(make_job(
            source="arbeitnow", source_type="board", title=item.get("title") or "", company=item.get("company_name") or "",
            url=item.get("url") or f"https://www.arbeitnow.com/jobs/{item.get('slug')}", location=location if isinstance(location, str) else ", ".join(location or []),
            description_html=item.get("description") or "", source_job_id=item.get("slug") or "", date_posted=item.get("created_at"),
            work_mode="remote" if item.get("remote") else "",
        ))
    return jobs


def remoteok() -> List[Dict]:
    jobs = []
    for item in http.get_json("https://remoteok.com/api")[1:]:
        jobs.append(make_job(
            source="remoteok", source_type="board", title=item.get("position") or "", company=item.get("company") or "",
            url=item.get("url") or "", application_url=item.get("apply_url") or "", location=item.get("location") or "",
            description_html=item.get("description") or "", source_job_id=str(item.get("id") or ""), date_posted=item.get("date"), work_mode="remote",
            extra={"logo": item.get("company_logo") or item.get("logo") or ""},
        ))
    return jobs


def himalayas() -> List[Dict]:
    jobs = {}
    for query in ("assistant", "operations coordinator", "project coordinator", "executive assistant", "sustainability", "immigration", "research assistant", "administrator"):
        data = http.get_json("https://himalayas.app/jobs/api/search?" + urllib.parse.urlencode({"q": query, "country": "GR"}))
        for item in data.get("jobs") or []:
            regions = item.get("locationRestrictions") or []
            zones = item.get("timezoneRestrictions") or []
            if zones and not any(-1 <= float(z) <= 4 for z in zones if isinstance(z, (int, float, str)) and str(z).lstrip("-").replace(".", "").isdigit()):
                regions = regions + ["timezone outside Europe"]
            job = make_job(
                source="himalayas", source_type="board", title=item.get("title") or "", company=item.get("companyName") or "",
                url=item.get("applicationLink") or f"https://himalayas.app/companies/{item.get('companySlug')}/jobs", location="Remote; " + ", ".join(regions) if regions else "Remote",
                description_html=item.get("description") or item.get("excerpt") or "", source_job_id=item.get("guid") or "",
                date_posted=item.get("pubDate"), valid_through=item.get("expiryDate"), work_mode="remote", remote_regions=regions,
                salary={"min": item.get("minSalary"), "max": item.get("maxSalary"), "currency": item.get("currency"), "period": item.get("salaryPeriod"), "published": True} if item.get("minSalary") else {},
                extra={"logo": item.get("companyLogo") or ""},
            )
            jobs[job["id"]] = job
    return list(jobs.values())


def weworkremotely() -> List[Dict]:
    xml = http.text("https://weworkremotely.com/remote-jobs.rss")
    jobs = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.S):
        def tag(name):
            m = re.search(rf"<{name}>(.*?)</{name}>", block, re.S)
            return re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1)).strip() if m else ""
        raw_title = tag("title")
        company, _, title = raw_title.partition(":")
        jobs.append(make_job(
            source="weworkremotely", source_type="board", title=title.strip() or raw_title, company=company.strip(),
            url=tag("link"), location=tag("region") or "Anywhere", description_html=tag("description"), source_job_id=tag("guid"),
            date_posted=tag("pubDate"), work_mode="remote",
        ))
    return jobs


def workingnomads() -> List[Dict]:
    jobs = []
    for item in http.get_json("https://www.workingnomads.com/api/exposed_jobs/"):
        jobs.append(make_job(
            source="workingnomads", source_type="board", title=item.get("title") or "", company=item.get("company_name") or "",
            url=item.get("url") or "", location=item.get("location") or "", description_html=item.get("description") or "",
            source_job_id=item.get("url") or "", date_posted=item.get("pub_date"), work_mode="remote",
        ))
    return jobs
