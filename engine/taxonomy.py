"""Vocabulary for discovery and classification, in English and Greek."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

ROLE_FAMILIES: Dict[str, List[str]] = {
    "executive_admin": [
        r"executive assistant", r"personal assistant", r"corporate administrator", r"office (administrator|coordinator|manager|assistant)",
        r"administrative (assistant|coordinator|officer|specialist|associate)", r"team assistant", r"administrator\b",
        r"γραμματε", r"διοικητικ(ή|ός|ου|ής) (υποστήριξ|υπάλληλ|στέλεχ)", r"υπάλληλος γραφείου", r"βοηθός διοίκησης", r"back[- ]?office",
    ],
    "operations": [
        r"operations (coordinator|assistant|associate|specialist|administrator|analyst)", r"business operations", r"travel operations",
        r"business services", r"operations officer", r"coordinator\b", r"συντονιστ",
    ],
    "projects": [
        r"project (assistant|coordinator|officer|administrator|support)", r"programme (assistant|coordinator|officer)", r"program (assistant|coordinator)",
        r"proposal", r"tender", r"grant", r"eu (project|programme|program|funded)", r"horizon europe", r"erasmus", r"interreg",
        r"βοηθός έργου", r"συντονιστής έργου", r"διαχείριση έργ", r"ευρωπαϊκ(ά|ών) προγρ", r"συγχρηματοδοτ", r"εσπα", r"προτάσε", r"διαγωνισμ",
    ],
    "research": [
        r"research (assistant|coordinator|administrator|officer|associate|analyst)", r"junior (research|data) analyst", r"policy (assistant|officer|analyst)",
        r"european affairs", r"ερευνητικ", r"βοηθός ερευνητή", r"ερευνητικός συνεργάτης",
    ],
    "environment": [
        r"sustainab", r"\besg\b", r"environment", r"biodiversit", r"ecosystem", r"climate", r"conservation", r"natural resource",
        r"\bgis\b", r"qgis", r"περιβάλλ", r"βιωσιμ", r"αειφορ", r"βιοποικιλ", r"οικοσυστ", r"κλιματ",
    ],
    "mobility": [
        r"immigration", r"\bvisa (coordinator|specialist|officer|administrator|operations|case)", r"relocation (coordinator|specialist|consultant|manager|advisor|associate)",
        r"global mobility", r"mobility (coordinator|specialist|associate|advisor)", r"case ?worker", r"case (manager|coordinator|officer)", r"work permit", r"μετανάστ",
        r"move coordinator",
    ],
    "people_ops": [
        r"people operations", r"hr (coordinator|assistant|administrator|services|operations|generalist)", r"human resources (assistant|coordinator)",
        r"talent (operations|coordinator)", r"recruit(ing|ment) coordinator", r"onboarding (coordinator|specialist)", r"ανθρώπινου δυναμικού",
    ],
    "education_admin": [
        r"student services", r"admissions (officer|administrator|coordinator)", r"registrar", r"international (office|programmes|programs)", r"academic (administrator|coordinator)",
    ],
    "documentation": [
        r"documentation (specialist|assistant|coordinator)", r"document control", r"compliance (assistant|coordinator|associate)", r"quality (assistant|documentation)",
        r"data entry",
    ],
}

EXCLUDED_FAMILIES: Dict[str, List[str]] = {
    "sales": [
        r"\bsales\b", r"account executive", r"\bsdr\b", r"\bbdr\b", r"business development", r"key account", r"account manager",
        r"commercial (manager|executive|specialist)", r"lead generation", r"inside sales", r"πωλ(ήσ|ητ|ησ)", r"σύμβουλος πωλήσεων", r"εμπορικ(ός|ού) αντιπρόσωπ",
        r"\bbroker\b", r"telemarketing", r"retention (agent|specialist|representative)", r"διακράτησης", r"alliances?\b", r"partnerships? (manager|lead|director)",
        r"ecosystem development", r"revenue operations", r"sales operations", r"\bgtm\b", r"go-to-market",
    ],
    "customer_service": [
        r"customer (service|support|success|care|experience|operations)", r"client (support|services representative)", r"help ?desk", r"service desk",
        r"call (center|centre)", r"contact (center|centre)", r"εξυπηρέτηση πελατ", r"τηλεφωνικ(ή|ό) (εξυπηρ|κέντρ)", r"\bagent\b", r"εκπρόσωπος",
        r"technical support", r"support (specialist|representative|agent|associate)", r"\bbpo\b", r"overdue|receivables|collections?\b|debt", r"ληξιπρόθεσμ",
    ],
    "moderation": [r"content (moderat|review)", r"trust (and|&) safety", r"moderator"],
    "hospitality": [
        r"bartender", r"barista", r"waiter", r"waitress", r"waitstaff", r"\bcook\b", r"\bchef\b", r"housekeep", r"receptionist", r"front desk", r"hotel",
        r"σερβιτ", r"μάγειρ", r"καμαριέρ", r"ρεσεψιον", r"μπάρμαν", r"υπάλληλος υποδοχής",
    ],
    "retail": [r"cashier", r"retail (associate|assistant)", r"store (associate|assistant)", r"ταμ(ίας|ία)", r"πωλήτρια", r"εποχική απασχόληση", r"merchandis"],
    "teaching": [r"teacher", r"\btutor\b", r"lecturer", r"professor", r"faculty", r"εκπαιδευτικ(ός|ού)", r"καθηγητ", r"δ\.?ε\.?π\.?", r"μέλους δεπ"],
    "engineering": [
        r"engineer", r"developer", r"programmer", r"devops", r"\bsre\b", r"architect", r"data scientist", r"machine learning", r"software",
        r"\bsap\b", r"(it|systems?|network|database|netsuite|jira|salesforce|linux) (administrator|support|admin)", r"consultant",
        r"(salesforce|hubspot|endpoint|intune|defender|encompass|crm|okta|jamf|servicenow|m365|microsoft 365|azure|aws|cloud|platform|zendesk|workday|marketo|revenue systems)\b[^,;]*administrator",
        r"administrator\s*[-–(]\s*(revenue|systems|it|cloud|crm)", r"\bmatch administrator\b",
        r"μηχανικ", r"προγραμματιστ", r"ηλεκτρολόγ", r"ψυκτικ", r"υδραυλικ", r"τεχνικ(ός|ού) ",
    ],
    "unpaid": [r"volunteer", r"unpaid", r"εθελοντ", r"internship \(unpaid\)"],
    "trades": [r"driver", r"οδηγ", r"warehouse", r"αποθήκ", r"picker", r"forklift", r"εργάτ", r"production (worker|operator)", r"χειριστ", r"courier", r"security guard", r"φύλακ"],
    "health": [r"nurse", r"νοσηλ", r"doctor", r"ιατρ", r"pharmacist", r"φαρμακοποι", r"therapist", r"physio", r"μαί(α|ες)", r"psychologist"],
    "finance_specialist": [r"accountant", r"λογιστ", r"payroll", r"auditor", r"controller", r"treasury", r"tax (senior|associate|manager)", r"actuar"],
    "legal": [r"lawyer", r"attorney", r"solicitor", r"counsel", r"δικηγόρ", r"paralegal", r"legal (assistant|secretary|intake)", r"law firm", r"litigation", r"intake (specialist|coordinator)"],
    "marketing": [r"marketing", r"social media", r"seo\b", r"copywriter", r"growth"],
}

SENIOR_TITLE = re.compile(r"\b(senior|sr\.?|staff|principal|lead|head|director|vp|vice president|chief|manager|διευθυντ|προϊστάμεν|υπεύθυν)\b", re.I)
MANAGER_OK = re.compile(r"office manager|project manager assistant|assistant (to the )?manager", re.I)

GREEK_STRONG = [
    r"(άριστη|πολύ καλή|εξαιρετική|άψογη) γνώση (της )?ελληνικ", r"(fluent|native|excellent|very good|proficient|strong|business[- ]level|full professional|perfect|advanced)[^.\n]{0,30}\bgreek\b",
    r"\bgreek\b[^.\n]{0,25}(native|fluent|c1|c2|b2|mother tongue|proficien)", r"μητρική γλώσσα[^.\n]{0,20}ελληνικ", r"greek and english (are )?(required|essential|necessary)",
    r"fluency in (both )?greek", r"ελληνικά[^.\n]{0,20}(άριστα|πολύ καλά|επίπεδο γ2|επίπεδο γ1|c2|c1)", r"(proficiency|fluency|command|knowledge) (in|of) (the )?(both )?greek",
    r"greek language (proficiency|skills)", r"άριστη γνώση ελληνικής", r"\bboth greek and english\b", r"\bgreek (&|and) english (language|languages|skills|written|verbal|communication)",
    r"(written|verbal|communication)[^.\n]{0,40}\bgreek\b",
]
GREEK_SOFT = [r"greek (is )?(a plus|an advantage|preferred|nice to have|desirable)", r"basic greek", r"knowledge of greek (is )?(a plus|an asset)", r"γνώση ελληνικών θα εκτιμηθεί"]
ENGLISH_FIRST = [r"working language is english", r"english[- ]speaking (team|environment|company)", r"international (team|environment|company)", r"english only", r"no greek required"]

REQUIREMENT_CONCEPTS: List[Tuple[str, str, List[str]]] = [
    ("deadlines", "Meet deadlines and manage several tasks", [r"deadline", r"multiple (tasks|priorities|cases|projects)", r"prioriti", r"time management", r"προθεσμ", r"πολλαπλ(ών|ές) (εργασι|έργ)"]),
    ("documentation", "Documents, records, filing", [r"document", r"record", r"filing", r"files?\b", r"αρχεί", r"έγγραφ", r"δικαιολογητικ"]),
    ("confidentiality", "Discretion with sensitive information", [r"confidential", r"discretion", r"sensitive", r"εχεμύθ", r"εμπιστευτικ"]),
    ("communication", "Clear written and spoken communication", [r"communication", r"communicat", r"επικοινων", r"written and (verbal|spoken)"]),
    ("stakeholders", "Coordinate with several people or teams", [r"stakeholder", r"cross-functional", r"liais", r"coordinat", r"συντονισ", r"συνεργασία με"]),
    ("international", "International or multicultural work", [r"international", r"multicultural", r"diverse (cultures|backgrounds)", r"global team", r"διεθν"]),
    ("organisation", "Strong organisation and attention to detail", [r"organi[sz]ation", r"organi[sz]ed", r"attention to detail", r"detail[- ]oriented", r"accura", r"οργανωτικ", r"λεπτομέρει"]),
    ("office_tools", "Microsoft Office or Google Workspace", [r"ms office", r"microsoft office", r"\bexcel\b", r"\bword\b", r"powerpoint", r"outlook", r"google (workspace|sheets|docs)"]),
    ("crm", "CRM or case-management systems", [r"\bcrm\b", r"case management", r"ticketing", r"salesforce", r"hubspot"]),
    ("atlassian", "Jira or Confluence", [r"\bjira\b", r"confluence"]),
    ("hr_systems", "HR systems", [r"hibob", r"\bhris\b", r"workday", r"bamboohr", r"personio"]),
    ("immigration", "Immigration or visa processes", [r"immigration", r"\bvisa", r"residence permit", r"work permit", r"relocation", r"global mobility"]),
    ("english", "English", [r"\benglish\b", r"αγγλικ"]),
    ("dutch", "Dutch", [r"\bdutch\b", r"nederlands", r"flemish", r"ολλανδικ"]),
    ("greek_lang", "Greek", [r"\bgreek\b", r"ελληνικ"]),
    ("research", "Research and report writing", [r"research", r"desk research", r"report(s|ing)\b", r"έρευν", r"αναφορ(ές|ών)"]),
    ("data", "Data handling and analysis", [r"data (analysis|collection|entry|processing)", r"statistic", r"quantitative", r"spreadsheet", r"ανάλυση δεδομένων"]),
    ("gis", "GIS or mapping", [r"\bgis\b", r"qgis", r"arcgis", r"γεωγραφικ(ά|ών) συστ"]),
    ("environment", "Environment, sustainability or biodiversity knowledge", [r"sustainab", r"\besg\b", r"environment", r"biodiversit", r"ecosystem", r"climate", r"περιβάλλ", r"βιωσιμ"]),
    ("eu_policy", "EU institutions, policy or programmes", [r"\beu\b", r"european (union|commission|affairs|programmes|projects)", r"horizon", r"policy", r"ευρωπαϊκ"]),
    ("proposals", "Proposals, tenders or grants", [r"proposal", r"tender", r"grant", r"προτάσ", r"διαγωνισμ", r"εσπα"]),
    ("travel_industry", "Travel or events industry experience", [r"travel (industry|agency|management)", r"event (management|planning|organi)", r"booking (travel|flights)"]),
    ("finance", "Bookkeeping, accounting or budgets", [r"bookkeep", r"accounting", r"invoic", r"budget", r"payroll", r"λογιστ", r"τιμολόγ"]),
    ("degree_business", "Degree in business, economics or a technical field", [r"degree in (business|economics|finance|accounting|engineering|computer)", r"business or technical (subject|degree)", r"πτυχίο (οικονομικ|διοίκησης επιχειρ)"]),
    ("degree_any", "University degree", [r"bachelor", r"university degree", r"\bdegree\b", r"πτυχίο", r"aei", r"αει"]),
    ("masters", "Master's degree", [r"master'?s", r"\bmsc\b", r"μεταπτυχιακ"]),
    ("biology", "Biology or natural-science degree", [r"degree in biology", r"biologist", r"βιολόγ", r"πτυχίο βιολογ", r"marine biolog"]),
    ("phd", "Doctorate", [r"\bphd\b", r"ph\.d", r"doctorate", r"διδακτορικ"]),
    ("driving", "Driving licence", [r"driver'?s licen[cs]e", r"driving licen[cs]e", r"δίπλωμα οδήγησης"]),
    ("diving", "Dive certification", [r"diving cert", r"open water", r"scuba", r"κατάδυσ"]),
    ("travel_required", "Travel for work", [r"travel (up to|frequently|required|regularly|internationally)", r"willing(ness)? to travel", r"ταξίδ"]),
    ("years", "Years of experience", [r"(\d+)\+?\s*(?:-|to|–)?\s*\d*\s*years", r"(\d+)\s*(?:χρόνια|έτη)"]),
]

GLOSSARY = [
    (r"άριστη γνώση (της )?ελληνικής( γλώσσας)?|άριστη γνώση ελληνικών", "excellent Greek required"),
    (r"πολύ καλή γνώση (της )?ελληνικής|πολύ καλή γνώση ελληνικών", "very good Greek required"),
    (r"πολύ καλή γνώση (της )?αγγλικής|πολύ καλή γνώση αγγλικών", "very good English"),
    (r"άριστη γνώση (της )?αγγλικής|άριστη γνώση αγγλικών", "excellent English"),
    (r"πτυχίο αει", "university degree"),
    (r"προϋπηρεσία", "prior experience"),
    (r"πλήρης απασχόληση", "full-time"),
    (r"μερική απασχόληση", "part-time"),
    (r"τηλεργασία", "remote work"),
    (r"υβριδικ", "hybrid"),
    (r"απαραίτητα προσόντα", "required qualifications"),
    (r"επιθυμητά προσόντα", "desired qualifications"),
    (r"σύμβαση έργου", "fixed project contract"),
    (r"πρόσκληση εκδήλωσης ενδιαφέροντος", "call for expressions of interest"),
    (r"δίπλωμα οδήγησης", "driving licence"),
    (r"στρατιωτικές υποχρεώσεις", "military service completed (applies to Greek men)"),
]


def find(patterns: List[str], text_value: str) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, text_value, re.I)
        if match:
            return match.group(0)
    return None


def family_of(title: str, body: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (positive family, excluded family) from the title first, then the opening of the description."""
    lowered = title.lower()
    excluded = None
    for name, patterns in EXCLUDED_FAMILIES.items():
        if find(patterns, lowered):
            excluded = name
            break
    positive = None
    for name, patterns in ROLE_FAMILIES.items():
        if find(patterns, lowered):
            positive = name
            break
    if positive is None:
        head = body[:600].lower()
        for name, patterns in ROLE_FAMILIES.items():
            if name == "environment":
                continue
            if find(patterns, head):
                positive = name
                break
    return positive, excluded


def gist(text_value: str) -> List[str]:
    notes = []
    for pattern, english in GLOSSARY:
        if re.search(pattern, text_value, re.I):
            notes.append(english)
    return notes
