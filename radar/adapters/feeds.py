"""RSS 2.0 / Atom parsing that ignores namespaces, plus helpers to split 'Title at Company' style headlines."""
import re
import xml.etree.ElementTree as ET


def _local(tag):
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def parse_feed(text):
    text = text.lstrip("﻿ \n\r\t")
    text = re.sub(r"&(?!(?:[a-z]+|#\d+|#x[0-9a-f]+);)", "&amp;", text, flags=re.I)
    root = ET.fromstring(text.encode("utf-8"))
    items = []
    for el in root.iter():
        name = _local(el.tag)
        if name not in ("item", "entry"):
            continue
        it = {"title": "", "link": "", "date": None, "description": "", "company": "", "locations": [], "types": [], "remote": None, "categories": []}
        for ch in el:
            n = _local(ch.tag)
            val = (ch.text or "").strip()
            if n == "title":
                it["title"] = val
            elif n == "link":
                it["link"] = ch.get("href") or val or it["link"]
            elif n == "guid" and not it["link"] and val.startswith("http"):
                it["link"] = val
            elif n in ("pubdate", "published", "updated", "date") and not it["date"]:
                it["date"] = val
            elif n in ("description", "summary", "content", "encoded"):
                if len(val) > len(it["description"]):
                    it["description"] = val
            elif n in ("company", "company_name", "author") and val:
                it["company"] = it["company"] or val
            elif n in ("location", "region", "locations", "country", "city"):
                if val:
                    it["locations"].append(val)
                for sub in ch:
                    if (sub.text or "").strip():
                        it["locations"].append(sub.text.strip())
            elif n in ("job_type", "type", "employment_type"):
                if val:
                    it["types"].append(val)
            elif n in ("remote", "remotestatus", "remote_status", "workplace"):
                it["remote"] = val
            elif n == "category":
                if val:
                    it["categories"].append(val)
        items.append(it)
    return items


_SPLITS = [
    re.compile(r"^(?P<company>[^:]{2,60}):\s+(?P<title>.+)$"),                       # WWR: "Company: Title"
    re.compile(r"^(?P<title>.+?)\s+(?:—|–|\|)\s+(?P<company>[^—–|]{2,60})$"),            # "Title — Company"
    re.compile(r"^(?P<title>.+?)\s+at\s+(?P<company>[^,]{2,60})(?:,.*)?$", re.I),       # "Title at Company"
    re.compile(r"^(?P<company>.{2,60}?)\s+is hiring(?:\s+an?)?\s+(?P<title>.+)$", re.I),  # "Company is hiring a Title"
    re.compile(r"^(?P<title>.+?)\s+-\s+(?P<company>[^-]{2,60})$"),                    # "Title - Company"
]
DESIGN_WORDS = re.compile(r"design|ux|ui\b", re.I)


def split_title_company(headline, prefer=None):
    """Split a feed headline into (title, company). prefer: index of the pattern to try first."""
    h = re.sub(r"\s+", " ", headline or "").strip()
    order = list(range(len(_SPLITS)))
    if prefer is not None:
        order.remove(prefer)
        order.insert(0, prefer)
    for i in order:
        m = _SPLITS[i].match(h)
        if not m:
            continue
        t, c = m.group("title").strip(), m.group("company").strip()
        # If the 'company' part looks like the job title, swap.
        if DESIGN_WORDS.search(c) and not DESIGN_WORDS.search(t):
            t, c = c, t
        if DESIGN_WORDS.search(t):
            return t, c
    return h, ""
