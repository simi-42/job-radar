"""Check that a job found on a board or through search is still open on its own page."""
import re

from . import http
from .adapters.boards import jsonld_jobs
from .model import TODAY, parse_date

CLOSED = re.compile(
    r"no longer accepting applications|no longer available|position has been filled|job has expired|this job (?:has )?(?:been )?closed|"
    r"position is closed|posting (?:has )?closed|applications? (?:are|is) (?:now )?closed|job not found|vacancy has been filled|"
    r"this job is no longer|role has been filled|nicht mehr verfügbar|stelle ist (?:bereits )?besetzt|job you are looking for (?:is|was) not found|"
    r"this posting is no longer|page you(?:'re| are) looking for (?:doesn't|does not) exist", re.I)


def check(job):
    """Returns (live, details). live: 'page live' | 'closed' | 'unverified'. May fill company/location from structured data."""
    url = job.get("apply_url") or job.get("url")
    if not url or "linkedin.com" in url:
        return "unverified", {}
    try:
        status, text, final = http.fetch(url, timeout=20, retries=1)
    except http.FetchError as e:
        if e.status in (404, 410):
            return "closed", {}
        return "unverified", {}
    head = text[:200000]
    fill = {}
    src = {"id": job.get("source", "verify"), "url": final}
    for j in jsonld_jobs(head, final, src):
        vt = parse_date(j.get("valid_through"))
        if vt and vt < TODAY:
            return "closed", {}
        fill = {k: j[k] for k in ("company", "locations", "description", "workplace_hint", "posted", "emp_hint", "org_url") if j.get(k) and j[k] != "Unknown"}
        break
    if CLOSED.search(re.sub(r"<[^>]+>", " ", head)):
        return "closed", {}
    if final.rstrip("/").count("/") <= 2 and url.rstrip("/").count("/") > 3:
        return "closed", {}  # redirected to a homepage
    return "page live", fill
