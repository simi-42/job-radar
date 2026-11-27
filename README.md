# Job radar

A personal job tracker for product design roles. It reads job boards and company careers pages, scores each job against your CV, labels whether you can do it from Hungary, and alerts your phone about good new matches.

It runs twice a day (05:17 and 17:17 Budapest time) on GitHub Actions, which is free for public repositories and uses no AI tokens unless you add a key. The site is a single page on GitHub Pages.

## Where jobs come from

1. **Company job boards**, polled directly every day: 448 companies from your Follow the Money tracker, Hungarian product companies, top European startups and design-forward companies (`config/companies.json`). The run finds each company's board (Greenhouse, Lever, Ashby, Workable, Recruitee, Personio, SmartRecruiters, BambooHR, Teamtailor, Breezy, Pinpoint, Workday) by reading its website. These jobs count as verified because they come from the company's own board.
2. **Job boards and aggregators** (`config/sources.json`): your bookmarked boards, the Grassroots & Grace impact list, the boards from the Follow the Money tracker, remote-job APIs, VC portfolio job boards and Hidden Jobs.
3. **Boards found automatically.** When a listing on any board links to a company's own job board, that board is added to daily tracking.
4. **Search engines**: daily queries for product/UX/design-systems roles on company job boards and LinkedIn. A weekly pass looks up every board marked `search: true`. Needs `BRAVE_API_KEY` or `SERPER_API_KEY`; without either, a few DuckDuckGo queries run instead.

Jobs found on a board or through search are opened on their own page to check they're still live.

## What each job gets

- **Match score (0–100)**, made of title (30), seniority (15), skills from your CV (35) and domain (10), minus penalties such as a required language you don't speak. Change the weights in `config/profile.json`. Scores rank jobs; they never hide them.
- **From Hungary: yes / maybe / no**, with the reason. Yes means based in Hungary, remote worldwide, remote Europe/EU/EMEA, your time zone is allowed, or EU work rights are enough. Maybe means remote but limited to another country, or the location isn't stated.
- Workplace, location, employment type, seniority, posting age, salary when given, and where it was found.

Junior roles and internships are dropped, along with office or hybrid jobs outside Europe. Remote jobs from anywhere are kept, and the "From Hungary" filter sorts them out.

## Setup (once)

1. **Pages:** Settings → Pages → Source: GitHub Actions.
2. **Phone alerts:** install the ntfy app and subscribe to a hard-to-guess topic name. Then add it as the repository secret `NTFY_TOPIC` (Settings → Secrets and variables → Actions).
3. **Optional secrets:**
   - `BRAVE_API_KEY` or `SERPER_API_KEY` turns on the search-engine angle.
   - `ANTHROPIC_API_KEY` adds an AI read of the top new jobs each day, at most 30 per run, using Claude Haiku. Each job is scored once and the result is cached.
   - `CV_TEXT` gives the AI read your full CV. Otherwise it uses the summary in `profile.json`.
4. **Refresh button and adding boards from the site:** open Sources on the site and paste a fine-grained GitHub token. Limit it to this repository, with Actions read/write and Contents read/write. The token is stored only in that browser.

## Alerts

You get an alert for each new job with a match of 70 or more that you can do from Hungary. Hungary-based office jobs count too. Three or fewer arrive as separate notifications; more come as one digest. Change these rules under `alerts` in `config/profile.json`.

## Files

- `config/`: what you edit (profile, sources, companies, search queries).
- `radar/`: the pipeline (Python standard library only).
- `data/`: run state (first-seen dates, alerts sent, boards found).
- `docs/`: the site and its data.

Run locally with `python -m radar.run`. Run the tests with `python -m unittest discover -s tests -t .`.
