"""Employer applicant-tracking systems with public job-board endpoints."""

from __future__ import annotations

import json
import re
from typing import Dict, List

from .. import http
from ..model import job_from_jsonld, jobpostings_from_html, make_job, strip_html


def greenhouse(token: str, company: str) -> List[Dict]:
    data = http.get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    jobs = []
    for item in data.get("jobs") or []:
        location = (item.get("location") or {}).get("name") or ""
        offices = ", ".join(o.get("name", "") for o in item.get("offices") or [])
        content = item.get("content") or ""
        content = content.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&amp;", "&")
        questions = []
        jobs.append(make_job(
            source=f"greenhouse:{token}", source_type="ats", title=item.get("title") or "", company=company,
            url=item.get("absolute_url") or "", location=f"{location}; {offices}".strip("; "), description_html=content,
            source_job_id=str(item.get("id") or ""), date_posted=item.get("first_published") or item.get("updated_at"),
            department=", ".join(d.get("name", "") for d in item.get("departments") or []), extra={"ats": "greenhouse", "questions": questions},
        ))
    return jobs


def lever(slug: str, company: str) -> List[Dict]:
    data = http.get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    jobs = []
    for item in data:
        categories = item.get("categories") or {}
        lists = "".join(f"<h3>{block.get('text', '')}</h3><ul>{block.get('content', '')}</ul>" for block in item.get("lists") or [])
        body = (item.get("descriptionPlain") or strip_html(item.get("description") or "")) + "\n" + strip_html(lists) + "\n" + (item.get("additionalPlain") or "")
        all_locations = categories.get("allLocations") or [categories.get("location") or ""]
        jobs.append(make_job(
            source=f"lever:{slug}", source_type="ats", title=item.get("text") or "", company=company, url=item.get("hostedUrl") or "",
            application_url=item.get("applyUrl") or "", location=", ".join(all_locations), description_text=body,
            source_job_id=item.get("id") or "", date_posted=item.get("createdAt"), work_mode=(item.get("workplaceType") or "").lower(),
            employment_type=categories.get("commitment") or "", department=categories.get("team") or "", extra={"ats": "lever"},
        ))
    return jobs


def ashby(board: str, company: str) -> List[Dict]:
    data = http.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true")
    jobs = []
    for item in data.get("jobs") or []:
        if item.get("isListed") is False:
            continue
        locations = [item.get("location") or ""] + [s.get("location", "") for s in item.get("secondaryLocations") or []]
        address = ((item.get("address") or {}).get("postalAddress") or {})
        if address.get("addressCountry"):
            locations.append(address["addressCountry"])
        salary = {}
        comp = item.get("compensation") or {}
        tiers = comp.get("summaryComponents") or []
        for tier in tiers:
            if tier.get("compensationType") == "Salary":
                salary = {"min": tier.get("minValue"), "max": tier.get("maxValue"), "currency": tier.get("currencyCode"), "period": tier.get("interval"), "published": True}
        jobs.append(make_job(
            source=f"ashby:{board}", source_type="ats", title=item.get("title") or "", company=company, url=item.get("jobUrl") or "",
            application_url=item.get("applyUrl") or "", location=", ".join(l for l in locations if l), description_html=item.get("descriptionHtml") or "",
            source_job_id=item.get("id") or "", date_posted=item.get("publishedAt"), work_mode="remote" if item.get("isRemote") else (item.get("workplaceType") or "").lower(),
            employment_type=item.get("employmentType") or "", department=item.get("department") or "", salary=salary, extra={"ats": "ashby"},
        ))
    return jobs


def _from_smartrecruiters_blob(blob: str, company_id: str, company: str, url: str) -> Dict:
    data = json.loads(blob)
    sections = (data.get("content") or {}).get("sections") or {}
    chunks = []
    if isinstance(sections, dict):
        for key in ("jobDescription", "qualifications", "additionalInformation"):
            section = sections.get(key) or {}
            if isinstance(section, dict) and section.get("text"):
                label = section.get("title") or ""
                chunks.append(f"{label}\n{section['text']}" if label else section["text"])
    slug = url.rstrip("/").split("/")[-1]
    fallback = slug.split("--", 1)[-1].replace("-", " ").strip().title() if "--" in slug else ""
    return make_job(
        source=f"smartrecruiters:{company_id}", source_type="ats", title=data.get("jobTitle") or fallback or company,
        company=(data.get("company") or {}).get("name") or company, url=url, location=data.get("jobAdLocation") or "",
        description_text=strip_html("\n\n".join(chunks)), source_job_id=str(data.get("uuid") or slug.split("-")[0]),
        date_posted=data.get("postedDate") or "", employment_type=data.get("employmentType") or "", extra={"ats": "smartrecruiters"},
    )


def repair_smartrecruiters(job: Dict) -> bool:
    raw = (job.get("description_text") or job.get("description_html") or "").strip()
    title = job.get("title") or ""
    if not (raw.startswith("{") or title.startswith("http")):
        return False
    if not raw.startswith("{"):
        return False
    try:
        fixed = _from_smartrecruiters_blob(raw, job.get("source", "").split(":", 1)[-1], job.get("company") or "", job.get("canonical_url") or "")
    except (json.JSONDecodeError, TypeError):
        return False
    for field in ("title", "company", "location_raw", "description_text", "date_posted", "employment_type"):
        if fixed.get(field):
            job[field] = fixed[field]
    job["language"] = fixed.get("language") or job.get("language")
    return True


def smartrecruiters(company_id: str, company: str, detail_limit: int = 30, known: set = frozenset()) -> List[Dict]:
    """The SmartRecruiters API disallows crawlers in robots.txt, so this reads the public careers page and the job page."""
    listing = http.text(f"https://careers.smartrecruiters.com/{company_id}")
    links = list(dict.fromkeys(re.findall(rf'href="(https://jobs\.smartrecruiters\.com/{re.escape(company_id)}/[^"]+)"', listing)))
    jobs = []
    for url in links[:detail_limit]:
        try:
            page = http.text(url)
        except Exception:
            continue
        posting_id = url.rstrip("/").split("/")[-1].split("-")[0]
        start = page.find('{"uuid"')
        if start >= 0:
            try:
                job = _from_smartrecruiters_blob(page[start: page.rfind("}") + 1], company_id, company, url)
                job["source_job_id"] = posting_id
                jobs.append(job)
                continue
            except (json.JSONDecodeError, TypeError):
                pass
        found = jobpostings_from_html(page)
        if found:
            job = job_from_jsonld(found[0], source=f"smartrecruiters:{company_id}", url=url, company=company)
            job["source_type"] = "ats"
            job["source_job_id"] = posting_id
            job["extra"]["ats"] = "smartrecruiters"
            jobs.append(job)
            continue
        title = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
        heading = strip_html(title.group(1)) if title else ""
        if not heading or heading.startswith("http"):
            continue
        jobs.append(make_job(source=f"smartrecruiters:{company_id}", source_type="ats", title=heading, company=company, url=url,
                             description_text=strip_html(page)[:8000], source_job_id=posting_id, extra={"ats": "smartrecruiters"}))
    return jobs


def workable_account(slug: str, company: str) -> List[Dict]:
    data = http.post_json(f"https://apply.workable.com/api/v3/accounts/{slug}/jobs", {"query": "", "location": [], "department": [], "worktype": [], "remote": []})
    jobs = []
    for item in data.get("results") or []:
        location = item.get("location") or {}
        loc = ", ".join(x for x in (location.get("city"), location.get("region"), location.get("country")) if x)
        shortcode = item.get("shortcode")
        url = f"https://apply.workable.com/{slug}/j/{shortcode}/"
        body = ""
        try:
            detail = http.get_json(f"https://apply.workable.com/api/v2/accounts/{slug}/jobs/{shortcode}")
            body = strip_html((detail.get("description") or "") + (detail.get("requirements") or "") + (detail.get("benefits") or ""))
        except Exception:
            pass
        jobs.append(make_job(
            source=f"workable:{slug}", source_type="ats", title=item.get("title") or "", company=company, url=url, application_url=url + "apply/",
            location=loc, description_text=body, source_job_id=shortcode, date_posted=item.get("published"),
            work_mode="remote" if item.get("remote") else (item.get("workplace") or ""), extra={"ats": "workable"},
        ))
    return jobs


def recruitee(slug: str, company: str) -> List[Dict]:
    data = http.get_json(f"https://{slug}.recruitee.com/api/offers/")
    jobs = []
    for item in data.get("offers") or []:
        jobs.append(make_job(
            source=f"recruitee:{slug}", source_type="ats", title=item.get("title") or "", company=company, url=item.get("careers_url") or "",
            application_url=item.get("careers_apply_url") or "", location=", ".join(x for x in (item.get("city"), item.get("country")) if x),
            description_html=(item.get("description") or "") + (item.get("requirements") or ""), source_job_id=str(item.get("id") or ""),
            date_posted=item.get("published_at") or item.get("created_at"), work_mode="remote" if item.get("remote") else "", extra={"ats": "recruitee"},
        ))
    return jobs


def personio(slug: str, company: str) -> List[Dict]:
    xml = http.text(f"https://{slug}.jobs.personio.de/xml")
    jobs = []
    for block in re.findall(r"<position>(.*?)</position>", xml, re.S):
        def tag(name):
            m = re.search(rf"<{name}>(.*?)</{name}>", block, re.S)
            return re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1)).strip() if m else ""
        identifier = tag("id")
        body = " ".join(re.sub(r"<!\[CDATA\[|\]\]>", "", v) for v in re.findall(r"<value>(.*?)</value>", block, re.S))
        jobs.append(make_job(
            source=f"personio:{slug}", source_type="ats", title=tag("name"), company=company, url=f"https://{slug}.jobs.personio.de/job/{identifier}",
            location=tag("office"), description_html=body, source_job_id=identifier, date_posted=tag("createdAt"), extra={"ats": "personio"},
        ))
    return jobs


def workday(tenant: str, site: str, host: str, company: str, search: str = "", limit: int = 40) -> List[Dict]:
    base = f"https://{tenant}.{host}.myworkdayjobs.com"
    data = http.post_json(f"{base}/wday/cxs/{tenant}/{site}/jobs", {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": search})
    jobs = []
    for item in (data.get("jobPostings") or [])[:limit]:
        path = item.get("externalPath") or ""
        url = f"{base}/en-US/{site}{path}"
        body = ""
        try:
            detail = http.get_json(f"{base}/wday/cxs/{tenant}/{site}{path}")
            info = detail.get("jobPostingInfo") or {}
            body = strip_html(info.get("jobDescription") or "")
            posted = info.get("startDate")
        except Exception:
            posted = ""
        jobs.append(make_job(
            source=f"workday:{tenant}", source_type="ats", title=item.get("title") or "", company=company, url=url, application_url=url + "/apply",
            location=item.get("locationsText") or "", description_text=body, source_job_id=(item.get("bulletFields") or [path])[0],
            date_posted=posted, extra={"ats": "workday"},
        ))
    return jobs


def manatal(slug: str, company: str, location: str) -> List[Dict]:
    html = http.text(f"https://www.careers-page.com/{slug}")
    ids = list(dict.fromkeys(re.findall(rf"/{re.escape(slug)}/job/([A-Za-z0-9]+)", html)))
    jobs = []
    for job_id in ids[:15]:
        url = f"https://www.careers-page.com/{slug}/job/{job_id}"
        try:
            page = http.text(url)
        except Exception:
            continue
        title = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
        jobs.append(make_job(
            source=f"manatal:{slug}", source_type="ats", title=strip_html(title.group(1)) if title else job_id, company=company, url=url,
            location=location, description_html=page, source_job_id=job_id, extra={"ats": "manatal"},
        ))
    return jobs


ATS_SIGNATURES = [
    ("greenhouse", r"boards(?:-api)?\.greenhouse\.io/(?:v1/boards/)?([a-z0-9_-]+)"),
    ("greenhouse", r"job-boards\.greenhouse\.io/([a-z0-9_-]+)"),
    ("lever", r"jobs\.lever\.co/([a-z0-9_.-]+)"),
    ("ashby", r"jobs\.ashbyhq\.com/([A-Za-z0-9_.-]+)"),
    ("workable", r"apply\.workable\.com/([a-z0-9_-]+)"),
    ("smartrecruiters", r"(?:careers|jobs)\.smartrecruiters\.com/([A-Za-z0-9_-]+)"),
    ("recruitee", r"([a-z0-9-]+)\.recruitee\.com"),
    ("personio", r"([a-z0-9-]+)\.jobs\.personio\.(?:de|com)"),
    ("teamtailor", r"([a-z0-9-]+)\.teamtailor\.com"),
    ("manatal", r"careers-page\.com/([a-z0-9-]+)"),
    ("workday", r"([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]+)"),
]
IGNORE_TOKENS = {"embed", "js", "api", "v1", "jobs", "www", "careers", "static", "assets"}


def detect(domain_or_url: str) -> List[Dict]:
    """Find public ATS boards from an employer homepage and careers page."""
    start = domain_or_url if domain_or_url.startswith("http") else f"https://{domain_or_url}"
    pages = [start]
    found: List[Dict] = []
    seen = set()
    try:
        home = http.text(start, timeout=15)
    except Exception:
        return found
    for href in re.findall(r'href="([^"]+)"', home):
        if re.search(r"career|jobs|join|work-with|vacanc|θέσεις|καριέρα", href, re.I):
            if href.startswith("/"):
                href = start.rstrip("/") + href
            if href.startswith("http") and href not in pages:
                pages.append(href)
    blobs = [home]
    for page in pages[1:4]:
        try:
            blobs.append(http.text(page, timeout=15))
        except Exception:
            continue
    for blob in blobs:
        for name, pattern in ATS_SIGNATURES:
            for match in re.finditer(pattern, blob):
                token = match.group(1)
                if token.lower() in IGNORE_TOKENS:
                    continue
                key = (name, token.lower())
                if key in seen:
                    continue
                seen.add(key)
                record = {"ats": name, "token": token}
                if name == "workday":
                    record = {"ats": name, "token": match.group(1), "host": match.group(2), "site": match.group(3)}
                found.append(record)
        if "application/ld+json" in blob and "JobPosting" in blob:
            found.append({"ats": "jsonld", "token": start})
    return found
