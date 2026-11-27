"""Small HTTP client on the standard library: retries, gzip, per-host politeness, offline fixtures."""
import gzip
import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
import zlib
from urllib.parse import urlparse

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0 Safari/537.36 job-radar/1.0 (personal job tracker)")

_lock = threading.Lock()
_host_sem = {}
_host_last = {}
PER_HOST = 3
MIN_GAP = 0.25

# Offline mode for tests: map URL substrings to fixture files.
FIXTURES = None  # dict {substring: path} or None


class FetchError(Exception):
    def __init__(self, url, status=None, msg=""):
        super().__init__(f"{status or ''} {msg} {url}".strip())
        self.url, self.status, self.msg, self.body = url, status, msg, ""


def _sem(host):
    with _lock:
        if host not in _host_sem:
            _host_sem[host] = threading.Semaphore(PER_HOST)
        return _host_sem[host]


def _decode(body, enc):
    if enc == "gzip" or body[:2] == b"\x1f\x8b":
        try:
            body = gzip.decompress(body)
        except OSError:
            pass
    elif enc == "deflate":
        try:
            body = zlib.decompress(body)
        except zlib.error:
            body = zlib.decompress(body, -zlib.MAX_WBITS)
    for cs in ("utf-8", "latin-1"):
        try:
            return body.decode(cs)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", "replace")


def _fixture(url):
    for key, path in FIXTURES.items():
        if key in url:
            with open(path, encoding="utf-8") as f:
                return 200, f.read(), url
    raise FetchError(url, None, "no fixture")


def fetch(url, method="GET", data=None, headers=None, timeout=25, retries=2, accept=None):
    """Return (status, text, final_url). Raises FetchError on network errors and 4xx/5xx."""
    if FIXTURES is not None:
        return _fixture(url)
    host = urlparse(url).netloc
    h = {"User-Agent": UA, "Accept-Encoding": "gzip, deflate",
         "Accept": accept or "application/json, text/html, application/xml;q=0.9, */*;q=0.8",
         "Accept-Language": "en-GB,en;q=0.9"}
    if headers:
        h.update(headers)
    body = None
    if data is not None:
        if isinstance(data, (dict, list)):
            body = json.dumps(data).encode()
            h.setdefault("Content-Type", "application/json")
        elif isinstance(data, str):
            body = data.encode()
        else:
            body = data
    last = None
    for attempt in range(retries + 1):
        sem = _sem(host)
        with sem:
            with _lock:
                gap = time.time() - _host_last.get(host, 0)
            if gap < MIN_GAP:
                time.sleep(MIN_GAP - gap)
            with _lock:
                _host_last[host] = time.time()
            req = urllib.request.Request(url, data=body, headers=h, method=method)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    text = _decode(r.read(), r.headers.get("Content-Encoding"))
                    return r.status, text, r.geturl()
            except urllib.error.HTTPError as e:
                last = FetchError(url, e.code, e.reason if isinstance(e.reason, str) else "")
                try:
                    last.body = _decode(e.read(400), e.headers.get("Content-Encoding"))[:300]   # API errors say why here
                except Exception:
                    last.body = ""
                if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                    time.sleep(1.5 * (attempt + 1) + random.random())
                    continue
                raise last
            except Exception as e:  # timeouts, DNS, TLS, resets
                last = FetchError(url, None, type(e).__name__)
                if attempt < retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                raise last
    raise last


def get_text(url, **kw):
    return fetch(url, **kw)[1]


def get_json(url, **kw):
    text = fetch(url, **kw)[1]
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise FetchError(url, None, f"bad json: {e}")


def secret(name):
    v = os.environ.get(name, "").strip()
    return v or None
