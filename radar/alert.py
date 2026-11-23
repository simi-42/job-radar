"""Phone alerts through ntfy.sh (free app, no account). Topic comes from the NTFY_TOPIC secret."""
from . import http


def _post(server, payload):
    http.fetch(server.rstrip("/") + "/", method="POST", data=payload, retries=1)


def send(jobs, site_url):
    topic = http.secret("NTFY_TOPIC")
    if not topic or not jobs:
        return 0
    server = http.secret("NTFY_SERVER") or "https://ntfy.sh"
    try:
        if len(jobs) <= 3:
            for j in jobs:
                msg = f"{j['company']} · {j['hu_why']}\nMatch {j['score']}" + (f" · {j['loc']}" if j.get("loc") else "")
                _post(server, {"topic": topic, "title": j["title"][:150], "message": msg, "tags": ["briefcase"],
                               "priority": 4 if j["score"] >= 80 else 3, "click": j.get("apply_url") or j["url"],
                               "actions": [{"action": "view", "label": "Open radar", "url": site_url}] if site_url else []})
            return len(jobs)
        lines = [f"• {j['score']} · {j['title']} at {j['company']} ({j['hu_why']})" for j in jobs[:8]]
        if len(jobs) > 8:
            lines.append(f"…and {len(jobs) - 8} more")
        _post(server, {"topic": topic, "title": f"{len(jobs)} new matches", "message": "\n".join(lines), "tags": ["briefcase"],
                       "priority": 4, "click": site_url or ""})
        return len(jobs)
    except http.FetchError:
        return 0
