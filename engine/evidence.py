"""Candidate evidence ledger, requirement matching and the factual linter."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from . import taxonomy

ROOT = Path(__file__).resolve().parent.parent
_cache: Optional[Dict] = None

END_DATES = {"april-2026": ("2026-04", "Jan 2026 – Apr 2026"), "may-2026": ("2026-05", "Jan 2026 – May 2026"), "current": ("", "Jan 2026 – present")}


def profile() -> Dict:
    global _cache
    if _cache is None:
        raw = os.environ.get("PROFILE_JSON") or (ROOT / "profile.json").read_text()
        data = json.loads(raw)
        overrides = ROOT / "data" / "confirmations.json"
        if overrides.exists():
            try:
                data["preferences"].update({k: v for k, v in json.loads(overrides.read_text()).items() if v not in (None, "")})
            except (ValueError, KeyError):
                pass
        end = data["preferences"].get("role2_end", "april-2026")
        for role in data["experience"]:
            if role["id"] == "exp_2" and end in END_DATES:
                role["end"], role["dates"] = END_DATES[end]
        if data["preferences"].get("r1_tech_claims") == "confirmed":
            for item in data["evidence"]:
                if item["id"] == "r1_tech":
                    item["confirmed"] = True
        _cache = data
    return _cache


def reset() -> None:
    global _cache
    _cache = None


def usable() -> List[Dict]:
    return [item for item in profile()["evidence"] if item.get("confirmed")]


def by_id(identifier: str) -> Optional[Dict]:
    return next((item for item in profile()["evidence"] if item["id"] == identifier), None)


STRONG = {"deadlines", "documentation", "confidentiality", "communication", "stakeholders", "international", "organisation", "office_tools", "crm", "atlassian", "hr_systems", "immigration", "english", "dutch", "degree_any", "masters"}
ACADEMIC = {"research", "data", "gis", "environment", "eu_policy"}
ABSENT = {"travel_industry", "finance", "proposals", "biology", "phd", "driving", "diving", "degree_business"}


def requirement_lines(body: str) -> List[str]:
    lines = [line.strip(" •-*\t") for line in re.split(r"[\n•]|(?<=[.;])\s+(?=[A-ZΑ-Ω])", body) if line.strip()]
    keep = []
    for line in lines:
        if 12 <= len(line) <= 400:
            keep.append(line)
    return keep[:220]


def importance(line: str) -> str:
    low = line.lower()
    if re.search(r"\b(must|required|essential|mandatory|necessary|you have|you bring|minimum)\b|απαραίτητ|απαιτείται", low):
        return "mandatory"
    if re.search(r"\b(plus|preferred|nice to have|advantage|asset|desirable|ideally|bonus)\b|επιθυμητ|θα εκτιμηθεί|θα συνεκτιμηθεί", low):
        return "preferred"
    return "inferred"


def years_required(body: str) -> Optional[int]:
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "ten": 10, "ενός": 1, "δύο": 2, "τριών": 3, "τεσσάρων": 4, "πέντε": 5}
    normalised = re.sub(r"\b(" + "|".join(words) + r")\b\s*\(?(\d)?\)?", lambda m: m.group(2) or str(words[m.group(1).lower()]), body, flags=re.I)
    found = []
    for match in re.finditer(r"(\d{1,2})\)?\s*\+?\s*(?:-|–|to|έως)?\s*(\d{1,2})?\s*\)?\s*(?:years|yrs|χρόνια|έτη|ετών)", normalised, re.I):
        context = normalised[max(0, match.start() - 70): match.end() + 70].lower()
        if re.search(r"experience|εμπειρ|προϋπηρεσ", context) and not re.search(r"up to \d", context[:80]):
            found.append(int(match.group(1)))
    return min(found) if found else None


def match_requirements(body: str, greek_strong: bool) -> List[Dict]:
    matrix: List[Dict] = []
    seen = set()
    evidence_index: Dict[str, List[str]] = {}
    for item in usable():
        for tag in item.get("tags", []):
            evidence_index.setdefault(tag, []).append(item["id"])
    for line in requirement_lines(body):
        for concept, label, patterns in taxonomy.REQUIREMENT_CONCEPTS:
            if concept in seen or concept == "years":
                continue
            if not taxonomy.find(patterns, line):
                continue
            seen.add(concept)
            level = importance(line)
            if concept == "greek_lang":
                status = "absent" if greek_strong else "weak"
                note = "Her Greek is A2." if greek_strong else "Her Greek is A2. This reads as useful rather than required."
                ids = ["lang_gr"]
            elif concept in STRONG:
                status, note, ids = "strong", "", evidence_index.get(concept, [])[:3]
                if not ids:
                    status = "transferable"
            elif concept in ACADEMIC:
                status, note, ids = "transferable", "From her degrees, not from a paid role.", evidence_index.get(concept, [])[:3]
            elif concept == "travel_required":
                status, note, ids = "unknown", "Travel willingness is not confirmed yet.", []
            elif concept in ABSENT:
                status, ids = "absent", []
                note = {
                    "proposals": "No proposal or grant-writing experience. Document assembly is the closest real skill.",
                    "degree_business": "Her degrees are " + " and ".join(e["credential"].split(" ", 1)[-1] for e in profile()["education"] if e["id"] in ("edu_ba", "edu_msc")) + ".",
                    "travel_industry": "No travel-industry job. Do not imply one.",
                    "finance": "No accounting or bookkeeping role.",
                    "biology": "No biology degree.",
                    "phd": "No doctorate.",
                    "driving": "No driving licence on her CVs.",
                    "diving": "No dive certificate.",
                }.get(concept, "")
            else:
                status, note, ids = "unknown", "", []
            matrix.append({"concept": concept, "requirement": line[:220], "label": label, "importance": level, "match": status, "evidence_ids": ids, "note": note})
    years = years_required(body)
    if years is not None:
        status = "strong" if years <= 1 else "transferable" if years == 2 else "weak" if years <= 3 else "absent"
        matrix.append({"concept": "years", "requirement": f"About {years}+ years of experience", "label": "Years of experience", "importance": "mandatory", "match": status, "evidence_ids": [e["id"] for e in usable() if e.get("parent", "").startswith("exp_")][:2], "note": "She has about one year of operations plus a few months in a second role."})
    return matrix


def coverage(matrix: List[Dict]) -> float:
    weights = {"mandatory": 3, "inferred": 2, "preferred": 1}
    values = {"strong": 1.0, "transferable": 0.6, "weak": 0.3, "unknown": 0.5, "absent": 0.0}
    total = sum(weights[row["importance"]] for row in matrix) or 1
    return sum(weights[row["importance"]] * values[row["match"]] for row in matrix) / total


FORBIDDEN = [
    (r"greek\s*\(?(b1|b2|c1|c2|fluent|native|proficient|advanced)", "Greek is A2. The document says something higher."),
    (r"(fluent|native|proficient) (in )?greek", "Greek is A2. The document says something higher."),
    (r"professional gis|gis (specialist|analyst|officer)|years of gis", "GIS is academic training, not a paid GIS job."),
    (r"(professional|paid) (esg|sustainability|research)|esg (analyst|consultant|specialist) at", "The master's is not paid ESG or research employment."),
    (r"environmental scientist|biologist|ecologist", "She is not a working scientist."),
    (r"lawyer|attorney|legal counsel|law firm", "Her visa role was at a placement agency, not a law firm."),
    (r"dive (certificate|certification)|open water|driving licen[cs]e|driver'?s licen[cs]e", "No dive or driving qualification is on her CVs."),
    (r"biology degree|degree in biology", "She has no biology degree."),
    (r"grant[- ]writ(er|ing) experience|experienced grant", "No grant-writing experience."),
    (r"\bphd\b|doctorate", "No doctorate."),
    (r"(managed|led|supervised) (a )?team", "No team-management experience on her CVs."),
]


def lint(text_value: str, *, allow_unconfirmed: bool = False, kind: str = "cv") -> List[Dict]:
    """Return problems. Severity critical blocks ready-to-apply."""
    problems: List[Dict] = []
    low = (text_value or "").lower()
    roles = profile()["experience"]
    for role in roles:
        employer, title = role["employer"].lower(), role["title"].lower()
        needs_title = kind == "cv" or re.search(r"sales", title)
        if needs_title and employer in low and title not in low:
            problems.append({"severity": "critical", "issue": f"{role['employer']} appears without the real title {role['title']}."})
        if re.search(r"\b(operations|account|office) (manager|coordinator|lead) (at|with) " + re.escape(employer), low):
            problems.append({"severity": "critical", "issue": f"The {role['employer']} title was altered."})
    for pattern, message in FORBIDDEN:
        hit = re.search(pattern, low)
        if hit and not re.search(r"(no|not|without)[^.]{0,40}" + re.escape(hit.group(0)), low):
            problems.append({"severity": "critical", "issue": message, "text": hit.group(0)})
    if not allow_unconfirmed and re.search(r"chatbot|subscription|refund|late payment|app feedback", low):
        problems.append({"severity": "critical", "issue": "Unconfirmed claims about refunds, subscriptions, app feedback or a chatbot."})
    if "atlas.ti" in low and by_id("msc_atlasti") and not by_id("msc_atlasti").get("confirmed"):
        problems.append({"severity": "critical", "issue": "ATLAS.ti is not confirmed on the CVs in this workspace."})
    for number in re.findall(r"\b\d{2,}(?:[.,]\d+)?\s*(%|percent|cases|clients|applications|candidates|files|eur|€)", low):
        problems.append({"severity": "critical", "issue": "An unsupported number or metric appears.", "text": number})
    allowed_employers = {r["employer"].lower() for r in roles}
    for employer in re.findall(r"(?:at|with|for) ([A-Z][A-Za-z&]+(?: [A-Z][A-Za-z&]+)?) \((?:20\d\d)", text_value or ""):
        if employer.lower() not in allowed_employers:
            problems.append({"severity": "warning", "issue": f"Unknown employer named: {employer}"})
    return problems
