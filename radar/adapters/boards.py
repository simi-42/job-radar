"""Job boards and aggregators: named APIs, RSS, Getro talent boards, and a generic reader for any page."""
import json
import re
from urllib.parse import urljoin, urlparse

from .. import http
from ..classify import title_family
from ..detect import parse_ats_url
from ..model import html_to_text, make_job
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
URL_KEYS = ("url", "absolute_url", "applyUrl", "apply_url", "jobUrl", "job_url", "hostedUrl", "link", "href", "permalink", "canonicalUrl", "slug", "path")
CO_KEYS = ("company", "companyName", "company_name", "organization", "organisation", "employer", "hiringOrganization", "org", "startup")
LOC_KEYS = ("location", "locations", "locationName", "city", "country", "jobLocation", "candidate_required_location", "office", "offices")
DATE_KEYS = ("datePosted", "posted", "postedAt", "posted_at", "published_at", "publishedAt", "created_at", "createdAt", "date", "pubDate")
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
    url = next((d[k] for k in URL_KEYS if isinstance(d.get(k), str) and d.get(k)), "")
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


def generic(src, url=None):
    url = url or src["url"]
    status, page, final = http.fetch(url)
    stripped = page.lstrip()[:200].lower()
    if stripped.startswith("<?xml") or "<rss" in stripped or "<feed" in stripped:
        return rss(src, url)
    out = jsonld_jobs(page, final, src)
    out += _walk_page_json(page, src, final)
    if not out:
        for f in _FEED_LINK.findall(page)[:2]:
            try:
                out += rss(src, urljoin(final, f))
            except Exception:
                pass
    if not out:
        out = links_jobs(page, final, src)
    # de-duplicate by URL
    seen, uniq = set(), []
    for j in out:
        if j["url"] in seen:
            continue
        seen.add(j["url"])
        uniq.append(j)
    return uniq


NAMED = {
    "hiddenjobs": hiddenjobs, "rss": rss, "remotive": remotive, "remoteok": remoteok, "himalayas": himalayas,
    "arbeitnow": arbeitnow, "jobicy": jobicy, "workingnomads": workingnomads, "reliefweb": reliefweb,
    "getro": getro, "generic": generic,
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
