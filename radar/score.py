"""Resume match score. Rules first (free); optional LLM pass on the most promising new jobs."""
import json
import re

from . import http

TITLE_POINTS = {"core": 30, "leadership": 24, "adjacent": 12}


def _count(text_low, kw):
    if kw in ("ai", "ios", "cad", "3d", "css", "html", "llm", "b2b", "saas", "media", "news"):
        return 1 if re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", text_low) else 0
    return 1 if kw in text_low else 0


def rules(job, profile, family, sen, lang_flags, tags):
    text = (job["title"] + "\n" + job.get("description", "")).lower()
    has_desc = len(job.get("description", "")) > 300
    parts = {}
    parts["title"] = TITLE_POINTS.get(family, 0)
    parts["seniority"] = profile["seniority"]["points"].get(sen, 8)

    matched = [k for k, w in profile["skills"].items() if w and _count(text, k)]
    weight = sum(profile["skills"][k] for k in matched)
    target = profile.get("skills_target", 20)
    if has_desc:
        parts["skills"] = round(min(35, 35 * weight / target))
    else:
        # No description to read: give a neutral middle value so title-only listings aren't buried.
        parts["skills"] = max(14, round(min(35, 35 * weight / target)))

    dom = [k for k in profile["domains"] if _count(text, k)]
    dom_pts = min(profile.get("domain_max", 10), sum(profile["domains"][k] for k in dom))
    for t in tags or []:
        dom_pts += profile.get("tag_bonus", {}).get(t, 0)
    parts["domain"] = min(profile.get("domain_max", 10), dom_pts)

    flags = []
    pen = 0
    for label, p in lang_flags:
        flags.append(label)
        pen += p
    for k, p in profile.get("avoid", {}).items():
        if _count(text, k):
            flags.append(f"mentions {k}")
            pen += p
            break
    parts["penalty"] = -pen

    score = max(0, min(100, sum(parts.values())))
    gaps = []
    if not has_desc:
        gaps.append("no description to read; score is from the title")
    return score, parts, matched[:12], dom[:6], flags, gaps


# ---------- optional LLM pass ----------

SYSTEM = ("You score job ads against one candidate. Reply with JSON only: "
          '{"score": 0-100, "hu": "yes"|"maybe"|"no", "why": "<one sentence, max 25 words>", "gaps": ["<max 3 short items>"]}. '
          "score = how well the candidate fits the role's requirements (seniority, skills, domain), not the location. "
          "hu = can the candidate do this job while living in Hungary (EU citizen, UTC+1): yes if Hungary-based, remote worldwide, "
          "remote Europe/EU/EMEA or her time zone is allowed; no if office/hybrid elsewhere or remote restricted to another country; maybe if unclear.")


def llm_score(job, profile, api_key, cv_text=None):
    body = {
        "model": profile["llm"]["model"],
        "max_tokens": 200,
        "system": [
            {"type": "text", "text": SYSTEM},
            {"type": "text", "text": "Candidate:\n" + (cv_text or profile["summary"]), "cache_control": {"type": "ephemeral"}},
        ],
        "messages": [{"role": "user", "content":
                      f"Job: {job['title']} at {job['company']}\nLocation: {'; '.join(job.get('locations') or []) or 'not stated'}\n"
                      f"Workplace: {job.get('workplace')}\n\n{job.get('description', '')[:3500]}"}],
    }
    data = http.get_json("https://api.anthropic.com/v1/messages", method="POST", data=body, timeout=60, retries=1,
                         headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"})
    text = "".join(b.get("text", "") for b in data.get("content", []))
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    out = json.loads(m.group(0))
    usage = data.get("usage", {})
    return {
        "score": int(max(0, min(100, out.get("score", 0)))),
        "hu": out.get("hu") if out.get("hu") in ("yes", "maybe", "no") else None,
        "why": str(out.get("why", ""))[:200],
        "gaps": [str(g)[:80] for g in (out.get("gaps") or [])][:3],
        "tokens": usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0) + usage.get("output_tokens", 0),
    }
