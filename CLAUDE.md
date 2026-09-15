# Claude plan usage on M5Stack Core

Shows Claude Pro/Max plan limits (the same percentages as `/usage` in Claude Code)
on an M5Stack Core (Basic, ESP32, 320x240, 3 buttons) running UIFlow2 MicroPython.

## Architecture

    PC (Python 3, stdlib only)                            M5Stack Core (UIFlow2)
    ~/.claude/.credentials.json  --read-->  bridge  <--HTTP GET /usage--  display loop
                                              |
                                              +--HTTPS--> api.anthropic.com/api/oauth/usage

The device polls `GET http://<pc-ip>:8765/usage` over Wi-Fi. If that fails it finds a
bridge by UDP broadcast (see Discovery below), so the PC's IP can change or the device
can move to another PC.

The bridge polls Anthropic every 60 s, pre-formats everything (rounded percentages,
"2h 14m" reset strings, local reset times), and serves one small JSON on port 8765.
The device only parses JSON and draws — no token, no TLS, no date math on the ESP32.

**The OAuth token never leaves the PC** except to api.anthropic.com. That split is the
point of the design; do not move the token onto the device.

## Files

| File | Runs on | Purpose |
| --- | --- | --- |
| `claude_usage_bridge.py` | PC | Reads token, calls Anthropic, serves `/usage` JSON over HTTP |
| `start_bridge.bat` | PC | Launcher with a console window (`--interval 60`), for debugging |
| `start_bridge_hidden.bat` | PC | Same, via `pythonw.exe` (no window); output goes to `bridge.log` |
| `stop_bridge.bat` | PC | Kills any running bridge (matches python processes running `claude_usage_bridge.py`) |
| `m5_claude_usage.py` | M5Stack | Paste into the uiflow2.m5stack.com Python tab |
| `main.m5f2` | UIFlow2 | Project file; its `pythonCode` field embeds a copy of `m5_claude_usage.py`. Keep them in sync |

## Wire format (`GET http://<pc-ip>:8765/usage`)

```json
{"ok": true, "err": "", "plan": "Pro", "updated": "14:32",
 "session": {"pct": 23, "left": "2h 14m", "at": "Tue 21:00"},
 "weekly":  {"pct": 41, "left": "3d 4h",  "at": "Fri 09:00"},
 "opus":    null, "sonnet": {"pct": 12, "left": "3d 4h", "at": "Fri 09:00"}}
```

`ok: false` carries `err` (short string, rendered in red on the device). A limit is
`null` when the API omits it or reports no utilization; the device then draws `--`.
Keep `err` under ~22 chars — that is all the header fits.

## Discovery (UDP, same port 8765)

- Device sends `CLAUDE_USAGE?` to the subnet broadcast (from `ifconfig()` ip/mask) and to
  `255.255.255.255`, 3 tries with a 1 s timeout. The bridge replies `CLAUDE_USAGE! <http port>`.
  The first reply wins.
- Host order: `/flash/claude_usage_pc.txt` (last bridge found), then `PC_HOST`. On any
  fetch failure: `discover()`, then one retry. Header shows "finding PC..." while
  searching and "PC not found" when nothing answers.
- The saved file takes priority over `PC_HOST`, so editing `PC_HOST` does nothing once
  a host has been saved. Delete the file to reset.
- Several PCs running bridges: the device stays with whichever answered until it fails.
- Verified 2026-09-15 on the PC only, with a CPython client (subnet, global broadcast and
  unicast all answered; other packets ignored). Not yet run on the ESP32.

## Device UI

- Main page: Session (5h) and Weekly (all models) cards — big percentage, bar, reset time.
- Details page: Weekly Opus and Weekly Sonnet.
- Bar colour by threshold: green < 50%, amber 50–79%, red >= 80%.
- BtnA refresh now, BtnB toggle page, BtnC cycle brightness (40/120/255).
- Poll interval 30 s (`POLL_MS`); on failure the last good numbers stay on screen
  and the header shows "PC not found" / "no Wi-Fi" / `HTTP <code>`.
- Colours are the dark Claude palette (`BG 0x141413`, `ORANGE 0xD97757`); UIFlow2
  takes 24-bit ints directly.
- `requests` import is tried as `requests2` → `requests` → `urequests` because the
  module name differs across UIFlow2 firmware builds.

## Setup

1. `claude` in a terminal, then `/login` — fills `~/.claude/.credentials.json`.
2. `start_bridge.bat`; allow Python through Windows Firewall on **Private** networks.
   Verify: `http://localhost:8765/usage` shows `"ok": true`.
3. Paste `m5_claude_usage.py` into uiflow2.m5stack.com → Run (or Download for autostart).
   `PC_HOST` is optional (discovery finds the PC); set `WIFI_SSID`/`WIFI_PASS` only if the device has
   no Wi-Fi config from M5Burner.
4. Autostart (installed 2026-09-15): `shell:startup\Claude Usage Bridge.lnk` runs
   `pythonw.exe claude_usage_bridge.py --interval 60` in this folder, so no window appears.
   It points at `pythonw.exe` directly, not a `.bat`, because a `.bat` flashes a console.

## Gotchas / status

- **`api/oauth/usage` is undocumented.** Headers that matter: `Authorization: Bearer
  <accessToken>` and `anthropic-beta: oauth-2025-04-20`. Response blocks seen in the
  wild: `five_hour`, `seven_day`, `seven_day_opus`, `seven_day_sonnet` (each with
  `utilization` 0–100 and `resets_at` ISO-8601 Z). It may change without notice.
- **PC side verified live on 2026-09-15** (Pro plan): `five_hour` and `seven_day` came
  back; `seven_day_opus`/`seven_day_sonnet` were null, so the Details page shows `--` on Pro.
  The device side has not yet been verified on hardware.
- **Hidden mode / logging:** under `pythonw.exe`, `sys.stdout` is None, so `setup_logging()`
  writes to `bridge.log` (1 MB, one backup). With a console, it logs to stdout.
- **One bridge at a time:** `Server.allow_reuse_address` is False on Windows, where
  SO_REUSEADDR would let a second bridge bind 8765 too. A duplicate logs
  "cannot listen on port 8765" and exits.
- **Token expiry:** Claude Code refreshes it; the bridge only reads. Expired token →
  `err: "token expired - open claude"`, fixed by opening `claude` once.
- `CLAUDE_USAGE_TOKEN` env var overrides the credentials file (useful for testing).
- Only the bridge holds secrets — keep tokens out of committed files and out of logs
  (`poller()` logs state JSON, which deliberately excludes the token).

## Environment

- Windows 11, Python 3.12 at `C:\Program Files\Python312\python.exe`.
- PC has two LAN IPs on one /24: `192.168.90.15` and `192.168.90.132`. Discovery replies
  come from `.15`.
- Firewall already allows `python.exe` and `pythonw.exe` inbound on TCP and UDP. The profile is
  **Public** (the Ethernet network is marked Public).
