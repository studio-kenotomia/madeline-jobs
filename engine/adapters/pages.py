"""EU bodies, research networks, Thessaloniki institutions and generic employer pages."""

from __future__ import annotations

import html as html_lib
import re
import urllib.parse
from typing import Dict, List, Set

from .. import http
from ..model import job_from_jsonld, jobpostings_from_html, make_job, strip_html


def cedefop() -> List[Dict]:
    """Cedefop is the EU agency based in Pylaia, Thessaloniki. Vacancies and traineeships."""
    jobs = []
    xml = http.text("https://www.cedefop.europa.eu/en/about-cedefop/job-opportunities/vacancies.rss")
    for block in re.findall(r"<item>(.*?)</item>", xml, re.S):
        title = re.search(r"<title>(.*?)</title>", block, re.S)
        link = re.search(r"<link>(.*?)</link>", block, re.S)
        description = re.search(r"<description>(.*?)</description>", block, re.S)
        date_value = re.search(r"<pubDate>(.*?)</pubDate>", block, re.S)
        if not title or not link:
            continue
        body = html_lib.unescape(description.group(1)) if description else ""
        url = link.group(1).strip()
        try:
            page = http.text(url)
            body = strip_html(page)[:12000]
        except Exception:
            pass
        jobs.append(make_job(
            source="cedefop", source_type="page", title=html_lib.unescape(title.group(1)).strip(), company="Cedefop (EU agency)",
            url=url, location="Thessaloniki (Pylaia), Greece", description_text=body, source_job_id=url, date_posted=date_value.group(1) if date_value else "",
        ))
    trainee = http.text("https://www.cedefop.europa.eu/en/about-cedefop/job-opportunities/trainees")
    body = strip_html(trainee)
    if re.search(r"(call|applications?) (is |are )?(now )?open|apply (now|by)|deadline", body, re.I):
        jobs.append(make_job(
            source="cedefop", source_type="page", title="Cedefop traineeship (paid, graduates)", company="Cedefop (EU agency)",
            url="https://www.cedefop.europa.eu/en/about-cedefop/job-opportunities/trainees", location="Thessaloniki (Pylaia), Greece",
            description_text=body[:8000], source_job_id="cedefop-trainees",
        ))
    return jobs


def euraxess(known: Set[str], detail_limit: int = 30) -> List[Dict]:
    ids: List[str] = []
    for term in ("Thessaloniki", "Greece environment", "Greece project", "Greece research assistant"):
        for page in (0, 1):
            listing = http.text("https://euraxess.ec.europa.eu/jobs/search?" + urllib.parse.urlencode({"search_api_fulltext": term, "page": page}))
            for job_id in re.findall(r'href="/jobs/(\d+)"', listing):
                if job_id not in ids:
                    ids.append(job_id)
    jobs = []
    fetched = 0
    for job_id in ids:
        if job_id in known or fetched >= detail_limit:
            continue
        fetched += 1
        url = f"https://euraxess.ec.europa.eu/jobs/{job_id}"
        try:
            page = http.text(url)
        except Exception:
            continue
        body = strip_html(page)
        country = re.search(r"Country\s+([A-Z][a-zA-Z ]+?)\s+(?:City|State|Type)", body)
        city = re.search(r"City\s+([^\n]+?)\s+(?:Website|Street|Postal)", body)
        if not country or "Greece" not in country.group(1):
            jobs.append(make_job(source="euraxess", source_type="page", title="(outside Greece)", company="", url=url, location=country.group(1) if country else "Unknown", description_text="", source_job_id=job_id))
            continue
        title = re.search(r"<h1[^>]*>\s*<span[^>]*>(.*?)</span>", page, re.S) or re.search(r'<meta property="og:title" content="([^"]+)"', page)
        org = re.search(r"Organisation/Company\s+(.+?)\s+(?:Department|Research Field)", body)
        deadline = re.search(r"Application Deadline\s+(\d{1,2} \w{3} \d{4})", body)
        jobs.append(make_job(
            source="euraxess", source_type="page", title=strip_html(title.group(1)) if title else "Research position", company=org.group(1) if org else "",
            url=url, location=f"{city.group(1) if city else ''}, Greece", description_text=body[:15000], source_job_id=job_id, valid_through=deadline.group(1) if deadline else "",
        ))
    return jobs


def bstdb() -> List[Dict]:
    """Black Sea Trade and Development Bank, headquartered in Thessaloniki. English working language."""
    page = http.text("https://www.bstdb.org/career")
    jobs = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        cells = [strip_html(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) < 4:
            continue
        ref, position, closing, status = cells[:4]
        if re.search(r"closed|filled|under review", status, re.I):
            continue
        link = re.search(r'href="([^"]+)"', row)
        url = urllib.parse.urljoin("https://www.bstdb.org/career", link.group(1)) if link else f"https://www.bstdb.org/career#ref-{ref}"
        jobs.append(make_job(
            source="bstdb", source_type="page", title=position, company="Black Sea Trade and Development Bank", url=url,
            location="Thessaloniki, Greece", description_text=f"{position}. Status: {status}. Closing date: {closing}.", source_job_id=ref, valid_through=closing,
        ))
    return jobs


def certh() -> List[Dict]:
    jobs = []
    for category in (1, 2, 3, 4):
        url = f"https://www.certh.gr/jobs.browsecurrentprojectsinexternalsite.el.aspx?idProjectCategoryType={category}"
        page = http.text(url)
        for href, label in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.S):
            name = strip_html(label)
            if len(name) < 12 or not re.search(r"θέσ|πρόσκλ|σύμβασ|position|call|job|ερευν|συνεργ", name, re.I):
                continue
            full = urllib.parse.urljoin(url, href)
            jobs.append(make_job(source="certh", source_type="page", title=name[:220], company="CERTH (Thessaloniki)", url=full, location="Thessaloniki (Thermi), Greece", description_text=name, source_job_id=full))
    return jobs


def draxis() -> List[Dict]:
    """DRAXIS lists open roles on its careers page. Old position pages stay in the sitemap even when closed."""
    page = http.text("https://draxis.gr/workwith/")
    block = page[page.lower().find("open positions"):][:20000] if "open positions" in page.lower() else ""
    titles = [strip_html(t) for t in re.findall(r"<h[2-4][^>]*>(.*?)</h[2-4]>", block, re.S)]
    jobs = []
    for href in re.findall(r'href="(https://draxis\.gr/position/[^"]+)"', block):
        detail = http.text(href)
        title = re.search(r"<h1[^>]*>(.*?)</h1>", detail, re.S)
        body = strip_html(detail)
        location = re.search(r"(Thessaloniki|Athens)[^,\n]*,[^,\n]*Greece", body)
        jobs.append(make_job(source="draxis", source_type="page", title=strip_html(title.group(1)) if title else href, company="DRAXIS Environmental", url=href, location=location.group(0) if location else "Greece", description_text=body[:12000], source_job_id=href))
    return jobs


def html_announcements(source: str, company: str, url: str, location: str, include: str, exclude: str = r"$^") -> List[Dict]:
    page = http.text(url)
    jobs = []
    seen = set()
    for href, label in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.S):
        name = strip_html(label)
        full = urllib.parse.urljoin(url, href)
        if full in seen or len(name) < 8:
            continue
        if not re.search(include, full + " " + name, re.I) or re.search(exclude, full + " " + name, re.I):
            continue
        seen.add(full)
        jobs.append(make_job(source=source, source_type="page", title=name[:220], company=company, url=full, location=location, description_text=name, source_job_id=full))
    return jobs


def isea() -> List[Dict]:
    page = http.text("https://isea.com.gr/career-opportunities/")
    jobs = []
    for heading in re.findall(r"<h3[^>]*>(.*?)</h3>", page, re.S):
        name = strip_html(heading)
        if not name.lower().startswith("job position"):
            continue
        index = page.find(heading)
        nearby = strip_html(page[index: index + 3000])
        pdf = re.search(r'href="(https://isea\.com\.gr/wp-content/uploads/isea-jobs/[^"]+\.pdf)"', page[index: index + 5000])
        body = nearby
        if pdf:
            try:
                from pypdf import PdfReader
                import io
                raw = http.fetch(pdf.group(1))[2]
                body = nearby + "\n" + "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(raw)).pages)
            except Exception:
                pass
        deadline = re.search(r"deadline:?\s*(\d{1,2}(?:st|nd|rd|th)? \w+ \d{4})", body, re.I)
        jobs.append(make_job(
            source="isea", source_type="page", title=name.replace("Job position:", "").strip(), company="iSea", url=pdf.group(1) if pdf else "https://isea.com.gr/career-opportunities/",
            location="Thessaloniki, Greece", description_text=body[:12000], source_job_id=(pdf.group(1) if pdf else name), valid_through=re.sub(r"(st|nd|rd|th)", "", deadline.group(1)) if deadline else "",
        ))
    return jobs


def generic_jobposting_pages(urls: List[str], source: str, company: str) -> List[Dict]:
    jobs = []
    for url in urls:
        try:
            page = http.text(url)
        except Exception:
            continue
        for item in jobpostings_from_html(page):
            jobs.append(job_from_jsonld(item, source=source, url=url, company=company))
    return jobs


def sitemap_job_urls(domain: str, limit: int = 40) -> List[str]:
    """Discover job-like URLs from robots.txt sitemaps, newest first."""
    urls: List[tuple] = []
    candidates = []
    try:
        robots = http.text(f"https://{domain}/robots.txt", check_robots=False)
        candidates = re.findall(r"(?im)^sitemap:\s*(\S+)", robots)
    except Exception:
        pass
    candidates = candidates or [f"https://{domain}/sitemap.xml", f"https://{domain}/sitemap_index.xml"]
    queue = list(candidates)
    visited = set()
    while queue and len(visited) < 8:
        sitemap = queue.pop(0)
        if sitemap in visited:
            continue
        visited.add(sitemap)
        try:
            xml = http.text(sitemap)
        except Exception:
            continue
        for loc in re.findall(r"<sitemap>\s*<loc>(.*?)</loc>", xml, re.S):
            if re.search(r"job|career|position|vacanc|θεσ", loc, re.I):
                queue.insert(0, loc.strip())
        for loc, mod in re.findall(r"<url>\s*<loc>(.*?)</loc>(?:.*?<lastmod>(.*?)</lastmod>)?", xml, re.S):
            if re.search(r"/(jobs?|careers?|positions?|vacanc|openings?|θεσεις)/[^/]+", loc, re.I):
                urls.append((mod or "", loc.strip()))
    urls.sort(reverse=True)
    return [u for _, u in urls[:limit]]
