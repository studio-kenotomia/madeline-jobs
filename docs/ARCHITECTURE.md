# Architecture

## Where things run

| Part | Runs on | Why |
| --- | --- | --- |
| Discovery, ranking, radar, documents, email | GitHub Actions, every 10 minutes | Keeps running when the Mac is asleep or offline |
| Phone dashboard | GitHub Pages at `studio-kenotomia.com/madeline-jobs/` | Static files plus an encrypted payload |
| Mac dashboard mirror | `server.py` on `127.0.0.1:8787` | Same web app, cached for offline use, sends commands |
| Apply Bridge | `bridge/bridge.mjs` (Playwright) on the Mac | Logins and cookies stay on the Mac |

Exactly one scheduler sends email: the Actions job runs `run.py --primary`. The Mac never runs discovery.

## Data flow

1. `run.py` loads `state/state.enc` from the `state` branch (one force-pushed commit, so history does not grow).
2. Open GitHub issues from the owner are applied as commands (status, feedback, facts, import, prepare).
3. Due sources run in parallel. Each source has its own interval and exponential backoff after failures.
4. Jobs are normalised, ranked, merged with existing records, versioned when the text changes, and closed when they disappear or pass their deadline.
5. The company graph and Opportunity Radar update; heavy radar signals run once a day.
6. CV and cover-letter models are rebuilt only when the job or the profile changes. Word and PDF files are rendered for the short list.
7. Exceptional alerts and the three-day digest go out through Resend with idempotency keys.
8. The site payload and files are encrypted with `DASH_KEY` (AES-256-GCM, PBKDF2-SHA256, 120k iterations) and deployed to Pages.

## Writing from the phone

The Pages site is static. Buttons open a prefilled GitHub issue. The `issues` trigger runs the workflow in `inbox` mode, which applies the command, closes the issue and redeploys within a couple of minutes. Only issues opened by the repository owner are honoured. The Mac dashboard creates the same issues through the API, so there is one writer.

## Privacy

The repository is public so Actions minutes are free. It contains no contact details, no CV text and no photo in plain form:

- `data/profile.enc` and `data/photo.enc` are sealed with `DASH_KEY` and unsealed only inside the runner.
- The state branch and the Pages payload are ciphertext.
- `profile.json`, the photo, caches, packages and the Playwright profile are gitignored.

## Not built, and why

- Web-search discovery is wired (`engine/adapters/search.py`) but off until a `BRAVE_API_KEY` secret exists.
- No LLM is used. Classification and tailoring are deterministic so nothing can invent a fact. A model adapter can be added later behind the same linter.
- Elevate Greece has no public data feed, so it is a manual watch.
- LinkedIn, UN Jobs and IOM disallow crawlers; Indeed and Glassdoor block bots. They are manual watches on purpose.
