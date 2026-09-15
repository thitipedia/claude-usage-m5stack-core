"""
Claude plan usage bridge for M5Stack.

Runs on your PC. Reads the Claude Code login token from ~/.claude/.credentials.json,
asks Anthropic for your plan limits (same data as /usage in Claude Code), and serves a
small, pre-formatted JSON at http://<pc-ip>:8765/usage for the M5Stack to poll.
It also answers UDP broadcasts on the same port so the M5Stack can find this PC's IP.
The token never leaves this PC except to api.anthropic.com.

Note: api/oauth/usage is undocumented and may change. The token is refreshed by
Claude Code itself, so if it expires, just open `claude` once.

Usage:  python claude_usage_bridge.py   [--port 8765] [--interval 60]
        Run with pythonw.exe to hide the console; output then goes to bridge.log.
"""
import argparse
import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path

CRED_FILE = Path.home() / ".claude" / ".credentials.json"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
DISCOVER = b"CLAUDE_USAGE?"  # device broadcasts this; we reply b"CLAUDE_USAGE! <http port>"

state = {"ok": False, "err": "starting", "updated": ""}
lock = threading.Lock()
log = logging.getLogger("bridge")


def setup_logging():
    if sys.stdout is None:  # pythonw.exe: no console, so log to a size-capped file
        handler = RotatingFileHandler(Path(__file__).with_name("bridge.log"),
                                      maxBytes=1_000_000, backupCount=1, encoding="utf-8")
    else:
        handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def read_token():
    if os.environ.get("CLAUDE_USAGE_TOKEN"):
        return os.environ["CLAUDE_USAGE_TOKEN"], ""
    if not CRED_FILE.exists():
        raise RuntimeError("no creds - log in to claude")
    data = json.loads(CRED_FILE.read_text(encoding="utf-8"))
    oauth = data.get("claudeAiOauth") or {}
    token = oauth.get("accessToken")
    if not token:
        raise RuntimeError("no token - log in to claude")
    expires = oauth.get("expiresAt")  # epoch ms
    if expires and expires / 1000 < time.time():
        raise RuntimeError("token expired - open claude")
    return token, oauth.get("subscriptionType") or ""


def fmt_left(iso):
    """'2026-09-15T14:00:00Z' -> ('2h 14m', 'Tue 21:00' local)."""
    if not iso:
        return "", ""
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    secs = max(0, int((t - datetime.now(timezone.utc)).total_seconds()))
    d, rem = divmod(secs, 86400)
    h, m = rem // 3600, rem % 3600 // 60
    left = f"{d}d {h}h" if d else (f"{h}h {m:02d}m" if h else f"{m}m")
    return left, t.astimezone().strftime("%a %H:%M")


def limit(block):
    if not block or block.get("utilization") is None:
        return None
    left, at = fmt_left(block.get("resets_at"))
    return {"pct": round(float(block["utilization"])), "left": left, "at": at}


def fetch():
    token, plan = read_token()
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
        "Content-Type": "application/json",
        "User-Agent": "claude-usage-m5stack/1.0",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = json.loads(r.read())
    return {
        "ok": True,
        "err": "",
        "plan": plan.capitalize(),
        "session": limit(raw.get("five_hour")),
        "weekly": limit(raw.get("seven_day")),
        "opus": limit(raw.get("seven_day_opus")),
        "sonnet": limit(raw.get("seven_day_sonnet")),
        "updated": datetime.now().strftime("%H:%M"),
    }


def poller(interval):
    global state
    while True:
        try:
            new = fetch()
        except urllib.error.HTTPError as e:
            new = dict(state, ok=False, err=f"HTTP {e.code}")
        except Exception as e:  # noqa: BLE001 - show any failure on the device
            new = dict(state, ok=False, err=str(e)[:40])
        with lock:
            state = new
        log.info(json.dumps(new))
        time.sleep(interval)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] not in ("/", "/usage"):
            self.send_error(404)
            return
        with lock:
            body = json.dumps(state).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def discovery_server(sock, port):
    """Answer the device's UDP broadcast so it can find this PC without a fixed IP."""
    while True:
        try:
            msg, addr = sock.recvfrom(64)
            if msg.strip() == DISCOVER:
                sock.sendto(b"CLAUDE_USAGE! %d" % port, addr)
                log.info(f"discovery: answered {addr[0]}")
        except OSError as e:  # e.g. WinError 10054 after replying to a vanished sender
            log.info(f"discovery: {e}")
            time.sleep(0.1)


class Server(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second bridge bind the same port; refuse instead.
    allow_reuse_address = os.name != "nt"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--interval", type=int, default=60, help="seconds between API polls")
    a = ap.parse_args()
    setup_logging()
    try:
        server = Server(("0.0.0.0", a.port), Handler)
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind(("0.0.0.0", a.port))
    except OSError as e:  # usually another bridge already holds the port
        log.error(f"cannot listen on port {a.port}: {e}")
        raise SystemExit(1)
    threading.Thread(target=poller, args=(a.interval,), daemon=True).start()
    threading.Thread(target=discovery_server, args=(udp, a.port), daemon=True).start()
    log.info(f"Serving on http://0.0.0.0:{a.port}/usage  (Ctrl+C to stop)")
    server.serve_forever()
