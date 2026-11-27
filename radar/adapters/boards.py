"""Job boards and aggregators: named APIs, RSS, Getro talent boards, and a generic reader for any page."""
import json
import re
from urllib.parse import urljoin, urlparse

from .. import http
from ..classify import title_family
from ..detect import parse_ats_url
from ..model import html_to_text, make_job, registrable
from .feeds import parse_feed, split_title_company

DESC = 4000


def _j(title, company, url, src, **kw):
    return make_job(title=title, company=company, url=url, source=src, kind="board", board=src, **kw)


def hiddenjobs(src):
    data = http.get_json(src["url"])
    out = []
    for j in data.get("jobs", []):
        if not title_family(j.get("title")):
            continue
        loc = j.get("location") or ""
        geo = [x for x in (j.get("country"), j.get("city")) if x and x != "Europe-wide"]
        if j.get("country") == "Europe-wide":
            geo.append("Europe")
        out.append(_j(j["title"], j.get("company"), j.get("url"), src["id"], locations=[loc], workplace=j.get("workplace"),
                      posted=j.get("posted"), emp=[j.get("type") or ""], extra_geo=geo, salary=j.get("salary")))
    return out


def rss(src, url=None):
    items = parse_feed(http.get_text(url or src["url"], accept="application/rss+xml, application/xml, text/xml"))
    out = []
    prefer = 0 if "weworkremotely" in (url or src["url"]) else None
    for it in items:
        title, company = it["title"], it["company"]
        if not company:
            title, company = split_title_company(title, prefer)
        if not title_family(title):
            continue
        desc = html_to_text(it["description"], DESC)
        locs = list(it["locations"])
        if not company:
            m = re.search(r"^([^·|\n]{2,60})\s·", desc)  # Hidden Jobs style "Company · City · ..."
            if m:
                company = m.group(1).strip()
        out.append(_j(title, company or urlparse(it["link"]).netloc, it["link"], src["id"], locations=locs, workplace=it.get("remote"),
                      posted=it["date"], description=desc, emp=it["types"] + it["categories"]))
    return out


def remotive(src):
    data = http.get_json(src["url"])
    out = []
    for j in data.get("jobs", []):
        if not title_family(j.get("title")):
            continue
        out.append(_j(j["title"], j.get("company_name"), j.get("url"), src["id"], locations=[j.get("candidate_required_location", "")],
                      remote=True, posted=j.get("publication_date"), description=html_to_text(j.get("description", ""), DESC),
                      emp=[j.get("job_type", "")], salary=j.get("salary") or None))
    return out


def remoteok(src):
    data = http.get_json(src["url"])
    out = []
    for j in data if isinstance(data, list) else []:
        if not isinstance(j, dict) or not j.get("position") or not title_family(j.get("position")):
            continue
        sal = f"{j.get('salary_min')}–{j.get('salary_max')} USD" if j.get("salary_min") else None
        out.append(_j(j["position"], j.get("company"), j.get("url"), src["id"], apply_url=j.get("apply_url"), locations=[j.get("location", "")],
                      remote=True, posted=j.get("date") or j.get("epoch"), description=html_to_text(j.get("description", ""), DESC),
                      emp=list(j.get("tags") or []), salary=sal))
    return out


def himalayas(src):
    out = []
    urls = [src["url"]]
    if "search" in src["url"]:
        urls += [src["url"].replace("product%20designer", q) for q in ("ux%20designer", "design%20systems")]
    for u in urls:
        try:
            data = http.get_json(u)
        except http.FetchError:
            if u == urls[0]:
                raise
            continue
        for j in data.get("jobs", []):
            if not title_family(j.get("title")):
                continue
            locs = list(j.get("locationRestrictions") or []) or ["Worldwide"]
            tz = j.get("timezoneRestrictions") or []
            geo = [f"UTC{('+' if float(t) >= 0 else '')}{t}" for t in tz[:1]] if tz else []
            sal = f"{j.get('minSalary')}–{j.get('maxSalary')} {j.get('currency', '')}" if j.get("minSalary") else None
            desc = html_to_text(j.get("description", ""), DESC)
            if tz:
                tzf = [float(t) for t in tz if str(t).lstrip("-+").replace(".", "").isdigit()]
                if any(0 <= t <= 3 for t in tzf):
                    desc = "Time zones: CET +/- 2 hours allowed.\n" + desc
                elif tzf:
                    desc = f"Time zones allowed: UTC{min(tzf):+g} to UTC{max(tzf):+g}\n" + desc
            out.append(_j(j["title"], j.get("companyName"), j.get("applicationLink") or j.get("guid"), src["id"], locations=locs, remote=True,
                          posted=j.get("pubDate"), description=desc, emp=[j.get("employmentType", "")],
                          seniority_hint=" ".join(j.get("seniority") or []), salary=sal))
    return out


def arbeitnow(src):
    out = []
    url = src["url"]
    for _ in range(6):
        data = http.get_json(url)
        for j in data.get("data", []):
            if not title_family(j.get("title")):
                continue
            out.append(_j(j["title"], j.get("company_name"), j.get("url"), src["id"], locations=[j.get("location", "")], remote=j.get("remote"),
                          posted=j.get("created_at"), description=html_to_text(j.get("description", ""), DESC), emp=list(j.get("job_types") or [])))
        url = (data.get("links") or {}).get("next")
        if not url:
            break
    return out


def jobicy(src):
    data = http.get_json(src["url"])
    out = []
    for j in data.get("jobs", []):
        if not title_family(j.get("jobTitle")):
            continue
        sal = f"{j.get('annualSalaryMin')}–{j.get('annualSalaryMax')} {j.get('salaryCurrency', '')}" if j.get("annualSalaryMin") else None
        out.append(_j(j["jobTitle"], j.get("companyName"), j.get("url"), src["id"], locations=[j.get("jobGeo", "")], remote=True,
                      posted=j.get("pubDate"), description=html_to_text(j.get("jobDescription") or j.get("jobExcerpt", ""), DESC),
                      emp=list(j.get("jobType") or []), seniority_hint=j.get("jobLevel"), salary=sal))
    return out


def workingnomads(src):
    data = http.get_json(src["url"])
    out = []
    for j in data if isinstance(data, list) else []:
        if not title_family(j.get("title")):
            continue
        out.append(_j(j["title"], j.get("company_name"), j.get("url"), src["id"], locations=[j.get("location", "")], remote=True,
                      posted=j.get("pub_date"), description=html_to_text(j.get("description", ""), DESC), emp=[j.get("tags", "")]))
    return out


def reliefweb(src):
    data = http.get_json(src["url"])
    out = []
    for r in data.get("data", []):
        f = r.get("fields", {})
        if not title_family(f.get("title")):
            continue
        org = (f.get("source") or [{}])[0].get("name", "")
        locs = [c.get("name", "") for c in f.get("country") or []] + [c.get("name", "") for c in f.get("city") or []]
        out.append(_j(f["title"], org, f.get("url_alias") or f.get("url"), src["id"], locations=locs,
                      posted=(f.get("date") or {}).get("created"), description=html_to_text(f.get("body-html") or f.get("body", ""), DESC),
                      emp=[t.get("name", "") for t in f.get("type") or []]))
    return out


# ---------- Getro talent boards (VC portfolio job boards) ----------

def getro(src):
    page = http.get_text(src["url"])
    out = _walk_page_json(page, src)
    m = re.search(r'"collectionId"\s*:\s*"?(\d+)', page) or re.search(r'collections/(\d+)', page)
    if m:
        cid = m.group(1)
        for q in ("product designer", "ux designer", "design systems"):
            try:
                data = http.get_json(f"https://api.getro.com/api/v2/collections/{cid}/search/jobs", method="POST",
                                     data={"hitsPerPage": 50, "page": 0, "filters": "", "query": q})
            except http.FetchError:
                break
            for j in ((data.get("results") or {}).get("jobs") or data.get("jobs") or []):
                title = j.get("title", "")
                if not title_family(title):
                    continue
                org = j.get("organization") or {}
                locs = j.get("locations") or j.get("searchable_locations") or []
                locs = [l if isinstance(l, str) else (l.get("name") or "") for l in locs]
                out.append(_j(title, org.get("name"), j.get("url"), src["id"], locations=locs, workplace=j.get("work_mode"),
                              posted=j.get("created_at"), seniority_hint=j.get("seniority"), emp=[j.get("employment_type") or ""]))
    return out


# ---------- generic page reader ----------

_JSONLD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
_DATA_SCRIPTS = [
    re.compile(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', re.S),
    re.compile(r'<script[^>]+type=["\']application/json["\'][^>]*>(.*?)</script>', re.S),
    re.compile(r'data-page=["\'](\{.*?\})["\']', re.S),
    re.compile(r'window\.__(?:INITIAL_STATE|NUXT|APOLLO_STATE|PRELOADED_STATE)__\s*=\s*(\{.*?\});\s*</script>', re.S),
]
_FEED_LINK = re.compile(r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*href=["\']([^"\']+)["\']', re.I)
_A = re.compile(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', re.S | re.I)

TITLE_KEYS = ("title", "jobTitle", "job_title", "name", "position", "text", "role")
URL_KEYS = ("url", "absolute_url", "applyUrl", "apply_url", "jobUrl", "job_url", "hostedUrl", "link", "href", "permalink", "canonicalUrl",
            "url_external", "external_url", "externalUrl", "application_url", "applicationUrl", "apply_link", "applyLink", "slug", "path")
CO_KEYS = ("company", "companyName", "company_name", "organization", "organisation", "organization_name", "organizationName", "orgName",
           "org_name", "employer", "employer_name", "hiringOrganization", "org", "startup")
LOC_KEYS = ("location", "locations", "locationName", "location_name", "city", "country", "jobLocation", "candidate_required_location",
            "office", "offices", "card_locations", "locality")
DATE_KEYS = ("datePosted", "posted", "postedAt", "posted_at", "published_at", "publishedAt", "date_published", "datePublished",
             "published", "created_at", "createdAt", "date", "pubDate")
REMOTE_KEYS = ("remote", "isRemote", "is_remote", "workplaceType", "work_mode", "remoteType", "workplace", "jobLocationType")


def _name(v):
    if isinstance(v, dict):
        return v.get("name") or v.get("title") or v.get("label") or ""
    if isinstance(v, list):
        return ", ".join(filter(None, (_name(x) for x in v[:4])))
    return str(v) if v is not None else ""


def _loc(v):
    if isinstance(v, list):
        return [x for x in (_loc1(i) for i in v[:6]) if x]
    x = _loc1(v)
    return [x] if x else []


def _loc1(v):
    if isinstance(v, dict):
        addr = v.get("address") if isinstance(v.get("address"), dict) else v
        parts = [addr.get(k) for k in ("name", "addressLocality", "city", "addressRegion", "addressCountry", "country") if isinstance(addr.get(k), str)]
        if not parts and isinstance(addr.get("addressCountry"), dict):
            parts = [addr["addressCountry"].get("name")]
        return ", ".join(dict.fromkeys(p for p in parts if p))
    return str(v) if isinstance(v, (str, int)) else ""


def _job_from_dict(d, base, src):
    title = next((d[k] for k in TITLE_KEYS if isinstance(d.get(k), str)), "")
    if not title or len(title) > 140 or not title_family(title):
        return None
    url = ""
    for k in URL_KEYS:
        v = d.get(k)
        if isinstance(v, dict):  # per-language URLs, e.g. {"en": "/en/job/..."}
            v = v.get("en") or next((x for x in v.values() if isinstance(x, str)), "")
        if isinstance(v, str) and v:
            url = v
            break
    if not url:
        return None
    if not url.startswith("http"):
        url = urljoin(base, url if url.startswith("/") or "/" in url else f"/jobs/{url}")
    co = next((_name(d[k]) for k in CO_KEYS if d.get(k)), "")
    locs = []
    for k in LOC_KEYS:
        if d.get(k):
            locs += _loc(d[k])
    rem = next((d[k] for k in REMOTE_KEYS if d.get(k) not in (None, "")), None)
    wp = None
    if isinstance(rem, bool):
        wp = "remote" if rem else None
    elif isinstance(rem, str):
        wp = rem
    date = next((d[k] for k in DATE_KEYS if d.get(k)), None)
    desc = next((d[k] for k in ("description", "descriptionPlain", "summary", "excerpt", "snippet") if isinstance(d.get(k), str)), "")
    emp = d.get("employmentType") or d.get("employment_type") or d.get("jobType") or d.get("job_type") or ""
    return _j(title, co, url, src["id"], locations=locs, workplace=wp, posted=date, description=html_to_text(desc, DESC),
              emp=emp if isinstance(emp, list) else [str(emp)])


def _walk(obj, base, src, out, depth=0):
    if depth > 14 or len(out) > 400:
        return
    if isinstance(obj, dict):
        j = _job_from_dict(obj, base, src)
        if j:
            out.append(j)
            return
        for v in obj.values():
            if isinstance(v, (dict, list)):
                _walk(v, base, src, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            if isinstance(v, (dict, list)):
                _walk(v, base, src, out, depth + 1)


def _walk_page_json(page, src, base=None):
    base = base or src["url"]
    out = []
    for pat in _DATA_SCRIPTS:
        for m in pat.finditer(page):
            raw = m.group(1)
            if raw.startswith("{&quot;"):
                import html as _h
                raw = _h.unescape(raw)
            try:
                _walk(json.loads(raw), base, src, out)
            except (json.JSONDecodeError, RecursionError):
                continue
    return out


def jsonld_jobs(page, base, src):
    out = []
    for m in _JSONLD.finditer(page):
        try:
            data = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, list):
                stack.extend(d)
                continue
            if not isinstance(d, dict):
                continue
            if "@graph" in d:
                stack.extend(d["@graph"] if isinstance(d["@graph"], list) else [d["@graph"]])
            if "itemListElement" in d:
                stack.extend(x.get("item", x) if isinstance(x, dict) else x for x in d["itemListElement"])
            t = d.get("@type")
            if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                title = d.get("title") or d.get("name") or ""
                if not title_family(title):
                    continue
                remote = "remote" if str(d.get("jobLocationType", "")).upper() == "TELECOMMUTE" else None
                req = _loc(d.get("applicantLocationRequirements")) if d.get("applicantLocationRequirements") else []
                job = _j(title, _name(d.get("hiringOrganization")), d.get("url") or base, src["id"],
                         locations=_loc(d.get("jobLocation")) + req, workplace=remote, posted=d.get("datePosted"),
                         description=html_to_text(d.get("description", ""), DESC),
                         emp=d.get("employmentType") if isinstance(d.get("employmentType"), list) else [str(d.get("employmentType") or "")])
                job["valid_through"] = d.get("validThrough")
                org = d.get("hiringOrganization") if isinstance(d.get("hiringOrganization"), dict) else {}
                same = org.get("sameAs")
                job["org_url"] = (same[0] if isinstance(same, list) and same else same) or org.get("url")
                out.append(job)
    return out


_FLAG = re.compile(r"^[\U0001F1E6-\U0001F1FF]{2}\s*")
_TITLE_START = re.compile(r"\b(senior|sr\.?|lead|staff|principal|head|junior|mid|founding|product|ux|ui|user|interaction|digital|design|experience)\b", re.I)


def _clean_link_title(text):
    """'🇩🇰 København, DK Senior Product Designer - Twoday' -> (title, company, location)."""
    t, loc = text, ""
    if _FLAG.match(t):
        t = _FLAG.sub("", t)
        m = _TITLE_START.search(t)
        if m and m.start() > 0:
            loc, t = t[:m.start()].strip(" ,·-"), t[m.start():]
    t = re.sub(r"^(?:location not specified|remote job)\s*", "", t, flags=re.I)
    t = re.split(r"\s{2,}| · | \| ", t)[0]
    t = re.sub(r"^.*?\bfor a position of\s+", "", t, flags=re.I)
    company = ""
    m = re.match(r"^(?P<company>.{2,60}?) is hiring (?:a |an )?(?:for a position of )?(?P<title>.+)$", text, re.I)
    if m:
        company = m.group("company").strip()
    m = re.search(r"\s+in\s+([A-Z][^,]{1,40}(?:,\s*[A-Za-z ]{2,30})?)$", t)
    if m and not loc:
        loc, t = m.group(1), t[:m.start()]
    t2, c2 = split_title_company(t)
    if c2 and title_family(t2):
        t, company = t2, company or c2
    return re.split(r"\s{2,}| · | \| ", t)[0][:120].strip(), company, loc


def _company_from_url(url):
    m = re.search(r"/compan(?:y|ies)/([a-z0-9][a-z0-9-]{1,60})/", url) or re.search(r"-at-([a-z0-9-]+?)-[0-9a-f]{6,}/?$", url)
    if m:
        return m.group(1).replace("-", " ").title()
    return ""


def links_jobs(page, base, src):
    out, seen = [], set()
    host = urlparse(base).netloc
    for href, inner in _A.findall(page):
        text = re.sub(r"\s+", " ", html_to_text(inner)).strip()
        if not text or len(text) > 160:
            continue
        # Use the first line-ish chunk as the title
        title = re.split(r"\s{2,}|\n| · | \| ", text)[0][:120]
        if not title_family(title):
            continue
        url = urljoin(base, href)
        if url in seen or urlparse(url).scheme not in ("http", "https"):
            continue
        seen.add(url)
        title, company, loc = _clean_link_title(text)
        if not title_family(title):
            continue
        company = company or _company_from_url(url)
        rest = text.replace(title, "").strip(" ·|-—")
        out.append(_j(title, company, url, src["id"], locations=[loc] if loc else [], description=rest[:300]))
        if len(out) >= 60:
            break
    return out


# ---------- why a board gave nothing ----------
# Filled per run: {source id: {"reason": ..., "status": ..., ...}}. Shown on the site so unreadable boards get a direct link.
DIAG = {}

_BLOCK = re.compile(r"just a moment\.\.\.|cf-chl|challenge-platform|attention required|access denied|captcha|"
                    r"verify you are (?:a )?human|are you a robot|request unsuccessful|incapsula|datadome|perimeterx", re.I)
_SPA = re.compile(r'id=["\'](?:root|app|__next|__nuxt|svelte)["\']|ng-version=|data-reactroot|enable javascript|requires javascript', re.I)
_JOBLINK = re.compile(r"/(?:jobs?|positions?|vacanc|opportunit|roles?|careers?|stellen|emploi|offre|listing)[/-]?[\w-]", re.I)


def _visible_text(page):
    page = re.sub(r"<(script|style|noscript|svg)\b.*?</\1>", " ", page, flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page)).strip()


def diagnose(src, status, page, found, via=None):
    """Record why a board read gave what it gave: ok / no_match / needs_js / blocked."""
    text = _visible_text(page or "")
    links = [h for h, _ in _A.findall(page or "")]
    joblinks = len({h for h in links if _JOBLINK.search(h)})
    if found:
        reason = "ok"
    elif _BLOCK.search((page or "")[:20000]) and len(text) < 4000:
        reason = "blocked"
    elif joblinks >= 5 and len(text) > 1500:
        reason = "no_match"   # listings are readable; none are design roles today
    elif len(text) < 1500 or _SPA.search(page or "") or joblinks < 3:
        reason = "needs_js"
    else:
        reason = "unclear"
    DIAG[src["id"]] = {"reason": reason, "status": status, "text": len(text), "job_links": joblinks, "via": via}
    return reason


# ---------- WordPress job boards (WP Job Manager) ----------

def wp_jobs(src, page, final):
    """WP Job Manager boards publish a filtered RSS feed and a REST route even when the page itself is built by JavaScript."""
    if "wp-content" not in page and "wp-json" not in page:
        return []
    p = urlparse(final)
    base = f"{p.scheme}://{p.netloc}"
    try:
        out = rss(src, f"{base}/?feed=job_feed&search_keywords=design&posts_per_page=100")
        if out:
            return out
    except Exception:  # not a feed, or no WP Job Manager
        pass
    try:
        data = http.get_json(f"{base}/wp-json/wp/v2/job-listings?search=design&per_page=100")
    except Exception:
        return []
    out = []
    for d in data if isinstance(data, list) else []:
        title = html_to_text(((d.get("title") or {}).get("rendered")) or "")
        if not title_family(title):
            continue
        meta = d.get("meta") or {}
        loc = meta.get("_job_location") or ""
        wp = "remote" if meta.get("_remote_position") in (1, "1", True) else None
        out.append(_j(title, meta.get("_company_name") or "", d.get("link"), src["id"], locations=[loc] if loc else [],
                      workplace=wp, posted=d.get("date"), description=html_to_text((d.get("content") or {}).get("rendered", ""), DESC)))
    return out


# ---------- boards whose search runs on Algolia (80,000 Hours, Probably Good, Idealist, ...) ----------

_ALG_PAIR = re.compile(r'["\']([A-Z0-9]{10})["\']\s*,\s*["\']([a-f0-9]{32})["\']')
_ALG_APP = re.compile(r'(?:appId|applicationId|application_id|ALGOLIA_APP(?:LICATION)?_ID|algoliaAppId)\W{1,6}([A-Z0-9]{10})\b')
_ALG_DSN = re.compile(r'\b([a-zA-Z0-9]{10})(?:-dsn)?\.algolia(?:net)?\.(?:net|io)')
_ALG_KEY = re.compile(r'(?:apiKey|searchApiKey|searchKey|search_key|search_api_key|searchOnlyApiKey|ALGOLIA_(?:SEARCH_)?(?:API_)?KEY|algoliaApiKey)'
                      r'\W{1,6}([A-Za-z0-9+/=]{32,400})["\']')
_ALG_IDX = re.compile(r'(?:indexName|index_name|ALGOLIA_INDEX(?:_NAME)?|algoliaIndex)\W{1,6}([\w.\-]{2,80})["\']')
_ALG_ROUTE = re.compile(r'([A-Za-z][\w.\-]{1,60})(?:\[|%5B)query(?:\]|%5D)=')
_SCRIPT_SRC = re.compile(r'<script[^>]+src=["\']([^"\']+)["\']', re.I)
_NOT_APP_JS = re.compile(r"googletagmanager|google-analytics|gtag|hotjar|facebook|intercom|stripe|recaptcha|cookie|consent|segment|"
                         r"clarity|hubspot|sentry|polyfill|jquery|plausible|fathom|crisp|zendesk|youtube|vimeo|maps\.google", re.I)


def _algolia_config(page, final, src):
    """Find Algolia app id, search key and index names in the page and its own scripts."""
    texts = [page]
    if "algolia" not in page.lower():
        host = registrable(urlparse(final).netloc)
        srcs = [urljoin(final, s) for s in _SCRIPT_SRC.findall(page) if not _NOT_APP_JS.search(s)]
        srcs = [s for s in srcs if registrable(urlparse(s).netloc) == host or re.search(r"cloudfront|vercel|netlify|cdn\.", s)]
        srcs.sort(key=lambda s: 0 if re.search(r"_app|main|app[.-]|index|pages/|jobs|search|board", s) else 1)
        for s in srcs[:8]:
            try:
                js = http.get_text(s, timeout=20)
            except Exception:
                continue
            if "algolia" in js.lower() or _ALG_PAIR.search(js):
                texts.append(js)
    blob = "\n".join(texts)
    app = key = None
    m = _ALG_PAIR.search(blob)
    if m:
        app, key = m.group(1), m.group(2)
    app = app or next(iter(_ALG_APP.findall(blob)), None)
    if not app:
        dsn = [a.upper() for a in _ALG_DSN.findall(blob) if not a.isdigit()]
        app = dsn[0] if dsn else None
    key = key or next(iter(_ALG_KEY.findall(blob)), None)
    idx = _ALG_ROUTE.findall(src.get("url", "")) + _ALG_ROUTE.findall(final) + _ALG_IDX.findall(blob)
    idx = list(dict.fromkeys(i for i in idx if not i.lower().startswith(("http", "query"))))
    return app, key, idx[:5]


def algolia_jobs(src, page, final, query="design"):
    app, key, indices = _algolia_config(page, final, src)
    if not (app and key and indices):
        return []
    p = urlparse(final)
    head = {"X-Algolia-Application-Id": app, "X-Algolia-API-Key": key, "Referer": final, "Origin": f"{p.scheme}://{p.netloc}"}
    for idx in indices:
        try:
            data = http.get_json(f"https://{app.lower()}-dsn.algolia.net/1/indexes/{idx}/query", method="POST", headers=head,
                                 data={"params": f"query={query}&hitsPerPage=300"})
        except Exception:
            continue
        out = []
        for hit in data.get("hits") or []:
            if not any(isinstance(hit.get(k), (str, dict)) and hit.get(k) for k in URL_KEYS):
                hit = dict(hit, url=f"{src.get('direct') or src['url']}#job-{hit.get('objectID', '')}")
            j = _job_from_dict(hit, final, src)
            if j:
                out.append(j)
        if out or data.get("nbHits"):
            return out
    return []


def generic(src, url=None):
    url = url or src["url"]
    status, page, final = http.fetch(url)
    stripped = page.lstrip()[:200].lower()
    if stripped.startswith("<?xml") or "<rss" in stripped or "<feed" in stripped:
        out = rss(src, url)
        DIAG[src["id"]] = {"reason": "ok" if out else "no_match", "status": status, "via": "feed"}
        return out
    via = "page"
    out = jsonld_jobs(page, final, src)
    out += _walk_page_json(page, src, final)
    if not out:
        for f in _FEED_LINK.findall(page)[:2]:
            try:
                out += rss(src, urljoin(final, f))
                via = "feed"
            except Exception:
                pass
    if not out:
        out = wp_jobs(src, page, final)
        via = "wordpress feed" if out else via
    if not out:
        out = links_jobs(page, final, src)
        via = "page links" if out else via
    if not out and (_ALG_ROUTE.search(url) or "algolia" in page.lower() or _SPA.search(page)):
        out = algolia_jobs(src, page, final)
        via = "algolia" if out else via
    # de-duplicate by URL
    seen, uniq = set(), []
    for j in out:
        if j["url"] in seen:
            continue
        seen.add(j["url"])
        uniq.append(j)
    diagnose(src, status, page, len(uniq), via)
    return uniq


# ---------- curated roundups (e.g. jessica.tech weekly Tech for Good jobs) ----------
# Every company job board linked in a roundup is handed to the run so it gets tracked daily (BOARD_LINKS),
# and the design roles in it come through as jobs straight away.
BOARD_LINKS = []   # (job url, company) found in roundups this run
# A job is a heading holding a location and the linked title ("### Remote, Europe [Senior UX Designer](...)");
# the paragraph after it opens with the organisation ("[Wikimedia](...) is the nonprofit that ...").
_JOB_HEAD = re.compile(r"<h([2-4])[^>]*>(.*?)</h\1>\s*(?:<p[^>]*>(.*?)</p>)?", re.S | re.I)
_GEO_WORDS = re.compile(r"remote|location|global|europe|united|usa|\buk\b|asia|africa|americas|hybrid|countries|timezone", re.I)


def _org_from_para(para):
    m = _A.search(para or "")
    if m and (para or "").lstrip().lower().startswith(("<a", "<strong><a", "<b><a")):
        return re.sub(r"\s+", " ", html_to_text(m.group(2))).strip()[:80]
    first = re.split(r"\s+(?:is|are|makes|builds|works|helps|was)\s", html_to_text(para or ""), maxsplit=1)[0].strip()
    return first if 1 <= len(first.split()) <= 6 else ""


def roundup(src):
    """Read the newest post(s) of a blog that lists jobs as linked titles in headings, organisation in the next paragraph."""
    status, index, final = http.fetch(src["url"])
    pat = src.get("post_pattern")
    posts = []
    for href, _ in _A.findall(index):
        u = urljoin(final, href)
        if (re.search(pat, u) if pat else u.startswith(final.rstrip("/") + "/") and u.rstrip("/") != final.rstrip("/")) and u not in posts:
            posts.append(u)
    posts = sorted(posts, reverse=True)[: int(src.get("posts", 2))] or [final]
    out, seen = [], set()
    for post in posts:
        try:
            _, page, pfinal = http.fetch(post)
        except Exception:
            continue
        own = urlparse(pfinal).netloc
        last_org = ""
        for _, head, para in _JOB_HEAD.findall(page):
            links = [(urljoin(pfinal, h), re.sub(r"\s+", " ", html_to_text(t)).strip()) for h, t in _A.findall(head)]
            links = [(u, t) for u, t in links if urlparse(u).netloc and urlparse(u).netloc != own]
            if not links:   # a section or organisation heading, e.g. "## Remote or UK" or "## Alzheimer's Society"
                text = re.sub(r"\s+", " ", html_to_text(head)).strip(" :")
                last_org = "" if _GEO_WORDS.search(text) or len(text) > 60 else text
                continue
            org = _org_from_para(para) or last_org
            loc = re.sub(r"\s+", " ", html_to_text(re.sub(r"<a\b.*?</a>", " ", head, flags=re.S))).strip(" :;,-")
            loc = re.sub(r"https?://\S+", "", loc).strip(" :;,-")
            for url, text in links:
                if url in seen:
                    continue
                seen.add(url)
                company = org or _company_from_url(url)
                BOARD_LINKS.append((url, company))
                if text and title_family(text):
                    out.append(_j(text[:120], company, url, src["id"], locations=[loc] if loc else []))
        for h, _ in _A.findall(page):   # links outside job headings can still point at company job boards
            u = urljoin(pfinal, h)
            if u not in seen and urlparse(u).netloc not in ("", own):
                seen.add(u)
                BOARD_LINKS.append((u, ""))
    DIAG[src["id"]] = {"reason": "ok" if out else ("no_match" if seen else "unclear"), "status": status,
                       "via": f"{len(posts)} post{'s' if len(posts) != 1 else ''}, {len(seen)} links"}
    return out

NAMED = {
    "hiddenjobs": hiddenjobs, "rss": rss, "remotive": remotive, "remoteok": remoteok, "himalayas": himalayas,
    "arbeitnow": arbeitnow, "jobicy": jobicy, "workingnomads": workingnomads, "reliefweb": reliefweb,
    "getro": getro, "generic": generic, "roundup": roundup,
}
DOMAIN_ADAPTER = {
    "remotive.com": "remotive", "remoteok.com": "remoteok", "himalayas.app": "himalayas", "arbeitnow.com": "arbeitnow",
    "jobicy.com": "jobicy", "workingnomads.com": "workingnomads", "reliefweb.int": "reliefweb", "getro.com": "getro",
}


def resolve_adapter(src):
    """For adapter 'auto': company job boards become tracked boards; known APIs get their adapter; else generic."""
    a = src.get("adapter") or "auto"
    if a != "auto":
        return a, None
    key = parse_ats_url(src["url"])
    if key:
        return "board", key
    host = urlparse(src["url"]).netloc.replace("www.", "")
    for d, name in DOMAIN_ADAPTER.items():
        if host.endswith(d):
            return name, None
    if re.search(r"\.(rss|xml)$|/feed/?$|feed=", src["url"]):
        return "rss", None
    return "generic", None
