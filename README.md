# Jobright Job Scraper

Scrapes job recommendations from Jobright (title, company, location, recruiter LinkedIn, apply link, Jobright link, keywords) and outputs JSON.

> This uses Playwright and your saved browser session state to call Jobright’s recommendations API endpoint. The endpoint and JSON shape may change at any time.
> Use responsibly and follow the site’s terms.

## What it collects

Each job in the output includes:

- `jobId`
- `title`
- `company`
- `location`
- `jobright_url`
- `apply_url`
- `linkedin_recruiters` (filtered from social connections: recruiter/talent/sourcer/HR)
- `keywords` (skills/tags/taxonomy signals)
- `raw` (the original job dict pulled from the API)

## Requirements

- Python 3.10+ (uses `list[...]` and `str | None` typing)
- Playwright + Chromium browser

## Install

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate

pip install -r requirements.txt
python -m playwright install chromium
```

## First time login

Create `jobright_state.json` -> `python jobright_scrape.py --login`

Fetch up to 50 jobs into `jobright_recs.json` -> `python jobright_scrape.py --max 50 --out jobright_recs.json`

## Missing `jobright_state.json`

Run the login flow FIRST -> `python jobright_scrape.py --login`
