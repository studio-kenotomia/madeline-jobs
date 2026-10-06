#!/usr/bin/env python3
"""Mac side: mirrors the cloud dashboard for offline use, forwards commands, and runs the Apply Bridge.

Discovery does not run here. The scheduler lives in GitHub Actions so it keeps going when the lid is closed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine import crypto  # noqa: E402

DATA = ROOT / "data"
CACHE = DATA / "cache"
PACKAGES = DATA / "packages"
WEB = ROOT / "web"
PORT = 8787
PAGES = os.environ.get("DASHBOARD_URL", "https://studio-kenotomia.com/madeline-jobs/")
REPO = "studio-kenotomia/madeline-jobs"
CACHE.mkdir(parents=True, exist_ok=True)
PACKAGES.mkdir(parents=True, exist_ok=True)
STATUS = {"last_sync": None, "sync_error": "", "bridge_runs": 0}


def passphrase() -> str:
    for line in (DATA / "ACCESS.txt").read_text().splitlines():
        if line.startswith("Passphrase:"):
            return line.split(":", 1)[1].strip()
    return ""


def github_token() -> str:
    result = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n", text=True, capture_output=True)
    for line in result.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    return ""


def github(path: str, method: str = "GET", payload=None):
    token = github_token()
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}{path}", method=method, data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "job-radar-mac", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode()
        return json.loads(body) if body else {}


def sync_once() -> None:
    try:
        payload = urllib.request.urlopen(urllib.request.Request(PAGES + "payload.enc?t=" + str(time.time()), headers={"User-Agent": "job-radar-mac"}), timeout=30).read()
        (CACHE / "payload.enc").write_bytes(payload)
        data = crypto.decrypt_json(passphrase(), payload.decode())
        wanted = {"photo"}
        for job in [j for tier in data["tiers"].values() for j in tier] + data.get("tracked", []):
            for name in job.get("has_files", []):
                wanted.add(f"{job['id']}-{name}")
        (CACHE / "files").mkdir(exist_ok=True)
        for name in wanted:
            target = CACHE / "files" / f"{name}.enc"
            try:
                blob = urllib.request.urlopen(PAGES + f"files/{name}.enc", timeout=30).read()
                target.write_bytes(blob)
            except urllib.error.HTTPError:
                continue
        STATUS.update(last_sync=time.strftime("%Y-%m-%d %H:%M"), sync_error="")
        queue = data.get("health", {}).get("queue", [])
        seen_file = DATA / "queue_seen.json"
        seen = set(json.loads(seen_file.read_text())) if seen_file.exists() else set()
        for item in queue:
            if item["id"] not in seen:
                subprocess.run(["osascript", "-e", 'display notification "An application is queued for the Apply Bridge." with title "Job radar"'], check=False)
                seen.add(item["id"])
        seen_file.write_text(json.dumps(sorted(seen)))
    except Exception as error:
        STATUS["sync_error"] = f"{type(error).__name__}: {error}"


def syncer() -> None:
    while True:
        sync_once()
        time.sleep(300)


def relay_once() -> None:
    """Fetch the sources that block GitHub's servers and publish them, encrypted, on the mac-relay branch."""
    import base64
    os.environ["RADAR_HOST"] = "mac"
    from engine.adapters import greek
    jobs, meta = [], {}
    for name, fn in (("skywalker", greek.skywalker), ("dypa", greek.dypa_hotjobs)):
        try:
            found = fn()
            jobs.extend(found)
            meta[name] = {"ok": True, "count": len(found)}
        except Exception as error:
            meta[name] = {"ok": False, "error": f"{type(error).__name__}: {error}"[:200]}
    feed = {"at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()), "jobs": jobs, "meta": meta}
    content = crypto.encrypt_json(passphrase(), feed)
    blob = github("/git/blobs", "POST", {"content": base64.b64encode(content.encode()).decode(), "encoding": "base64"})
    tree = github("/git/trees", "POST", {"tree": [{"path": "feed.enc", "mode": "100644", "type": "blob", "sha": blob["sha"]}]})
    commit = github("/git/commits", "POST", {"message": "relay", "tree": tree["sha"], "parents": []})
    try:
        github("/git/refs/heads/mac-relay", "PATCH", {"sha": commit["sha"], "force": True})
    except urllib.error.HTTPError:
        github("/git/refs", "POST", {"ref": "refs/heads/mac-relay", "sha": commit["sha"]})
    STATUS["relay"] = {"at": feed["at"], **{k: v.get("count", v.get("error")) for k, v in meta.items()}}


def relayer() -> None:
    time.sleep(20)
    while True:
        try:
            relay_once()
        except Exception as error:
            STATUS["relay_error"] = f"{type(error).__name__}: {error}"[:200]
        time.sleep(1800)


def find_job(data, job_id):
    for job in [j for tier in data["tiers"].values() for j in tier] + data.get("tracked", []):
        if job["id"] == job_id:
            return job
    return None


def prepare(job_id: str) -> dict:
    key = passphrase()
    data = crypto.decrypt_json(key, (CACHE / "payload.enc").read_text())
    job = find_job(data, job_id)
    if not job:
        return {"ok": False, "message": "This job is not in the current short list."}
    folder = PACKAGES / job_id
    folder.mkdir(exist_ok=True)
    files = {}
    for name, filename in (("cv_pdf", "CV.pdf"), ("cover_pdf", "Cover_letter.pdf")):
        sealed = CACHE / "files" / f"{job_id}-{name}.enc"
        if sealed.exists():
            stem = data["profile"]["name"].replace(" ", "_")
            path = folder / f"{stem}_{filename}"
            path.write_bytes(crypto.decrypt_bytes(key, sealed.read_text()))
            files["cv" if name == "cv_pdf" else "cover"] = str(path)
    if "cv" not in files:
        return {"ok": False, "message": "No CV file yet. The next cloud run renders it for short-listed jobs."}
    profile = data["profile"]
    first, _, last = profile["name"].partition(" ")
    package = {
        "apply_url": job.get("apply_url") or job.get("url"), "ai_policy": job.get("ai_policy"), "allow_cover_text": job.get("ai_policy") != "prohibited",
        "cover_text": "\n\n".join(p["text"] for p in (job.get("cover_model") or {}).get("paragraphs", [])) if job.get("ai_policy") != "prohibited" else "",
        "files": files, "fields": {"first_name": first, "last_name": last, "full_name": profile["name"], "email": profile["email"], "phone": profile["phone"], "city": "Thessaloniki, Greece", "linkedin": ""},
    }
    (folder / "package.json").write_text(json.dumps(package))
    report = folder / "report.json"
    if report.exists():
        report.unlink()
    subprocess.Popen(["node", str(ROOT / "bridge" / "bridge.mjs"), str(folder / "package.json")], cwd=str(ROOT / "bridge"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    STATUS["bridge_runs"] += 1
    for _ in range(90):
        if report.exists():
            result = json.loads(report.read_text())
            left = [x for x in result["left_for_review"] if x]
            message = (f"Prepared, not submitted. Filled {len(result['filled'])} fields, uploaded {len(result['uploaded'])} file(s). "
                       f"{len(left)} questions and {len(result['skipped_sensitive'])} sensitive fields are waiting for her. " + " ".join(result["notes"]))
            try:
                github("/issues", "POST", {"title": f"status {job_id} prepared", "body": "Apply Bridge prepared the form on the Mac. Not submitted."})
            except Exception:
                pass
            return {"ok": True, "message": message, "report": result}
        time.sleep(1)
    return {"ok": True, "message": "The browser window is open. The bridge is still working; check the window."}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def _send(self, code, body: bytes, kind: str):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; connect-src 'self' blob: data:; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, payload):
        self._send(code, json.dumps(payload).encode(), "application/json")

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        return origin in (None, f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            return self._json(200, {"ok": True, **STATUS})
        if path == "/api/bridge/status":
            return self._json(200, {"online": (ROOT / "bridge" / "node_modules" / "playwright").exists(), **STATUS})
        if path == "/payload.enc":
            return self._send(200, (CACHE / "payload.enc").read_bytes(), "text/plain") if (CACHE / "payload.enc").exists() else self._send(404, b"", "text/plain")
        if path.startswith("/files/"):
            target = CACHE / "files" / Path(path).name
            return self._send(200, target.read_bytes(), "text/plain") if target.exists() else self._send(404, b"", "text/plain")
        name = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (WEB / name).resolve()
        if WEB.resolve() in target.parents or target == WEB.resolve() / "index.html":
            if target.exists() and target.is_file():
                kind = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css"}.get(target.suffix, "application/octet-stream")
                return self._send(200, target.read_bytes(), kind)
        self._send(404, b"Not found", "text/plain")

    def do_POST(self):
        if not self._same_origin():
            return self._json(403, {"error": "cross-origin request refused"})
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        if path == "/api/command":
            title = str(body.get("title") or "")[:300]
            if not title or "\n" in title:
                return self._json(400, {"error": "bad command"})
            github("/issues", "POST", {"title": title, "body": "Sent from the Mac dashboard."})
            return self._json(200, {"ok": True})
        if path == "/api/run":
            github("/actions/workflows/radar.yml/dispatches", "POST", {"ref": "main", "inputs": {"force": "false"}})
            return self._json(200, {"ok": True})
        if path == "/api/sync":
            sync_once()
            return self._json(200, STATUS)
        if path.startswith("/api/bridge/prepare/"):
            return self._json(200, prepare(path.rsplit("/", 1)[-1]))
        self._json(404, {"error": "unknown"})


def main():
    threading.Thread(target=syncer, daemon=True).start()
    threading.Thread(target=relayer, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Mac dashboard on http://127.0.0.1:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
