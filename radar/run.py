"""Daily run: collect from every angle, classify, score, verify, alert, publish.

python -m radar.run            # normal daily run
python -m radar.run --full     # also run the weekly site searches and re-detect company boards
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import re
import sys
import time
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from . import alert, classify, detect, geo, http, score, verify
from .adapters import ats, boards, search
from .model import TODAY, company_domain, job_key, norm_company

ROOT = Path(__file__).resolve().parent.parent
CFG, DATA, PUB = ROOT / "config", ROOT / "data", ROOT / "docs" / "data"
KIND_RANK = {"ats": 0, "board": 1, "search": 2}
HU_RANK = {"yes": 0, "maybe": 1, "no": 2}


def load(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        if default is None:
            raise
        return default


def save(path, obj, pretty=False):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, ensure_ascii=False, indent=1 if pretty else None, separators=None if pretty else (",", ":"))
    Path(path).write_text(txt + "\n", encoding="utf-8")


def log(*a):
    print(*a, flush=True)


def days_between(a, b):
    try:
        return (date.fromisoformat(b) - date.fromisoformat(a)).days
    except (TypeError, ValueError):
        return 999


_JUNK_TITLE = re.compile(r"\b\d+\s*(?:days?|weeks?|hours?|months?|[hdwm])\s+ago\b|[$€£]\s?\d", re.I)
_PAY_TAIL = re.compile(r"\s*(?:[|·•]|\s-\s)\s*[^|·•]*?[$€£]\s?\d[^|·•]*$|\s*\([^()]*[$€£]\s?\d[^()]*\)")


def clean_title(t):
    """'Design Systems Specialist - Fully Remote | Upto $80/hr' -> 'Design Systems Specialist - Fully Remote'."""
    return _PAY_TAIL.sub("", t or "").strip(" -|·") or t


def loc_label(locs, cc):
    """Short place text for the card. A remote job open to 150 countries shouldn't read 'Afghanistan · Albania · Algeria'."""
    if len(locs) <= 4:
        return " · ".join(locs)
    if "HU" in (cc or []):
        return f"Hungary and {len(locs) - 1} other places"
    return f"{len(locs)} places"


class Run:
    def __init__(self, full=False, budget_s=40 * 60):
        self.t0 = time.time()
        self.budget = budget_s
        self.full = full or datetime.now(timezone.utc).weekday() == 0
        self.profile = load(CFG / "profile.json")
        classify.set_profile(self.profile)
        self.sources = load(CFG / "sources.json")["sources"]
        self.companies = load(CFG / "companies.json")["companies"]
        self.search_cfg = load(CFG / "search.json")
        self.state = load(DATA / "state.json", {"jobs": {}, "runs": [], "search": {}})
        self.bstate = load(DATA / "boards.json", {"companies": {}, "discovered": {}})
        prev = load(PUB / "jobs.json", {"jobs": []})
        self.prev = {j["id"]: j for j in prev.get("jobs", [])}
        self.first_run = not self.prev
        self.raw = []
        self.src_health = {}
        self.board_health = {}
        self.ok_boards = set()
        self.search_stats = {"provider": search.provider(), "queries": 0, "results": 0, "boards_found": 0, "jobs": 0, "errors": 0}
        self.excluded = {norm_company(c) for c in self.profile.get("exclude_companies", [])}
        self.site_url = os.environ.get("SITE_URL", "")
        self.known_domains = {norm_company(c["name"]): company_domain(c.get("site")) for c in self.companies if c.get("site")}

    def time_left(self):
        return self.budget - (time.time() - self.t0)

    # ---------- 1. find each company's job board ----------
    def detect_companies(self, limit=500):
        todo = []
        for c in self.companies:
            rec = self.bstate["companies"].get(c["name"])
            if c.get("ats"):
                if not rec or rec.get("board") != c["ats"]:
                    self.bstate["companies"][c["name"]] = {"board": c["ats"], "method": "hint", "checked": TODAY}
                continue
            stale = rec and rec.get("board") is None and days_between(rec.get("checked"), TODAY) >= (7 if self.full else 30)
            if not rec or stale:
                todo.append(c)
        todo = todo[:limit]
        if not todo:
            return
        log(f"detecting job boards for {len(todo)} companies")
        with cf.ThreadPoolExecutor(16) as ex:
            futs = {ex.submit(detect.detect_company, c): c for c in todo}
            for f in cf.as_completed(futs):
                c = futs[f]
                try:
                    board, method = f.result()
                except Exception as e:
                    board, method = None, f"error {type(e).__name__}"
                self.bstate["companies"][c["name"]] = {"board": board, "method": method, "checked": TODAY}
        found = sum(1 for c in todo if self.bstate["companies"][c["name"]]["board"])
        log(f"  found {found} of {len(todo)}")

    def discover(self, key, company, origin, tags=None):
        d = self.bstate["discovered"]
        if key in d:
            for t in tags or []:
                if t not in d[key].setdefault("tags", []):
                    d[key]["tags"].append(t)
            return False
        if any(r.get("board") == key for r in self.bstate["companies"].values()):
            return False
        if len(d) >= 1500:
            return False
        d[key] = {"company": company or ats.guess_company(key), "origin": origin, "added": TODAY, "fails": 0, "tags": list(tags or [])}
        return True

    # ---------- 2. job boards and aggregators ----------
    def run_sources(self):
        def one(src):
            adapter, key = boards.resolve_adapter(src)
            if adapter == "board":
                name = re.sub(r"\s*(careers|jobs|job board|board|vacancies)$", "", src.get("name") or "", flags=re.I).strip()
                self.discover(key, name, f"added: {src['name']}")
                return src, adapter, [], None
            if adapter == "none":
                return src, adapter, [], None
            fn = boards.NAMED.get(adapter)
            if not fn:
                return src, adapter, [], f"unknown adapter {adapter}"
            try:
                return src, adapter, fn(src), None
            except Exception as e:
                code = getattr(e, "status", None)
                boards.DIAG[src["id"]] = {"reason": "blocked" if code in (401, 403, 429, 451) else "error", "status": code}
                return src, adapter, [], f"{type(e).__name__}: {str(e)[:160]}"

        active = [s for s in self.sources if s.get("enabled", True)]
        log(f"reading {len(active)} boards and aggregators")
        with cf.ThreadPoolExecutor(12) as ex:
            for src, adapter, jobs, err in ex.map(one, active):
                for j in jobs:
                    j["source_name"] = src["name"]
                    if src.get("impact"):
                        j["impact_src"] = src["name"]
                    self.raw.append((j, []))
                why = boards.DIAG.get(src["id"]) or {"reason": "skipped" if adapter == "none" else ("ok" if jobs else "no_match")}
                self.src_health[src["id"]] = {"ok": err is None, "count": len(jobs), "error": err, "adapter": adapter, "why": why}
                log(f"  {src['id']:<20} {adapter:<12} {'ok' if not err else 'FAIL'} {len(jobs):>4} {why['reason']:<9} {err or ''}")

    # ---------- 3. search engines ----------
    def run_search(self):
        cfg = self.search_cfg
        prov = self.search_stats["provider"]
        queries = list(cfg.get("daily", []))
        if prov == "duckduckgo":
            queries = queries[:6]
        queries = queries[: cfg.get("max_daily", 30)]
        # The radar runs twice a day; searching once a day is enough and halves the use of paid search credits.
        # A newly added search key (e.g. Serper after DuckDuckGo found nothing) gets a fresh start straight away.
        st = self.state.setdefault("search", {})
        new_provider = st.get("provider") != prov
        if st.get("last_daily") == TODAY and not self.full and not new_provider:
            queries = []
        else:
            st["last_daily"] = TODAY
        st["provider"] = prov
        last_weekly = st.get("last_weekly")
        if self.full or new_provider or days_between(last_weekly, TODAY) >= 7:
            hosts = []
            for s in self.sources:
                if s.get("search"):
                    h = urlparse(s["url"]).netloc.replace("www.", "")
                    if h and h not in hosts:
                        hosts.append(h)
            n = cfg.get("sites_per_query", 5)
            weekly = [f"{cfg['weekly_site_terms']} (" + " OR ".join(f"site:{h}" for h in hosts[i:i + n]) + ")" for i in range(0, len(hosts), n)]
            if prov == "duckduckgo":
                weekly = weekly[:4]
            queries += weekly[: cfg.get("max_weekly", 40)]
            self.state["search"]["last_weekly"] = TODAY
        if not queries:
            return
        log(f"search: {len(queries)} queries via {prov}")
        for q in queries:
            if self.time_left() < 600:
                break
            try:
                results = search.query(q, cfg.get("freshness_days", 7))
            except Exception as e:
                self.search_stats["errors"] += 1
                why = (getattr(e, "body", "") or "").strip()
                self.search_stats["last_error"] = f"{getattr(e, 'status', '') or type(e).__name__} {why[:160]}".strip()
                log(f"  search failed: {type(e).__name__} {str(e)[:120]} {why[:200]}")
                if prov == "duckduckgo" or self.search_stats["errors"] >= 3 and not self.search_stats["queries"]:
                    break   # the same failure on every query (no credits, bad key): stop and report it
                continue
            self.search_stats["queries"] += 1
            self.search_stats["results"] += len(results)
            for r in results:
                key, job = search.to_job(r)
                if key and self.discover(key, "", "search"):
                    self.search_stats["boards_found"] += 1
                if job:
                    job["source_name"] = "LinkedIn (search)" if job["source"] == "linkedin" else f"Search: {job['source']}"
                    self.raw.append((job, []))
                    self.search_stats["jobs"] += 1

    # ---------- 4. company boards ----------
    def harvest(self):
        n = 0
        for j, _ in self.raw:
            for u in (j.get("apply_url"), j.get("url")):
                key = detect.parse_ats_url(u)
                if key and self.discover(key, j.get("company") if j.get("company") != "Unknown" else "", f"via {j.get('source_name')}",
                                         ["impact"] if j.get("impact_src") else None):
                    n += 1
        for u, company in boards.BOARD_LINKS:
            key = detect.parse_ats_url(u)
            if key and self.discover(key, company, "via a jobs roundup", ["impact"]):
                n += 1
        log(f"harvested {n} new company job boards from listings")

    def find_sites(self, limit=250):
        """Find the website (for the logo) of company boards the radar discovered."""
        todo = [(k, d) for k, d in self.bstate["discovered"].items()
                if not d.get("site") and days_between(d.get("site_checked"), TODAY) >= 30][:limit]
        if not todo:
            return
        with cf.ThreadPoolExecutor(16) as ex:
            for (k, d), site in zip(todo, ex.map(lambda kd: detect.find_site(kd[0], kd[1]["company"]), todo)):
                d["site_checked"] = TODAY
                if site:
                    d["site"] = site
        log(f"websites: found {sum(1 for k, d in todo if d.get('site'))} of {len(todo)} discovered companies")

    def run_boards(self):
        owners, sites = {}, {}
        for c in self.companies:
            rec = self.bstate["companies"].get(c["name"]) or {}
            if rec.get("board"):
                owners[rec["board"]] = (c["name"], c.get("tags", []))
                sites[rec["board"]] = company_domain(c.get("site"))
        impact_names = {f"via {x['name']}" for x in self.sources if x.get("impact")}
        for key, d in self.bstate["discovered"].items():
            tags = ["discovered"] + list(d.get("tags", []))
            if d.get("origin") in impact_names and "impact" not in tags:
                tags.append("impact")
            if key not in owners and (d.get("fails", 0) < 6 or self.full):
                owners[key] = (d["company"], tags)  # boards failing 6 runs in a row are retried weekly
                sites[key] = d.get("site")
        log(f"reading {len(owners)} company job boards")

        def one(item):
            key, (company, tags) = item
            try:
                if key.startswith("generic:"):
                    jobs = boards.generic({"id": f"careers:{company}", "url": key[8:]})
                    for j in jobs:
                        j["kind"] = "ats"
                        if not j["company"] or j["company"] in ("Unknown", urlparse(key[8:]).netloc):
                            j["company"] = company
                else:
                    jobs = ats.fetch_board(key, company)
                return key, company, tags, jobs, None
            except Exception as e:
                return key, company, tags, [], f"{type(e).__name__}: {str(e)[:120]}"

        with cf.ThreadPoolExecutor(20) as ex:
            for key, company, tags, jobs, err in ex.map(one, owners.items()):
                self.board_health[key] = {"company": company, "ok": err is None, "count": len(jobs), "error": err}
                d = self.bstate["discovered"].get(key)
                if err is None:
                    self.ok_boards.add(key)
                    if d:
                        d["fails"] = 0
                        d["last_ok"] = TODAY
                elif d:
                    d["fails"] = d.get("fails", 0) + 1
                for j in jobs:
                    j["board_key"] = key
                    j["source_name"] = f"{company} careers"
                    j["company_domain"] = sites.get(key)
                    self.raw.append((j, tags))
        ok = sum(1 for h in self.board_health.values() if h["ok"])
        log(f"  {ok} boards ok, {len(self.board_health) - ok} failed, {sum(h['count'] for h in self.board_health.values())} design jobs")

    # ---------- 5. classify, merge, score ----------
    def process(self):
        drop = set(self.profile["seniority"]["drop"])
        groups = {}
        for j, tags in self.raw:
            if norm_company(j["company"]) in self.excluded:
                continue
            fam = classify.title_family(j["title"])
            if not fam:
                continue
            sen = classify.seniority(j["title"], j.get("seniority_hint"))
            if sen in drop:
                continue
            text_low = (j["title"] + "\n" + j.get("description", "")).lower()
            wp = classify.workplace(j, text_low)
            g = classify.geo_and_eligibility(j, text_low, wp)
            if g["region"] in ("North America", "Other") and wp != "remote":
                continue
            j.update(fam=fam, sen=sen, wp=wp, **g, tags=tags)
            unknown = j["company"] in ("", "Unknown")
            key = ("url|" + j["url"]) if unknown else job_key(j["company"], j["title"])
            groups.setdefault(key, []).append(j)
        recs = {}
        for key, items in groups.items():
            items.sort(key=lambda x: (KIND_RANK[x["kind"]], -len(x.get("description", ""))))
            p = items[0]
            best = self._merged_eligibility(items, p, max((x.get("description", "") for x in items), key=len))
            desc = max((x.get("description", "") for x in items), key=len)
            locs, cc, tags, srcs, emp = [], [], [], [], []
            for x in items:
                for l in x["locations"]:
                    if l and l not in locs:
                        locs.append(l)
                for c in x["countries"]:
                    if c not in cc:
                        cc.append(c)
                for t in x["tags"]:
                    if t not in tags:
                        tags.append(t)
                s = {"n": x.get("source_name") or x["source"], "u": x["url"], "k": x["kind"]}
                if x.get("board_key"):
                    s["b"] = x["board_key"]
                if not any(o["n"] == s["n"] for o in srcs):
                    srcs.append(s)
            text_low = (p["title"] + "\n" + desc).lower()
            for x in items:
                for e in classify.employment(x, text_low):
                    if e not in emp:
                        emp.append(e)
            lf = classify.language_flags(text_low)
            imp = None
            if "ftm" in tags:
                imp = "On your Follow the Money list"
            elif "impact" in tags:
                imp = "Impact company"
            else:
                src = next((x["impact_src"] for x in items if x.get("impact_src")), None)
                if src:
                    imp = f"Found on {src}"
                else:
                    t = classify.impact_text(text_low)
                    if t:
                        imp = "Ad " + t
            if imp and "impact" not in tags:
                tags.append("impact")
            merged = dict(p, description=desc)
            sen, senw = p["sen"], None
            if sen == "unspecified":   # no level in the title: use the experience the ad asks for
                yr = classify.years_required(desc)
                if yr:
                    sen, senw = classify.level_from_years(yr[0]), f"Ad asks for {yr[1]} of experience"
                    if sen in drop:
                        continue
            sc, parts, matched, dom, flags, gaps = score.rules(merged, self.profile, p["fam"], sen, lf, tags)
            jid = hashlib.sha1(key.encode()).hexdigest()[:12]
            dom = next((x["company_domain"] for x in items if x.get("company_domain")), None) or self.known_domains.get(norm_company(p["company"]))
            if not dom:
                for x in items:
                    dom = company_domain(x.get("apply_url")) or company_domain(x.get("url"))
                    if dom:
                        break
            floor = (date.fromisoformat(TODAY) - timedelta(days=400)).isoformat()   # older "posted" dates are placeholders
            posted = min((x["posted"] for x in items if x.get("posted") and x["posted"] >= floor), default=None)
            if posted and posted > TODAY:
                posted = TODAY
            recs[jid] = {
                "id": jid, "title": clean_title(p["title"]), "company": p["company"] if p["company"] != "Unknown" else "",
                "url": p["url"], "apply": p.get("apply_url"), "sources": srcs, "kind": p["kind"],
                "loc": loc_label(locs, cc), "cc": cc, "region": best["region"], "wp": best["wp"], "hu": best["hu"], "huw": best["hu_why"],
                "emp": emp, "sen": sen, "senw": senw, "fam": p["fam"], "score": sc, "rules": sc, "parts": parts, "skills": matched, "domains": dom,
                "flags": flags, "gaps": gaps, "posted": posted, "tags": tags, "salary": next((x["salary"] for x in items if x.get("salary")), None),
                "snip": desc[:700], "live": "verified" if p["kind"] == "ats" else "listed", "checked": TODAY, "imp": imp, "dom": dom,
                "_desc": desc, "_locs": locs, "_board": p.get("board"),
            }
        self.cur = recs
        log(f"{len(self.raw)} raw listings → {len(recs)} unique design jobs")

    def _merged_eligibility(self, items, p, desc):
        """One Hungary decision from everything the sources say about a job. A source that leaves the place
        out must not outvote one that names a hybrid office in another country."""
        locs, hints, tags = [], [], []
        for x in items:
            for l in x.get("locations") or []:
                if l and l not in locs:
                    locs.append(l)
            for h in x.get("geo_hint") or []:
                if h and h not in hints:
                    hints.append(h)
            tags += [t for t in x.get("tags") or [] if t not in tags]
        known = [x["wp"] for x in items if x["wp"] != "unknown"]
        own = [x["wp"] for x in items if x["kind"] == "ats" and x["wp"] != "unknown"]   # the company's own board knows best
        wp = own[0] if own else next((w for w in ("hybrid", "onsite", "remote") if w in known), "unknown")
        if "hungary" in tags and not any(geo.countries_in(l) for l in locs + hints):
            hints.append("Hungary")   # a Hungarian company that doesn't name the city
        g = classify.geo_and_eligibility({"locations": locs, "geo_hint": hints}, (p["title"] + "\n" + desc).lower(), wp)
        return dict(g, wp=wp)

    # ---------- 6. lifecycle ----------
    def lifecycle(self):
        meta = self.state["jobs"]
        # The day each source was first read: jobs without a posting date that were already there that day
        # have no real date, so they are kept out of the "posted in the last N days" filters.
        src_first = self.state.setdefault("src_first", {})
        seen_by = {}
        for jid, r in self.cur.items():
            f = meta.get(jid, {}).get("first", TODAY)
            for s in r.get("sources", []):
                seen_by[s.get("n")] = min(seen_by.get(s.get("n"), TODAY), f)
        for n, f in seen_by.items():
            src_first.setdefault(n, f)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for jid, r in self.cur.items():
            m = meta.setdefault(jid, {"first": TODAY, "first_at": now})
            m.pop("closed", None)
            m["last"] = TODAY
            r["first"], r["last"] = m["first"], TODAY
            r["seen"] = m.get("first_at") or m["first"] + "T00:00:00+00:00"   # when the radar first found it; the site's "New" badge
            if not r.get("posted"):
                start = min((src_first.get(s.get("n"), TODAY) for s in r.get("sources", [])), default=TODAY)
                if r["first"] <= start:
                    r["undated"] = True
            if r["kind"] != "ats" and m.get("live") and days_between(m.get("checked"), TODAY) < 3:
                r["live"], r["checked"] = m["live"], m["checked"]
            if m.get("llm"):
                self._apply_llm(r, m["llm"])
        carried = closed = dropped = 0
        for jid, old in self.prev.items():
            if jid in self.cur:
                continue
            m = meta.get(jid, {})
            if old.get("live") == "closed":
                if days_between(old.get("closed"), TODAY) <= 14:
                    self.cur[jid] = old
                else:
                    dropped += 1
                    meta.pop(jid, None)
                continue
            if old.get("kind") == "ats":
                keys = [s.get("b") for s in old.get("sources", []) if s.get("b")]
                if keys and any(k in self.ok_boards for k in keys):
                    old.update(live="closed", closed=TODAY)
                    m["closed"] = TODAY
                    closed += 1
                else:
                    carried += 1
                self.cur[jid] = old
            else:
                if old.get("posted") and old["posted"] < (date.fromisoformat(TODAY) - timedelta(days=400)).isoformat():
                    old.pop("posted")
                if days_between(old.get("last"), TODAY) > 5 or _JUNK_TITLE.search(old.get("title", "")) \
                        or (old.get("kind") == "search" and search.junk(old.get("title"), old.get("url"))):
                    dropped += 1
                    meta.pop(jid, None)
                    continue
                self.cur[jid] = old
                carried += 1
        log(f"lifecycle: {closed} closed, {carried} carried over, {dropped} dropped")

    # ---------- 7. verify board/search finds ----------
    def verify(self, limit=300):
        todo = [r for r in self.cur.values() if r.get("kind") != "ats" and r.get("live") != "closed"
                and (r.get("live") == "listed" or days_between(r.get("checked"), TODAY) >= 3)]
        todo.sort(key=lambda r: -r.get("score", 0))
        todo = todo[:limit]
        if not todo or self.time_left() < 300:
            return
        log(f"verifying {len(todo)} board/search listings on their own pages")

        def one(r):
            try:
                return r, verify.check({"url": r["url"], "apply_url": r.get("apply"), "source": r["sources"][0]["n"] if r.get("sources") else ""})
            except Exception:
                return r, ("unverified", {})

        with cf.ThreadPoolExecutor(12) as ex:
            for r, (live, fill) in ex.map(one, todo):
                r["live"], r["checked"] = live, TODAY
                m = self.state["jobs"].setdefault(r["id"], {"first": TODAY})
                m["live"], m["checked"] = live, TODAY
                if live == "closed":
                    r["closed"] = TODAY
                if fill.get("company") and not r.get("company"):
                    r["company"] = fill["company"]
                if fill.get("org_url") and not r.get("dom"):
                    r["dom"] = company_domain(fill["org_url"])
                if fill.get("locations") or fill.get("workplace_hint"):
                    if fill.get("locations") and not r.get("loc"):
                        r["loc"] = " · ".join(fill["locations"][:3])
                    self._reclassify(r, fill)

    def _reclassify(self, r, fill):
        """Re-run workplace and Hungary checks with what the job's own page says, if that is clearer."""
        from .model import make_job
        desc = fill.get("description") or r.get("_desc") or r.get("snip", "")
        locs = list(dict.fromkeys((r.get("_locs") or ([r["loc"]] if r.get("loc") else [])) + (fill.get("locations") or [])))
        j = make_job(title=r["title"], company=r.get("company", ""), url=r["url"], source="verify", kind="board", locations=locs,
                     workplace=fill.get("workplace_hint"), description=desc)
        low = (r["title"] + "\n" + desc).lower()
        wp = classify.workplace(j, low)
        g = classify.geo_and_eligibility(j, low, wp)
        if r.get("hu") == "maybe" or r.get("wp") == "unknown":
            r.update(wp=wp, hu=g["hu"], huw=g["hu_why"], region=g["region"], cc=g["countries"])

    # ---------- 8. optional LLM pass ----------
    def _apply_llm(self, r, l):
        r["llm"] = {"s": l["score"], "why": l.get("why", ""), "gaps": l.get("gaps", [])}
        r["score"] = l["score"]
        if r.get("hu") == "maybe" and l.get("hu") in ("yes", "no"):
            r["hu"] = l["hu"]
            r["huw"] = (r.get("huw") or "") + " (read by AI)"

    def llm(self):
        key = http.secret("ANTHROPIC_API_KEY")
        self.llm_stats = {"on": bool(key), "scored": 0, "tokens": 0}
        if not key:
            return
        cfg = self.profile["llm"]
        meta = self.state["jobs"]
        todo = [r for r in self.cur.values() if r.get("_desc") and not meta.get(r["id"], {}).get("llm")
                and r["rules"] >= cfg["min_rule_score"] and r["hu"] in cfg["hu"] and r.get("live") != "closed"]
        todo.sort(key=lambda r: -r["rules"])
        cv = http.secret("CV_TEXT")
        for r in todo[: cfg["max_per_run"]]:
            try:
                res = score.llm_score({"title": r["title"], "company": r["company"], "locations": r["_locs"], "workplace": r["wp"],
                                       "description": r["_desc"]}, self.profile, key, cv)
            except Exception as e:
                log(f"  llm failed: {type(e).__name__} {str(e)[:100]}")
                break
            if res:
                meta[r["id"]]["llm"] = res
                self._apply_llm(r, res)
                self.llm_stats["scored"] += 1
                self.llm_stats["tokens"] += res.get("tokens", 0)
        log(f"llm: scored {self.llm_stats['scored']} jobs, {self.llm_stats['tokens']} tokens")

    # ---------- 9. alerts ----------
    def alerts(self):
        cfg = self.profile["alerts"]
        meta = self.state["jobs"]
        fresh = []
        for r in self.cur.values():
            m = meta.get(r["id"], {})
            if m.get("alerted") or r.get("live") == "closed" or r.get("first") != TODAY or r.get("undated") \
                    or (r.get("posted") and days_between(r["posted"][:10], TODAY) > 14):
                continue
            ok_place = r["hu"] in cfg["hu"] or (cfg.get("also_hungary_onsite") and "HU" in r.get("cc", []))
            if r["score"] >= cfg["min_score"] and ok_place:
                fresh.append(r)
        fresh.sort(key=lambda r: -r["score"])
        # First run: everything is "new", so send one digest of the top matches and mark the rest as seen.
        batch = fresh[: cfg["max_per_run"]]
        payload = [{"title": r["title"], "company": r["company"] or "Unknown", "hu_why": r["huw"], "score": r["score"],
                    "loc": r["loc"], "url": r["url"], "apply_url": r.get("apply")} for r in batch]
        sent = alert.send(payload, self.site_url)
        for r in (fresh if self.first_run else batch):
            meta[r["id"]]["alerted"] = TODAY
        self.alert_count = sent
        log(f"alerts: {sent} sent ({len(fresh)} qualified)")

    # ---------- 10. publish ----------
    def publish(self):
        jobs = []
        for r in self.cur.values():
            out = {k: v for k, v in r.items() if not k.startswith("_") and v not in (None, "", [], {})}
            jobs.append(out)
        jobs.sort(key=lambda r: (r.get("live") == "closed", -r.get("score", 0)))
        save(PUB / "jobs.json", {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "count": len(jobs), "jobs": jobs})

        src_rows = []
        for s in self.sources:
            h = self.src_health.get(s["id"], {})
            src_rows.append({"id": s["id"], "name": s["name"], "url": s["url"], "origin": s.get("origin", ""), "enabled": s.get("enabled", True),
                             "search": s.get("search", False), "adapter": h.get("adapter") or s.get("adapter"), "ok": h.get("ok"),
                             "count": h.get("count", 0), "error": h.get("error"), "note": s.get("note"),
                             "impact": bool(s.get("impact")), "direct": s.get("direct") or s["url"],
                             "why": (h.get("why") or {}).get("reason") or ("paused" if not s.get("enabled", True) else None),
                             "via": (h.get("why") or {}).get("via")})
        comp = self.bstate["companies"]
        open_jobs = [j for j in jobs if j.get("live") != "closed"]
        meta = {
            "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "duration_s": round(time.time() - self.t0),
            "full": self.full,
            "counts": {"open": len(open_jobs), "new_today": sum(1 for j in open_jobs if j.get("first") == TODAY),
                       "hu_yes": sum(1 for j in open_jobs if j.get("hu") == "yes"), "alerts": getattr(self, "alert_count", 0),
                       "closed_recent": len(jobs) - len(open_jobs)},
            "sources": src_rows,
            "boards": {"tracked": len(self.board_health), "ok": len(self.ok_boards),
                       "failed": [{"key": k, "company": h["company"], "error": h["error"]} for k, h in self.board_health.items() if not h["ok"]][:80],
                       "discovered": len(self.bstate["discovered"])},
            "companies": {"total": len(self.companies), "with_board": sum(1 for c in self.companies if (comp.get(c["name"]) or {}).get("board"))},
            "search": self.search_stats,
            "llm": getattr(self, "llm_stats", {"on": False}),
        }
        save(PUB / "meta.json", meta, pretty=True)
        # state: keep job meta for 60 days after last sighting
        jm = self.state["jobs"]
        for jid in list(jm):
            if jid not in self.cur and days_between(jm[jid].get("last"), TODAY) > 60:
                del jm[jid]
        self.state["runs"] = (self.state.get("runs", []) + [{"date": TODAY, "s": meta["duration_s"], **meta["counts"]}])[-60:]
        save(DATA / "state.json", self.state)
        save(DATA / "boards.json", self.bstate, pretty=True)
        log(f"published {len(jobs)} jobs ({meta['counts']['open']} open, {meta['counts']['new_today']} new, {meta['counts']['hu_yes']} doable from Hungary)")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="weekly extras: site searches, re-detect boards")
    ap.add_argument("--no-search", action="store_true")
    ap.add_argument("--no-boards", action="store_true")
    args = ap.parse_args(argv)
    r = Run(full=args.full)
    steps = [("detect", r.detect_companies), ("sources", r.run_sources)]
    if not args.no_search:
        steps.append(("search", r.run_search))
    steps.append(("harvest", r.harvest))
    if not args.no_boards:
        steps += [("sites", r.find_sites), ("boards", r.run_boards)]
    steps += [("process", r.process), ("lifecycle", r.lifecycle), ("verify", r.verify), ("llm", r.llm), ("alerts", r.alerts), ("publish", r.publish)]
    for name, fn in steps:
        t = time.time()
        try:
            fn()
        except Exception:
            log(f"step {name} crashed:\n{traceback.format_exc()}")
            if name in ("process", "publish"):
                sys.exit(1)
        log(f"[{name}] {time.time() - t:.1f}s")


if __name__ == "__main__":
    main()
