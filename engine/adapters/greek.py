"""Greek job boards, the public employment service and public-sector job notices."""

from __future__ import annotations

import html as html_lib
import re
import urllib.parse
from typing import Dict, List, Set

from .. import http
from ..model import job_from_jsonld, jobpostings_from_html, make_job, strip_html

KARIERA_CATEGORIES = [
    "administrative-or-secretarial-jobs", "human-resources-jobs", "research-and-development-jobs", "operations-jobs",
    "procurement-or-supply-chain-jobs", "quality-assurance-jobs", "public-relations-jobs", "other-jobs", "general-management-jobs",
]


def kariera(known: Set[str], detail_limit: int = 45) -> List[Dict]:
    """Category listings first, then JSON-LD on detail pages not seen before."""
    links: List[str] = []
    for category in KARIERA_CATEGORIES:
        for page in (1, 2):
            url = f"https://www.kariera.gr/en/jobs/{category}" + (f"?page={page}" if page > 1 else "")
            try:
                listing = http.text(url)
            except Exception:
                break
            found = re.findall(r'href="(/en/jobs/[a-z0-9\-]+/\d+)"', listing)
            for link in found:
                if link.split("/")[3] in KARIERA_CATEGORIES and link not in links:
                    links.append(link)
    jobs = []
    fetched = 0
    for link in links:
        job_id = link.rsplit("/", 1)[-1]
        if job_id in known or fetched >= detail_limit:
            continue
        fetched += 1
        url = "https://www.kariera.gr" + link
        try:
            page = http.text(url)
        except Exception:
            continue
        for item in jobpostings_from_html(page):
            job = job_from_jsonld(item, source="kariera", url=url)
            job["source_type"] = "board"
            job["extra"]["category"] = link.split("/")[3]
            job["extra"]["board_id"] = job_id
            jobs.append(job)
            break
    return jobs


SKYWALKER_TERMS = ["administrative", "assistant", "coordinator", "project", "office", "research", "environment", "operations", "γραμματεία", "διοικητικ", "βοηθός", "περιβάλλον", "english"]
GREEK_MONTHS = {
    "ιανουαρίου": 1, "φεβρουαρίου": 2, "μαρτίου": 3, "απριλίου": 4, "μαΐου": 5, "μαιου": 5, "ιουνίου": 6,
    "ιουλίου": 7, "αυγούστου": 8, "σεπτεμβρίου": 9, "οκτωβρίου": 10, "νοεμβρίου": 11, "δεκεμβρίου": 12,
}


def parse_listing_text(raw: str) -> Dict:
    """Pull a real title, date and place out of a Skywalker listing card."""
    flat = re.sub(r"\s+", " ", strip_html(raw))
    date_value = ""
    dated = re.search(r"(\d{1,2})\s+([Α-Ωα-ωά-ώϊϋΐΰ]+)\s+(20\d{2})", flat)
    if dated and dated.group(2).lower() in GREEK_MONTHS:
        date_value = f"{dated.group(3)}-{GREEK_MONTHS[dated.group(2).lower()]:02d}-{int(dated.group(1)):02d}"
    title = ""
    titled = re.search(r"20\d{2}\s+(.+?)\s+περιοχ", flat) or re.search(r"πριν\s+\d+\s+\S+\s+(.+?)\s+περιοχ", flat)
    if titled:
        title = re.sub(r"^(Νέα θέση εργασίας\s+)?(πριν\s+\d+\s+\S+\s+)?", "", titled.group(1)).strip(" -–|")
    if not title or title.lower().startswith("word.send") or title.lower().startswith("http"):
        title = ""
    location = "Greece"
    if re.search(r"Θεσσαλονίκ|Thessaloniki|Καλαμαριά|Πυλαία|Θέρμη", flat):
        location = "Thessaloniki, Greece"
    elif re.search(r"Αθήν|Athens|Αττικ", flat):
        location = "Athens, Greece"
    elif re.search(r"Πάτρ", flat):
        location = "Patras, Greece"
    elif re.search(r"Ηράκλει|Χανί", flat):
        location = "Crete, Greece"
    mode = "remote" if re.search(r"Εξ αποστάσεως|\bremote\b", flat, re.I) else "hybrid" if "Υβριδικ" in flat else "onsite"
    pay = re.search(r"από\s+[\d.,]+\s+εώς\s+[\d.,]+\s*€\s*/\s*μήνας", flat)
    parts = [p for p in (title, location, date_value, pay.group(0) if pay else "") if p]
    note = "Skywalker only gives automated readers the title, place and date. Open the listing for the full advertisement."
    return {"title": title[:180], "date": date_value, "location": location, "work_mode": mode, "description": (". ".join(parts) + ". " + note).strip()}


def repair_skywalker(job: Dict) -> bool:
    raw = job.get("description_text") or ""
    title = (job.get("title") or "").lower()
    if not (title.startswith("word.send") or title.startswith("http") or "class=" in raw or "περιοχές" in raw[:900]):
        return False
    parsed = parse_listing_text(raw)
    if not parsed["title"]:
        return False
    job["title"] = parsed["title"]
    if parsed["date"]:
        job["date_posted"] = parsed["date"]
    job["location_raw"] = parsed["location"]
    job["work_mode"] = parsed["work_mode"]
    job["description_text"] = parsed["description"]
    return True


def skywalker() -> List[Dict]:
    jobs: Dict[str, Dict] = {}
    for term in SKYWALKER_TERMS:
        url = "https://www.skywalker.gr/el/aggelies-ergasias?" + urllib.parse.urlencode({"keywords": term})
        page = http.text(url)
        for block in re.findall(r'<li\s+data-id\s+class="res".*?</li>\s*(?=<li\s+data-id|</ul>)', page, re.S)[:60]:
            ad = re.search(r'data-bigAd="([^"]+)"\s+data-bigAdSlug="([^"]+)"', block)
            if not ad:
                continue
            ad_id, slug = ad.group(1), html_lib.unescape(ad.group(2))
            text_value = strip_html(block)
            parsed = parse_listing_text(text_value)
            title = parsed["title"] or slug.replace("-", " ")
            if title.lower().startswith("word.send"):
                continue
            company = re.search(r'/profile/etairias/[^/]+/([^"]+)"', block)
            logo = re.search(r'<img[^>]+src="(https://www\.skywalker\.gr/storage/clients/logos/[^"]+)"', block)
            job = make_job(
                source="skywalker", source_type="board", title=title, company=(company.group(1).replace("-", " ").title() if company else ""),
                url=f"https://www.skywalker.gr/el/aggelia-ergasias/{ad_id}/{urllib.parse.quote(slug)}", location=parsed["location"],
                description_text=parsed["description"], source_job_id=ad_id, date_posted=parsed["date"], work_mode=parsed["work_mode"],
                extra={"detail": "listing only; the site blocks automated reads of full ads", "logo": logo.group(1) if logo else ""},
            )
            jobs[job["id"]] = job
    return list(jobs.values())


def _location_hint(text_value: str) -> str:
    for marker in ("Θεσσαλονίκ", "Αττικ", "Αθήν", "Πειραι", "Thessaloniki", "Athens", "Κρήτ", "Πάτρ", "Λάρισ"):
        index = text_value.find(marker)
        if index >= 0:
            return text_value[max(0, index - 30): index + 40].strip()
    return "Greece"


def dypa_hotjobs(max_pages: int = 25) -> List[Dict]:
    jobs = []
    for page_number in range(1, max_pages + 1):
        try:
            page = http.text(f"https://www.dypa.gov.gr/hotjobs?page={page_number}", timeout=60)
        except Exception:
            if page_number == 1:
                raise
            break
        starts = [m.start() for m in re.finditer(r'<div[^>]+data-unique-id="', page)]
        if not starts:
            break
        for index, start in enumerate(starts):
            block = page[start: starts[index + 1] if index + 1 < len(starts) else start + 20000]
            attrs = dict(re.findall(r'data-([a-z_\-]+)="([^"]*)"', block[:1500]))
            region = attrs.get("nomos-name", "")
            if "ΘΕΣΣΑΛΟΝΙΚ" not in region.upper():
                continue
            headings = [strip_html(html_lib.unescape(h)) for h in re.findall(r"<h3[^>]*>(.*?)</h3>", block, re.S)]
            subtitle = re.search(r"<h4[^>]*>(.*?)</h4>", block, re.S)
            title = headings[0] if headings else attrs.get("category-name", "DYPA vacancy")
            link = re.search(r'href="(https://www\.dypa\.gov\.gr/[^"]*hotjobs[^"]*)"', block)
            jobs.append(make_job(
                source="dypa", source_type="public_registry", title=title, company="", url=link.group(1) if link else f"https://www.dypa.gov.gr/hotjobs#job-{attrs.get('unique-id')}",
                location=f"{region} (Greece)", description_text=strip_html(html_lib.unescape(block))[:4000], source_job_id=attrs.get("unique-id", ""),
                employment_type=attrs.get("apascolisi-text", ""), extra={"category": attrs.get("category-name", ""), "education": attrs.get("education_level", ""), "subtitle": strip_html(subtitle.group(1)) if subtitle else ""},
            ))
    return jobs


def dypa_career_day_employers(url: str = "https://www.dypa.gov.gr/57i-hmera-karieras-dypa-thessaloniki-11-12-septemvrioy-2026") -> List[Dict]:
    """Employers and their advertised specialties from the Thessaloniki Career Day table."""
    page = http.text(url)
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S)
    employers = []
    for row in rows:
        cells = [strip_html(html_lib.unescape(c)) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if len(cells) < 3 or not cells[1] or cells[1].upper().startswith("ΕΠΙΧΕΙΡΗΣΗ"):
            continue
        roles = [r.strip(" -•") for r in re.split(r"\n|- ", cells[2]) if r.strip(" -•")]
        employers.append({"name": cells[1].strip(), "roles": roles, "source": url})
    return employers


DIAVGEIA_ORGS = {
    "99202041": "Aristotle University of Thessaloniki",
    "99202922": "International Hellenic University",
    "99206919": "University of Macedonia",
    "100073032": "University of Macedonia research fund",
    "99220974": "CERTH (Centre for Research and Technology Hellas)",
    "99201074": "Thessaloniki Master Plan and Environment Organisation",
    "5009": "Region of Central Macedonia",
    "6114": "Municipality of Thessaloniki",
    "100047565": "Metropolitan Thessaloniki Development Agency",
    "99221105": "Thessaloniki Port Authority",
}


def diavgeia(days: int = 21) -> List[Dict]:
    """Calls for staff and project contracts published by Thessaloniki public bodies."""
    from datetime import date, timedelta
    since = (date.today() - timedelta(days=days)).isoformat()
    jobs = []
    for org, name in DIAVGEIA_ORGS.items():
        for query in ({"type": "Γ.3.1"}, {"q": "πρόσκληση εκδήλωσης ενδιαφέροντος"}):
            params = {"org": org, "size": 50, "from_issue_date": since, "sort": "recent"}
            params.update(query)
            data = http.get_json("https://diavgeia.gov.gr/opendata/search?" + urllib.parse.urlencode(params))
            for decision in data.get("decisions") or []:
                subject = decision.get("subject") or ""
                low = subject.lower()
                if not re.search(r"πρόσκληση|προκήρυξη|πλήρωση|σύμβαση έργου|συνεργάτ|θέσ", low):
                    continue
                if re.search(r"αποτελεσμ|έγκριση πρακτικ|ανάκληση|ορισμός επιτροπ|εκλεκτορικ|συγκρότηση|μέλους δεπ|θέσης δ\.?ε\.?π|καθηγητ|προμήθει|ανάθεση|εργασιών|υπηρεσιών καθαρ", low):
                    continue
                ada = decision.get("ada") or ""
                jobs.append(make_job(
                    source="diavgeia", source_type="public_registry", title=subject[:240], company=name,
                    url=f"https://diavgeia.gov.gr/decision/view/{ada}", location="Thessaloniki, Greece",
                    description_text=subject, source_job_id=ada, date_posted=decision.get("issueDate"),
                    extra={"document": decision.get("documentUrl") or "", "note": "Public notice. Read the PDF for requirements, usually in Greek."},
                ))
    return jobs
