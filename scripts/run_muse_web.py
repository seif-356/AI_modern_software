"""Collect the supplemental Muse panel through a local form, or replay its saved replies."""
import argparse
import hashlib
import html
import json
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from filelock import FileLock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bugfix import Budget, SYSTEMS, evaluate, load_bugs
from bugfix.systems.base import RepairResult

OUT = ROOT / "results/phase3/pilots"
CALLS = OUT / "muse-web-calls.jsonl"
DATA = ROOT / "data/phase3/bugs.jsonl"


def append(path, row):
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")


class FormModel:
    def __init__(self, replay):
        rows = [json.loads(line) for line in CALLS.read_text(encoding="utf-8").splitlines()] if CALLS.exists() else []
        self.saved = {row["id"]: row for row in rows}
        if len(self.saved) != len(rows):
            raise ValueError("Duplicate browser reply")
        self.replay = replay
        self.used = set()
        self.cv = threading.Condition()
        self.pending = None
        self.done = False

    def chat(self, messages, budget, role):
        budget.check()
        key = f"{self.bug}/{self.system}/{budget.calls + 1}"
        prompt = "\n\n".join(m["content"] for m in messages)
        with self.cv:
            if key not in self.saved:
                if self.replay:
                    raise ValueError(f"Missing browser reply for {key}")
                self.pending = dict(id=key, role=role, prompt=prompt)
                self.cv.wait_for(lambda: key in self.saved)
            record = self.saved[key]
            if record["prompt"] != prompt or record["role"] != role:
                raise ValueError(f"Prompt mismatch for {key}")
            self.used.add(key)
        budget.calls += 1  # Only visible submissions are measurable.
        return record["reply"]


def collect(model):
    pilot = json.loads((OUT / "muse-web-gcd.json").read_text(encoding="utf-8"))
    rows = []
    digest = hashlib.sha256(DATA.read_bytes()).hexdigest()
    if digest != pilot["dataset_sha256"]:
        raise ValueError("The matched-panel input differs from the GCD pilot dataset")
    for bug in load_bugs(DATA):
        for system in ("s0", "s1", "s2", "s2r"):
            model.bug, model.system = bug.id, system
            budget = Budget(max_calls=4)
            if bug.id == pilot["bug_id"] and system == "s0":
                result = RepairResult(system, pilot["first_reply_code"], True, "single_shot")
                budget.calls = 1
            else:
                result = SYSTEMS[system](bug, model, budget)
            score = evaluate(bug, result)
            rows.append(dict(bug_id=bug.id, system=system, data_sha256=digest,
                             browser_submissions=budget.calls, stop_reason=result.stop_reason,
                             final_code=result.final_code, reviewer_approved=result.reviewer_approved,
                             **score))
            print(len(rows), bug.id, system, score["label"], flush=True)
    output = OUT / "muse-web-panel.jsonl"
    if set(model.saved) != model.used:
        raise ValueError("The browser call log contains unused replies")
    temp = output.with_suffix(".tmp")
    temp.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n")
    temp.replace(output)


def serve(model, port):
    class Form(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            with model.cv:
                job = model.pending
                body = "<h1>Panel finished</h1>" if model.done else "<h1>Scoring</h1>"
                if job:
                    key = html.escape(job["id"], quote=True)
                    body = (f'<h1>Pending browser request</h1><p id="job">{key}</p><p id="role">{job["role"]}</p>'
                            f'<pre id="prompt">{html.escape(job["prompt"])}</pre>'
                            f'<form method="post"><input type="hidden" name="id" value="{key}">'
                            '<label>First Muse reply<textarea name="reply" required></textarea></label>'
                            '<button>Save reply</button></form>')
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body.encode())

        def do_POST(self):
            if self.headers.get("Origin") != f"http://127.0.0.1:{port}":
                return self.send_error(403)
            fields = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
            with model.cv:
                job = model.pending
                if not job or fields.get("id") != [job["id"]] or not fields.get("reply"):
                    return self.send_error(409)
                row = dict(**job, reply=fields["reply"][0].replace("\r\n", "\n"),
                           captured_at=datetime.now(timezone.utc).isoformat())
                append(CALLS, row)
                model.saved[job["id"]] = row
                model.pending = None
                model.cv.notify_all()
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
    return HTTPServer(("127.0.0.1", port), Form)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect", action="store_true", help="Enable the loopback collection form.")
    parser.add_argument("--port", type=int, default=18189)
    args = parser.parse_args()
    import tempfile
    lock = Path(tempfile.gettempdir()) / ("sw403-muse-" + hashlib.sha256(str(OUT).encode()).hexdigest()[:16] + ".lock")
    with FileLock(lock, timeout=0):
        model = FormModel(replay=not args.collect)
        if args.collect:
            server = serve(model, args.port)
            threading.Thread(target=server.serve_forever, daemon=True).start()
        collect(model)
        model.done = True
