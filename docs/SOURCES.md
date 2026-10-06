# Sources

All sources are defined in `engine/registry.py`. Employer boards come from `data/companies.json`.

## Employer applicant-tracking systems (public job-board endpoints)

Greenhouse, Lever, Ashby, SmartRecruiters, Workday (Pfizer's Thessaloniki hub, Fragomen), Manatal (Pinewood, Anatolia, ACT). Adapters also exist for Workable accounts, Recruitee and Personio. Interval 20–60 minutes.

## Job boards with machine-readable feeds

| Source | Method | Interval |
| --- | --- | --- |
| Workable job search | JSON, 14 queries for Thessaloniki, Greece and remote Europe, paginated | 20 min |
| Kariera.gr | Office categories, then JobPosting JSON-LD on unseen detail pages | 40 min |
| Skywalker.gr | Listing cards only; full ads block automated readers | 40 min |
| Remotive, Jobicy, Remote OK, Himalayas, We Work Remotely, Working Nomads, Arbeitnow | Public JSON or RSS | 60–120 min |

## Greek public sources

- DYPA Hot Jobs: paginated HTML cards, filtered to Thessaloniki.
- DYPA Thessaloniki Career Day: the employer and specialty table seeds the company graph.
- Diavgeia: staff calls (type Γ.3.1) and calls for expressions of interest from Aristotle University, International Hellenic University, University of Macedonia, CERTH, the Region, the Municipality, the port and the development agency.

## EU and institutions

Cedefop (EU agency in Pylaia; RSS plus the traineeship page), EURAXESS (Greece searches, detail pages), Black Sea Trade and Development Bank, CERTH project positions, DRAXIS, iSea (PDF parsed), EKBY, American Farm School / Perrotis.

## Radar signals

EU Funding & Tenders search, DYPA Career Day participation, relevant hiring history, speculative-CV invitations, and ATS detection on company domains (`engine/adapters/ats.detect`).

## Generic tools

- `model.jobpostings_from_html`: Schema.org JobPosting JSON-LD, including `applicantLocationRequirements` and `validThrough`.
- `pages.sitemap_job_urls`: robots.txt sitemaps, newest job-like URLs first.
- `ats.detect`: Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Recruitee, Personio, Teamtailor, Manatal and Workday signatures.

## Politeness

`engine/http.py` checks robots.txt (RFC 9309) for every host, spaces requests per host, retries 429 and 5xx with backoff, and refuses private addresses for imported URLs. No CAPTCHA solving, no proxy rotation, no logins.

## Health

Every source records last attempt, last success, item count, duration, consecutive failures and next run. A source that normally returns jobs and suddenly returns none, or returns items without titles or links, is marked degraded. The Sources screen shows healthy, degraded, failing, waiting, manual and planned groups.
