"""Resend email: rare immediate alerts and a briefing every third day at 10:00 Athens time."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import escape
from typing import Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

ATHENS = ZoneInfo("Europe/Athens") if ZoneInfo else timezone(timedelta(hours=3))
DASHBOARD = os.environ.get("DASHBOARD_URL", "https://studio-kenotomia.com/madeline-jobs/")
SENDER = os.environ.get("RESEND_FROM", "Job radar <jobs@oneball.gr>")
RECIPIENTS = [r.strip() for r in os.environ.get("ALERT_TO", "").split(",") if r.strip()]
ANCHOR = date(2026, 10, 7)


def link(job_id: str = "") -> str:
    """Deep link that opens the job card and unlocks her documents on that phone."""
    key = os.environ.get("DASH_KEY", "")
    parts = [f"job={job_id}"] if job_id else []
    if key:
        parts.append(f"k={key}")
    return DASHBOARD + ("#" + "&".join(parts) if parts else "")


def configured() -> bool:
    return bool(os.environ.get("RESEND_API_KEY"))


def send(subject: str, html_body: str, text_body: str, idempotency_key: str, to: Optional[List[str]] = None) -> Dict:
    key = os.environ.get("RESEND_API_KEY")
    if not key:
        return {"ok": False, "error": "RESEND_API_KEY is not set"}
    payload = {"from": SENDER, "to": to or RECIPIENTS, "subject": subject, "html": html_body, "text": text_body}
    request = urllib.request.Request(
        "https://api.resend.com/emails", data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Idempotency-Key": idempotency_key[:256], "User-Agent": "madeline-job-radar"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return {"ok": True, "id": json.loads(response.read().decode()).get("id")}
    except urllib.error.HTTPError as error:
        return {"ok": False, "error": f"{error.code} {error.read().decode()[:300]}"}
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


def due_digest(now: datetime, sent: List[Dict]) -> Optional[str]:
    """Return the due date (ISO) of an unsent digest, if 10:00 Athens on a due day has passed."""
    local = now.astimezone(ATHENS)
    today = local.date()
    days = (today - ANCHOR).days
    if days < 0:
        return None
    last_due = today - timedelta(days=days % 3)
    if last_due == today and local.hour < 10:
        last_due -= timedelta(days=3)
    if last_due < ANCHOR:
        return None
    if any(item.get("due") == last_due.isoformat() for item in sent):
        return None
    if (today - last_due).days > 2:
        return None
    return last_due.isoformat()


def next_digest(now: datetime, sent: List[Dict]) -> str:
    local = now.astimezone(ATHENS)
    day = max(ANCHOR, local.date())
    for _ in range(4):
        if (day - ANCHOR).days % 3 == 0:
            moment = datetime(day.year, day.month, day.day, 10, tzinfo=ATHENS)
            if moment > local and not any(s.get("due") == day.isoformat() for s in sent):
                return moment.strftime("%A %d %B, 10:00 Athens")
        day += timedelta(days=1)
    return ""


def _job_block(job: Dict, rank_line: str) -> str:
    a = job["analysis"]
    reasons = "".join(f"<li>{escape(r)}</li>" for r in a.get("reasons", [])[:3])
    gaps = "".join(f"<li>{escape(g)}</li>" for g in (a.get("blockers", []) + a.get("gaps", []))[:2])
    salary = job.get("salary") or {}
    pay = f"{salary.get('min')}–{salary.get('max')} {salary.get('currency', '')} {salary.get('period', '')}".strip() if salary.get("published") and salary.get("min") else "Not published"
    geo = a.get("geo", {})
    remote_line = {"onsite": "In Thessaloniki", "confirmed": "Remote, Greece allowed", "likely": "Remote, Greece likely allowed", "unclear": "Remote, Greece not confirmed"}.get(geo.get("greece_remote"), "")
    posted = job.get("date_posted") or "unknown"
    deadline = job.get("valid_through") or "none stated"
    docs = "CV and cover letter ready" if job.get("doc_status") in ("draft", "ready") else "Documents not generated yet"
    friction = "Employer bans AI-written answers, so she writes the form answers herself." if a.get("ai_policy") == "prohibited" else "Standard application."
    return f"""<div style="border:1px solid #e4dcd0;border-radius:12px;padding:14px;margin:12px 0">
<div style="font-size:12px;color:#5e574e;text-transform:uppercase;letter-spacing:.05em">{escape(rank_line)}</div>
<div style="font-size:18px;font-weight:600;margin:4px 0">{escape(job['title'])}</div>
<div style="color:#444">{escape(job['company'])} · {escape(job.get('location_raw') or '')} · {escape(remote_line)}</div>
<div style="color:#444;font-size:14px;margin-top:4px">Posted {escape(posted)} · first seen {escape((job.get('first_seen') or '')[:16].replace('T', ' '))} UTC · deadline {escape(deadline)} · pay {escape(pay)}</div>
<ul style="margin:8px 0 0;padding-left:18px">{reasons}</ul>
<ul style="margin:4px 0 0;padding-left:18px;color:#8a3d12">{gaps}</ul>
<div style="font-size:14px;color:#444;margin-top:6px">{escape(docs)}. {escape(friction)}</div>
<div style="margin-top:10px"><a href="{link(job['id'])}" style="background:#e94f6a;color:#fff;padding:10px 14px;border-radius:999px;text-decoration:none;font-weight:600">Open the card</a>
&nbsp;<a href="{escape(job.get('application_url') or job.get('canonical_url') or '')}" style="color:#1f4e79">Original listing</a></div></div>"""


def exceptional_email(job: Dict) -> Dict:
    a = job["analysis"]
    minutes = int((datetime.now(timezone.utc) - datetime.fromisoformat(job["first_seen"])).total_seconds() // 60)
    where = {"onsite": "Thessaloniki", "confirmed": "Remote, Greece allowed"}.get(a["geo"]["greece_remote"], job.get("location_raw", ""))
    subject = f"Exceptional match: {job['title']} — {where} — found {minutes} min ago"
    html_body = f"""<div style="font-family:-apple-system,Segoe UI,sans-serif;max-width:620px;color:#1c1915">
<p>One new role clears every bar: right city or Greece-friendly remote, right level, strong evidence, no blocker.</p>
{_job_block(job, f"{a['score']}/100 · Exceptional")}
<p style="color:#5e574e;font-size:13px">Nothing has been submitted. Review the CV, then apply from the employer's page.</p></div>"""
    text_body = f"{subject}\n\n{job['company']} · {job.get('location_raw', '')}\n" + "\n".join("- " + r for r in a.get("reasons", [])[:3]) + f"\n\n{link(job['id'])}"
    return {"subject": subject, "html": html_body, "text": text_body}


def digest_email(best: List[Dict], radar: List[Dict], stats: Dict, since: str) -> Dict:
    strong = len(best)
    radar_part = f" + {len(radar)} compan{'y' if len(radar) == 1 else 'ies'} to watch" if radar else ""
    subject = f"Job briefing — {strong} strong new role{'s' if strong != 1 else ''}{radar_part}" if strong else f"Job briefing — nothing worth applying to since {since}"
    blocks = []
    if best:
        blocks.append("<h2 style='font-size:16px'>Best new opportunity</h2>" + _job_block(best[0], f"{best[0]['analysis']['score']}/100 · {best[0]['analysis']['tier'].replace('_', ' ').title()}"))
    if len(best) > 1:
        blocks.append("<h2 style='font-size:16px'>Other worthwhile roles</h2>" + "".join(_job_block(j, f"{j['analysis']['score']}/100 · {j['analysis']['tier'].title()}") for j in best[1:3]))
    if radar:
        items = "".join(f"<li><b>{escape(r['company'])}</b> — {escape(r['why'])} <i>No confirmed vacancy.</i></li>" for r in radar[:3])
        blocks.append(f"<h2 style='font-size:16px'>Opportunity radar</h2><ul>{items}</ul>")
    reasons = ", ".join(f"{k.replace('excluded:', '').replace('_', ' ')} {v}" for k, v in sorted(stats.get("rejections", {}).items(), key=lambda kv: -kv[1])[:6])
    noise = f"{stats.get('raw', 0)} listings checked across {stats.get('sources', 0)} sources since {since}. Most were dropped for: {reasons or 'nothing notable'}."
    html_body = f"""<div style="font-family:-apple-system,Segoe UI,sans-serif;max-width:640px;color:#1c1915">
{''.join(blocks) or '<p>No new role was strong enough to recommend. The search kept running the whole time.</p>'}
<h2 style='font-size:16px'>Ignored noise</h2><p style="color:#5e574e">{escape(noise)}</p>
<p><a href="{link()}">Open the job app</a></p></div>"""
    text_lines = [subject, ""] + [f"- {j['title']} — {j['company']} ({j['analysis']['score']}/100) {link(j['id'])}" for j in best[:3]] + ["", noise]
    return {"subject": subject, "html": html_body, "text": "\n".join(text_lines)}
