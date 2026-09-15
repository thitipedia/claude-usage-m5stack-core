# Claude usage on M5Stack Core

Shows your Claude Pro/Max plan limits (the same numbers as `/usage` in Claude Code) on an
M5Stack Core. It shows the 5-hour session limit, the weekly limit for all models, and the
weekly Opus and Sonnet limits when your plan has them.

A small Python bridge on your PC reads your Claude Code login, asks Anthropic for your usage,
and serves it as JSON on your local network. The M5Stack fetches that JSON over Wi-Fi and draws it.

```
PC                                                       M5Stack Core (UIFlow2)
~/.claude/.credentials.json --read--> bridge  <--HTTP GET /usage (Wi-Fi)-- display
                                        |      <--UDP "CLAUDE_USAGE?"----- finds PC
                                        +--HTTPS--> api.anthropic.com/api/oauth/usage
```

Your OAuth token never leaves your PC except to go to `api.anthropic.com`. The device only
ever sees rounded percentages and reset times.

> **Note:** `api/oauth/usage` is an undocumented endpoint used by Claude Code. It may change
> or stop working without notice.

## Features

- **Main page:** Session (5h) and Weekly (all models): percentage, colour bar, time until
  reset and the local reset time.
- **Details page:** Weekly Opus and Weekly Sonnet. These show `--` when your plan has no
  separate limit, which is normal on Pro.
- **Bar colours:** green below 50%, amber from 50 to 79%, red at 80% and above.
- **Offline:** the last good numbers stay on screen, and the header shows what's wrong.
- **Finding the PC:** if the device can't reach the PC, it broadcasts on the LAN and uses
  whichever bridge answers. This works when the PC's IP changes or you move to another PC.
- **Hidden bridge:** the bridge can run with no console window and start when you log in.

## Requirements

**Hardware:** M5Stack Core (Basic, ESP32, 320×240, three buttons) and a 2.4 GHz Wi-Fi network
shared with the PC.

**PC:**
- Python 3.10 or newer, standard library only. Tested on Windows 11 with Python 3.12.
- [Claude Code](https://claude.com/claude-code), logged in with a Claude Pro or Max
  subscription (`claude`, then `/login`).

**Device:** UIFlow2 firmware (flash it with M5Burner) and the web IDE at
[uiflow2.m5stack.com](https://uiflow2.m5stack.com).

## Repository layout

| File | Runs on | Purpose |
| --- | --- | --- |
| `claude_usage_bridge.py` | PC | Reads the token, polls Anthropic, serves `/usage` JSON over HTTP and answers discovery broadcasts |
| `start_bridge.bat` | PC | Starts the bridge in a console window (handy for watching output) |
| `start_bridge_hidden.bat` | PC | Starts the bridge with no window; output goes to `bridge.log` |
| `stop_bridge.bat` | PC | Stops any running bridge |
| `m5_claude_usage.py` | M5Stack | Device app (MicroPython) |
| `main.m5f2` | UIFlow2 | UIFlow2 project file that embeds a copy of `m5_claude_usage.py` |

There is nothing to compile. The bridge is a plain Python script, and the device app is
MicroPython that UIFlow2 uploads as it is.

## Setup

### 1. PC: run the bridge

```bash
claude
```

Run `/login` inside Claude Code if you haven't already. This fills `~/.claude/.credentials.json`.

```bash
python claude_usage_bridge.py --interval 60
```

Options:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--port` | `8765` | HTTP port. Discovery uses the same number on UDP |
| `--interval` | `60` | Seconds between calls to Anthropic |

Check it in a browser at `http://localhost:8765/usage`. You should see `"ok": true`.

The first time it runs, Windows Firewall asks whether to allow Python. Allow it on the network
type you're on (Private or Public), otherwise the device can't reach it. Note that
`python.exe` and `pythonw.exe` get separate firewall rules.

### 2. Device: upload the app

1. Flash **UIFlow2** onto the Core with M5Burner and set up its Wi-Fi there.
2. Open [uiflow2.m5stack.com](https://uiflow2.m5stack.com) and connect the device.
3. Either open `main.m5f2`, or create a new project and paste `m5_claude_usage.py` into the
   **Python** tab.
4. Edit the settings at the top if needed:

   ```python
   PC_HOST = "192.168.1.20:8765"  # first PC to try; blank = find one automatically
   PORT = 8765                     # bridge port, used for discovery
   WIFI_SSID = ""                  # leave blank if Wi-Fi is already set in UIFlow/M5Burner
   WIFI_PASS = ""
   POLL_MS = 30000
   ```

5. Click **Run** to try it, or **Download** to save it to the device so it starts at boot.

> Don't commit a copy with a real `WIFI_SSID`/`WIFI_PASS` filled in.

### 3. PC: start the bridge automatically and hidden (Windows)

- **Start it now with no window:** run `start_bridge_hidden.bat`. It calls
  `C:\Program Files\Python312\pythonw.exe`, so edit that path if your Python is somewhere else.
- **Stop it:** run `stop_bridge.bat`.
- **Start at login:** press Win+R, open `shell:startup`, and create a shortcut there with:
  - **Target:** `"C:\Program Files\Python312\pythonw.exe" claude_usage_bridge.py --interval 60`
  - **Start in:** the folder that contains this repo

  Point the shortcut at `pythonw.exe` directly rather than at a `.bat`, because a `.bat`
  briefly flashes a console window.

When the bridge runs hidden, it writes its output to `bridge.log` next to the script. The log
is capped at 1 MB with one backup. Only one bridge can hold the port at a time; a second copy
logs `cannot listen on port 8765` and exits.

## Using it

| Button | Action |
| --- | --- |
| **A** (left) | Refresh now |
| **B** (middle) | Switch between the main and details pages |
| **C** (right) | Cycle brightness (40 / 120 / 255) |

The device polls every 30 seconds and the bridge refreshes from Anthropic every 60 seconds,
so the numbers can be up to about 90 seconds old.

### Header messages

The header fits about 22 characters, so longer messages are cut off.

| Message | Meaning |
| --- | --- |
| `updated 14:32` | Last successful update, in the PC's local time |
| `finding PC...` | Couldn't reach the PC; broadcasting to find a bridge |
| `PC not found` | No bridge answered. Check that the bridge is running, the firewall allows Python, and both are on the same LAN |
| `no Wi-Fi` | The device couldn't join Wi-Fi |
| `token expired - open claude` | Open Claude Code once so it refreshes the login |
| `no creds - log in to claude` / `no token - ...` | Run `claude` and `/login` |
| `HTTP 401`, `HTTP 429`, ... | Anthropic returned an error. The last good numbers stay on screen |

## How the device finds the PC

1. The device tries the last bridge it reached, which it saves in `/flash/claude_usage_pc.txt`.
   The first time, it uses `PC_HOST`.
2. If that fails, it sends `CLAUDE_USAGE?` by UDP to port 8765, both to the subnet broadcast
   address and to `255.255.255.255`. It tries three times, waiting 1 second each.
3. Any bridge that hears it replies `CLAUDE_USAGE! <http port>`. The first reply wins and is
   saved.

Broadcasts don't cross routers, so the PC must be on the same local network. Once an address
is saved, it takes priority over `PC_HOST`. Delete `/flash/claude_usage_pc.txt` on the device
to go back to `PC_HOST`.

## JSON API

`GET http://<pc-ip>:8765/usage` (also served at `/`):

```json
{"ok": true, "err": "", "plan": "Pro", "updated": "14:32",
 "session": {"pct": 23, "left": "2h 14m", "at": "Tue 21:00"},
 "weekly":  {"pct": 41, "left": "3d 4h",  "at": "Fri 09:00"},
 "opus": null, "sonnet": null}
```

- **`pct`:** percentage used, rounded to a whole number.
- **`left`:** time until the limit resets.
- **`at`:** the reset time in the PC's local time zone.
- **`null` limit:** Anthropic didn't report that limit.
- **Errors:** `ok: false` comes with a short `err` message. The last known limits are kept in
  the response.

Other clients on your network, such as scripts or other displays, can use the same endpoint.

## Security notes

- The bridge only reads `~/.claude/.credentials.json`. It never writes or refreshes the token;
  Claude Code does that.
- The token is sent only to `api.anthropic.com`. It isn't served, logged or sent to the device.
- `/usage` has no authentication. Anyone on your LAN can read your usage percentages, but
  nothing else.
- For testing, set the `CLAUDE_USAGE_TOKEN` environment variable to use a token instead of the
  credentials file.

## Troubleshooting

- **`http://localhost:8765/usage` doesn't load:** the bridge isn't running. Run
  `start_bridge.bat` to see the error in a console, or read `bridge.log`.
- **It works on the PC but the device says `PC not found`:**
  - Allow `python.exe`/`pythonw.exe` through Windows Firewall, for both TCP and UDP.
  - Make sure the device and PC are on the same subnet.
  - Some guest or "client isolation" Wi-Fi networks block device-to-device traffic.
- **The details page shows `--`:** your plan has no separate Opus or Sonnet weekly limit.
- **Numbers never update:** open `claude` once so the token gets refreshed.
