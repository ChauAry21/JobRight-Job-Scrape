import os, json, pytest, threading
import jobright_scrape as js
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

pytestmark = pytest.mark.integration

if os.getenv("RUN_PLAYWRIGHT_INTEGRATION") != "1":
    pytest.skip("Set RUN_PLAYWRIGHT_INTEGRATION=1 to run Playwright integration tests.", allow_module_level=True)


pytest.importorskip("playwright.sync_api")

class _Server:
    def __init__(self, mode: str):
        self.mode = mode
        self.httpd = None
        self.thread = None
        self.base_url = None

    def start(self):
        mode = self.mode

        class Handler(BaseHTTPRequestHandler):
            def _send(self, code: int, body: bytes, content_type: str):
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt, *args):
                return

            def do_GET(self):
                parsed = urlparse(self.path)

                if parsed.path == "/jobs/recommend":
                    body = b"<html><body>recommendations</body></html>"
                    return self._send(200, body, "text/html; charset=utf-8")

                if parsed.path == "/swan/recommend/list/jobs":
                    if mode == "forbidden":
                        return self._send(403, b'{"error":"forbidden"}', "application/json")

                    qs = parse_qs(parsed.query)
                    count = int(qs.get("count", ["10"])[0])

                    jobs = []
                    for i in range(count):
                        job_id = f"job-{i}"
                        jobs.append(
                            {
                                "jobInfoId": job_id,
                                "jobTitle": "Software Engineer",
                                "companyName": "Acme",
                                "jobLocation": "Remote",
                                "applyUrl": "/apply/123",
                                "detailUrl": f"/jobs/info/{job_id}",
                                "socialConnections": [
                                    {
                                        "fullName": "Jane Recruiter",
                                        "jobTitle": "Technical Recruiter",
                                        "companyName": "Acme",
                                        "linkedinUrl": "https://linkedin.com/in/jane",
                                    },
                                    {
                                        "fullName": "Bob Engineer",
                                        "jobTitle": "Software Engineer",
                                        "companyName": "Acme",
                                        "linkedinUrl": "https://linkedin.com/in/bob",
                                    },
                                ],
                                "jdCoreSkills": [{"skill": "Python"}, {"skill": "SQL"}],
                                "recommendationTags": ["New Grad", "Remote"],
                            }
                        )

                    payload = {"data": {"jobs": jobs}}
                    body = json.dumps(payload).encode("utf-8")
                    return self._send(200, body, "application/json; charset=utf-8")

                return self._send(404, b"not found", "text/plain; charset=utf-8")

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = httpd.server_address[1]
        self.httpd = httpd
        self.base_url = f"http://127.0.0.1:{port}"

        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        self.thread = t

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()


@pytest.fixture()
def state_file(tmp_path):
    p = tmp_path / "jobright_state.json"
    p.write_text(json.dumps({"cookies": [], "origins": []}), encoding="utf-8")
    return p


def test_fetch_recommendations_integration_ok(tmp_path, monkeypatch, state_file):
    srv = _Server(mode="ok")
    srv.start()
    try:
        monkeypatch.chdir(tmp_path)

        monkeypatch.setattr(js, "STATE_FILE", str(state_file))
        monkeypatch.setattr(js, "BASE", srv.base_url)
        monkeypatch.setattr(js, "RECS_PAGE", f"{srv.base_url}/jobs/recommend")
        monkeypatch.setattr(js, "RECS_API", f"{srv.base_url}/swan/recommend/list/jobs")

        jobs = js.fetch_recommendations_via_api(max_items=3, page_size=3)

        assert len(jobs) == 3
        j0 = jobs[0]
        assert j0["jobId"].startswith("job-")
        assert j0["title"] == "Software Engineer"
        assert j0["company"] == "Acme"
        assert j0["location"] == "Remote"

        assert j0["apply_url"].startswith(srv.base_url)
        assert j0["jobright_url"].startswith(srv.base_url)

        recs = j0["linkedin_recruiters"]
        assert len(recs) == 1
        assert recs[0]["fullName"] == "Jane Recruiter"

        assert "Python" in j0["keywords"]
        assert "New Grad" in j0["keywords"]
    finally:
        srv.stop()


def test_fetch_recommendations_integration_forbidden(tmp_path, monkeypatch, state_file):
    srv = _Server(mode="forbidden")
    srv.start()
    try:
        monkeypatch.chdir(tmp_path)

        monkeypatch.setattr(js, "STATE_FILE", str(state_file))
        monkeypatch.setattr(js, "BASE", srv.base_url)
        monkeypatch.setattr(js, "RECS_PAGE", f"{srv.base_url}/jobs/recommend")
        monkeypatch.setattr(js, "RECS_API", f"{srv.base_url}/swan/recommend/list/jobs")

        with pytest.raises(PermissionError) as e:
            js.fetch_recommendations_via_api(max_items=1, page_size=1)

        assert "Auth failed" in str(e.value)
    finally:
        srv.stop()