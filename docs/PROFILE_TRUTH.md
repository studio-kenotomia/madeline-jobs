# Profile truth

The candidate profile is a sealed evidence ledger (`data/profile.enc`). Unseal locally with `DASH_KEY=… .venv/bin/python scripts/seal.py unseal`, edit `profile.json`, then `seal` and commit `data/profile.enc`.

## Structure

- `identity`, `languages`, `education`, `experience`
- `evidence[]`: one record per claim, with `id`, `parent` (the role or degree), `fact`, `tags`, `source` (which CV), `confirmed`, and `needs_confirmation` where relevant
- `summaries` and `cover` openings per role family
- `skills[]`: each skill lists the evidence that supports it
- `preferences`: conservative defaults for unresolved facts

Only `confirmed: true` evidence reaches documents. Each CV bullet keeps the evidence id it came from, shown in the studio under "Why is each line allowed?".

## Hard rules enforced by the linter (`engine/evidence.py`, mirrored in `web/studio.js`)

- Job titles stay exactly as on the CVs. In a CV, an employer named without its real title is a critical error; in a cover letter, the rule applies to the sales title.
- Greek never above the level in the ledger.
- GIS, statistics and research methods are described as academic training.
- No paid ESG, research or scientist employment.
- No law-firm framing of the visa role.
- No driving, diving, biology, doctorate or grant-writing claims.
- No team-management claims.
- No numbers or metrics that the ledger does not contain.
- Unconfirmed claims (marked `needs_confirmation`) are blocked until the Facts screen confirms them.

A document with a critical problem stays `needs_fix` and cannot be marked ready.

## Facts to confirm

Answered from the Facts screen and stored in state:

- `role2_end`: April 2026 (default), May 2026, or current
- `travel_weeks`: can she travel 2–4 times a year for 1–2 weeks
- `us_night_hours`
- `r1_tech_claims`: the unconfirmed refunds, subscriptions, app feedback and chatbot work
- `salary_floor_eur_month`

Discovery never waits for these.
