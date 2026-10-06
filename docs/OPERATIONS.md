# Operations

## Secrets (GitHub repository settings)

| Name | Purpose |
| --- | --- |
| `DASH_KEY` | Passphrase for the profile, state, payload and files |
| `RESEND_API_KEY` | Email through Resend (sender domain `oneball.gr`) |
| `ALERT_TO` | Optional recipient override; otherwise the profile's `alert_to` |
| `BRAVE_API_KEY` | Optional web-search discovery |

Variable `RESEND_FROM` can override the sender, default `Job radar <jobs@oneball.gr>`.

## Schedule

- `radar.yml` runs every 10 minutes and on demand. Each source runs only when its own interval has passed, so core employer boards refresh every 20 minutes.
- Exceptional alerts are sent at most once per job.
- The digest goes out every third day at 10:00 Europe/Athens, starting 7 October 2026. A late run still sends that day's digest once; a missed digest older than two days is skipped.

## Commands

- Force every source now: Actions → radar → Run workflow → force.
- Phone commands: buttons open a GitHub issue with the command in the title.
- Mac: `zsh ~/madeline-jobs/install.sh` installs the mirror and the bridge. Dashboard `http://127.0.0.1:8787`, health `http://127.0.0.1:8787/health`.

## Local test cycle

```
cd ~/madeline-jobs
DASH_KEY=… .venv/bin/python run.py --state /tmp/state.enc --site /tmp/site --only greenhouse:canonical workable-search --force
.venv/bin/python -m unittest discover -s tests
```

Local runs omit `--primary`, so they never email.

## Backups and restore

The `state` branch holds one commit; the previous run's state is the commit before a force push. To restore, check out an older workflow artifact or push a saved `state.enc` to the branch. The first prototype database is backed up under `data/backups/`, and its saved, applied and skipped statuses were migrated by fingerprint.

## Deleting personal data

Delete `data/profile.enc` and `data/photo.enc`, delete the `state` branch, and unpublish Pages. Locally remove `profile.json`, `data/photo.png`, `data/cache`, `data/packages` and `playwright-profile`.
