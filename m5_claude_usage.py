# Claude plan usage display - M5Stack Core (Basic) / UIFlow2 (MicroPython)
# Paste into the Python tab at https://uiflow2.m5stack.com and Download/Run.
# Needs claude_usage_bridge.py running on your PC; the device polls it over Wi-Fi.
# If the PC can't be reached, the device broadcasts on the LAN to find a bridge
# (the same PC at a new IP, or another PC) and remembers the one that answers.
#
#   BtnA = refresh now   BtnB = screen on/off   BtnC = brightness
import M5
from M5 import *
import network
import socket
import time

# ---- settings -----------------------------------------------------------
PC_HOST = "192.168.90.15:8765"  # first PC to try; blank = find one automatically
PORT = 8765                     # bridge port, used for discovery
WIFI_SSID = ""                   # leave blank if Wi-Fi is already set in UIFlow/M5Burner
WIFI_PASS = ""
POLL_MS = 30000
HOST_FILE = "/flash/claude_usage_pc.txt"  # last bridge found, survives reboot
DISCOVER = b"CLAUDE_USAGE?"
# -------------------------------------------------------------------------

try:
    import requests2 as requests
except ImportError:
    try:
        import requests
    except ImportError:
        import urequests as requests

W, H = 320, 240
BG = 0x141413
CARD = 0x262624
TRACK = 0x3D3D3A
TEXT = 0xFAF9F5
MUTED = 0x9C9A92
ORANGE = 0xD97757
GREEN = 0x5DB872
AMBER = 0xE8A33D
RED = 0xE5534B

lcd = M5.Lcd
data = None
err = "connecting..."
screen_on = True
bright_levels = [40, 120, 255]
bright_i = 1


def font(size):
    f = {12: lcd.FONTS.DejaVu12, 18: lcd.FONTS.DejaVu18,
         24: lcd.FONTS.DejaVu24, 40: lcd.FONTS.DejaVu40}[size]
    lcd.setFont(f)


def text(s, x, y, size, color, bg, align="left"):
    font(size)
    lcd.setTextColor(color, bg)
    if align == "right":
        x -= lcd.textWidth(s)
    elif align == "center":
        x -= lcd.textWidth(s) // 2
    lcd.drawString(s, x, y)


def level_color(pct):
    if pct >= 80:
        return RED
    if pct >= 50:
        return AMBER
    return GREEN


def card(y, h, title, lim):
    x, w = 8, W - 16
    lcd.fillRoundRect(x, y, w, h, 8, CARD)
    text(title, x + 12, y + 10, 18, MUTED, CARD)
    if not lim:
        text("--", x + w - 12, y + 6, 24, MUTED, CARD, "right")
        return
    pct = max(0, min(100, lim["pct"]))
    col = level_color(pct)
    text("%d%%" % pct, x + w - 12, y + 6, 24, col, CARD, "right")
    bx, by, bw, bh = x + 12, y + 40, w - 24, 14
    lcd.fillRoundRect(bx, by, bw, bh, 7, TRACK)
    fw = bw * pct // 100
    if fw > 0:
        lcd.fillRoundRect(bx, by, max(fw, bh), bh, 7, col)
    if lim.get("left"):
        text("resets in " + lim["left"], bx, y + h - 22, 12, MUTED, CARD)
        text(lim.get("at", ""), x + w - 12, y + h - 22, 12, MUTED, CARD, "right")


def header():
    lcd.fillRect(0, 0, W, 32, BG)
    lcd.fillCircle(16, 16, 6, ORANGE)
    plan = (data or {}).get("plan", "")
    text("Claude " + plan, 30, 7, 18, TEXT, BG)
    if err:
        text(err[:22], W - 8, 10, 12, RED, BG, "right")
    elif data:
        text("updated " + data.get("updated", ""), W - 8, 10, 12, MUTED, BG, "right")


def footer():
    lcd.fillRect(0, H - 20, W, 20, BG)
    for x, label in ((68, "Refresh"), (160, "Screen"), (252, "Light")):
        text(label, x, H - 16, 12, MUTED, BG, "center")


def draw():
    lcd.fillScreen(BG)
    header()
    d = data or {}
    card(38, 86, "Session (5h)", d.get("session"))
    card(130, 86, "Weekly (all models)", d.get("weekly"))
    footer()


def set_screen(on):
    """BtnB blanks the display; polling keeps running in the background."""
    global screen_on
    screen_on = on
    try:  # not every UIFlow2 build exposes sleep()/wakeup()
        lcd.wakeup() if on else lcd.sleep()
    except Exception:
        pass
    lcd.setBrightness(bright_levels[bright_i] if on else 0)
    if on:
        draw()


def wifi_up():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected() and WIFI_SSID:
        wlan.connect(WIFI_SSID, WIFI_PASS)
    t0 = time.ticks_ms()
    while not wlan.isconnected() and time.ticks_diff(time.ticks_ms(), t0) < 15000:
        time.sleep_ms(200)
    return wlan.isconnected()


def apply(j):
    global data, err
    if j.get("ok"):
        data, err = j, ""
    else:
        err = j.get("err") or "bridge error"
        if j.get("session"):
            data = j


def load_host():
    try:
        with open(HOST_FILE) as f:
            return f.read().strip()
    except Exception:
        return ""


def save_host(h):
    try:
        with open(HOST_FILE, "w") as f:
            f.write(h)
    except Exception as e:
        print("save host error:", e)


host = load_host() or PC_HOST


def discover():
    """Broadcast on the LAN; the first bridge that answers becomes the host."""
    global host, err
    err = "finding PC..."
    if screen_on:
        header()
    ip, mask = network.WLAN(network.STA_IF).ifconfig()[:2]
    a = [int(x) for x in ip.split(".")]
    m = [int(x) for x in mask.split(".")]
    subnet = ".".join(str(a[i] | (255 ^ m[i])) for i in range(4))
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except Exception:
            pass  # not every build has SO_BROADCAST; ESP-IDF allows broadcast anyway
        s.settimeout(1)
        for _ in range(3):
            for target in (subnet, "255.255.255.255"):
                try:
                    s.sendto(DISCOVER, (target, PORT))
                except OSError:
                    pass
            try:
                msg, addr = s.recvfrom(64)
            except OSError:
                continue  # timeout, try again
            if msg.startswith(b"CLAUDE_USAGE! "):
                host = "%s:%d" % (addr[0], int(msg.split()[1]))
                save_host(host)
                print("found bridge at", host)
                return True
    finally:
        s.close()
    return False


def get_usage():
    if not host:
        return False
    r = None
    try:
        url = "http://%s/usage" % host
        try:
            r = requests.get(url, timeout=5)
        except TypeError:  # this requests module has no timeout argument
            r = requests.get(url)
        apply(r.json())
        return True
    except Exception as e:
        print("fetch error:", host, e)
        return False
    finally:
        if r:
            try:
                r.close()
            except Exception:
                pass


def fetch():
    global err
    if not network.WLAN(network.STA_IF).isconnected() and not wifi_up():
        err = "no Wi-Fi"
        return
    if get_usage():
        return
    if discover() and get_usage():
        return
    err = "PC not found"


M5.begin()
lcd.setBrightness(bright_levels[bright_i])
draw()
wifi_up()
last = -POLL_MS

while True:
    M5.update()
    if BtnA.wasPressed():
        err = "refreshing..."
        if screen_on:
            header()
        last = -POLL_MS
    if BtnB.wasPressed():
        set_screen(not screen_on)
    if BtnC.wasPressed() and screen_on:
        bright_i = (bright_i + 1) % len(bright_levels)
        lcd.setBrightness(bright_levels[bright_i])
    if time.ticks_diff(time.ticks_ms(), last) >= POLL_MS:
        last = time.ticks_ms()
        fetch()
        if screen_on:
            draw()
    time.sleep_ms(30)
