# Ranking

Code: `engine/rank.py`, vocabulary in `engine/taxonomy.py`, requirement matching in `engine/evidence.py`.

## 1. Eligibility gate

A job is dropped before scoring when:

- the title is in an excluded family: sales (including alliances, revenue and sales operations), customer service and support (including collections), moderation, hospitality, retail, teaching, engineering and IT administration, trades, health, finance specialists, legal, marketing
- the title is plainly senior (senior, head, director, chief)
- five or more years are required
- a biology degree plus diving or driving, or a doctorate, is required
- the location fails geography

## 2. Geography

- On-site or hybrid: Thessaloniki and its suburbs only.
- Remote: `confirmed` when the listing names Greece, Europe, EMEA, EU or worldwide; `likely` when it names Greece under another city; `unclear` for bare "remote"; `no` when it names another country, a US-only rule, or a regional title suffix such as "- Americas".
- Unclear but otherwise strong roles go to Verify location, never Apply today.

## 3. Components

Role fit, evidence coverage, location, language, seniority, education, domain interest, freshness, source confidence, application effort, and pay against an optional floor. Weighted into 0–100, then nudged by freshness (12% at most) and by soft feedback weights (±8 at most).

## 4. Language

Strong Greek wording, or a Greek-language ad without an English-working signal, is a blocker: score capped at 55, never Apply today. An on-site Thessaloniki ad that does not mention Greek gets a small penalty and an "ask whether the team works in English" note.

## 5. Tiers

- Exceptional: 86+, no gaps or blockers, Thessaloniki or confirmed remote, a direct source, fresh. Usually none.
- Apply today: 74+. Roles that support a sales network, and manager titles without a junior marker, are capped at 73.
- Worth considering: 62+.
- Verify location: 70+ with unclear geography.
- Stretch: 42+. Archive below.

The dashboard shows at most 2 exceptional, 3 apply, 3 worth, 3 verify and 3 radar items. Everything else stays searchable.

## Regression tests

`tests/test_rank.py` with `tests/fixtures.json`: Canonical executive assistant (apply, AI ban, the "diversity is not diving" bug), Canonical travel operations (degree gap), DOTSOFT proposal assistant (Greek blocker), Pinewood teacher, iSea field role, Dutch customer support, US-only remote, remote tied to another country, bare remote, a Thessaloniki English-language project coordinator (top), a native-Greek secretarial ad, sales operations, an Americas-only title, and a manager title. Document tests cover exact titles, Greek level, degree names, evidence traces, linter coverage and real DOCX output.
