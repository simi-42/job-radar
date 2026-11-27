"""Stapply's open job dataset (https://github.com/kalil0321/ats-scrapers, data CC0 1.0).

Stapply reads tens of thousands of company job boards every day and publishes the result as one Parquet file.
The radar reads only the columns it needs, for design titles, with DuckDB, once per new snapshot.
Company boards that Stapply already covers are then left out of the radar's own daily reads.
"""
import csv
import io
import re
import time

from .. import geo, http
from ..classify import title_family
from ..detect import parse_ats_url
from ..model import html_to_text, make_job

MANIFEST = "https://storage.stapply.ai/jobs/v1/manifest.json"
HOST = "https://storage.stapply.ai/"
INVENTORY = "https://raw.githubusercontent.com/kalil0321/ats-scrapers/main/ats-companies/{}.csv"
# Company-board systems the radar reads itself; Stapply's lists of the boards it covers on each of them.
INVENTORY_KINDS = ["greenhouse", "lever", "ashby", "workable", "recruitee", "personio", "smartrecruiters",
                   "bamboohr", "teamtailor", "breezy", "pinpoint", "workday", "oracle"]
# Job boards in Stapply's data that the radar used to read itself (Stapply source name -> radar source id).
BOARD_SOURCES = {"remoteok": "remoteok", "weworkremotely": "wwr", "welcometothejungle": "wttj", "ycombinator": "ycjobs"}
DESIGN_RE = r"(?i)(design|\bux\b|\bui\b|user experience|interaction|experience architect)"
WANT = ["title", "company", "url", "apply_url", "location", "locations", "country_iso", "region", "is_remote", "workplace_type",
        "posted_at", "source_created_at", "employment_type", "experience", "salary_summary", "ats_type"]
DESC = 3000


def norm_key(key):
    """Board keys compared without the EU-host variant or Personio's domain suffix."""
    kind, _, slug = (key or "").partition(":")
    kind = kind.replace("-eu", "")
    if kind == "personio":
        slug = slug.split("|")[0]
    return f"{kind}:{slug.lower()}"


def covered_boards():
    """Board keys (radar format, normalised) that Stapply reads every day."""
    keys = set()
    for kind in INVENTORY_KINDS:
        try:
            text = http.get_text(INVENTORY.format(kind), timeout=60)
        except http.FetchError:
            continue
        for row in csv.DictReader(io.StringIO(text)):
            k = parse_ats_url(row.get("url") or "")
            if k:
                keys.add(norm_key(k))
    return keys


def _parquet_url(manifest):
    p = ((manifest.get("all") or {}).get("parquet")) or ""
    if p.startswith(("http://", "https://")):
        return p
    return HOST + p.lstrip("/")


def _keep_place(country, remote, place):
    """Europe, Hungary or remote. Rows with no place at all are left out: in this data they are mostly
    boards from outside Europe, and they would only fill the "maybe" list."""
    if remote:
        return True
    if country:
        return geo.is_europe(country.upper())
    low = (place or "").lower()
    if not low:
        return False
    return bool(re.search(r"europe|emea|worldwide|anywhere|remote", low)) or any(geo.is_europe(c) for c in geo.countries_in(place))


def read(manifest=None, parquet=None, log=print):
    """Returns (jobs, stats). jobs are radar job dicts, kind 'ats', board 'stapply'."""
    import duckdb   # only needed here; installed in the GitHub workflow

    manifest = manifest or http.get_json(MANIFEST, timeout=60)
    src = parquet or _parquet_url(manifest)
    con = duckdb.connect()
    if src.startswith("http"):
        con.execute("INSTALL httpfs; LOAD httpfs;")
    t = time.time()
    have = {r[0]: r[1] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{src}')").fetchall()}
    cols = [c for c in WANT if c in have]
    desc = f"left(description, {DESC}) AS description" if "description" in have else "NULL AS description"
    rows = con.execute(f"SELECT {', '.join(cols)}, {desc} FROM read_parquet('{src}') WHERE regexp_matches(title, ?)",
                       [DESIGN_RE]).fetchall()
    log(f"stapply: {len(rows)} design-titled rows in {time.time() - t:.0f}s from {src}")
    names = cols + ["description"]
    out, types = [], {}
    for row in rows:
        r = dict(zip(names, row))
        title = r.get("title") or ""
        if not title_family(title) or not r.get("url"):
            continue
        wp = (r.get("workplace_type") or "").lower()
        remote = r.get("is_remote") is True or "remote" in wp
        place = r.get("location") or ""
        if not _keep_place(r.get("country_iso"), remote, place):
            continue
        locs = [place] if place else []
        extra = r.get("locations")
        if isinstance(extra, list):
            locs += [str(x) for x in extra if x and str(x) not in locs][:6]
        if r.get("country_iso") and not locs:
            locs.append(geo.label(r["country_iso"].upper()))
        emp = r.get("employment_type")
        posted = r.get("posted_at") or r.get("source_created_at")
        job = make_job(title=title, company=r.get("company") or "", url=r["url"], source="stapply", kind="ats",
                       locations=locs, workplace="remote" if remote else (wp or None), posted=str(posted) if posted else None,
                       description=html_to_text(r.get("description") or "", DESC), emp=[emp] if isinstance(emp, str) else emp,
                       salary=r.get("salary_summary"), apply_url=r.get("apply_url"),
                       extra_geo=[geo.label(r["country_iso"].upper())] if r.get("country_iso") else [],
                       seniority_hint=r.get("experience") if isinstance(r.get("experience"), str) else None)
        job["board_key"] = "stapply"
        job["source_name"] = "Company board (via Stapply)"
        out.append(job)
        a = r.get("ats_type") or ""
        types[a] = types.get(a, 0) + 1
    stats = {"generated_at": manifest.get("generated_at"), "rows": len(rows), "jobs": len(out), "by_source": types,
             "seconds": round(time.time() - t)}
    return out, stats
