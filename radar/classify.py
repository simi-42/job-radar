"""Role family, seniority, workplace, geography, Hungary eligibility, employment type, language needs."""
import re

from . import geo

PROFILE = None  # set by run.load_profile()


def set_profile(p):
    global PROFILE
    PROFILE = p


# ---------- title ----------

_PHYSICAL = ("industrial", "furniture", "jewel", "footwear", "apparel", "mechanical", "interior", "fashion", "packaging", "textile",
             "landscape", "kitchen", "bathroom", "hardware", "cad designer", "cad drafter", "electrical", "circuit", "toy ", "lighting designer")


def title_family(title):
    """'core' | 'leadership' | 'adjacent' | None. Uses the profile's title lists."""
    t = " " + (title or "").lower().replace("–", "-") + " "
    t = re.sub(r"\s+", " ", t)
    tl = PROFILE["titles"]
    if any(x in t for x in _PHYSICAL):
        return None
    if any(x in t for x in tl["exclude"]):
        # 'ux researcher' etc. are out, but 'product designer' with 'graphic' in a long title is rare enough
        if not any(x in t for x in ("product designer", "ux designer", "ux/ui", "ui/ux")):
            return None
    if "design system" in t and re.search(r"engineer|developer|frontend|front-end", t):
        return "adjacent"
    if any(x in t for x in tl["leadership"]):
        return "leadership"
    if re.search(r"design engineer|design technologist|ux engineer|service designer|creative technologist", t):
        return "adjacent"
    if any(x in t for x in tl["core"]):
        return "core"
    if re.search(r"\b(ux|ux/ui|ui/ux|ui ux|ux ui|product)\b.{0,25}\bdesigner", t):
        return "core"
    if any(x in t for x in tl["adjacent"]):
        return "adjacent"
    if re.fullmatch(r"\s*(senior |sr\.? |lead |staff |principal |founding )?(digital )?designer\s*", t):
        return "adjacent"
    return None


_SEN = [
    ("intern", r"\bintern(ship)?\b|working student|werkstudent|trainee|praktikant|praktikum|apprentice|gyakornok|stagiaire|alternan|apprenti"),
    ("junior", r"\bjunior\b|\bjr\.?\b|entry[- ]level|graduate|\bassociate\b"),
    ("head", r"\bhead of\b|\bdirector\b|\bvp\b|vice president|\bchief\b"),
    ("principal", r"\bprincipal\b"),
    ("staff", r"\bstaff\b"),
    ("lead", r"\blead\b|\bmanager\b|team lead"),
    ("senior", r"\bsenior\b|\bsr\.?\b|\bsnr\b|\biii\b|\bexpert\b|\bsenior-"),
    ("mid", r"\bmid\b|\bmedior\b|\bintermediate\b|\bmid-level\b|\bii\b|\bregular\b"),
]


def seniority(title, hint=None):
    t = (title or "").lower()
    if re.search(r"mid\s*/\s*senior|mid-senior|medior/senior", t):
        return "senior"
    for name, pat in _SEN:
        if re.search(pat, t):
            return name
    h = (hint or "").lower()
    if h:
        for name, pat in _SEN:
            if re.search(pat, h):
                return name
    return "unspecified"


# ---------- workplace ----------

def workplace(job, text_low):
    hint = (job.get("workplace_hint") or "").lower()
    locs = " ".join(job.get("locations") or []).lower()
    title = (job.get("title") or "").lower()
    if "hybrid" in hint or "hybrid" in locs:
        return "hybrid"
    if "remote" in hint or job.get("remote_flag") is True:
        return "remote"
    if hint in ("onsite", "on-site", "on site", "office", "in-office", "in office"):
        return "onsite"
    if "hybrid" in locs or "hybrid" in title:
        return "hybrid"
    if "remote" in locs or "remote" in title or "anywhere" in locs or "home office" in locs or "homeoffice" in locs:
        return "remote"
    if re.search(r"\b(fully|100%|completely|full) ?remote\b|remote[- ]first|work from anywhere|fully distributed", text_low):
        return "remote"
    if re.search(r"\bhybrid\b", text_low[:4000]):
        return "hybrid"
    if re.search(r"\bon[- ]?site\b|in[- ]office|office[- ]based", text_low[:4000]):
        return "onsite"
    if job.get("remote_flag") is False and locs:
        return "onsite"
    return "unknown"


# ---------- eligibility ----------

_NEG_COUNTRY = re.compile(
    r"(?:must|need to|needs to|required to|should|have to|you['’]?ll need to)\s+(?:be\s+)?(?:currently\s+)?(?:based|located|living|resid\w*|live)\s+(?:in|within)\s+(?:the\s+)?([a-z .]{2,30})")
_AUTH = re.compile(
    r"(?:authori[sz]ed|eligible|legally (?:able|allowed|authori[sz]ed)|right|permission|permit)\s+to\s+work\s+in\s+(?:the\s+)?([a-z .]{2,30})")
_US_ONLY = re.compile(r"\b(?:us|u\.s\.|usa|united states)[- ](?:based|only|residents?)\b|\bremote\s*[(,\-–]\s*(?:us|usa|united states|u\.s\.)\b"
                      r"|\bremote\s*[(,\-–]\s*(?:uk|united kingdom|canada|india|australia)\b|\b(?:uk|canada)[- ](?:based|only)\b")
_ANYWHERE = re.compile(r"work from anywhere|anywhere in the world|from anywhere|location[- ]independent|fully distributed|remote[- ]worldwide|globally remote|work remotely from any")
_EUROPE_REMOTE = re.compile(r"(?:remote|anywhere|based)\s+(?:in|within|across|from)\s+(?:the\s+)?(?:eu\b|europe|european union|emea|eea|cee|central europe|eastern europe)"
                            r"|(?:european|cet|cest|emea|eu)\s+time ?zones?|within europe|across europe|anywhere in europe|remote,?\s*(?:eu|europe|emea)\b")
_TZ = re.compile(r"(?:utc|gmt)\s*([+\-−–]\s*\d{1,2}(?::\d\d)?)\s*(?:to|-|–|—|and|through)\s*(?:utc|gmt)?\s*([+\-−–]\s*\d{1,2}(?::\d\d)?)")
_CET_PM = re.compile(r"\b(?:cet|cest)\s*(?:\+/-|±|\+-|plus or minus)\s*(\d)")
_US_TZ = re.compile(r"\b(?:est|edt|pst|pdt|cst|mst|eastern|pacific)\s+(?:time|hours|time ?zone|working hours|overlap)|overlap with (?:us|u\.s\.|est|pst|eastern|pacific)")

EU_TERMS = ("eu", "the eu", "european union", "europe", "eea", "eu/eea", "an eu country", "eu countries")


_ANY_REGION = re.compile(r"^\s*(?:in|within|across)\s+(?:the\s+)?(?:us\b|u\.s\.|usa|united states|north america|canada|americas|latam|latin america|uk\b|united kingdom|india|australia|apac)")


def _anywhere(desc):
    for m in _ANYWHERE.finditer(desc):
        tail = desc[m.end():m.end() + 45]
        if re.search(r"\b(for|up to)\b.{0,25}\b(days?|weeks?|months?)\b|\d+\s*(days?|weeks?)", tail):
            continue  # 'work from anywhere for 4 weeks a year' is a perk, not a remote policy
        if _ANY_REGION.search(tail):
            continue  # 'anywhere in the US' is not worldwide
        return True
    return False


def _tz_num(s):
    s = s.replace("−", "-").replace("–", "-").replace(" ", "")
    try:
        return float(s.split(":")[0])
    except ValueError:
        return None


def _first_words(s, n=3):
    return " ".join(s.strip(" .").split()[:n])


def geo_and_eligibility(job, text_low, wp):
    """Returns dict: countries, region, hu ('yes'|'maybe'|'no'), hu_why."""
    locs = job.get("locations") or []
    loc_low = " | ".join(locs).lower() + " " + " ".join(job.get("geo_hint") or []).lower()
    countries = []
    for l in locs + (job.get("geo_hint") or []):
        for c in geo.countries_in(l):
            if c not in countries:
                countries.append(c)
    worldwide = geo.has_any(loc_low, geo.WORLDWIDE)
    europe_word = geo.has_any(" " + loc_low + " ", geo.EUROPE_WORDS)
    americas_word = geo.has_any(loc_low, geo.AMERICAS_WORDS)

    eu_countries = [c for c in countries if geo.is_europe(c)]
    if "HU" in countries:
        region = "Hungary"
    elif eu_countries or europe_word:
        region = "Europe"
    elif worldwide:
        region = "Worldwide"
    elif any(c in ("US", "CA") for c in countries) or americas_word:
        region = "North America"
    elif countries:
        region = "Other"
    else:
        region = "Not stated"

    home = PROFILE["home"]
    desc = text_low[:12000]
    lab = ", ".join(geo.label(c) for c in countries[:3])

    if "HU" in countries:
        return dict(countries=countries, region=region, hu="yes",
                    hu_why={"remote": "Remote, Hungary listed", "hybrid": "Hybrid in Hungary", "onsite": "Office in Hungary"}.get(wp, "Based in Hungary"))

    if wp != "remote":
        if wp == "unknown" and not countries and not worldwide and not europe_word:
            return dict(countries=countries, region=region, hu="maybe", hu_why="Location and remote policy not stated")
        if wp == "unknown" and (worldwide or europe_word) and not countries:
            return dict(countries=countries, region=region, hu="maybe", hu_why="Europe-wide listing, remote policy not stated")
        where = lab or region
        return dict(countries=countries, region=region, hu="no",
                    hu_why={"hybrid": f"Hybrid in {where}", "onsite": f"Office in {where}"}.get(wp, f"In {where}, not listed as remote"))

    # --- remote ---
    neg = None
    for m in _NEG_COUNTRY.finditer(desc):
        target = _first_words(m.group(1))
        tc = geo.countries_in(target)
        if any(t in target for t in EU_TERMS) or "HU" in tc or (tc and all(geo.is_europe(c) for c in tc) and "europe" in target):
            continue
        if tc:
            neg = geo.label(tc[0])
            break
    auth_eu = False
    for m in _AUTH.finditer(desc):
        target = _first_words(m.group(1))
        if any(target.startswith(t) for t in EU_TERMS):
            auth_eu = True
            continue
        tc = geo.countries_in(target)
        if tc and "HU" not in tc and not neg:
            neg = geo.label(tc[0])
    us_only = bool(_US_ONLY.search(loc_low + " " + desc[:3000]))

    tz_ok = None
    m = _TZ.search(desc) or _TZ.search(loc_low)
    if m:
        a, b = _tz_num(m.group(1)), _tz_num(m.group(2))
        if a is not None and b is not None:
            lo, hi = min(a, b), max(a, b)
            tz_ok = lo <= home["utc_offset"] <= hi or lo <= home["utc_offset"] + 1 <= hi
    if _CET_PM.search(desc) or _CET_PM.search(loc_low):
        tz_ok = True

    non_eu_only = bool(countries) and not eu_countries
    if (americas_word or non_eu_only) and not europe_word:
        # Location restricted to the Americas or other non-European countries
        if us_only or not worldwide:
            if tz_ok is True or _US_TZ.search(desc):
                return dict(countries=countries, region=region, hu="maybe", hu_why=f"Remote in {lab or 'the Americas'}; your time zone listed, residency may be required")
            return dict(countries=countries, region=region, hu="no", hu_why=f"Remote, {lab or 'Americas'} only")
        return dict(countries=countries, region=region, hu="maybe", hu_why=f"Listed as worldwide and {lab}; check residency")
    if neg and not (worldwide or europe_word):
        return dict(countries=countries, region=region, hu="no", hu_why=f"Remote, must be in {neg}")
    if neg:
        return dict(countries=countries, region=region, hu="maybe", hu_why=f"Listed as remote Europe, but asks to be in {neg}")
    if worldwide or _anywhere(desc):
        if us_only and not worldwide:
            return dict(countries=countries, region=region, hu="no", hu_why="Remote, US only")
        return dict(countries=countries, region="Worldwide" if region in ("Not stated", "Other", "North America") else region,
                    hu="yes", hu_why="Remote, worldwide")
    if europe_word or _EUROPE_REMOTE.search(desc) or (auth_eu and home.get("eu_citizen")):
        return dict(countries=countries, region="Europe" if region in ("Not stated", "Other") else region,
                    hu="yes", hu_why="Remote, Europe" + (" (EU work rights)" if auth_eu and not europe_word else ""))
    if tz_ok is True:
        return dict(countries=countries, region=region, hu="yes", hu_why="Remote, your time zone allowed")
    if us_only or tz_ok is False:
        return dict(countries=countries, region=region, hu="no", hu_why=f"Remote, {lab or 'US/UK'} only" if us_only else "Remote, time zone outside yours")
    if countries:
        non_eu = [c for c in countries if not geo.is_europe(c)]
        if non_eu and not eu_countries:
            if _US_TZ.search(desc):
                return dict(countries=countries, region=region, hu="maybe", hu_why=f"Remote in {lab}; US-hours overlap asked")
            return dict(countries=countries, region=region, hu="no", hu_why=f"Remote in {lab}")
        return dict(countries=countries, region=region, hu="maybe", hu_why=f"Remote in {lab}; check if Hungary works")
    return dict(countries=countries, region=region, hu="maybe", hu_why="Remote, country not stated")


# ---------- employment type ----------

_EMP = [
    ("full-time", r"full[- ]?time|\bvollzeit\b|\bpermanent\b|\bcdi\b|\bfulltime\b|teljes munkaid"),
    ("part-time", r"part[- ]?time|\bteilzeit\b|\bparttime\b|részmunkaid"),
    ("contract", r"\bcontract(or)?\b|fixed[- ]term|\btemporary\b|\bcdd\b|befristet|\bb2b\b|interim|maternity cover|parental leave cover|határozott"),
    ("freelance", r"freelanc|freiberuf|\bself[- ]employed\b|\bgig\b|vállalkozói"),
    ("internship", r"\binternship\b|\bintern\b|werkstudent|working student"),
]


def employment(job, text_low):
    hints = " ".join(job.get("emp_hint") or []).lower()
    title = (job.get("title") or "").lower()
    out = []
    for name, pat in _EMP:
        if re.search(pat, hints) or re.search(pat, title):
            out.append(name)
    if not out:
        head = text_low[:2500]
        for name, pat in _EMP:
            if name in ("full-time", "part-time", "freelance") and re.search(pat, head):
                out.append(name)
        if not out and re.search(r"\b(?:contract|contractor)\s+(?:role|position|basis|engagement)\b", text_low):
            out.append("contract")
    return out


# ---------- languages ----------

_LANGS = ["french", "dutch", "swedish", "danish", "norwegian", "finnish", "spanish", "italian", "polish", "czech", "portuguese", "romanian", "greek",
          "japanese", "mandarin", "chinese", "hebrew", "arabic", "turkish", "russian", "ukrainian", "slovak", "croatian", "serbian", "bulgarian",
          "lithuanian", "latvian", "estonian", "catalan", "flemish", "icelandic", "slovenian"]
_LANG_RE = re.compile(r"(?:fluent|fluency|native|proficien\w*|business[- ]level|excellent|strong|professional|written and spoken|c1|c2)\s+(?:\w+\s+){0,4}?(" + "|".join(_LANGS) + r")"
                      r"|(" + "|".join(_LANGS) + r")\s+(?:\w+\s+){0,3}?(?:is\s+)?(?:required|a must|mandatory|essential|necessary|needed)")
_GER_HIGH = re.compile(r"(?:fluent|native|c1|c2|verhandlungssicher|fließend|muttersprach)\w*\s+(?:\w+\s+){0,3}?(?:german|deutsch)|(?:german|deutsch)\w*\s+(?:\w+\s+){0,3}?(?:c1|c2|verhandlungssicher|fließend|muttersprach)")
_STOP = {
    "German": [" und ", " die ", " der ", " wir ", " sie ", " mit ", " für ", " eine ", " ist "],
    "French": [" et ", " les ", " des ", " nous ", " vous ", " pour ", " une ", " avec "],
    "Dutch": [" en ", " het ", " een ", " wij ", " voor ", " met ", " je ", " van "],
    "Spanish": [" y ", " los ", " las ", " para ", " con ", " una ", " nuestro "],
    "Italian": [" e ", " gli ", " per ", " con ", " una ", " nostro ", " della "],
    "Polish": [" oraz ", " jest ", " dla ", " się ", " oraz ", " jako "],
    "Swedish": [" och ", " att ", " för ", " med ", " som ", " vi "],
    "Hungarian": [" és ", " az ", " hogy ", " egy ", " vagy ", " számára "],
}
_EN = [" and ", " the ", " you ", " with ", " for ", " our ", " are "]


def language_flags(text_low):
    flags = []
    m = _LANG_RE.search(text_low)
    if m:
        flags.append(("needs " + (m.group(1) or m.group(2)).title(), PROFILE["language_penalty"]))
    if _GER_HIGH.search(text_low):
        flags.append(("asks for fluent German (you have B2)", 4))
    sample = " " + text_low[:3000] + " "
    if len(sample) > 400:
        en = sum(sample.count(w) for w in _EN)
        best, best_n = None, 0
        for lang, words in _STOP.items():
            n = sum(sample.count(w) for w in words)
            if n > best_n:
                best, best_n = lang, n
        if best and best_n > en * 1.3 and best_n > 12:
            if best.lower() in PROFILE["language_ok"]:
                flags.append((f"ad written in {best}", 0 if best == "Hungarian" else 2))
            else:
                flags.append((f"ad written in {best}", PROFILE["language_penalty"]))
    return flags


# ---------- impact ----------

_IMP = {}


def _imp_patterns():
    if not _IMP:
        sig = PROFILE.get("impact_signals", {})
        for kind in ("strong", "weak"):
            _IMP[kind] = [(t, re.compile(r"(?<![a-z])" + re.escape(t))) for t in sig.get(kind, [])]
    return _IMP


def impact_text(text_low):
    """Return a short reason if the text shows impact work (one strong signal or two weak ones), else None."""
    pats = _imp_patterns()
    head = text_low[:6000]
    for t, pat in pats.get("strong", []):
        if pat.search(head):
            return f"mentions {t}"
    weak = [t for t, pat in pats.get("weak", []) if pat.search(head)]
    if len(weak) >= 2:
        return f"mentions {weak[0]} and {weak[1]}"
    return None
