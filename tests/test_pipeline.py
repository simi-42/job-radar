"""End-to-end run on fixtures shaped like each API's real responses. No network."""
import json
import pathlib
import shutil
import tempfile
import unittest

from radar import http
import radar.run as run

HERE = pathlib.Path(__file__).parent
FX = HERE / "fixtures"

LONG = ("We are looking for a Senior Product Designer to own end-to-end design for our B2B SaaS platform. You will run user research, "
        "usability tests and A/B tests, prototype in Figma and scale our design system across web and mobile. Experience with complex "
        "enterprise tools, 0-to-1 work and collaboration with engineers is a plus. ") * 3

FIXTURES = {
    # Greenhouse: detail first (its URL also contains the list path)
    "boards-api.greenhouse.io/v1/boards/acme/jobs/111": {"id": 111, "title": "Senior Product Designer", "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/111",
        "location": {"name": "Remote - Europe"}, "updated_at": "2026-11-20T10:00:00Z", "first_published": "2026-11-19T10:00:00Z",
        "content": "&lt;p&gt;" + LONG + "&lt;/p&gt;", "offices": [{"name": "Berlin"}], "metadata": [{"name": "Employment", "value": "Full-time"}]},
    "boards-api.greenhouse.io/v1/boards/acme/jobs": {"jobs": [
        {"id": 111, "title": "Senior Product Designer", "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/111", "location": {"name": "Remote - Europe"}, "updated_at": "2026-11-20T10:00:00Z"},
        {"id": 112, "title": "Backend Engineer", "absolute_url": "x", "location": {"name": "Berlin"}}]},
    "api.lever.co/v0/postings/beta": [
        {"id": "a1", "text": "Product Designer (Design Systems)", "hostedUrl": "https://jobs.lever.co/beta/a1", "applyUrl": "https://jobs.lever.co/beta/a1/apply",
         "categories": {"location": "New York, NY", "commitment": "Full-time", "allLocations": ["New York, NY"]}, "workplaceType": "remote", "country": "US",
         "createdAt": 1763600000000, "descriptionPlain": LONG + " Candidates must be authorized to work in the United States.", "lists": []},
        {"id": "a2", "text": "UX Designer", "hostedUrl": "https://jobs.lever.co/beta/a2", "categories": {"location": "Budapest", "commitment": "Contract"},
         "workplaceType": "hybrid", "country": "HU", "createdAt": 1763500000000, "descriptionPlain": LONG, "lists": []}],
    "api.ashbyhq.com/posting-api/job-board/gamma": {"jobs": [
        {"id": "g1", "title": "Staff Product Designer", "location": "Remote", "secondaryLocations": [], "isRemote": True, "workplaceType": "Remote",
         "employmentType": "FullTime", "publishedAt": "2026-11-22T08:00:00Z", "jobUrl": "https://jobs.ashbyhq.com/gamma/g1",
         "descriptionPlain": LONG + " We hire anywhere between UTC-1 and UTC+3.", "isListed": True,
         "compensation": {"compensationTierSummary": "€90K – €110K"}}]},
    "remotive.com/api": {"jobs": [{"id": 1, "url": "https://remotive.com/remote-jobs/design/senior-product-designer-1", "title": "Senior Product Designer",
        "company_name": "Delta", "job_type": "full_time", "publication_date": "2026-11-21T00:00:00", "candidate_required_location": "Worldwide",
        "description": "<p>" + LONG + "</p>"}, {"id": 2, "url": "u", "title": "Copywriter", "company_name": "Z"}]},
    "weworkremotely.com": open(FX / "wwr.xml").read() if (FX / "wwr.xml").exists() else "",
    "raw.githubusercontent.com/sarabrunettini": (FX / "hiddenjobs.json").read_text(),
    "example-board.test": """<html><head><script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting","title":"Lead UX Designer",
        "hiringOrganization":{"@type":"Organization","name":"Epsilon"},"jobLocationType":"TELECOMMUTE","applicantLocationRequirements":{"@type":"Country","name":"European Union"},
        "datePosted":"2026-11-18","url":"https://epsilon.test/jobs/1","description":"Lead our design system."}</script></head><body></body></html>""",
    "next-board.test": """<html><script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"jobs":[{"title":"Product Designer","slug":"pd-zeta",
        "company":{"name":"Zeta"},"location":"Amsterdam, Netherlands","remote":false,"postedAt":"2026-11-10"},{"title":"Sales Lead","slug":"s"}]}}}</script></html>""",
    "links-board.test": """<html><body><a href="/job/1">Senior Product Designer at Eta</a><a href="/about">About us</a>
        <a href="https://jobs.ashbyhq.com/theta/123">Product Designer</a></body></html>""",
    "api.ashbyhq.com/posting-api/job-board/theta": {"jobs": [{"id": "t1", "title": "Product Designer", "location": "Budapest, Hungary", "workplaceType": "OnSite",
        "employmentType": "PartTime", "publishedAt": "2026-11-15T08:00:00Z", "jobUrl": "https://jobs.ashbyhq.com/theta/123", "descriptionPlain": LONG}]},
}

WWR = """<?xml version="1.0"?><rss version="2.0"><channel><item><title>Iota: Senior Product Designer</title><region>Anywhere in the World</region>
<link>https://weworkremotely.com/remote-jobs/iota-senior-product-designer</link><pubDate>Sat, 21 Nov 2026 10:00:00 +0000</pubDate>
<description>&lt;p&gt;Design our app.&lt;/p&gt;</description></item><item><title>Kappa: Customer Support</title><link>x</link></item></channel></rss>"""


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        (self.tmp / "config").mkdir()
        shutil.copy(HERE.parent / "config" / "profile.json", self.tmp / "config")
        shutil.copy(HERE.parent / "config" / "search.json", self.tmp / "config")
        srcs = [
            {"id": "hiddenjobs", "name": "Hidden Jobs", "url": "https://raw.githubusercontent.com/sarabrunettini/hiddenjobs/main/jobs.json", "adapter": "hiddenjobs"},
            {"id": "remotive", "name": "Remotive", "url": "https://remotive.com/api/remote-jobs?category=design", "adapter": "remotive"},
            {"id": "wwr", "name": "WWR", "url": "https://weworkremotely.com/categories/remote-design-jobs.rss", "adapter": "rss"},
            {"id": "ld", "name": "LD board", "url": "https://example-board.test/jobs", "adapter": "generic"},
            {"id": "nx", "name": "Next board", "url": "https://next-board.test/jobs", "adapter": "generic"},
            {"id": "ln", "name": "Links board", "url": "https://links-board.test/jobs", "adapter": "auto"},
            {"id": "added", "name": "Theta board", "url": "https://jobs.ashbyhq.com/theta", "adapter": "auto"},
        ]
        (self.tmp / "config" / "sources.json").write_text(json.dumps({"sources": srcs}))
        comps = [{"name": "Acme", "site": "https://acme.test", "ats": "greenhouse:acme", "tags": ["ftm", "impact"]},
                 {"name": "Beta", "site": "https://beta.test", "ats": "lever:beta", "tags": ["top-eu"]},
                 {"name": "Gamma", "site": "https://gamma.test", "ats": "ashby:gamma", "tags": ["design-forward"]}]
        (self.tmp / "config" / "companies.json").write_text(json.dumps({"companies": comps}))
        fxdir = self.tmp / "fx"
        fxdir.mkdir()
        mapping = {}
        for i, (k, v) in enumerate(FIXTURES.items()):
            p = fxdir / f"{i}.txt"
            if k == "weworkremotely.com":
                v = WWR
            p.write_text(v if isinstance(v, str) else json.dumps(v))
            mapping[k] = str(p)
        http.FIXTURES = mapping
        run.CFG, run.DATA, run.PUB = self.tmp / "config", self.tmp / "data", self.tmp / "docs" / "data"

    def tearDown(self):
        http.FIXTURES = None
        shutil.rmtree(self.tmp)

    def test_run(self):
        run.main(["--no-search"])
        jobs = json.loads((run.PUB / "jobs.json").read_text())["jobs"]
        meta = json.loads((run.PUB / "meta.json").read_text())
        by = {(j.get("company"), j["title"]): j for j in jobs}

        acme = by[("Acme", "Senior Product Designer")]
        self.assertEqual((acme["hu"], acme["wp"], acme["live"]), ("yes", "remote", "verified"))
        self.assertGreaterEqual(acme["score"], 70)
        self.assertIn("ftm", acme["tags"])
        self.assertEqual(acme.get("imp"), "On your Follow the Money list")

        beta_us = by[("Beta", "Product Designer (Design Systems)")]
        self.assertEqual(beta_us["hu"], "no")
        beta_hu = by[("Beta", "UX Designer")]
        self.assertEqual((beta_hu["hu"], beta_hu["wp"]), ("yes", "hybrid"))
        self.assertIn("contract", beta_hu["emp"])

        gamma = by[("Gamma", "Staff Product Designer")]
        self.assertEqual(gamma["hu"], "yes")
        self.assertEqual(gamma.get("salary"), "€90K – €110K")

        self.assertEqual(by[("Delta", "Senior Product Designer")]["hu"], "yes")
        self.assertEqual(by[("Iota", "Senior Product Designer")]["hu"], "yes")
        self.assertEqual(by[("Epsilon", "Lead UX Designer")]["hu"], "yes")
        self.assertIn(("Zeta", "Product Designer"), by)
        theta = by[("Theta", "Product Designer")]
        self.assertEqual((theta["kind"], theta["hu"]), ("ats", "yes"))
        self.assertIn("part-time", theta["emp"])
        self.assertTrue(all(classify_ok(j["title"]) for j in jobs))

        hidden = [j for j in jobs if any(s["n"] == "Hidden Jobs" for s in j["sources"])]
        self.assertGreater(len(hidden), 40)
        self.assertGreater(meta["boards"]["discovered"], 20)  # harvested from Hidden Jobs URLs
        self.assertTrue(meta["sources"][0]["ok"])

        # second run: Acme job disappears from its board -> closed
        FIX2 = dict(http.FIXTURES)
        p = self.tmp / "fx" / "acme_empty.txt"
        p.write_text(json.dumps({"jobs": []}))
        FIX2 = {("boards-api.greenhouse.io/v1/boards/acme/jobs"): str(p), **{k: v for k, v in http.FIXTURES.items() if "acme" not in k}}
        http.FIXTURES = FIX2
        run.main(["--no-search"])
        jobs2 = {j["id"]: j for j in json.loads((run.PUB / "jobs.json").read_text())["jobs"]}
        self.assertEqual(jobs2[acme["id"]]["live"], "closed")
        self.assertEqual(jobs2[gamma["id"]]["first"], gamma["first"])


def classify_ok(t):
    from radar import classify
    return classify.title_family(t) is not None


if __name__ == "__main__":
    unittest.main()
