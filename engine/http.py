"""Polite HTTP: robots.txt, per-host spacing, retries, private-address guard."""

from __future__ import annotations

import ipaddress
import json
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from typing import Dict, Optional, Tuple

AGENT = "PersonalJobRadar/3.0"
BROWSER_AGENT = "Mozilla/5.0 (compatible; PersonalJobRadar/3.0)"

_robots: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}
_robots_lock = threading.Lock()
_last_hit: Dict[str, float] = {}
_host_lock = threading.Lock()
SPACING = 0.6


class Blocked(Exception):
    pass


def _host(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc.lower()


def public_url(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parts.hostname, None)
    except socket.gaierror:
        return False
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast:
            return False
    return True


def allowed(url: str) -> bool:
    host = _host(url)
    with _robots_lock:
        if host not in _robots:
            parser = urllib.robotparser.RobotFileParser()
            try:
                request = urllib.request.Request(f"https://{host}/robots.txt", headers={"User-Agent": BROWSER_AGENT})
                with urllib.request.urlopen(request, timeout=12) as response:
                    parser.parse(response.read().decode("utf-8", "replace").splitlines())
                _robots[host] = parser
            except Exception:
                _robots[host] = None
        parser = _robots[host]
    if parser is None:
        return True
    return parser.can_fetch("PersonalJobRadar", url) and parser.can_fetch("*", url)


def _space(host: str) -> None:
    with _host_lock:
        wait = _last_hit.get(host, 0) + SPACING - time.time()
        _last_hit[host] = max(time.time(), _last_hit.get(host, 0) + SPACING)
    if wait > 0:
        time.sleep(wait)


def fetch(
    url: str,
    *,
    data: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    method: Optional[str] = None,
    timeout: int = 25,
    retries: int = 2,
    check_robots: bool = True,
    insecure: bool = False,
) -> Tuple[int, str, bytes]:
    if check_robots and not allowed(url):
        raise Blocked(f"robots.txt disallows {url}")
    merged = {"User-Agent": BROWSER_AGENT, "Accept": "application/json,text/html,application/xml;q=0.9,*/*;q=0.5", "Accept-Language": "en,el;q=0.8"}
    merged.update(headers or {})
    context = ssl._create_unverified_context() if insecure else None
    last_error: Exception = RuntimeError("no attempt")
    for attempt in range(retries + 1):
        _space(_host(url))
        request = urllib.request.Request(url, data=data, headers=merged, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                return response.status, response.headers.get("content-type", ""), response.read()
        except urllib.error.HTTPError as error:
            if error.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2 ** attempt * 2)
                last_error = error
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            last_error = error
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise
    raise last_error


def text(url: str, **kwargs) -> str:
    return fetch(url, **kwargs)[2].decode("utf-8", "replace")


def get_json(url: str, **kwargs):
    return json.loads(text(url, **kwargs))


def post_json(url: str, payload, **kwargs):
    headers = {"Content-Type": "application/json"}
    headers.update(kwargs.pop("headers", {}) or {})
    return json.loads(fetch(url, data=json.dumps(payload).encode(), headers=headers, method="POST", **kwargs)[2].decode("utf-8", "replace"))
