"""Recognise company job-board (ATS) URLs and find a company's board from its website."""
import re
from urllib.parse import urljoin, urlparse, unquote

from . import http
from .model import norm_company

PATTERNS = [
    ("greenhouse-eu", re.compile(r"(?:job-boards|boards)\.eu\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)")),
    ("greenhouse-eu", re.compile(r"boards-api\.eu\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)")),
    ("greenhouse", re.compile(r"(?:job-boards|boards)\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=)?([A-Za-z0-9_-]+)")),
    ("greenhouse", re.compile(r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)")),
    ("greenhouse", re.compile(r"greenhouse\.io/embed/job_board(?:/js)?\?for=([A-Za-z0-9_-]+)")),
    ("lever-eu", re.compile(r"jobs\.eu\.lever\.co/([A-Za-z0-9_.-]+)")),
    ("lever", re.compile(r"jobs\.lever\.co/([A-Za-z0-9_.-]+)")),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)")),
    ("ashby", re.compile(r"api\.ashbyhq\.com/posting-api/job-board/([A-Za-z0-9_.%-]+)")),
    ("workable", re.compile(r"apply\.workable\.com/(?!api\b|j/)([A-Za-z0-9_-]+)")),
    ("recruitee", re.compile(r"(?<![a-z0-9-])([a-z0-9-]+)\.recruitee\.com")),
    ("personio", re.compile(r"(?<![a-z0-9-])([a-z0-9-]+)\.jobs\.personio\.(?:de|com)")),
    ("smartrecruiters", re.compile(r"(?:careers|jobs)\.smartrecruiters\.com/([A-Za-z0-9_-]+)")),
    ("bamboohr", re.compile(r"(?<![a-z0-9-])([a-z0-9-]+)\.bamboohr\.com")),
    ("teamtailor", re.compile(r"(?<![a-z0-9-])([a-z0-9-]+)\.teamtailor\.com")),
    ("breezy", re.compile(r"(?<![a-z0-9-])([a-z0-9-]+)\.breezy\.hr")),
    ("pinpoint", re.compile(r"(?<![a-z0-9-])([a-z0-9-]+)\.pinpointhq\.com")),
    ("workday", re.compile(r"([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]+)")),
]
BAD_SLUGS = {"www", "api", "app", "apply", "jobs", "embed", "careers", "static", "assets", "cdn", "help", "support", "boards", "job-boards",
             "brandedboards", "en", "de", "fr", "v1", "v0", "posting-api", "wday", "login", "s", "j", "search", "blog", "status", "favicon.ico"}


def parse_ats_url(url):
    """Return 'kind:slug' for a URL on a known ATS, else None. Workday slug is 'tenant|wdN|site'."""
    if not url:
        return None
    u = unquote(url)
    for kind, pat in PATTERNS:
        m = pat.search(u)
        if not m:
            continue
        if kind == "workday":
            tenant, wd, site = m.group(1), m.group(2), m.group(3)
            if site.lower() in ("wday", "en-us"):
                continue
            return f"workday:{tenant}|{wd}|{site}"
        slug = m.group(1).strip("/.")
        if slug.lower() in BAD_SLUGS or len(slug) < 2:
            continue
        if kind == "personio":
            tld = "com" if ".jobs.personio.com" in u else "de"
            return f"personio:{slug}|{tld}"
        return f"{kind}:{slug}"
    return None


def find_ats_in_html(html_text):
    seen = []
    for kind, pat in PATTERNS:
        for m in pat.finditer(html_text):
            key = parse_ats_url(m.group(0))
            if key and key not in seen:
                seen.append(key)
    return seen


_CAREER_LINK = re.compile(r"""<a\b[^>]*href=["']([^"'#]+)["'][^>]*>(.*?)</a>""", re.I | re.S)
_CAREER_WORDS = re.compile(r"career|jobs|join|karrier|work-with-us|workwithus|vacanc|stellen|hiring|open-positions|openings|állás|werde-teil|we-are-hiring", re.I)


def _career_links(base, html_text):
    out = []
    for href, text in _CAREER_LINK.findall(html_text):
        if _CAREER_WORDS.search(href) or _CAREER_WORDS.search(re.sub("<[^>]+>", "", text)):
            u = urljoin(base, href.strip())
            if urlparse(u).scheme in ("http", "https") and u not in out:
                out.append(u)
    return out[:3]


def _slug_candidates(name, site):
    c = []
    host = urlparse(site or "").netloc.lower().replace("www.", "")
    stem = host.split(".")[0] if host else ""
    n = norm_company(name)
    dashed = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    for x in (stem, n, dashed, host):
        if x and x not in c and len(x) >= 3:
            c.append(x)
    return c[:4], stem


def _probe(kind, slug, name, stem):
    """Check one candidate board. Returns True if it exists and plausibly belongs to the company."""
    strong = slug == stem and len(slug) >= 5
    nn = norm_company(name)
    try:
        if kind in ("greenhouse", "greenhouse-eu"):
            host = "boards-api.eu.greenhouse.io" if kind.endswith("eu") else "boards-api.greenhouse.io"
            d = http.get_json(f"https://{host}/v1/boards/{slug}", retries=0, timeout=12)
            bn = norm_company(d.get("name", ""))
            return bool(bn) and (bn in nn or nn in bn)
        if kind == "workable":
            d = http.get_json(f"https://apply.workable.com/api/v1/widget/accounts/{slug}", retries=0, timeout=12)
            bn = norm_company(d.get("name", ""))
            return bool(bn) and (bn in nn or nn in bn)
        if not strong and slug != nn:
            return False
        if kind in ("lever", "lever-eu"):
            host = "api.eu.lever.co" if kind.endswith("eu") else "api.lever.co"
            d = http.get_json(f"https://{host}/v0/postings/{slug}?mode=json&limit=1", retries=0, timeout=12)
            return isinstance(d, list)
        if kind == "ashby":
            d = http.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", retries=0, timeout=12)
            return isinstance(d, dict) and "jobs" in d
        if kind == "recruitee":
            d = http.get_json(f"https://{slug}.recruitee.com/api/offers/", retries=0, timeout=12)
            return isinstance(d, dict) and "offers" in d
    except http.FetchError:
        return False
    return False


PROBE_ORDER = ["ashby", "greenhouse", "lever", "workable", "greenhouse-eu", "lever-eu", "recruitee"]


def detect_company(company):
    """Returns (board_key or 'generic:<url>' or None, method)."""
    if company.get("ats"):
        return company["ats"], "hint"
    pages = [u for u in (company.get("careers"), company.get("site")) if u]
    visited = set()
    career_pages = []
    for start in pages:
        queue = [start]
        hops = 0
        while queue and hops < 3:
            u = queue.pop(0)
            if u in visited:
                continue
            visited.add(u)
            hops += 1
            try:
                status, text, final = http.fetch(u, timeout=15, retries=0)
            except http.FetchError:
                continue
            key = parse_ats_url(final)
            if key:
                return key, "page"
            found = find_ats_in_html(text)
            if found:
                return found[0], "page"
            if u == company.get("careers") or _CAREER_WORDS.search(urlparse(final).path or "") or _CAREER_WORDS.search(urlparse(final).netloc):
                career_pages.append(final)
            queue.extend(l for l in _career_links(final, text) if l not in visited)
    cands, stem = _slug_candidates(company.get("name"), company.get("site"))
    for kind in PROBE_ORDER:
        for slug in cands:
            if "." in slug and kind != "ashby":
                continue
            if _probe(kind, slug, company.get("name"), stem):
                return f"{kind}:{slug}", "probe"
    if career_pages:
        return "generic:" + career_pages[0], "careers page"
    return None, "none"
