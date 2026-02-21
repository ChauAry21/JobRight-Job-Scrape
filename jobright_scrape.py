from __future__ import annotations

import argparse
import json
import re
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError


STATE_FILE = "jobright_state.json"
BASE = "https://jobright.ai"
RECS_PAGE = f"{BASE}/jobs/recommend"
RECS_API = f"{BASE}/swan/recommend/list/jobs"


def save_login_state() -> None:

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_navigation_timeout(120_000)

        page.goto(BASE, wait_until="domcontentloaded")
        input("Log in in the opened browser, then press ENTER here...")

        try:
            page.goto(RECS_PAGE, wait_until="domcontentloaded", timeout=120_000)
        except PWTimeoutError:
            pass

        page.wait_for_timeout(2000)
        input("Wait until you SEE recommendations, then press ENTER here...")

        context.storage_state(path=STATE_FILE)
        browser.close()
        print(f"[OK] Saved session to {STATE_FILE}")


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


_COMPANY_FROM_SUMMARY = re.compile(r"^([A-Z][A-Za-z0-9&.,'’\- ]{1,80})\s+is\s+", re.UNICODE)
_COMPANY_FROM_LOGO = re.compile(r"/([A-Za-z0-9-]+)_logo", re.IGNORECASE)


def extract_company(job: dict) -> str | None:
    company = _pick(
        job,
        "companyName",
        "company",
        "company_name",
        "jdCompanyName",
        "companyDisplayName",
        "companyTitle",
    )
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
        title = (p.get("jobTitle") or "")
        title_l = title.lower()
        if any(x in title_l for x in ("recruit", "talent", "sourc", "hr")):
            out.append(
                {
                    "fullName": p.get("fullName") or (f"{p.get('firstName','')}".strip() or None),
                    "jobTitle": p.get("jobTitle"),
                    "companyName": p.get("companyName"),
                    "linkedinUrl": p.get("linkedinUrl"),
                }
            )
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


def fetch_recommendations_via_api(max_items: int, sort_condition: int = 0, page_size: int = 10) -> list[dict]:
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

        while len(out) < max_items:
            count = min(page_size, max_items - len(out))
            qs = urlencode(
                {
                    "refresh": refresh,
                    "sortCondition": str(sort_condition),
                    "position": str(position),
                    "count": str(count),
                }
            )
            url = f"{RECS_API}?{qs}"

            resp = page.request.get(
                url,
                headers={
                    "accept": "application/json",
                    "referer": RECS_PAGE,
                    "origin": BASE,
                },
            )

            if resp.status in (401, 403):
                try:
                    page.goto(RECS_PAGE, wait_until="domcontentloaded", timeout=60_000)
                except PWTimeoutError:
                    pass
                page.wait_for_timeout(1200)
                resp = page.request.get(
                    url,
                    headers={
                        "accept": "application/json",
                        "referer": RECS_PAGE,
                        "origin": BASE,
                    },
                )

            if resp.status in (401, 403):
                browser.close()
                raise PermissionError(f"Auth failed calling {url} (HTTP {resp.status}). Run with --login again.")

            if resp.status != 200:
                print(f"[WARN] API returned HTTP {resp.status} at position={position}. Stopping.")
                break

            data = resp.json()
            job_dicts = _extract_job_dicts(data)

            if not job_dicts:
                with open("jobright_debug_payload.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                print("[INFO] No job objects found. Dumped jobright_debug_payload.json")
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

                apply_url = _pick(
                    j,
                    "applyUrl", "applyURL", "applyLink",
                    "externalUrl", "sourceUrl", "url", "originalUrl",
                )
                apply_url = norm_url(apply_url)

                jobright_url = _pick(j, "detailUrl", "jobUrl", "infoUrl", "jobrightUrl")
                jobright_url = norm_url(jobright_url)
                if jobright_url is None and job_id_str:
                    jobright_url = f"{BASE}/jobs/info/{job_id_str}"

                linkedin_recruiters = extract_linkedin_recruiters(j)
                keywords = extract_keywords(j)

                out.append(
                    {
                        "jobId": job_id_str,
                        "title": title,
                        "company": company,
                        "location": location,
                        "jobright_url": jobright_url,
                        "apply_url": apply_url,
                        "linkedin_recruiters": linkedin_recruiters,
                        "keywords": keywords,
                        "raw": j,
                    }
                )
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true", help="Open browser to log in and save session state")
    ap.add_argument("--max", type=int, default=50, help="Max jobs to fetch")
    ap.add_argument("--out", default="jobright_recs.json", help="Output json file")
    args = ap.parse_args()

    if args.login:
        save_login_state()

    try:
        jobs = fetch_recommendations_via_api(max_items=args.max)
    except FileNotFoundError:
        print(f"[ERROR] Missing {STATE_FILE}. Run: python jobright_scrape.py --login")
        return
    except PermissionError as e:
        print(f"[ERROR] {e}")
        return

    print(f"[OK] Fetched {len(jobs)} jobs")
    for j in jobs[:20]:
        print(f"- {j.get('title') or ''} | {j.get('company') or ''} | {j.get('location') or ''}")
        print(f"  jobright: {j.get('jobright_url')}")
        print(f"  apply: {j.get('apply_url')}")
        recs = j.get("linkedin_recruiters") or []
        if recs:
            print(f"  recruiters: {len(recs)}")
            for r in recs[:3]:
                print(f"   - {r.get('fullName')} ({r.get('jobTitle')}) -> {r.get('linkedinUrl')}")
        kws = j.get("keywords") or []
        if kws:
            print("  keywords:", ", ".join(kws[:12]))
        print()

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2)

    print(f"[OK] Wrote {args.out}")


if __name__ == "__main__":
    main()