"""Eligibility gate, explainable fit components, and recommendation tiers."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

from . import evidence, taxonomy

THESSALONIKI = [
    "thessaloniki", "tessaloniki", "salonica", "θεσσαλονίκ", "θεσ/νίκ", "kalamaria", "καλαμαριά", "pylaia", "pilea", "pylea", "πυλαία", "thermi", "θέρμη",
    "panorama", "πανόραμα", "evosmos", "εύοσμος", "neapoli", "νεάπολη", "stavroupoli", "σταυρούπολη", "ampelokipoi", "αμπελόκηποι", "chortiatis", "χορτιάτης",
    "oraiokastro", "ωραιόκαστρο", "sindos", "σίνδος", "kalochori", "καλοχώρι", "menemeni", "μενεμένη", "triandria", "τριανδρία", "toumpa", "τούμπα",
    "peraia", "περαία", "kordelio", "κορδελιό", "polichni", "πολίχνη", "agios pavlos", "nea michaniona",
]
REMOTE_OK = [
    r"\bgreece\b", r"ελλάδα", r"\bgr\b(?=$|[ ,;/)])", r"worldwide", r"anywhere", r"\bglobal\b", r"\bemea\b", r"\beurope\b", r"european union", r"\beu\b(?! citizens only in)",
    r"\beea\b", r"remote[- ]europe", r"cet\s*[±+-]", r"utc\s*[+±-]?\s*[0-3]\b", r"eastern europe", r"southern europe", r"balkans",
]
REMOTE_EXCLUDES = [
    r"\b(us|usa|u\.s\.|united states|canada|latam|latin america|apac|asia|india|philippines|brazil|mexico|australia|uk only|united kingdom only)\s*(only|based|residents|citizens)",
    r"must (be )?(based|located|reside) in (the )?(us|usa|united states|uk|united kingdom|canada|india|germany|france|spain|portugal|poland|netherlands)",
    r"authori[sz]ed to work in the (us|united states)", r"everyday americans", r"\bw-2\b", r"timezone outside europe", r"\bus clients\b",
]
US_HOURS = [r"(pst|est|cst|pacific|eastern|central) (time|hours|timezone)", r"(us|u\.s\.|american) (business )?hours", r"available (during|in) (the )?(us|u\.s\.|american|est|pst)", r"\b9(:00)? ?(am)? ?(-|to|–) ?(5|6)(:00)? ?pm (pst|est|pt|et)\b"]
OTHER_CITIES = [
    "athens", "αθήνα", "piraeus", "πειραιά", "marousi", "μαρούσι", "chalandri", "χαλάνδρι", "glyfada", "γλυφάδα", "heraklion", "ηράκλειο", "patra", "πάτρα",
    "larissa", "λάρισα", "ioannina", "ιωάννινα", "volos", "βόλος", "kilkis", "κιλκίς", "serres", "σέρρες", "katerini", "κατερίνη", "veria", "βέροια", "kavala", "καβάλα",
    "london", "amsterdam", "berlin", "paris", "madrid", "lisbon", "dublin", "brussels", "munich", "barcelona", "warsaw", "prague", "sofia", "bucharest", "cyprus", "limassol", "nicosia",
    "sheffield", "johannesburg", "new york", "san francisco", "toronto", "singapore",
]
AI_PATTERNS = [
    r"(use|in) (only )?your own words", r"ai[- ]generated", r"generated (content|answers|text)", r"plagiari[sz]m", r"chatgpt", r"large language model",
    r"without (the )?(use|help) of ai", r"do not use ai", r"use of ai (tools )?(will|may) (result in )?disqualif",
]
SCAM_PATTERNS = [r"telegram", r"whatsapp only", r"pay (a )?(fee|deposit)", r"training fee", r"processing fee", r"send money", r"crypto (payment|wallet)"]


def _low(*parts: str) -> str:
    return " ".join(p or "" for p in parts).lower()


COUNTRIES = [
    "philippines", "pakistan", "india", "georgia", "kenya", "nigeria", "south africa", "egypt", "united states", "usa", "canada", "mexico", "colombia", "argentina", "brazil",
    "chile", "peru", "belize", "costa rica", "new zealand", "australia", "japan", "china", "singapore", "malaysia", "indonesia", "vietnam", "thailand", "united arab emirates",
    "abu dhabi", "dubai", "saudi", "turkey", "israel", "ukraine", "serbia", "north macedonia", "albania", "bulgaria", "romania", "poland", "czech", "hungary", "germany",
    "france", "spain", "portugal", "italy", "netherlands", "belgium", "ireland", "united kingdom", "uk", "sweden", "denmark", "norway", "finland", "austria", "switzerland",
    "malta", "cyprus", "croatia", "slovenia", "slovakia", "lithuania", "latvia", "estonia", "luxembourg",
]
REGION_TITLE = re.compile(r"[-–(,]\s*(americas|apac|asia|us|usa|u\.s\.|north america|latam|uk|dach|nordics|india|japan|australia|anz|canada|mexico|brazil|shanghai|beijing|taipei|tokyo|singapore)\b", re.I)


def _countries_in(text_value: str) -> List[str]:
    return [c for c in COUNTRIES if re.search(rf"\b{re.escape(c)}\b", text_value)]


def geography(job: Dict) -> Dict:
    loc = _low(job.get("location_raw"), " ".join(job.get("remote_regions") or []))
    body = _low(job.get("description_text"))[:6000]
    mode = (job.get("work_mode") or "").lower()
    remote_words = bool(re.search(r"\bremote\b|telecommute|work from home|home[- ]based|τηλεργασία|εξ αποστάσεως|fully distributed", loc + " " + mode + " " + body[:1500]))
    hybrid = "hybrid" in loc + mode or "υβριδικ" in loc + body[:800]
    in_thess = any(word in loc for word in THESSALONIKI)
    other_city = next((city for city in OTHER_CITIES if city in loc), None)
    result = {"work_mode": "onsite", "greece_remote": "no", "evidence": "", "thessaloniki": in_thess, "verdict": "ineligible"}
    title_region = REGION_TITLE.search(job.get("title") or "")
    if title_region and not re.search(r"emea|europe|greece|worldwide", (job.get("title") or "").lower()):
        result.update(evidence=f"The title limits it to {title_region.group(1)}.")
        return result
    if in_thess:
        result.update(work_mode="remote" if mode == "remote" else ("hybrid" if hybrid else "onsite"), greece_remote="onsite", verdict="ok", evidence=job.get("location_raw", "")[:120])
        return result
    excluded = taxonomy.find(REMOTE_EXCLUDES, loc + " " + body)
    night_ok = str((evidence.profile().get("preferences") or {}).get("us_night_hours", "unknown")) == "yes"
    if not excluded and not night_ok:
        hours = taxonomy.find(US_HOURS, body)
        if hours:
            excluded = f"US working hours ({hours})"
    if remote_words or mode == "remote":
        result["work_mode"] = "remote"
        region_hit = taxonomy.find(REMOTE_OK, loc)
        strong_region = bool(region_hit and re.search(r"emea|europe|\beu\b|eea|european union|cet|balkans", region_hit))
        countries = [c for c in _countries_in(loc) if c not in ("greece",)]
        if re.search(r"greece|ελλάδα", loc):
            result.update(greece_remote="confirmed", evidence="Remote, and the listing names Greece.", verdict="ok")
            if other_city:
                result.update(greece_remote="likely", evidence=f"Remote, listed under {other_city.title()}. Confirm she can work from Thessaloniki.")
            return result
        if excluded and not strong_region:
            result.update(greece_remote="no", evidence=excluded, verdict="ineligible")
            return result
        if region_hit:
            confirmed = bool(re.search(r"worldwide|anywhere|emea|europe|\beu\b|eea|global", region_hit))
            if job.get("source_type") == "board" and not strong_region:
                confirmed = False
            result.update(greece_remote="confirmed" if confirmed else "likely", evidence=region_hit, verdict="ok")
            return result
        if countries or other_city:
            place = (countries or [other_city])[0]
            result.update(greece_remote="no", evidence=f"Remote, but hiring in {place.title()}.", verdict="ineligible")
            return result
        body_region = taxonomy.find(REMOTE_OK, body[:4000])
        if body_region and re.search(r"worldwide|anywhere|emea|europe|greece", body_region):
            result.update(greece_remote="likely", evidence=f"The description mentions {body_region}.", verdict="ok")
            return result
        result.update(greece_remote="unclear", evidence="Says remote without naming Greece, Europe, EMEA or worldwide.", verdict="verify")
        return result
    if other_city:
        result.update(evidence=f"On-site in {other_city}", verdict="ineligible")
        return result
    if re.search(r"greece|ελλάδα", loc) or not loc.strip():
        if any(word in body[:3000] for word in THESSALONIKI):
            result.update(thessaloniki=True, verdict="ok", greece_remote="onsite", evidence="The description names Thessaloniki.")
        elif re.search(r"greece|ελλάδα", loc):
            result.update(verdict="verify", greece_remote="unclear", evidence="Greece, but the city is not stated.")
        else:
            result.update(evidence="No location stated.", verdict="verify", greece_remote="unclear")
        return result
    result.update(evidence=f"Location: {job.get('location_raw', '')[:80]}")
    return result


def ai_policy(job: Dict) -> Tuple[str, str]:
    text_value = _low(job.get("title"), job.get("description_text"), " ".join(q.get("label", "") for q in job.get("extra", {}).get("questions", [])))
    hit = taxonomy.find(AI_PATTERNS, text_value)
    if hit:
        return "prohibited", hit
    if "canonical" in _low(job.get("company")):
        return "prohibited", "Canonical's application form disqualifies AI-generated answers."
    return "unknown", ""


def freshness(job: Dict, first_seen: str) -> Dict:
    today = datetime.now(timezone.utc)
    badges = []
    hours_seen = None
    if first_seen:
        try:
            seen = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
            hours_seen = (today - seen).total_seconds() / 3600
        except ValueError:
            pass
    posted = job.get("date_posted")
    age_days = None
    if posted:
        try:
            age_days = (today.date() - date.fromisoformat(posted)).days
        except ValueError:
            pass
    if hours_seen is not None and hours_seen < 1:
        badges.append("Just found")
    elif hours_seen is not None and hours_seen < 6:
        badges.append("Found in the last 6 hours")
    if age_days == 0:
        badges.append("Posted today")
    deadline_days = None
    if job.get("valid_through"):
        try:
            deadline_days = (date.fromisoformat(job["valid_through"]) - today.date()).days
            if 0 <= deadline_days <= 5:
                badges.append("Closing soon")
        except ValueError:
            pass
    if not posted:
        badges.append("Posting date unknown")
    score = 1.0
    if age_days is not None:
        score = 1.0 if age_days <= 2 else 0.85 if age_days <= 7 else 0.65 if age_days <= 21 else 0.45 if age_days <= 45 else 0.25
    elif hours_seen is not None:
        score = 0.9 if hours_seen < 48 else 0.6
    return {"badges": badges, "age_days": age_days, "hours_since_seen": hours_seen, "deadline_days": deadline_days, "score": score}


def evaluate(job: Dict, *, first_seen: str = "", soft_weights: Optional[Dict] = None) -> Dict:
    title = job.get("title") or ""
    body = job.get("description_text") or ""
    low_title = title.lower()
    low = _low(title, body)
    family, excluded = taxonomy.family_of(title, body)
    blockers: List[str] = []
    gaps: List[str] = []
    unknowns: List[str] = []
    reasons: List[str] = []
    rejection = ""

    if excluded:
        rejection = f"excluded:{excluded}"
    if excluded == "engineering" and re.search(r"project (assistant|coordinator)", low_title):
        rejection = ""
    if not rejection and (
        re.search(r"degree in biology|biologist|πτυχίο βιολογ", low) and re.search(r"diving|open water|scuba|κατάδυσ|driver'?s licen|δίπλωμα οδήγησης", low)
        or re.search(r"\bphd\b|ph\.d|doctorate|διδακτορικ", low) and re.search(r"required|must hold|απαραίτητ|essential", low)
    ):
        rejection = "specialist_requirement"
    if not rejection and family is None:
        rejection = "not_target_role"
    if not rejection and taxonomy.SENIOR_TITLE.search(low_title) and not taxonomy.MANAGER_OK.search(low_title):
        if re.search(r"\b(senior|sr\.?|staff|principal|head|director|vp|vice president|chief|διευθυντ|προϊστάμεν)\b", low_title):
            rejection = "seniority"
    geo = geography(job)
    if not rejection and geo["verdict"] == "ineligible":
        rejection = "geography"

    greek_strong = bool(taxonomy.find(taxonomy.GREEK_STRONG, low))
    greek_posting = job.get("language") == "el"
    english_first = bool(taxonomy.find(taxonomy.ENGLISH_FIRST, low))
    if not rejection and greek_posting and not english_first:
        greek_strong = True
    matrix = evidence.match_requirements(body, greek_strong)
    concepts = {row["concept"]: row for row in matrix}

    for concept in ("biology", "phd", "diving"):
        row = concepts.get(concept)
        if row and row["importance"] != "preferred":
            if not rejection:
                rejection = "specialist_requirement"
            blockers.append(row["note"] or row["label"])
    years_row = concepts.get("years")
    years = evidence.years_required(body)
    if years is not None and years >= 5 and not rejection:
        rejection = "seniority"

    result = {"rejection": rejection, "family": family, "geo": geo, "matrix": matrix}
    if rejection:
        return result

    if greek_strong:
        blockers.append("The ad is in Greek or asks for strong Greek. Her Greek is A2." if greek_posting else "The ad asks for strong Greek. Her Greek is A2.")
    elif geo["greece_remote"] == "onsite" and not english_first and not concepts.get("dutch"):
        unknowns.append("Greek is not mentioned. Ask whether the team works in English.")
    if concepts.get("driving") and concepts["driving"]["importance"] == "mandatory":
        blockers.append("A driving licence is required and is not on her CVs.")
    if concepts.get("degree_business") and concepts["degree_business"]["importance"] != "preferred":
        gaps.append("They ask for a business or technical degree. " + next((r["note"] for r in matrix if r["concept"] == "degree_business"), ""))
    if concepts.get("travel_industry"):
        gaps.append("Travel or events experience is listed. She has none, so the case rests on transferable organisation skills.")
    if concepts.get("proposals") and family == "projects":
        gaps.append("Proposal or tender experience is listed. She has document-assembly experience, not grant writing.")
    if concepts.get("finance") and concepts["finance"]["importance"] == "mandatory":
        gaps.append("Finance or bookkeeping is required. She has no accounting role.")
    commercial = bool(re.search(r"commercial|retail network|sales network|sales team|sales support|δίκτυο πωλήσεων", low))
    if commercial:
        gaps.append("The role supports a sales or retail operation. She does not want sales work.")
    if concepts.get("travel_required"):
        unknowns.append("Travel is part of the job. Her willingness to travel is not confirmed.")
    if years_row and years_row["match"] in ("weak", "absent"):
        gaps.append(f"They ask for about {years}+ years. She has roughly one and a half years across two roles.")
    if geo["greece_remote"] == "unclear":
        unknowns.append(geo["evidence"])
    if re.search(r"pacific time|pst\b|9:00 a\.?m\.? to 6:00 p\.?m\.? (pacific|pt)|us hours|est hours|eastern time", low):
        gaps.append("The hours are US time, which is evening or night in Thessaloniki.")
    if re.search(r"answering phones|front desk|reception|τηλεφωνικό κέντρο|υποδοχή", low):
        gaps.append("Part of the day is reception or phones.")

    policy, policy_evidence = ai_policy(job)
    scam = [hit for hit in (taxonomy.find([p], low) for p in SCAM_PATTERNS) if hit]

    role_fit = {
        "mobility": 0.95, "executive_admin": 0.9, "operations": 0.85, "documentation": 0.8, "people_ops": 0.75, "projects": 0.78,
        "education_admin": 0.85, "research": 0.7, "environment": 0.68,
    }.get(family, 0.5)
    if family == "environment" and re.search(r"assistant|coordinator|junior|trainee|intern|officer", low_title):
        role_fit = 0.78
    if commercial:
        role_fit -= 0.2
    if re.search(r"freelance|contractor|commission", low_title):
        role_fit -= 0.1
        gaps.append("Freelance or contractor terms. Check pay and contract before applying.")
    virtual = bool(re.search(r"virtual (assistant|executive|administrative)|\bva\b", low_title) or re.search(r"virtual assistant (agency|company)|our clients are (us|american)", low))
    if virtual:
        gaps.append("Virtual-assistant agencies usually mean US clients, US hours and low hourly pay.")
    if re.search(r"\b(junior|entry|graduate|trainee|assistant|associate|intern)\b", low_title):
        seniority_fit = 1.0
    elif re.search(r"\bmanager\b|υπεύθυν", low_title) and not taxonomy.MANAGER_OK.search(low_title):
        seniority_fit = 0.35
        gaps.append("The title says manager. Likely above one and a half years of experience.")
    else:
        seniority_fit = 0.85
    if years is not None:
        seniority_fit = min(seniority_fit, 1.0 if years <= 1 else 0.8 if years == 2 else 0.55 if years <= 3 else 0.35)

    language_fit = 0.2 if greek_strong else 0.75 if taxonomy.find(taxonomy.GREEK_SOFT, low) else 0.85 if (geo["greece_remote"] == "onsite" and not english_first) else 1.0
    if english_first:
        language_fit = min(1.0, language_fit + 0.1)
        reasons.append("The workplace runs in English.")
    if concepts.get("dutch"):
        reasons.append("Dutch is asked for. She is a native speaker.")
    location_fit = {"onsite": 1.0, "confirmed": 0.95, "likely": 0.8, "unclear": 0.5, "no": 0.0}[geo["greece_remote"]]
    coverage = evidence.coverage(matrix) if matrix else 0.55
    education_fit = 0.6 if concepts.get("degree_business") else 1.0
    domain = 0.6
    if re.search(r"environment|sustainab|esg|biodivers|climate|περιβάλλ|βιωσιμ", low):
        domain = 1.0
    if re.search(r"immigration|visa|relocation|mobility", low):
        domain = 1.0
    if re.search(r"\beu\b|european|horizon|erasmus|interreg|ευρωπαϊκ", low):
        domain = max(domain, 0.9)
    fresh = freshness(job, first_seen)
    source_conf = {"ats": 1.0, "jsonld": 0.9, "board": 0.75, "page": 0.8, "public_registry": 0.85, "manual": 0.9}.get(job.get("source_type", ""), 0.7)
    effort = 0.9 if policy == "prohibited" else 1.0
    pay = 1.0
    salary = job.get("salary") or {}
    floor = (evidence.profile()["preferences"] or {}).get("salary_floor_eur_month")
    if floor and salary.get("max") and str(salary.get("currency", "")).upper() in ("EUR", "€"):
        try:
            monthly = float(salary["max"]) / (12 if "year" in str(salary.get("period", "")).lower() else 1)
            if monthly < float(floor):
                pay = 0.6
                gaps.append(f"Published pay is under the floor of €{floor} a month.")
        except (TypeError, ValueError):
            pass

    components = {
        "role_fit": role_fit, "evidence_coverage": round(coverage, 3), "location_fit": location_fit, "language_fit": language_fit,
        "seniority_fit": seniority_fit, "education_fit": education_fit, "domain_interest": domain, "freshness": fresh["score"],
        "source_confidence": source_conf, "application_effort": effort, "compensation_quality": pay,
    }
    base = (
        role_fit * 22 + coverage * 22 + location_fit * 14 + language_fit * 12 + seniority_fit * 12
        + education_fit * 5 + domain * 6 + source_conf * 4 + effort * 1 + pay * 2
    )
    soft = 0.0
    for key, weight in (soft_weights or {}).items():
        if key.startswith("family:") and key[7:] == family:
            soft += weight
        if key.startswith("company:") and key[8:] == (job.get("company") or "").lower():
            soft += weight
    base = max(0.0, min(100.0, base + max(-8.0, min(8.0, soft))))
    overall = round(base * (0.88 + 0.12 * fresh["score"]))

    strong_rows = [row for row in matrix if row["match"] == "strong"]
    for row in strong_rows[:3]:
        reasons.append(f"Strong: {row['label'].lower()}.")
    transferable = [row for row in matrix if row["match"] == "transferable"]
    if transferable:
        reasons.append("Transferable: " + ", ".join(row["label"].lower() for row in transferable[:2]) + ".")
    if geo["greece_remote"] == "onsite":
        reasons.insert(0, "In Thessaloniki, where she lives.")
    elif geo["greece_remote"] == "confirmed":
        reasons.insert(0, f"Remote and open to Greece ({geo['evidence']}).")

    eligibility = "ELIGIBLE"
    if blockers:
        eligibility = "ELIGIBLE_WITH_GAP"
    if geo["verdict"] == "verify":
        eligibility = "VERIFY"
    if scam:
        eligibility = "VERIFY"
        unknowns.append("Possible scam signal: " + ", ".join(scam))

    hard_blocker = any("strong Greek" in b or "driving" in b for b in blockers)
    if hard_blocker:
        overall = min(overall, 55)
    capped = commercial or seniority_fit < 0.5 or virtual or (years is not None and years >= 3)
    if capped:
        overall = min(overall, 73)
    if eligibility == "VERIFY":
        tier = "verify" if overall >= 70 else "stretch" if overall >= 45 else "archive"
    elif overall >= 86 and not blockers and not gaps[:1] and geo["greece_remote"] in ("onsite", "confirmed") and source_conf >= 0.9 and fresh["score"] >= 0.85:
        tier = "exceptional"
    elif overall >= 74 and not hard_blocker:
        tier = "apply"
    elif overall >= 62 and not hard_blocker:
        tier = "worth"
    elif overall >= 42:
        tier = "stretch"
    else:
        tier = "archive"

    urgency = "watch"
    if tier in ("exceptional", "apply"):
        urgency = "apply_today" if (fresh["age_days"] is not None and fresh["age_days"] <= 3) or "Closing soon" in fresh["badges"] or (fresh["hours_since_seen"] or 99) < 24 else "prepare_this_week"
    elif tier == "worth":
        urgency = "prepare_this_week"

    result.update({
        "score": overall, "tier": tier, "eligibility": eligibility, "components": components, "reasons": reasons[:5], "gaps": gaps[:4],
        "blockers": blockers[:3], "unknowns": unknowns[:3], "ai_policy": policy, "ai_policy_evidence": policy_evidence,
        "freshness": fresh, "urgency": urgency, "variant": variant(family, low), "greek_gist": taxonomy.gist(body) if job.get("language") == "el" or "ελλην" in low else [],
        "scam_signals": scam,
    })
    return result


def variant(family: Optional[str], low: str) -> str:
    if family in ("mobility", "executive_admin", "operations", "projects", "research", "environment", "people_ops", "education_admin", "documentation"):
        if family == "operations" and re.search(r"executive|travel operations|corporate", low):
            return "executive_admin"
        return family
    return "operations"
