"""
Launcher page, in the same editorial style as motion-chimes: white page,
centred wordmark, small uppercase type, thin rules. Pick the input, beat
source and where the visualizer opens, check the live preview and the level
meters, then press Play. It stays open as a control panel while the
visualizer plays.
"""

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Page layout (pixels).
W, H = 1280, 760
MARGIN = 32
SIDE_W = 220
GAP = 36
VIEW_X = MARGIN + SIDE_W + GAP
VIEW_W = W - VIEW_X - MARGIN
VIEW_H = VIEW_W * 9 // 16
VIEW_Y = 104
NAV_BASELINE = 58
MAX_DEVICES = 8
ROW = 20

# Colours are BGR (OpenCV order); the greys are the same either way.
INK = (17, 17, 17)
GREY = (125, 125, 125)
RULE = (222, 222, 222)
PAPER = (255, 255, 255)
LIVE = (60, 60, 230)   # red dot shown while playing

# First font found wins: macOS Helvetica Neue, Windows Arial, Linux DejaVu.
FONT_FILES = {
    "regular": [
        ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
        ("/System/Library/Fonts/Helvetica.ttc", 0),
        (r"C:\Windows\Fonts\arial.ttf", 0),
        ("DejaVuSans.ttf", 0),
    ],
    "bold": [
        ("/System/Library/Fonts/HelveticaNeue.ttc", 1),
        ("/System/Library/Fonts/Helvetica.ttc", 1),
        (r"C:\Windows\Fonts\arialbd.ttf", 0),
        ("DejaVuSans-Bold.ttf", 0),
    ],
}

_font_cache = {}


def load_font(weight, size):
    key = (weight, size)
    if key not in _font_cache:
        for path, index in FONT_FILES[weight]:
            try:
                _font_cache[key] = ImageFont.truetype(path, size, index=index)
                break
            except OSError:
                continue
        else:
            _font_cache[key] = ImageFont.load_default(size=size)
    return _font_cache[key]


def in_rect(x, y, rect):
    x0, y0, x1, y1 = rect
    return x0 <= x <= x1 and y0 <= y <= y1


def shorten(text, font, width):
    if font.getlength(text) <= width:
        return text
    while text and font.getlength(text + "…") > width:
        text = text[:-1]
    return text + "…"


class Link:
    """A clickable word, underlined when selected or hovered."""

    def __init__(self, text, action, value, x, baseline, font):
        self.action, self.value, self.x, self.baseline, self.font = action, value, x, baseline, font
        self.text = shorten(text, font, SIDE_W)
        self.width = int(font.getlength(self.text))

    def hit(self, x, y):
        return (self.x - 6 <= x <= self.x + max(self.width, 40) + 6
                and self.baseline - self.font.size - 4 <= y <= self.baseline + 5)


class Launcher:
    def __init__(self, settings):
        self.fonts = {
            "word": load_font("bold", 32),
            "nav": load_font("regular", 13),
            "head": load_font("bold", 13),
            "body": load_font("regular", 13),
            "play": load_font("bold", 15),
        }
        self.settings = settings   # dict: device, link, fullscreen
        self.devices = []
        self.links = []
        self.mouse = (-1, -1)
        self.actions = []
        self.texts = []
        self.play_rect = (W - MARGIN - 200, VIEW_Y + VIEW_H + 22, W - MARGIN, VIEW_Y + VIEW_H + 74)

    def set_devices(self, devices):
        self.devices = devices
        self.layout()

    def layout(self):
        """Build the clickable lists down the left column."""
        body = self.fonts["body"]
        self.links = []
        y = VIEW_Y + 10
        self.heads = []

        def section(title, rows):
            nonlocal y
            self.heads.append((title, y))
            y += 28
            for text, action, value in rows:
                self.links.append(Link(text, action, value, MARGIN, y, body))
                y += ROW
            y += 30

        rows = [(name, "device", name) for _, name in self.devices[:MAX_DEVICES]]
        if not rows:
            rows = [("No inputs found", "none", None)]
        rows.append(("Refresh list", "refresh", None))
        section("INPUT", rows)
        section("BEAT", [("Kick drum", "link", False), ("Ableton Link", "link", True)])
        section("OPEN IN", [("Window", "fullscreen", False), ("Full screen", "fullscreen", True)])

    # ----- input -------------------------------------------------------

    def on_mouse(self, event, x, y, flags, _param):
        self.mouse = (x, y)
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        if in_rect(x, y, self.play_rect):
            self.actions.append(("play", None))
            return
        for link in self.links:
            if link.hit(x, y):
                self.actions.append((link.action, link.value))
                return

    def take_actions(self):
        actions, self.actions = self.actions, []
        return actions

    def selected(self, link):
        s = self.settings
        if link.action == "device":
            return link.value == s["device"]
        if link.action in ("link", "fullscreen"):
            return link.value == s[link.action]
        return False

    # ----- drawing -----------------------------------------------------

    def text(self, xy, text, font="body", colour=INK, anchor="ls", spacing=0):
        if isinstance(font, str):
            font = self.fonts[font]
        self.texts.append((xy, text, font, colour, anchor, spacing))

    def underline(self, canvas, x, width, baseline, colour=INK, thickness=1):
        cv2.line(canvas, (x, baseline + 4), (x + width, baseline + 4), colour, thickness)

    def render(self, preview, audio, beat, playing, link_error, frame_ms=0.0):
        canvas = np.full((H, W, 3), PAPER, np.uint8)
        self.texts = []
        self.draw_header(audio, beat, playing)
        self.draw_lists(canvas, audio, link_error)
        self.draw_preview(canvas, preview, playing, audio, frame_ms)
        self.draw_meters(canvas, audio)
        self.draw_play(canvas, playing)
        return self.flush_text(canvas)

    def draw_header(self, audio, beat, playing):
        if audio.stream is None:
            signal = "NO INPUT"
        elif audio.silent:
            signal = "NO SIGNAL"
        else:
            signal = f"INPUT {audio.db:.0f} DB"
        self.text((MARGIN, NAV_BASELINE), signal, "nav")
        self.text((W // 2, NAV_BASELINE + 6), "MASTER", "word", anchor="ms", spacing=1)
        self.text((W - MARGIN, NAV_BASELINE), beat.status(), "nav", anchor="rs")

    def draw_lists(self, canvas, audio, link_error):
        for title, y in self.heads:
            self.text((MARGIN, y), title, "head")
        mx, my = self.mouse
        for link in self.links:
            colour = GREY if link.action in ("none", "refresh") else INK
            text = link.text
            if link.action == "link" and link.value and link_error:
                text, colour = f"Ableton Link ({link_error})", GREY
            self.text((link.x, link.baseline), text, "body", colour)
            if self.selected(link) or link.hit(mx, my) and link.action != "none":
                self.underline(canvas, link.x, link.width, link.baseline, colour)
        if audio.error:
            last = max(l.baseline for l in self.links if l.action in ("refresh", "none"))
            self.text((MARGIN, last + 18), shorten(audio.error, self.fonts["body"], SIDE_W),
                      "body", LIVE)

    def draw_preview(self, canvas, preview, playing, audio, frame_ms):
        x0, y0 = VIEW_X, VIEW_Y
        img = preview
        if img.shape[1] != VIEW_W or img.shape[0] != VIEW_H:
            img = cv2.resize(img, (VIEW_W, VIEW_H), interpolation=cv2.INTER_AREA)
        canvas[y0:y0 + VIEW_H, x0:x0 + VIEW_W] = img
        # Caption under the preview, like a plate in a catalogue.
        y = y0 + VIEW_H + 30
        self.text((x0, y), "MASTER", "body")
        caption = f"Swirl  ·  {self.settings['device'] or 'No input'}"
        self.text((x0, y + 20), shorten(caption, self.fonts["body"], 300), "body")
        state = "Playing" if playing else "Preview"
        # Delay from sound arriving to it reaching the screen that we can measure:
        # the input's own buffer plus one frame. The screen adds a frame or two more.
        delay = f"  ·  delay ~{audio.latency * 1000 + frame_ms:.0f} ms" if audio.stream else ""
        self.text((x0, y + 40), state + delay, "body", GREY)
        if playing:
            cv2.circle(canvas, (x0 + 12 + int(self.fonts["body"].getlength(state + delay)), y + 35),
                       4, LIVE, -1, cv2.LINE_AA)

    def draw_meters(self, canvas, audio):
        """Bass / mid / high bars between the caption and Play."""
        x = VIEW_X + 330
        bar_w = 150
        for i, (name, level) in enumerate(zip(("BASS", "MID", "HIGH"), audio.level)):
            y = VIEW_Y + VIEW_H + 30 + i * 20
            self.text((x, y), name, "body", GREY)
            bx = x + 50
            cv2.line(canvas, (bx, y - 5), (bx + bar_w, y - 5), RULE, 2)
            cv2.line(canvas, (bx, y - 5), (bx + int(bar_w * float(level)), y - 5), INK, 2)

    def draw_play(self, canvas, playing):
        x0, y0, x1, y1 = self.play_rect
        hover = in_rect(*self.mouse, self.play_rect)
        fill = (60, 60, 60) if hover else INK
        cv2.rectangle(canvas, (x0, y0), (x1, y1), fill, -1)
        cy = (y0 + y1) // 2
        label = "STOP" if playing else "PLAY"
        if playing:
            cv2.rectangle(canvas, (x0 + 26, cy - 7), (x0 + 40, cy + 7), PAPER, -1)
        else:
            tri = np.array([[x0 + 26, cy - 9], [x0 + 26, cy + 9], [x0 + 42, cy]], np.int32)
            cv2.fillPoly(canvas, [tri], PAPER, cv2.LINE_AA)
        self.text((x0 + 58, cy + 6), label, "play", PAPER, spacing=2)
        hint = "Space to stop" if playing else "Space to play"
        self.text((x1, y1 + 20), hint, "body", GREY, anchor="rs")

    def flush_text(self, canvas):
        img = Image.fromarray(canvas)
        draw = ImageDraw.Draw(img)
        for (x, y), text, font, colour, anchor, spacing in self.texts:
            if not spacing:
                draw.text((x, y), text, font=font, fill=colour, anchor=anchor)
                continue
            # Letter-spaced text, drawn one character at a time.
            total = sum(font.getlength(c) for c in text) + spacing * (len(text) - 1)
            cx = x - total / 2 if anchor[0] == "m" else x
            for c in text:
                draw.text((cx, y), c, font=font, fill=colour, anchor="l" + anchor[1])
                cx += font.getlength(c) + spacing
        return np.array(img)
