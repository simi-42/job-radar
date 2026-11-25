"""Company job boards. Each returns make_job records for design-titled jobs only (details fetched only for those)."""
import xml.etree.ElementTree as ET

from .. import http
from ..classify import title_family
from ..geo import COUNTRY_NAMES
from ..model import html_to_text, make_job
from .feeds import parse_feed

DESC = 6000


def _cn(code):
    return COUNTRY_NAMES.get((code or "").upper(), code or "")


def greenhouse(slug, company, eu=False):
    base = f"https://boards-api{'.eu' if eu else ''}.greenhouse.io/v1/boards/{slug}"
    data = http.get_json(f"{base}/jobs")
    out = []
    for j in data.get("jobs", []):
        if not title_family(j.get("title")):
            continue
        d = j
        try:
            d = http.get_json(f"{base}/jobs/{j['id']}")
        except http.FetchError:
            pass
        locs = [(d.get("location") or {}).get("name", "")] + [o.get("name", "") for o in d.get("offices") or []]
        meta = [str(m.get("value")) for m in d.get("metadata") or [] if m.get("value")]
        out.append(make_job(title=j["title"], company=company, url=j.get("absolute_url"), source=f"greenhouse:{slug}", kind="ats",
                            locations=list(dict.fromkeys(locs)), posted=d.get("first_published") or d.get("updated_at"),
                            description=html_to_text(d.get("content", ""), DESC), emp=meta))
    return out


def lever(slug, company, eu=False):
    data = http.get_json(f"https://api{'.eu' if eu else ''}.lever.co/v0/postings/{slug}?mode=json")
    out = []
    for p in data if isinstance(data, list) else []:
        title = p.get("text", "")
        if not title_family(title):
            continue
        cats = p.get("categories") or {}
        locs = [cats.get("location", "")] + list(cats.get("allLocations") or [])
        desc = p.get("descriptionPlain", "") + "\n" + "\n".join(
            (l.get("text", "") + "\n" + html_to_text(l.get("content", ""))) for l in p.get("lists") or []) + "\n" + p.get("additionalPlain", "")
        sal = p.get("salaryRange") or {}
        out.append(make_job(title=title, company=company, url=p.get("hostedUrl"), apply_url=p.get("applyUrl"), source=f"lever:{slug}", kind="ats",
                            locations=list(dict.fromkeys(locs)), workplace=p.get("workplaceType"), posted=p.get("createdAt"),
                            description=desc[:DESC], emp=[cats.get("commitment", "")], extra_geo=[_cn(p.get("country"))],
                            salary=(f"{sal.get('min')}–{sal.get('max')} {sal.get('currency', '')} {sal.get('interval', '')}".strip() if sal.get("min") else None)))
    return out


def ashby(slug, company):
    data = http.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true")
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False or not title_family(j.get("title")):
            continue
        locs = [j.get("location", "")] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
        addr = ((j.get("address") or {}).get("postalAddress") or {})
        comp = (j.get("compensation") or {}).get("compensationTierSummary")
        out.append(make_job(title=j["title"], company=company, url=j.get("jobUrl"), apply_url=j.get("applyUrl"), source=f"ashby:{slug}", kind="ats",
                            locations=list(dict.fromkeys(locs)), remote=j.get("isRemote"), workplace=j.get("workplaceType"),
                            posted=j.get("publishedAt"), description=(j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml", "")))[:DESC],
                            emp=[j.get("employmentType", "")], extra_geo=[addr.get("addressCountry", "")], salary=comp))
    return out


def workable(slug, company):
    data = http.get_json(f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true")
    company = data.get("name") or company
    out = []
    for j in data.get("jobs", []):
        if not title_family(j.get("title")):
            continue
        locs = [", ".join(x for x in (l.get("city"), l.get("region"), l.get("country")) if x) for l in j.get("locations") or []]
        if not locs:
            locs = [", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x)]
        out.append(make_job(title=j["title"], company=company, url=j.get("url") or j.get("shortlink"), apply_url=j.get("application_url"),
                            source=f"workable:{slug}", kind="ats", locations=locs, remote=j.get("telecommuting"),
                            posted=j.get("published_on") or j.get("created_at"), description=html_to_text(j.get("description", ""), DESC),
                            emp=[j.get("employment_type", "")], seniority_hint=j.get("experience")))
    return out


def recruitee(slug, company):
    data = http.get_json(f"https://{slug}.recruitee.com/api/offers/")
    out = []
    for o in data.get("offers", []):
        if not title_family(o.get("title")):
            continue
        wp = "remote" if o.get("remote") else ("hybrid" if o.get("hybrid") else ("onsite" if o.get("on_site") else None))
        out.append(make_job(title=o["title"], company=o.get("company_name") or company, url=o.get("careers_url"), apply_url=o.get("careers_apply_url"),
                            source=f"recruitee:{slug}", kind="ats", locations=[o.get("location", ""), ", ".join(x for x in (o.get("city"), o.get("country")) if x)],
                            remote=o.get("remote"), workplace=wp, posted=o.get("published_at") or o.get("created_at"),
                            description=html_to_text((o.get("description") or "") + "\n" + (o.get("requirements") or ""), DESC),
                            emp=[o.get("employment_type_code", "")], extra_geo=[_cn(o.get("country_code"))]))
    return out


def personio(slug_tld, company):
    slug, _, tld = slug_tld.partition("|")
    tld = tld or "de"
    text = http.get_text(f"https://{slug}.jobs.personio.{tld}/xml?language=en", accept="application/xml")
    root = ET.fromstring(text.encode("utf-8"))
    out = []
    for p in root.iter("position"):
        g = lambda tag: (p.findtext(tag) or "").strip()
        title = g("name")
        if not title_family(title):
            continue
        offices = [g("office")] + [o.text or "" for o in p.findall("additionalOffices/office")]
        desc = "\n".join(((d.findtext("name") or "") + "\n" + html_to_text(d.findtext("value") or "")) for d in p.findall("jobDescriptions/jobDescription"))
        out.append(make_job(title=title, company=g("subcompany") or company, url=f"https://{slug}.jobs.personio.{tld}/job/{g('id')}?language=en",
                            source=f"personio:{slug}", kind="ats", locations=offices, posted=g("createdAt"), description=desc[:DESC],
                            emp=[g("employmentType"), g("schedule")], seniority_hint=g("seniority")))
    return out


def smartrecruiters(slug, company):
    data = http.get_json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?q=designer&limit=100")
    out = []
    for p in data.get("content", []):
        if not title_family(p.get("name")):
            continue
        loc = p.get("location") or {}
        desc, url = "", f"https://jobs.smartrecruiters.com/{slug}/{p['id']}"
        try:
            d = http.get_json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{p['id']}")
            secs = ((d.get("jobAd") or {}).get("sections") or {})
            desc = "\n".join(html_to_text((secs.get(k) or {}).get("text", "")) for k in ("jobDescription", "qualifications", "additionalInformation", "companyDescription")).strip()
            url = d.get("postingUrl") or url
        except http.FetchError:
            pass
        wp = "remote" if loc.get("remote") else ("hybrid" if loc.get("hybrid") else None)
        out.append(make_job(title=p["name"], company=(p.get("company") or {}).get("name") or company, url=url, source=f"smartrecruiters:{slug}",
                            kind="ats", locations=[loc.get("fullLocation") or ", ".join(x for x in (loc.get("city"), loc.get("country")) if x)],
                            remote=loc.get("remote"), workplace=wp, posted=p.get("releasedDate"), description=desc[:DESC],
                            emp=[(p.get("typeOfEmployment") or {}).get("label", "")], extra_geo=[_cn(loc.get("country"))],
                            seniority_hint=(p.get("experienceLevel") or {}).get("label")))
    return out


def bamboohr(slug, company):
    data = http.get_json(f"https://{slug}.bamboohr.com/careers/list")
    out = []
    for r in data.get("result", []):
        title = r.get("jobOpeningName", "")
        if not title_family(title):
            continue
        loc = r.get("atsLocation") or r.get("location") or {}
        desc = ""
        try:
            d = http.get_json(f"https://{slug}.bamboohr.com/careers/{r['id']}/detail")
            desc = html_to_text(((d.get("result") or {}).get("jobOpening") or {}).get("description", ""), DESC)
        except http.FetchError:
            pass
        lt = str(r.get("locationType", ""))
        wp = {"1": "remote", "2": "hybrid", "0": "onsite"}.get(lt)
        out.append(make_job(title=title, company=company, url=f"https://{slug}.bamboohr.com/careers/{r['id']}", source=f"bamboohr:{slug}", kind="ats",
                            locations=[", ".join(x for x in (loc.get("city"), loc.get("state"), loc.get("country")) if x)],
                            remote=r.get("isRemote"), workplace=wp, description=desc, emp=[r.get("employmentStatusLabel", "")]))
    return out


def teamtailor(slug, company):
    items = parse_feed(http.get_text(f"https://{slug}.teamtailor.com/jobs.rss", accept="application/rss+xml"))
    out = []
    for it in items:
        if not title_family(it["title"]):
            continue
        out.append(make_job(title=it["title"], company=company, url=it["link"], source=f"teamtailor:{slug}", kind="ats",
                            locations=it.get("locations") or [], workplace=it.get("remote"), posted=it.get("date"),
                            description=html_to_text(it.get("description", ""), DESC)))
    return out


def breezy(slug, company):
    data = http.get_json(f"https://{slug}.breezy.hr/json")
    out = []
    for p in data if isinstance(data, list) else []:
        if not title_family(p.get("name")):
            continue
        loc = p.get("location") or {}
        out.append(make_job(title=p["name"], company=(p.get("company") or {}).get("name") or company, url=p.get("url"), source=f"breezy:{slug}",
                            kind="ats", locations=[loc.get("name", "")], remote=loc.get("is_remote"), posted=p.get("published_date"),
                            emp=[(p.get("type") or {}).get("name", "")], extra_geo=[(loc.get("country") or {}).get("name", "")]))
    return out


def pinpoint(slug, company):
    data = http.get_json(f"https://{slug}.pinpointhq.com/postings.json")
    out = []
    for p in data.get("data", []) if isinstance(data, dict) else []:
        if not title_family(p.get("title")):
            continue
        loc = p.get("location") or {}
        out.append(make_job(title=p["title"], company=company, url=p.get("url"), source=f"pinpoint:{slug}", kind="ats",
                            locations=[loc.get("name", "") if isinstance(loc, dict) else str(loc)], workplace=p.get("workplace_type"),
                            description=html_to_text(p.get("description", ""), DESC), emp=[p.get("employment_type", "")]))
    return out


def workday(slug, company):
    tenant, wd, site = slug.split("|")
    host = f"https://{tenant}.{wd}.myworkdayjobs.com"
    api = f"{host}/wday/cxs/{tenant}/{site}"
    data = http.get_json(f"{api}/jobs", method="POST", data={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "designer"})
    out = []
    for p in data.get("jobPostings", []):
        title = p.get("title", "")
        if not title_family(title):
            continue
        path = p.get("externalPath", "")
        desc, locs, emp, wp, posted = "", [p.get("locationsText", "")], [], None, p.get("postedOn")
        try:
            d = http.get_json(f"{api}{path}").get("jobPostingInfo", {})
            desc = html_to_text(d.get("jobDescription", ""), DESC)
            locs = [d.get("location", "")] + list(d.get("additionalLocations") or []) or locs
            emp = [d.get("timeType", "")]
            wp = d.get("remoteType")
            posted = d.get("startDate") or posted
            if (d.get("country") or {}).get("descriptor"):
                locs.append(d["country"]["descriptor"])
        except http.FetchError:
            pass
        out.append(make_job(title=title, company=company, url=f"{host}/{site}{path}", source=f"workday:{tenant}", kind="ats",
                            locations=locs, workplace=wp, posted=posted, description=desc, emp=emp))
    return out


def oracle(slug, company):
    """Oracle Recruiting Cloud (HCM) public career sites. slug: 'host|siteNumber', e.g. 'ejst.fa.em3.oraclecloud.com|CX_1'."""
    host, _, site = slug.partition("|")
    out = []
    for kw in ("design", "UX"):
        url = (f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList"
               f"&finder=findReqs;siteNumber={site},keyword={kw},limit=100")
        data = http.get_json(url)
        for item in data.get("items", []):
            for r in item.get("requisitionList") or []:
                title = r.get("Title", "")
                if not title_family(title):
                    continue
                locs = [r.get("PrimaryLocation", "")] + [x.get("Name", "") for x in (r.get("secondaryLocations") or []) if isinstance(x, dict)]
                wp = {"ORA_REMOTE": "remote", "ORA_HYBRID": "hybrid", "ORA_ON_SITE": "onsite"}.get(r.get("WorkplaceTypeCode"))
                out.append(make_job(title=title, company=company, url=f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{r.get('Id')}",
                                    source=f"oracle:{host.split('.')[0]}", kind="ats", locations=locs, workplace=wp,
                                    posted=r.get("PostedDate"), description=html_to_text(r.get("ShortDescriptionStr") or "", DESC),
                                    extra_geo=[r.get("PrimaryLocationCountry") or ""]))
    seen = set()
    return [j for j in out if not (j["url"] in seen or seen.add(j["url"]))]


def fetch_board(key, company):
    kind, _, slug = key.partition(":")
    fn = {
        "greenhouse": lambda: greenhouse(slug, company), "greenhouse-eu": lambda: greenhouse(slug, company, eu=True),
        "lever": lambda: lever(slug, company), "lever-eu": lambda: lever(slug, company, eu=True),
        "ashby": lambda: ashby(slug, company), "workable": lambda: workable(slug, company),
        "recruitee": lambda: recruitee(slug, company), "personio": lambda: personio(slug, company),
        "smartrecruiters": lambda: smartrecruiters(slug, company), "bamboohr": lambda: bamboohr(slug, company),
        "teamtailor": lambda: teamtailor(slug, company), "breezy": lambda: breezy(slug, company),
        "pinpoint": lambda: pinpoint(slug, company), "workday": lambda: workday(slug, company),
        "oracle": lambda: oracle(slug, company),
    }.get(kind)
    if not fn:
        raise ValueError(f"unknown board kind {kind}")
    return fn()


def guess_company(key):
    kind, _, slug = key.partition(":")
    s = slug.split("|")[0]
    return s.replace("-", " ").replace("_", " ").replace(".com", "").replace(".org", "").title()
