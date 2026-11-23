import json
import pathlib
import unittest

from radar import classify
from radar.model import make_job

classify.set_profile(json.loads((pathlib.Path(__file__).parent.parent / "config" / "profile.json").read_text()))


def elig(locations=None, desc="", remote=None, workplace=None, title="Senior Product Designer"):
    j = make_job(title=title, company="X", url="u", source="s", kind="ats", locations=locations or [], remote=remote, workplace=workplace, description=desc)
    low = (title + "\n" + desc).lower()
    wp = classify.workplace(j, low)
    return wp, classify.geo_and_eligibility(j, low, wp)


class Titles(unittest.TestCase):
    def test_family(self):
        f = classify.title_family
        self.assertEqual(f("Senior Product Designer"), "core")
        self.assertEqual(f("UX/UI Designer (m/w/d)"), "core")
        self.assertEqual(f("Product Designer, Design Systems"), "core")
        self.assertEqual(f("Lead Product Designer"), "leadership")
        self.assertEqual(f("Head of Design"), "leadership")
        self.assertEqual(f("Design Systems Engineer"), "adjacent")
        self.assertEqual(f("Design Engineer"), "adjacent")
        self.assertIsNone(f("UX Researcher"))
        self.assertIsNone(f("Graphic Designer"))
        self.assertIsNone(f("Product Manager, Design Tools"))
        self.assertIsNone(f("Senior Backend Engineer"))
        self.assertIsNone(f("Industrial Product Designer"))
        self.assertIsNone(f("Marketing Designer"))
        self.assertEqual(f("Senior Designer"), "adjacent")

    def test_seniority(self):
        s = classify.seniority
        self.assertEqual(s("Senior Product Designer"), "senior")
        self.assertEqual(s("Staff Product Designer"), "staff")
        self.assertEqual(s("Product Designer"), "unspecified")
        self.assertEqual(s("Junior UX Designer"), "junior")
        self.assertEqual(s("UX Design Intern"), "intern")
        self.assertEqual(s("Mid/Senior Product Designer"), "senior")
        self.assertEqual(s("Product Designer, Early Stage"), "unspecified")
        self.assertEqual(s("Product Designer II"), "mid")


class Eligibility(unittest.TestCase):
    def test_hungary(self):
        wp, g = elig(["Budapest, Hungary"], workplace="Hybrid")
        self.assertEqual((wp, g["hu"], g["region"]), ("hybrid", "yes", "Hungary"))

    def test_remote_europe(self):
        wp, g = elig(["Remote - Europe"])
        self.assertEqual((wp, g["hu"]), ("remote", "yes"))
        wp, g = elig(["Berlin, Germany"], remote=True, desc="You can work remotely from anywhere in Europe.")
        self.assertEqual(g["hu"], "yes")

    def test_remote_worldwide(self):
        wp, g = elig(["Anywhere"], remote=True)
        self.assertEqual(g["hu"], "yes")

    def test_remote_us_only(self):
        wp, g = elig(["Remote, US"], remote=True)
        self.assertEqual(g["hu"], "no")
        wp, g = elig(["New York, NY"], remote=True, desc="Candidates must be authorized to work in the United States.")
        self.assertEqual(g["hu"], "no")

    def test_timezone(self):
        wp, g = elig(["Remote"], remote=True, desc="We hire anyone between UTC-1 and UTC+3.")
        self.assertEqual((g["hu"], g["hu_why"]), ("yes", "Remote, your time zone allowed"))
        wp, g = elig(["Remote"], remote=True, desc="Must work in UTC-8 to UTC-5 hours.")
        self.assertEqual(g["hu"], "no")

    def test_remote_one_country(self):
        wp, g = elig(["Remote, Germany"], remote=True)
        self.assertEqual(g["hu"], "maybe")
        wp, g = elig(["Remote, Germany"], remote=True, desc="You must be based in Germany.")
        self.assertEqual(g["hu"], "no")

    def test_eu_work_rights(self):
        wp, g = elig(["Remote"], remote=True, desc="You need the right to work in the EU.")
        self.assertEqual(g["hu"], "yes")

    def test_perk_not_policy(self):
        wp, g = elig(["Remote, Netherlands"], remote=True, desc="Perks: work from anywhere for up to 4 weeks a year.")
        self.assertEqual(g["hu"], "maybe")

    def test_onsite_elsewhere(self):
        wp, g = elig(["London, UK"], workplace="On-site")
        self.assertEqual((wp, g["hu"]), ("onsite", "no"))

    def test_americas(self):
        wp, g = elig(["North America"], remote=True, desc="Work from anywhere in North America.")
        self.assertEqual(g["hu"], "no")
        wp, g = elig(["US Only", "Anywhere in the World"], remote=True)
        self.assertEqual(g["hu"], "no")
        wp, g = elig(["United States"], remote=True, desc="Time zones: CET +/- 2 hours allowed.")
        self.assertEqual(g["hu"], "maybe")
        wp, g = elig(["Remote"], remote=True, desc="You can work from anywhere in the world.")
        self.assertEqual(g["hu"], "yes")

    def test_unknown(self):
        wp, g = elig([])
        self.assertEqual(g["hu"], "maybe")


class Impact(unittest.TestCase):
    def test_signals(self):
        f = classify.impact_text
        self.assertTrue(f("we are a certified b corp building tools for farmers"))
        self.assertTrue(f("our nonprofit helps refugees"))
        self.assertTrue(f("we help brands cut carbon emissions across their supply chain"))
        self.assertIsNone(f("work in a fast-paced environment with equity and a charity day"))
        self.assertIsNone(f("we use django and mongodb"))


class Employment(unittest.TestCase):
    def test_types(self):
        j = make_job(title="Freelance Product Designer", company="X", url="u", source="s", kind="ats", emp=["Contract"])
        self.assertEqual(set(classify.employment(j, "")), {"contract", "freelance"})
        j = make_job(title="Product Designer", company="X", url="u", source="s", kind="ats", emp=["FullTime"])
        self.assertEqual(classify.employment(j, ""), ["full-time"])


class Languages(unittest.TestCase):
    def test_flags(self):
        f = classify.language_flags("we need someone with fluent french and english")
        self.assertTrue(any("French" in x[0] for x in f))
        f = classify.language_flags("english is our working language. german is a plus.")
        self.assertEqual(f, [])


if __name__ == "__main__":
    unittest.main()
