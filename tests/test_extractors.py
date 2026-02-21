import jobright_scrape as js


def test_extract_job_dicts_filters_profiles():
    payload = {
        "data": [
            {"firstName": "Sam", "fullName": "Sam R", "linkedinUrl": "https://linkedin.com/in/x"},
            {"jobInfoId": 123, "jobTitle": "SWE", "companyName": "Acme", "applyUrl": "https://apply.example"},
        ]
    }
    jobs = js._extract_job_dicts(payload)
    assert len(jobs) == 1
    assert jobs[0]["jobTitle"] == "SWE"


def test_extract_company_fallback_from_summary():
    job = {"jobSummary": "OpenAI is building safe AGI."}
    assert js.extract_company(job) == "OpenAI"


def test_extract_company_fallback_from_logo_slug():
    job = {"jdLogo": "https://cdn.example.com/assets/openai_logo.png"}
    assert js.extract_company(job) == "openai"


def test_extract_linkedin_recruiters_filters_by_title_keywords():
    job = {
        "socialConnections": [
            {"fullName": "A Recruiter", "jobTitle": "Senior Recruiter", "linkedinUrl": "https://x"},
            {"fullName": "An Engineer", "jobTitle": "Software Engineer", "linkedinUrl": "https://y"},
            {"fullName": "Talent Person", "jobTitle": "Talent Sourcer", "linkedinUrl": "https://z"},
        ]
    }
    recs = js.extract_linkedin_recruiters(job)
    assert len(recs) == 2
    assert {r["fullName"] for r in recs} == {"A Recruiter", "Talent Person"}


def test_extract_keywords_dedupes_and_caps():
    job = {
        "jdCoreSkills": [{"skill": "Python"}, {"skill": "Python"}, {"skill": "SQL"}],
        "skillMatchingScores": [{"displayName": "Python"}, {"featureName": "AWS"}],
        "recommendationTags": ["New Grad", "Remote", "Remote"],
        "jobTaxonomyV3": ["Software", "Software"],
        "firstTaxonomy": "Engineering",
    }
    kws = js.extract_keywords(job, max_kw=5)
    assert len(kws) == 5
    assert len(set(kws)) == 5