from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from playwright.sync_api import TimeoutError as PWTimeoutError
from playwright.sync_api import sync_playwright

STATE_FILE = "jobright_state.json"
BASE = "https://jobright.ai"
RECS_PAGE = f"{BASE}/jobs/recommend"
RECS_API = f"{BASE}/swan/recommend/list/jobs"

_cache: dict = {"jobs": [], "fetched_at": None}


def _pick(d: dict, *keys: str) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _extract_job_dicts(obj: Any) -> list[dict]:
    PROFILE_KEYS = {"firstName", "fullName", "linkedinUrl"}
    ID_KEYS = {"jobInfoId", "jobId", "job_id", "jobID", "id"}
    TITLE_KEYS = {"jobTitle", "title", "positionTitle", "name"}
    COMPANY_KEYS = {"companyName", "company", "company_name"}
    APPLY_KEYS = {"applyUrl", "applyURL", "applyLink", "externalUrl", "sourceUrl", "url", "originalUrl"}
    jobs: list[dict] = []

    def is_job(d: dict) -> bool:
        keys = set(d.keys())
        if keys & PROFILE_KEYS:
            return False
        has_id = bool(keys & ID_KEYS)
        has_title = bool(keys & TITLE_KEYS)
        has_company = bool(keys & COMPANY_KEYS)
        has_apply = bool(keys & APPLY_KEYS)
        return has_id and has_title and (has_company or has_apply)

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            if is_job(x):
                jobs.append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)

    walk(obj)
    return jobs


_COMPANY_FROM_SUMMARY = re.compile(r"^([A-Z][A-Za-z0-9&.,''\- ]{1,80})\s+is\s+", re.UNICODE)
_COMPANY_FROM_LOGO = re.compile(r"/([A-Za-z0-9-]+)_logo", re.IGNORECASE)


def extract_company(job: dict) -> str | None:
    company = _pick(job, "companyName", "company", "company_name", "jdCompanyName", "companyDisplayName", "companyTitle")
    if isinstance(company, dict):
        company = _pick(company, "name", "companyName")
    if isinstance(company, str) and company.strip():
        return company.strip()
    for k in ("companyInfo", "companyVO", "companyDto"):
        v = job.get(k)
        if isinstance(v, dict):
            c = _pick(v, "name", "companyName", "displayName")
            if isinstance(c, str) and c.strip():
                return c.strip()
    sc = job.get("socialConnections")
    if isinstance(sc, list):
        for person in sc:
            if isinstance(person, dict):
                c = person.get("companyName")
                if isinstance(c, str) and c.strip():
                    return c.strip()
    summary = job.get("jobSummary")
    if isinstance(summary, str) and summary.strip():
        m = _COMPANY_FROM_SUMMARY.match(summary.strip())
        if m:
            return m.group(1).strip()
    logo = job.get("jdLogo")
    if isinstance(logo, str) and logo.strip():
        m = _COMPANY_FROM_LOGO.search(urlparse(logo).path)
        if m:
            return m.group(1)
    return None


def extract_linkedin_recruiters(job: dict) -> list[dict]:
    sc = job.get("socialConnections")
    if not isinstance(sc, list):
        return []
    out: list[dict] = []
    for p in sc:
        if not isinstance(p, dict):
            continue
        title = p.get("jobTitle") or ""
        title_l = title.lower()
        if any(x in title_l for x in ("recruit", "talent", "sourc", "hr")):
            out.append({
                "fullName": p.get("fullName") or (f"{p.get('firstName', '')}".strip() or None),
                "jobTitle": p.get("jobTitle"),
                "companyName": p.get("companyName"),
                "linkedinUrl": p.get("linkedinUrl"),
            })
    return out


def extract_keywords(job: dict, max_kw: int = 25) -> list[str]:
    kws: list[str] = []
    core = job.get("jdCoreSkills")
    if isinstance(core, list):
        for s in core:
            if isinstance(s, dict) and isinstance(s.get("skill"), str):
                kws.append(s["skill"])
    sms = job.get("skillMatchingScores")
    if isinstance(sms, list):
        for s in sms:
            if isinstance(s, dict):
                name = s.get("displayName") or s.get("featureName")
                if isinstance(name, str):
                    kws.append(name)
    for k in ("recommendationTags", "jobTags"):
        v = job.get(k)
        if isinstance(v, list):
            for x in v:
                if isinstance(x, str):
                    kws.append(x)
    v3 = job.get("jobTaxonomyV3")
    if isinstance(v3, list):
        for x in v3:
            if isinstance(x, str):
                kws.append(x)
    ft = job.get("firstTaxonomy")
    if isinstance(ft, str):
        kws.append(ft)
    seen = set()
    out: list[str] = []
    for x in kws:
        x = x.strip()
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
        if len(out) >= max_kw:
            break
    return out


def run_scrape(max_items: int = 50) -> list[dict]:
    if not Path(STATE_FILE).exists():
        raise FileNotFoundError(f"{STATE_FILE} not found")

    out: list[dict] = []
    seen_ids: set[str] = set()

    def norm_url(u: Any) -> str | None:
        if not isinstance(u, str) or not u.strip():
            return None
        u = u.strip()
        return urljoin(BASE, u) if u.startswith("/") else u

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=STATE_FILE)
        page = context.new_page()
        try:
            page.goto(RECS_PAGE, wait_until="domcontentloaded", timeout=60_000)
        except PWTimeoutError:
            pass
        page.wait_for_timeout(1500)

        position = 0
        refresh = "true"
        page_size = 10

        while len(out) < max_items:
            count = min(page_size, max_items - len(out))
            qs = urlencode({"refresh": refresh, "sortCondition": "0", "position": str(position), "count": str(count)})
            url = f"{RECS_API}?{qs}"
            resp = page.request.get(url, headers={"accept": "application/json", "referer": RECS_PAGE, "origin": BASE})
            if resp.status in (401, 403):
                try:
                    page.goto(RECS_PAGE, wait_until="domcontentloaded", timeout=60_000)
                except PWTimeoutError:
                    pass
                page.wait_for_timeout(1200)
                resp = page.request.get(url, headers={"accept": "application/json", "referer": RECS_PAGE, "origin": BASE})
            if resp.status in (401, 403):
                browser.close()
                raise PermissionError(f"Auth failed (HTTP {resp.status}). Session expired.")
            if resp.status != 200:
                break
            data = resp.json()
            job_dicts = _extract_job_dicts(data)
            if not job_dicts:
                break
            added = 0
            for j in job_dicts:
                job_id = _pick(j, "jobInfoId", "jobId", "id", "job_id", "jobID")
                job_id_str = str(job_id) if job_id is not None else None
                if job_id_str and job_id_str in seen_ids:
                    continue
                title = _pick(j, "jobTitle", "title", "positionTitle", "name")
                company = _pick(j, "companyName", "company", "company_name")
                if isinstance(company, dict):
                    company = _pick(company, "name", "companyName")
                if not company:
                    company = extract_company(j)
                location = _pick(j, "jobLocation", "location", "locationName", "city")
                if isinstance(location, dict):
                    location = _pick(location, "name", "displayName")
                apply_url = norm_url(_pick(j, "applyUrl", "applyURL", "applyLink", "externalUrl", "sourceUrl", "url", "originalUrl"))
                jobright_url = norm_url(_pick(j, "detailUrl", "jobUrl", "infoUrl", "jobrightUrl"))
                if jobright_url is None and job_id_str:
                    jobright_url = f"{BASE}/jobs/info/{job_id_str}"
                out.append({
                    "jobId": job_id_str,
                    "title": title,
                    "company": company,
                    "location": location,
                    "jobright_url": jobright_url,
                    "apply_url": apply_url,
                    "linkedin_recruiters": extract_linkedin_recruiters(j),
                    "keywords": extract_keywords(j),
                })
                if job_id_str:
                    seen_ids.add(job_id_str)
                added += 1
                if len(out) >= max_items:
                    break
            if added == 0:
                break
            position += count
            refresh = "false"

        context.storage_state(path=STATE_FILE)
        browser.close()

    return out


@asynccontextmanager
async def lifespan(app: FastAPI):
    if Path(STATE_FILE).exists():
        try:
            jobs = run_scrape(max_items=50)
            _cache["jobs"] = jobs
            _cache["fetched_at"] = datetime.now(timezone.utc).isoformat()
        except Exception as e:
            print(f"[WARN] Startup scrape failed: {e}")
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/jobs")
def get_jobs():
    return {
        "jobs": _cache["jobs"],
        "fetched_at": _cache["fetched_at"],
        "count": len(_cache["jobs"]),
    }


@app.post("/jobs/refresh")
def refresh_jobs():
    if not Path(STATE_FILE).exists():
        raise HTTPException(status_code=500, detail="Session file missing. Re-deploy with jobright_state.json.")
    try:
        jobs = run_scrape(max_items=50)
        _cache["jobs"] = jobs
        _cache["fetched_at"] = datetime.now(timezone.utc).isoformat()
        return {"jobs": jobs, "fetched_at": _cache["fetched_at"], "count": len(jobs)}
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok"}
