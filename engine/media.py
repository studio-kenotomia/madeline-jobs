"""Every job gets a picture: company cover and logo, refreshed daily, with a location photo as the last resort."""

from __future__ import annotations

import hashlib
import io
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from . import http, registry

AGGREGATORS = {
    "remotive.com", "himalayas.app", "remoteok.com", "weworkremotely.com", "jobicy.com", "workingnomads.com", "arbeitnow.com", "kariera.gr", "www.kariera.gr",
    "skywalker.gr", "www.skywalker.gr", "jobs.workable.com", "jobs.lever.co", "boards.greenhouse.io", "job-boards.greenhouse.io", "jobs.ashbyhq.com",
    "apply.workable.com", "jobs.smartrecruiters.com", "careers.smartrecruiters.com", "dypa.gov.gr", "www.dypa.gov.gr", "diavgeia.gov.gr", "euraxess.ec.europa.eu",
    "myworkdayjobs.com", "careers-page.com", "www.careers-page.com", "www.workingnomads.com", "remote.co", "jobgether.com",
}
MEDIA_VERSION = 2
LOCATION_ART = {
    "thessaloniki": "art/thessaloniki.jpg",
    "greece": "art/greece.jpg",
    "remote": "art/remote.jpg",
}


def company_key(job: Dict) -> str:
    return re.sub(r"[^a-z0-9α-ω]+", "-", (job.get("company") or "unknown").lower()).strip("-")[:60] or "unknown"


def company_domain(job: Dict) -> str:
    extra = job.get("extra") or {}
    for candidate in (extra.get("company_website"), extra.get("company_url")):
        if candidate:
            host = urllib.parse.urlsplit(candidate if "://" in candidate else "https://" + candidate).netloc.lower()
            if host and not any(host.endswith(a) for a in AGGREGATORS):
                return host.removeprefix("www.")
    name = (job.get("company") or "").lower()
    for company in registry.companies():
        if company["name"].lower() == name and company.get("domain"):
            return company["domain"]
    host = urllib.parse.urlsplit(job.get("canonical_url") or "").netloc.lower()
    if host and not any(host.endswith(a) for a in AGGREGATORS):
        return host.removeprefix("www.")
    return ""


def location_art(job: Dict) -> str:
    geo = (job.get("analysis") or {}).get("geo") or {}
    if geo.get("thessaloniki") or geo.get("greece_remote") == "onsite":
        return LOCATION_ART["thessaloniki"]
    if re.search(r"greece|ελλάδα|athens|αθήνα", (job.get("location_raw") or "").lower()):
        return LOCATION_ART["greece"]
    return LOCATION_ART["remote"]


def _og_image(url: str) -> Optional[str]:
    try:
        page = http.text(url, timeout=15)
    except Exception:
        return None
    for pattern in (r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)', r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
                    r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)'):
        match = re.search(pattern, page, re.I)
        if match:
            return urllib.parse.urljoin(url, match.group(1).replace("&amp;", "&"))
    return None


def _flat(image) -> bool:
    """True for logo banners and text-on-white cards, which look broken when cropped as a photo."""
    sample = image.convert("RGB").resize((64, 36))
    pixels = list(sample.getdata())
    buckets = {}
    for r, g, b in pixels:
        key = (r // 24, g // 24, b // 24)
        buckets[key] = buckets.get(key, 0) + 1
    dominant = max(buckets.values()) / len(pixels)
    colourful = sum(1 for r, g, b in pixels if max(r, g, b) - min(r, g, b) > 40) / len(pixels)
    return dominant > 0.45 or (len(buckets) < 18 and colourful < 0.35)


def _download(url: str, folder: Path, *, kind: str) -> Optional[Dict]:
    from PIL import Image
    try:
        status, content_type, blob = http.fetch(url, timeout=20, retries=1, check_robots=False)
    except Exception:
        return None
    if not blob or len(blob) < 300 or ("image" not in content_type and not blob[:4] in (b"\x89PNG", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1", b"RIFF", b"GIF8")):
        return None
    try:
        image = Image.open(io.BytesIO(blob))
        image.load()
    except Exception:
        return None
    width, height = image.size
    if kind == "cover" and (width < 300 or height < 160 or width / max(1, height) > 3.2):
        return None
    if kind == "cover" and _flat(image):
        return None
    if kind == "logo" and (width < 32 or height < 32):
        return None
    digest = hashlib.sha256(blob).hexdigest()[:16]
    folder.mkdir(parents=True, exist_ok=True)
    if image.mode in ("P", "LA") or (image.mode == "P" and "transparency" in image.info):
        image = image.convert("RGBA")
    if kind == "cover":
        image = image.convert("RGB")
        image.thumbnail((1200, 1200))
        name = f"{digest}.jpg"
        image.save(folder / name, "JPEG", quality=78, optimize=True, progressive=True)
    else:
        image = image.convert("RGBA")
        image.thumbnail((256, 256))
        name = f"{digest}.png"
        image.save(folder / name, "PNG", optimize=True)
    return {"file": f"media/{name}", "hash": digest, "size": [width, height], "from": url}


def refresh(state: Dict, jobs: List[Dict], folder: Path, now: datetime, budget: int = 35) -> Dict[str, int]:
    """Fetch missing or day-old pictures for the companies behind the given jobs."""
    media = state.setdefault("media", {})
    usage = state.setdefault("media_usage", {})
    stats = {"checked": 0, "covers": 0, "logos": 0}
    ordered = sorted(jobs, key=lambda j: (company_key(j) in media, -((j.get("analysis") or {}).get("score") or 0)))
    seen = set()
    for job in ordered:
        key = company_key(job)
        if key in seen:
            continue
        seen.add(key)
        entry = media.get(key) or {}
        fresh = entry.get("v") == MEDIA_VERSION and entry.get("at") and now - datetime.fromisoformat(entry["at"]) < timedelta(hours=24)
        files_ok = (not entry.get("cover") or (folder / Path(entry["cover"]).name).exists()) and (not entry.get("logo") or (folder / Path(entry["logo"]).name).exists())
        if fresh and files_ok:
            continue
        if stats["checked"] >= budget:
            break
        stats["checked"] += 1
        domain = company_domain(job)
        extra = job.get("extra") or {}
        cover = None
        for url in [job.get("canonical_url"), f"https://{domain}" if domain else None]:
            if not url:
                continue
            host = urllib.parse.urlsplit(url).netloc.lower()
            if url == job.get("canonical_url") and any(host.endswith(a) for a in AGGREGATORS) and host not in ("job-boards.greenhouse.io", "jobs.lever.co", "jobs.ashbyhq.com", "apply.workable.com"):
                continue
            og = _og_image(url)
            if og:
                cover = _download(og, folder, kind="cover")
                if cover and len(usage.setdefault(cover["hash"], [])) >= 3 and key not in usage[cover["hash"]]:
                    cover = None
                if cover:
                    break
        logo = None
        for url in [extra.get("logo"), f"https://www.google.com/s2/favicons?domain={domain}&sz=256" if domain else None]:
            if url:
                logo = _download(url, folder, kind="logo")
                if logo:
                    break
        if cover:
            usage.setdefault(cover["hash"], [])
            if key not in usage[cover["hash"]]:
                usage[cover["hash"]].append(key)
            stats["covers"] += 1
        if logo:
            stats["logos"] += 1
        keep_old = entry.get("v") == MEDIA_VERSION
        media[key] = {"v": MEDIA_VERSION, "at": now.isoformat(), "domain": domain, "cover": (cover or {}).get("file") or (entry.get("cover") if keep_old else None), "logo": (logo or {}).get("file") or entry.get("logo"),
                      "cover_from": (cover or {}).get("from") or entry.get("cover_from")}
    return stats


def for_job(state: Dict, job: Dict) -> Dict:
    entry = (state.get("media") or {}).get(company_key(job)) or {}
    if entry.get("v") != MEDIA_VERSION:
        entry = {"logo": entry.get("logo")}
    art = location_art(job)
    return {"image": entry.get("cover") or art, "image_kind": "company" if entry.get("cover") else "location", "logo": entry.get("logo"), "art": art}


def prune(state: Dict, folder: Path) -> int:
    keep = set()
    for entry in (state.get("media") or {}).values():
        for field in ("cover", "logo"):
            if entry.get(field):
                keep.add(Path(entry[field]).name)
    removed = 0
    if folder.exists():
        for path in folder.iterdir():
            if path.name not in keep:
                path.unlink()
                removed += 1
    return removed
