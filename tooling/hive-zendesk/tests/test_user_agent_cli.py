"""Exercise the installed command and capture headers at real HTTP server boundaries."""

import json
import os
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import metadata
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

from hivezendesk.fm import parse_frontmatter


def test_backfill_sends_installed_version_to_connector_and_bifrost(tmp_path):
    installed = metadata.version("vf-hive-zendesk")
    requests = []
    row = {
        "id": 14872,
        "subject": "Orders not allocating",
        "description": "The morning wave is stuck and nothing allocated for the whole shift.",
        "organization_id": 42,
        "updated_at": "2026-03-14T09:00:00Z",
        "tags": ["allocation"],
        "requester_id": 5,
    }
    answer = {
        "what_happened": "The morning wave did not allocate.",
        "how_it_closed": "Reran replenishment and the wave allocated.",
        "module": "allocation",
        "tags": ["allocation"],
        "routine": False,
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, payload, status=200):
            requests.append({
                "method": self.command,
                "path": self.path,
                "user_agent": self.headers.get("User-Agent"),
                "authorization": self.headers.get("Authorization"),
                "response_status": status,
            })
            encoded = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/tickets/closed":
                self.respond([row])
            elif path == "/tickets/14872":
                self.respond({"comments": [{
                    "author_id": 9,
                    "public": True,
                    "body": "Replenishment lagged behind demand; reran it and the wave allocated.",
                    "created_at": "2026-03-14T10:00:00Z",
                }]})
            else:
                self.respond({"error": "unexpected endpoint"}, 404)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path != "/v1/chat/completions":
                self.respond({"error": "unexpected endpoint"}, 404)
                return
            self.respond({"choices": [{
                "message": {"content": json.dumps(answer)}, "finish_reason": "stop",
            }]})
            requests[-1]["model"] = body.get("model")

    customers = tmp_path / "customers.yaml"
    customers.write_text("customers:\n- code: alpha\n  zendesk_orgs:\n  - id: 42\n")
    concepts = tmp_path / "concepts"
    concepts.mkdir()
    clients = tmp_path / "clients"
    state = tmp_path / "state"
    # Locate the console script from this interpreter's install, not another checkout.
    executable = shutil.which("hivezendesk", path=str(Path(sys.executable).parent))
    assert executable is not None, "install vf-hive-zendesk before running this test"
    command = [
        executable, "backfill", "--client", "alpha", "--customers", str(customers),
        "--clients-dir", str(clients), "--concepts-dir", str(concepts),
        "--state-dir", str(state), "--limit", "1",
    ]
    # Do not inherit deployment settings, credentials, proxies, or a developer's .env.
    env = {key: value for key, value in os.environ.items()
           if key in {"PATH", "SYSTEMROOT", "PYTHONPATH"}}
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        base = f"http://127.0.0.1:{server.server_port}"
        env.update({
            "CONNECTOR_BASE": base,
            "CONNECTOR_API_KEY": "fixture-connector-key",
            "BIFROST_BASE": f"{base}/v1",
            "BIFROST_API_KEY": "fixture-bifrost-key",
            "DISTILL_MODEL": "fixture-model",
        })
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True,
                                    text=True, timeout=30, check=False)
        finally:
            server.shutdown()
            thread.join(timeout=5)

    cards = list((clients / "alpha" / "issues").glob("*.md"))
    # This is product evidence, available via pytest -s: actual CLI output, wire headers,
    # and the generated public card, never an implementation-source snapshot.
    print(json.dumps({
        "fixture": "loopback connector and Bifrost, synthetic ticket and model response",
        "installed_distribution": "vf-hive-zendesk",
        "installed_version": installed,
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "requests": requests,
        "generated_cards": {p.name: p.read_text() for p in cards},
    }, indent=2))

    assert result.returncode == 0, result.stderr
    assert "fetched=1 emitted=1 skipped=0 cached=0 preserved=0 pii_held=0 failed=0" in result.stderr
    assert len(cards) == 1
    assert parse_frontmatter(cards[0].read_text())["distilled_by"] == f"hive-zendesk@{installed}"
    assert json.loads((state / "alpha.json").read_text()) == {"42": row["updated_at"]}
    assert [(r["method"], urlsplit(r["path"]).path) for r in requests] == [
        ("GET", "/tickets/closed"), ("GET", "/tickets/14872"),
        ("POST", "/v1/chat/completions"),
    ]
    assert parse_qs(urlsplit(requests[0]["path"]).query) == {
        "org_id": ["42"], "since": ["1970-01-01T00:00:00Z"],
    }
    assert parse_qs(urlsplit(requests[1]["path"]).query) == {"with_comments": ["true"]}
    assert [r["authorization"] for r in requests] == [
        "Bearer fixture-connector-key", "Bearer fixture-connector-key", "Bearer fixture-bifrost-key",
    ]
    assert requests[2]["model"] == "fixture-model"
    assert all(r["response_status"] == 200 for r in requests)
    assert [r["user_agent"] for r in requests] == [f"hivezendesk/{installed}"] * 3
