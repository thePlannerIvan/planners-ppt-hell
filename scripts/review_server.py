import argparse
import hashlib
import json
import os
import secrets
import signal
import socket
import sys
import uuid
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs


def safe_batch_id(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    return "".join(ch for ch in raw if ch.isalnum() or ch in ("_", "-"))


class ReviewHandler(SimpleHTTPRequestHandler):
    project_root: Path = None
    session_id: str = ""
    approval_key_hash: str = ""
    approval_key_required: bool = True

    def log_message(self, format, *args):
        print(f"[server] {args[0]}" if args else format, flush=True)

    def _json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, rel_path, content_type="text/html; charset=utf-8"):
        fp = self.project_root / rel_path
        if fp.exists():
            body = fp.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._json_response({"error": f"File not found: {rel_path}"}, 404)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def _sha256_file(self, rel_path):
        fp = self.project_root / rel_path
        if not fp.exists() or not fp.is_file():
            return ""
        digest = hashlib.sha256()
        with fp.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _png_hashes(self):
        png_dir = self.project_root / "_internal" / "03_png_preview"
        if not png_dir.exists():
            return {}
        return {
            p.name: self._sha256_file(p.relative_to(self.project_root))
            for p in sorted(png_dir.glob("*.png"))
        }

    def _append_event(self, event_type, details):
        event_path = self.project_root / "_internal" / "00_project" / "flow_events.jsonl"
        event_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "time": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "details": details,
        }
        with event_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _with_provenance(self, data, route):
        now = datetime.now(timezone.utc).isoformat()
        html_rel = "01_layout_direction.html" if route == "/layout-feedback" else "02_visual_review.html"
        approval_key = str(data.pop("approval_key", "")).strip()
        approval_key_verified = False
        if self.approval_key_hash:
            approval_key_verified = hashlib.sha256(approval_key.encode("utf-8")).hexdigest() == self.approval_key_hash

        data["provenance"] = {
            "source": "review_server",
            "route": route,
            "session_id": self.session_id,
            "submitted_at": now,
            "html": html_rel,
            "html_sha256": self._sha256_file(html_rel),
            "png_sha256": self._png_hashes() if route == "/review-feedback" else {},
            "approval_key_verified": approval_key_verified,
            "approval_key_required": self.approval_key_required,
        }
        if data.get("all_approved") is True and not approval_key_verified:
            data["all_approved"] = False
            data["approval_blocked_reason"] = "approval_key_missing_or_invalid"
            for page in data.get("pages", {}).values():
                if isinstance(page, dict):
                    page["approved"] = False
        return data

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path == "" or path == "/":
            self._serve_file("01_layout_direction.html")
        elif path == "/review":
            self._serve_file("02_visual_review.html")
        elif path == "/health":
            self._json_response({"status": "running", "uptime": "ok"})
        elif path.startswith("/_internal/03_png_preview/") or path.startswith("/_internal/05_review/versions/"):
            fp = self.project_root / path.lstrip("/")
            if fp.exists():
                ct = "image/png" if fp.suffix.lower() == ".png" else "image/svg+xml"
                body = fp.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._json_response({"error": "Not found"}, 404)
        else:
            self._json_response({"error": "Not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        body = self._read_body()
        data = {}
        if body:
            ct = self.headers.get("Content-Type", "")
            if "application/json" in ct:
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    pass
            elif "application/x-www-form-urlencoded" in ct:
                parsed = parse_qs(body.decode("utf-8"))
                data = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

        if path == "/layout-feedback":
            data["updated_at"] = datetime.now(timezone.utc).isoformat()
            data = self._with_provenance(data, "/layout-feedback")
            (self.project_root / "_internal" / "01_layout_plan" / "layout_feedback.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self._append_event("layout_feedback_submitted", data.get("provenance", {}))
            self._json_response({"status": "ok", "written": "_internal/01_layout_plan/layout_feedback.json"})

        elif path == "/review-feedback":
            data["submitted_at"] = datetime.now(timezone.utc).isoformat()
            data = self._with_provenance(data, "/review-feedback")
            review_dir = self.project_root / "_internal" / "05_review"
            review_dir.mkdir(parents=True, exist_ok=True)
            latest_path = review_dir / "feedback.json"
            latest_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            batch_id = safe_batch_id(data.get("batch_id"))
            if batch_id:
                batch_dir = review_dir / "batches"
                batch_dir.mkdir(parents=True, exist_ok=True)
                (batch_dir / f"{batch_id}.json").write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            self._append_event("visual_feedback_submitted", data.get("provenance", {}))
            written = ["_internal/05_review/feedback.json"]
            if batch_id:
                written.append(f"_internal/05_review/batches/{batch_id}.json")
            self._json_response({"status": "ok", "written": written})

        elif path == "/shutdown":
            self._archive_feedback()
            self._json_response({"status": "shutting_down"})
            print("[server] Shutting down.", flush=True)
            os.kill(os.getpid(), signal.SIGTERM)

        else:
            self._json_response({"error": "Unknown endpoint"}, 404)

    def _archive_feedback(self):
        archive_dir = self.project_root / "_internal" / "00_project"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / "feedback_archive.json"
        archive = {"archived_at": datetime.now(timezone.utc).isoformat(), "batches": []}
        layout_fb = self.project_root / "_internal" / "01_layout_plan" / "layout_feedback.json"
        review_fb = self.project_root / "_internal" / "05_review" / "feedback.json"
        if layout_fb.exists():
            archive["layout_feedback"] = json.loads(layout_fb.read_text(encoding="utf-8"))
        if review_fb.exists():
            archive["review_feedback"] = json.loads(review_fb.read_text(encoding="utf-8"))
        batch_dir = self.project_root / "_internal" / "05_review" / "batches"
        if batch_dir.exists():
            archive["review_feedback_batches"] = {
                p.stem: json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(batch_dir.glob("*.json"))
            }
        archive_path.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")


def find_port(start=8765):
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("No free port found")


def main():
    parser = argparse.ArgumentParser(description="Local review server for Planner's PPT Hell.")
    parser.add_argument("project_dir", help="Project root directory")
    parser.add_argument("--port", type=int, default=0, help="Port (default: auto-find from 8765)")
    parser.add_argument(
        "--approval-key",
        default=os.environ.get("SMART_SVG_APPROVAL_KEY", ""),
        help="Human approval key. If omitted, a one-time key is generated and printed. Can also use SMART_SVG_APPROVAL_KEY.",
    )
    args = parser.parse_args()

    root = Path(args.project_dir).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        sys.exit(1)

    port = args.port if args.port else find_port()
    ReviewHandler.project_root = root
    ReviewHandler.session_id = uuid.uuid4().hex
    ReviewHandler.approval_key_required = True
    approval_key = args.approval_key or secrets.token_urlsafe(10)
    ReviewHandler.approval_key_hash = hashlib.sha256(approval_key.encode("utf-8")).hexdigest()

    session_path = root / "_internal" / "00_project" / "review_session.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        json.dumps(
            {
                "source": "review_server",
                "session_id": ReviewHandler.session_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "port": port,
                "approval_key_required": ReviewHandler.approval_key_required,
                "approval_key_hash": ReviewHandler.approval_key_hash,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    server = ThreadingHTTPServer(("127.0.0.1", port), ReviewHandler)
    print(f"[server] Project: {root}")
    print(f"[server] Session: {ReviewHandler.session_id}", flush=True)
    print("[server] Human approval key: required", flush=True)
    print(f"[server] One-time approval key: {approval_key}", flush=True)
    print(f"[server] ═══════════════════════════════════════════════", flush=True)
    print(f"[server] Phase 1 — 版式方向审阅: http://127.0.0.1:{port}/", flush=True)
    print(f"[server] Phase 4 — 视觉审阅:     http://127.0.0.1:{port}/review", flush=True)
    print(f"[server] ═══════════════════════════════════════════════", flush=True)
    print(f"[server] Health: http://127.0.0.1:{port}/health", flush=True)
    print(f"[server] 请使用以上 URL 提交反馈，不要直接打开 file:// HTML。", flush=True)
    print(f"[server] Ctrl+C to stop", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] Stopped.", flush=True)
        server.server_close()


if __name__ == "__main__":
    main()
