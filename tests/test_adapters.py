"""Parse tests for every adapter, using payloads shaped like each service's documented responses."""
import json
import pathlib
import tempfile
import unittest

from radar import classify, detect, http, verify
from radar.adapters import ats, boards, search

classify.set_profile(json.loads((pathlib.Path(__file__).parent.parent / "config" / "profile.json").read_text()))
DESC = "Senior product designer for our SaaS platform, Figma, design systems. " * 8


def fixtures(d):
    tmp = pathlib.Path(tempfile.mkdtemp())
    m = {}
    for i, (k, v) in enumerate(d.items()):
        p = tmp / f"{i}"
        p.write_text(v if isinstance(v, str) else json.dumps(v))
        m[k] = str(p)
    http.FIXTURES = m


class Adapters(unittest.TestCase):
    def tearDown(self):
        http.FIXTURES = None

    def test_workable(self):
        fixtures({"apply.workable.com/api/v1/widget/accounts/acme": {"name": "Acme Ltd", "jobs": [
            {"title": "Product Designer", "shortcode": "AB1", "employment_type": "Full-time", "telecommuting": True, "url": "https://apply.workable.com/acme/j/AB1/",
             "published_on": "2026-11-20", "country": "Hungary", "city": "Budapest", "locations": [{"country": "Hungary", "city": "Budapest"}], "description": DESC},
            {"title": "Accountant", "url": "x"}]}})
        jobs = ats.workable("acme", "Acme")
        self.assertEqual(len(jobs), 1)
        self.assertEqual((jobs[0]["company"], jobs[0]["locations"][0], jobs[0]["remote_flag"]), ("Acme Ltd", "Budapest, Hungary", True))

    def test_recruitee(self):
        fixtures({"acme.recruitee.com/api/offers": {"offers": [{"title": "Senior UX Designer", "careers_url": "https://acme.recruitee.com/o/ux", "location": "Remote",
            "country_code": "NL", "remote": True, "employment_type_code": "fulltime", "published_at": "2026-11-01 10:00:00 UTC", "description": "<p>x</p>"}]}})
        j = ats.recruitee("acme", "Acme")[0]
        self.assertEqual((j["workplace_hint"], j["posted"], j["geo_hint"]), ("remote", "2026-11-01", ["Netherlands"]))

    def test_personio(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?><workzag-jobs><position><id>123</id><subcompany>Acme GmbH</subcompany><office>Berlin</office>
        <additionalOffices><office>Remote</office></additionalOffices><name>Product Designer (m/w/d)</name><jobDescriptions><jobDescription><name>About</name>
        <value><![CDATA[<p>Design things</p>]]></value></jobDescription></jobDescriptions><employmentType>permanent</employmentType><schedule>full-time</schedule>
        <seniority>experienced</seniority><createdAt>2026-11-10T09:00:00+00:00</createdAt></position></workzag-jobs>"""
        fixtures({"acme.jobs.personio.de/xml": xml})
        j = ats.personio("acme|de", "Acme")[0]
        self.assertEqual((j["title"], j["company"], j["locations"]), ("Product Designer", "Acme GmbH", ["Berlin", "Remote"]))
        self.assertIn("/job/123", j["url"])

    def test_smartrecruiters(self):
        fixtures({"postings/abc": {"postingUrl": "https://jobs.smartrecruiters.com/Acme/abc", "jobAd": {"sections": {"jobDescription": {"text": "<p>Do design</p>"}}}},
                  "companies/Acme/postings?q=designer": {"content": [{"id": "abc", "name": "Senior Product Designer", "releasedDate": "2026-11-18T00:00:00.000Z",
                      "location": {"city": "Lisbon", "country": "pt", "remote": False, "fullLocation": "Lisbon, Portugal"}, "company": {"name": "Acme"},
                      "typeOfEmployment": {"label": "Full-time"}}]}})
        j = ats.smartrecruiters("Acme", "Acme")[0]
        self.assertEqual((j["url"], j["geo_hint"], j["description"]), ("https://jobs.smartrecruiters.com/Acme/abc", ["Portugal"], "Do design"))

    def test_bamboohr_breezy_workday(self):
        fixtures({"acme.bamboohr.com/careers/7/detail": {"result": {"jobOpening": {"description": "<p>x</p>"}}},
                  "acme.bamboohr.com/careers/list": {"result": [{"id": 7, "jobOpeningName": "UX Designer", "atsLocation": {"country": "Hungary", "city": "Budapest"},
                      "isRemote": None, "locationType": "2", "employmentStatusLabel": "Full-Time"}]},
                  "acme.breezy.hr/json": [{"name": "Product Designer", "url": "https://acme.breezy.hr/p/1", "published_date": "2026-11-02T00:00:00Z",
                      "type": {"name": "Contract"}, "location": {"name": "Remote", "is_remote": True, "country": {"name": "Spain"}}}],
                  "wday/cxs/acme/Careers/job/": {"jobPostingInfo": {"jobDescription": "<p>x</p>", "location": "Budapest", "timeType": "Full time",
                      "remoteType": "Hybrid", "startDate": "2026-11-15", "country": {"descriptor": "Hungary"}}},
                  "wday/cxs/acme/Careers/jobs": {"jobPostings": [{"title": "Senior Product Designer", "externalPath": "/job/Budapest/Senior-Product-Designer_R1",
                      "locationsText": "Budapest", "postedOn": "Posted 3 Days Ago"}]}})
        self.assertEqual(ats.bamboohr("acme", "Acme")[0]["workplace_hint"], "hybrid")
        self.assertEqual(ats.breezy("acme", "Acme")[0]["emp_hint"], ["Contract"])
        w = ats.workday("acme|wd3|Careers", "Acme")[0]
        self.assertEqual((w["url"], w["workplace_hint"]), ("https://acme.wd3.myworkdayjobs.com/Careers/job/Budapest/Senior-Product-Designer_R1", "Hybrid"))

    def test_aggregators(self):
        fixtures({"remoteok.com/api": [{"legal": "x"}, {"position": "Senior Product Designer", "company": "Acme", "location": "Europe", "url": "https://remoteok.com/1",
                      "date": "2026-11-20T00:00:00+00:00", "description": "x", "tags": ["design"]}],
                  "himalayas.app": {"jobs": [{"title": "Product Designer", "companyName": "Acme", "locationRestrictions": [], "timezoneRestrictions": [-1, 0, 1, 2, 3],
                      "pubDate": 1763600000, "applicationLink": "https://himalayas.app/j/1", "employmentType": "Full Time", "seniority": ["Senior"]}]},
                  "arbeitnow.com": {"data": [{"title": "UX Designer (m/w/d)", "company_name": "Acme", "url": "https://arbeitnow.com/1", "remote": False,
                      "location": "Berlin", "created_at": 1763600000, "job_types": ["full time"]}], "links": {"next": None}},
                  "jobicy.com": {"jobs": [{"jobTitle": "Lead Product Designer", "companyName": "Acme", "url": "https://jobicy.com/1", "jobGeo": "EMEA",
                      "pubDate": "2026-11-21 10:00:00", "jobType": ["Full-Time"]}]},
                  "workingnomads.com": [{"title": "Product Designer", "company_name": "Acme", "url": "https://workingnomads.com/1", "location": "Anywhere", "pub_date": "2026-11-20"}]})
        for fn, url in [(boards.remoteok, "https://remoteok.com/api"), (boards.himalayas, "https://himalayas.app/jobs/api?limit=100"),
                        (boards.arbeitnow, "https://www.arbeitnow.com/api/job-board-api"), (boards.jobicy, "https://jobicy.com/api/v2/remote-jobs"),
                        (boards.workingnomads, "https://www.workingnomads.com/api/exposed_jobs/")]:
            jobs = fn({"id": "t", "url": url})
            self.assertEqual(len(jobs), 1, fn.__name__)
        h = boards.himalayas({"id": "t", "url": "https://himalayas.app/jobs/api?limit=100"})[0]
        self.assertIn("CET +/- 2", h["description"])

    def test_rss_wp_job_manager(self):
        feed = """<?xml version="1.0"?><rss version="2.0" xmlns:job_listing="https://wpjobmanager.com"><channel><item><title>Senior Product Designer</title>
        <link>https://euremotejobs.com/job/1</link><pubDate>Fri, 20 Nov 2026 09:00:00 +0000</pubDate><job_listing:company>Acme</job_listing:company>
        <job_listing:location>Remote, Europe</job_listing:location><job_listing:job_type>Full Time</job_listing:job_type><description>Do design &amp; things</description></item></channel></rss>"""
        fixtures({"euremotejobs.com": feed})
        j = boards.rss({"id": "eu", "url": "https://euremotejobs.com/?feed=job_feed"})[0]
        self.assertEqual((j["company"], j["locations"], j["posted"]), ("Acme", ["Remote, Europe"], "2026-11-20"))

    def test_resolve(self):
        self.assertEqual(boards.resolve_adapter({"url": "https://jobs.lever.co/acme", "adapter": "auto"}), ("board", "lever:acme"))
        self.assertEqual(boards.resolve_adapter({"url": "https://remotive.com/api/x", "adapter": "auto"})[0], "remotive")
        self.assertEqual(boards.resolve_adapter({"url": "https://foo.org/feed/", "adapter": "auto"})[0], "rss")
        self.assertEqual(boards.resolve_adapter({"url": "https://foo.org/jobs", "adapter": "auto"})[0], "generic")


class LinkTitles(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(boards._clean_link_title("🇩🇰 København, DK Senior Product Designer - Twoday"), ("Senior Product Designer", "Twoday", "København, DK"))
        t, c, l = boards._clean_link_title("Pika is hiring for a position of Senior Product Designer in Palo Alto, CA")
        self.assertEqual((t, c, l), ("Senior Product Designer", "Pika", "Palo Alto, CA"))
        self.assertEqual(boards._company_from_url("https://4dayweek.io/job/senior-product-designer-at-nexus-mods-ae641807"), "Nexus Mods")
        self.assertEqual(boards._company_from_url("https://www.remoterocketship.com/publicjobs/company/kettle/jobs/x"), "Kettle")


class Detect(unittest.TestCase):
    def tearDown(self):
        http.FIXTURES = None

    def test_urls(self):
        p = detect.parse_ats_url
        self.assertEqual(p("https://job-boards.greenhouse.io/figma/jobs/123"), "greenhouse:figma")
        self.assertEqual(p("https://job-boards.eu.greenhouse.io/dept/jobs/1"), "greenhouse-eu:dept")
        self.assertEqual(p("https://boards.greenhouse.io/embed/job_board?for=acme"), "greenhouse:acme")
        self.assertEqual(p("https://jobs.ashbyhq.com/ecosia.org/abc"), "ashby:ecosia.org")
        self.assertEqual(p("https://jobs.eu.lever.co/acme/1"), "lever-eu:acme")
        self.assertEqual(p("https://apply.workable.com/meridia/j/ABC/"), "workable:meridia")
        self.assertEqual(p("https://fairphone.jobs.personio.com/"), "personio:fairphone|com")
        self.assertEqual(p("https://cloudera.wd5.myworkdayjobs.com/External_Career/job/x"), "workday:cloudera|wd5|External_Career")
        self.assertEqual(p("https://cloudera.wd5.myworkdayjobs.com/en-US/External_Career/job/x"), "workday:cloudera|wd5|External_Career")
        self.assertIsNone(p("https://www.example.com/careers"))

    def test_detect_from_page(self):
        fixtures({"acme.test/careers": '<html><iframe src="https://jobs.ashbyhq.com/acme/embed"></iframe></html>',
                  "acme.test": '<html><a href="/careers">Careers</a></html>'})
        self.assertEqual(detect.detect_company({"name": "Acme", "site": "https://acme.test"}), ("ashby:acme", "page"))

    def test_probe(self):
        fixtures({"boards-api.greenhouse.io/v1/boards/zetacorp": {"name": "Zeta Corp"}, "zetacorp.test": "<html>nothing</html>"})
        self.assertEqual(detect.detect_company({"name": "Zeta Corp", "site": "https://zetacorp.test"}), ("greenhouse:zetacorp", "probe"))


class SearchAndVerify(unittest.TestCase):
    def tearDown(self):
        http.FIXTURES = None

    def test_to_job(self):
        k, j = search.to_job({"title": "Acme hiring Senior Product Designer in Budapest, Hungary | LinkedIn", "url": "https://www.linkedin.com/jobs/view/123?x=1", "snippet": "s"})
        self.assertEqual((k, j["company"], j["title"], j["locations"]), (None, "Acme", "Senior Product Designer", ["Budapest, Hungary"]))
        k, j = search.to_job({"title": "Product Designer - Acme", "url": "https://jobs.ashbyhq.com/acme/1"})
        self.assertEqual((k, j), ("ashby:acme", None))

    def test_verify(self):
        fixtures({"closed.test": "<html><h1>This job is no longer available</h1></html>",
                  "open.test": '<html><script type="application/ld+json">{"@type":"JobPosting","title":"Product Designer","hiringOrganization":{"name":"Acme"},'
                               '"validThrough":"2099-01-01","jobLocation":{"address":{"addressLocality":"Budapest","addressCountry":"HU"}}}</script></html>',
                  "expired.test": '<html><script type="application/ld+json">{"@type":"JobPosting","title":"Product Designer","validThrough":"2020-01-01"}</script></html>'})
        self.assertEqual(verify.check({"url": "https://closed.test/job/1/x"})[0], "closed")
        live, fill = verify.check({"url": "https://open.test/jobs/1/x"})
        self.assertEqual((live, fill.get("company")), ("page live", "Acme"))
        self.assertEqual(verify.check({"url": "https://expired.test/jobs/1/x"})[0], "closed")


if __name__ == "__main__":
    unittest.main()
