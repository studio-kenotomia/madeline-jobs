"""Normalized job records and shared parsing helpers."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from html import unescape
from typing import Dict, Iterable, List, Optional

GREEK = re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def strip_html(html: str) -> str:
    value = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html or "")
    value = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h[1-6]>|</div>", "\n", value)
    value = re.sub(r"(?i)<li[^>]*>", "\n• ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    value = unescape(value)
    value = re.sub(r"[ \t\u00a0]+", " ", value)
    value = re.sub(r"\n\s*\n+", "\n", value)
    return value.strip()


def language(text_value: str) -> str:
    sample = text_value[:3000]
    if not sample:
        return "unknown"
    greek = len(GREEK.findall(sample))
    letters = len(re.findall(r"[A-Za-z\u0370-\u03ff]", sample)) or 1
    return "el" if greek / letters > 0.3 else "en"


def parse_date(value) -> str:
    if not value:
        return ""
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, timezone.utc).date().isoformat()
    value = str(value).strip()
    match = re.match(r"(\d{4}-\d{2}-\d{2})", value)
    if match:
        return match.group(1)
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%d %b %Y", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(value[:31], fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def make_job(
    *,
    source: str,
    source_type: str,
    title: str,
    company: str,
    url: str,
    location: str = "",
    description_html: str = "",
    description_text: str = "",
    source_job_id: str = "",
    application_url: str = "",
    date_posted="",
    valid_through="",
    employment_type: str = "",
    work_mode: str = "",
    remote_regions: Optional[Iterable[str]] = None,
    salary: Optional[Dict] = None,
    department: str = "",
    extra: Optional[Dict] = None,
) -> Dict:
    body = description_text or strip_html(description_html)
    record = {
        "source": source,
        "source_type": source_type,
        "source_job_id": str(source_job_id or ""),
        "canonical_url": (url or "").strip(),
        "application_url": (application_url or url or "").strip(),
        "company": re.sub(r"\s+", " ", company or "").strip(),
        "title": re.sub(r"\s+", " ", unescape(title or "")).strip(),
        "description_html": (description_html or "")[:60000],
        "description_text": body[:30000],
        "language": language(f"{title} {body}"),
        "location_raw": re.sub(r"\s+", " ", location or "").strip(),
        "work_mode": work_mode or "",
        "remote_regions": sorted(set(r for r in (remote_regions or []) if r)),
        "date_posted": parse_date(date_posted),
        "valid_through": parse_date(valid_through),
        "employment_type": employment_type or "",
        "salary": salary or {},
        "department": department or "",
        "extra": extra or {},
    }
    record["id"] = job_key(record)
    record["content_hash"] = hashlib.sha256(
        "\n".join([record["title"], record["location_raw"], body[:20000], record["valid_through"]]).encode()
    ).hexdigest()[:20]
    return record


def job_key(record: Dict) -> str:
    if record.get("source_job_id"):
        basis = f"{record['source'].split(':')[0]}|{record['source_job_id']}"
    else:
        basis = re.sub(r"[?#].*$", "", record.get("canonical_url") or "")
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


def fingerprint(record: Dict) -> str:
    company = re.sub(r"[^a-z0-9α-ω]", "", (record.get("company") or "").lower())
    title = re.sub(r"[^a-z0-9α-ω]", "", (record.get("title") or "").lower())
    return f"{company}|{title}"


def jobpostings_from_html(html: str) -> List[Dict]:
    found = []
    for raw in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html or "", re.I | re.S):
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
                continue
            if not isinstance(item, dict):
                continue
            if "@graph" in item:
                stack.extend(item["@graph"] if isinstance(item["@graph"], list) else [item["@graph"]])
            kind = item.get("@type")
            kinds = kind if isinstance(kind, list) else [kind]
            if "JobPosting" in kinds:
                found.append(item)
    return found


def jsonld_location(item: Dict) -> str:
    places = item.get("jobLocation") or []
    places = places if isinstance(places, list) else [places]
    parts = []
    for place in places:
        if isinstance(place, dict):
            address = place.get("address") or {}
            if isinstance(address, dict):
                bits = [address.get("addressLocality"), address.get("addressRegion"), address.get("addressCountry")]
                bits = [b if isinstance(b, str) else (b or {}).get("name", "") if isinstance(b, dict) else "" for b in bits]
                parts.append(", ".join(b for b in bits if b))
            elif isinstance(address, str):
                parts.append(address)
    return " / ".join(p for p in parts if p)


def jsonld_remote(item: Dict) -> List[str]:
    regions = []
    requirements = item.get("applicantLocationRequirements") or []
    requirements = requirements if isinstance(requirements, list) else [requirements]
    for requirement in requirements:
        if isinstance(requirement, dict):
            regions.append(requirement.get("name") or "")
        elif isinstance(requirement, str):
            regions.append(requirement)
    return [r for r in regions if r]


def job_from_jsonld(item: Dict, *, source: str, url: str, company: str = "") -> Dict:
    org = item.get("hiringOrganization") or {}
    org_name = org.get("name") if isinstance(org, dict) else str(org or "")
    identifier = item.get("identifier")
    if isinstance(identifier, dict):
        identifier = identifier.get("value")
    salary = {}
    base = item.get("baseSalary")
    if isinstance(base, dict):
        value = base.get("value") or {}
        if isinstance(value, dict):
            salary = {
                "min": value.get("minValue") or value.get("value"),
                "max": value.get("maxValue") or value.get("value"),
                "currency": base.get("currency") or value.get("currency") or "",
                "period": value.get("unitText") or "",
                "published": True,
            }
    remote = jsonld_remote(item)
    mode = "remote" if str(item.get("jobLocationType") or "").upper() == "TELECOMMUTE" else ""
    logo = org.get("logo") if isinstance(org, dict) else ""
    if isinstance(logo, dict):
        logo = logo.get("url") or ""
    company_url = (org.get("sameAs") or org.get("url") or "") if isinstance(org, dict) else ""
    if isinstance(company_url, list):
        company_url = company_url[0] if company_url else ""
    return make_job(
        source=source,
        source_type="jsonld",
        title=item.get("title") or "",
        company=org_name or company,
        url=item.get("url") or url,
        location=jsonld_location(item),
        description_html=item.get("description") or "",
        source_job_id=str(identifier or ""),
        date_posted=item.get("datePosted"),
        valid_through=item.get("validThrough"),
        employment_type=str(item.get("employmentType") or ""),
        work_mode=mode,
        remote_regions=remote,
        salary=salary,
        extra={"logo": logo or "", "company_url": company_url or ""},
    )
