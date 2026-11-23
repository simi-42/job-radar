"""Job record, text cleaning, dates, keys."""
import hashlib
import html
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

TODAY = datetime.now(timezone.utc).date().isoformat()

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_BLOCK = re.compile(r"</?(p|div|br|li|ul|ol|h\d|tr|section|article)[^>]*>", re.I)
_SCRIPT = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.I | re.S)


def html_to_text(s, limit=None):
    if not s:
        return ""
    s = html.unescape(s) if "&lt;" in s else s
    s = _SCRIPT.sub(" ", s)
    s = _BLOCK.sub("\n", s)
    s = _TAG.sub(" ", s)
    s = html.unescape(s)
    s = "\n".join(_WS.sub(" ", line).strip() for line in s.splitlines())
    s = re.sub(r"\n{2,}", "\n", s).strip()
    return s[:limit] if limit else s


def parse_date(v):
    """ISO string, epoch seconds/ms, RFC 822, or relative 'Posted 3 Days Ago'. Returns YYYY-MM-DD or None."""
    if v in (None, "", 0):
        return None
    try:
        if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
            n = float(v)
            if n > 1e12:
                n /= 1000
            if n < 1e9:
                return None
            return datetime.fromtimestamp(n, timezone.utc).date().isoformat()
        s = str(v).strip()
        m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
        if m:
            return m.group(1)
        low = s.lower()
        if "today" in low or "just posted" in low:
            return TODAY
        if "yesterday" in low:
            return (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
        m = re.search(r"(\d+)\+?\s*(day|week|month|hour)s?\s*ago", low)
        if m:
            n, unit = int(m.group(1)), m.group(2)
            days = {"hour": 0, "day": n, "week": 7 * n, "month": 30 * n}[unit]
            return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        return parsedate_to_datetime(s).date().isoformat()
    except Exception:
        return None


_GENDER = re.compile(r"\((?:[mwfdxhkn]\s*/\s*){1,3}[mwfdxhkn]\)|\(\s*/\s*n\s*\)|\b[mwfdxhkn]/[mwfdxhkn](?:/[mwfdxhkn])?\b|\(all genders?\)|\(gn\)|\(d/f/m\)|:in\b|\*in\b", re.I)
_CO_SUFFIX = re.compile(r"\b(gmbh|ag|ltd|limited|inc|llc|plc|kft|zrt|nyrt|bv|b\.v\.|sa|s\.a\.|sas|sl|ab|as|a/s|oy|oyj|srl|spa|s\.r\.o\.|sp\. z o\.o\.|co|corp|corporation|group|holding|technologies|labs|hq)\b\.?", re.I)


def clean_title(t):
    t = html.unescape(t or "")
    t = _GENDER.sub("", t)
    t = re.sub(r"\s+", " ", t).strip(" -–—|,")
    return t


def norm_company(c):
    c = (c or "").lower()
    c = c.replace("&", "and")
    c = _CO_SUFFIX.sub(" ", c)
    c = re.sub(r"^the\s+", "", c)
    return re.sub(r"[^a-z0-9]+", "", c)


def norm_title(t):
    t = clean_title(t).lower()
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", t)
    t = re.sub(r"[^a-z0-9/ ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def job_key(company, title):
    return f"{norm_company(company)}|{norm_title(title)}"


def job_id(company, title):
    return hashlib.sha1(job_key(company, title).encode()).hexdigest()[:12]


def make_job(*, title, company, url, source, kind, locations=None, remote=None, workplace=None,
             posted=None, description="", emp=None, salary=None, apply_url=None, extra_geo=None,
             seniority_hint=None, board=None):
    """kind: 'ats' (company's own board), 'board' (aggregator/job board), 'search' (search engine)."""
    return {
        "title": clean_title(title),
        "company": (company or "").strip() or "Unknown",
        "url": url,
        "apply_url": apply_url,
        "source": source,
        "kind": kind,
        "board": board,
        "locations": [l for l in (locations or []) if l],
        "remote_flag": remote,
        "workplace_hint": workplace,
        "posted": parse_date(posted),
        "description": description or "",
        "emp_hint": emp or [],
        "salary": salary,
        "geo_hint": extra_geo or [],
        "seniority_hint": seniority_hint,
    }
