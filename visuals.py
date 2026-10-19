"""
Feedback visuals, the way the old iTunes / MilkDrop visualizers work: every
frame the previous picture is zoomed, turned and swirled a little, faded and
softened, and then the newest sound is drawn on top. The repeated warp drags
each waveform into tunnels and spirals until it fades out.

The audio decides how hard everything moves: bass drives the zoom, mids the
turn, highs the ripple, and each beat gives a kick.

Styles can be stacked. Each one keeps its own picture with its own motion
(Tunnel flies outwards while Bloom falls inwards), and the pictures are
blended together like light, so overlaps glow brighter.
"""

import math

import cv2
import numpy as np

STYLES = ("Tunnel", "Swirl", "Bloom")

# How far each style's colours sit round the colour wheel when stacked, so
# the layers stay apart instead of all turning the same colour.
STACK_HUE = {"Tunnel": 0, "Swirl": 60, "Bloom": 180}


def hue_colour(hue, sat=0.85, val=1.0):
    """Hue in degrees -> BGR floats 0..1."""
    hsv = np.uint8([[[int(hue % 360) // 2, int(sat * 255), int(val * 255)]]])
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0].astype(np.float32) / 255


def bgr8(c):
    return tuple(int(v * 255) for v in c)


class Layer:
    """One style: its own feedback picture, warp and drawing."""

    def __init__(self, style, w, h):
        self.style = style
        self.buf = np.zeros((h, w, 3), np.float32)
        self.ink = np.zeros((h, w, 3), np.uint8)

    def clear(self):
        self.buf[:] = 0

    def motion(self, t, bass, mid, pulse, spin, f):
        """(zoom, turn, swirl, decay) for this frame."""
        if self.style == "Tunnel":
            return (1 + (0.010 + 0.035 * bass + 0.03 * pulse) * f,
                    (0.003 + 0.012 * mid) * spin * f, 0.0, 0.935)
        if self.style == "Swirl":
            return (1 + (0.004 + 0.02 * bass + 0.015 * pulse) * f,
                    0.006 * math.sin(t * 0.37) * f,
                    (0.015 + 0.04 * mid) * math.sin(t * 0.23) * spin * f, 0.955)
        # Bloom: zooms out, so everything falls back into the centre.
        return (1 - (0.008 + 0.025 * bass + 0.02 * pulse) * f,
                (0.002 + 0.006 * mid) * spin * f, 0.008 * math.sin(t * 0.3) * f, 0.90)


class Visualizer:
    def __init__(self, width=960, height=540, styles=("Tunnel",)):
        self.w, self.h = width, height
        self.layers = {s: Layer(s, width, height) for s in STYLES}
        self.styles = [s for s in STYLES if s in styles] or [STYLES[0]]
        self.t = 0.0
        self.hue = 200.0
        self.spin = 1.0   # turn direction; flips now and then on a bar

        # Every pixel's position around the centre, in units of half the
        # picture height, so the warp is round on any screen shape. The warp
        # is smooth, so it's worked out at half size and scaled up.
        self.cx, self.cy, self.unit = width / 2, height / 2, height / 2
        hw, hh = width // 2, height // 2
        ys, xs = np.mgrid[0:hh, 0:hw].astype(np.float32)
        dx = (xs * width / hw - self.cx) / self.unit
        dy = (ys * height / hh - self.cy) / self.unit
        self.r = np.hypot(dx, dy)
        self.theta = np.arctan2(dy, dx)

    def clear(self):
        for layer in self.layers.values():
            layer.clear()

    def set_styles(self, styles):
        styles = [s for s in STYLES if s in styles] or [STYLES[0]]
        for s in styles:
            if s not in self.styles:
                self.layers[s].clear()   # a style switched back on starts fresh
        self.styles = styles

    def step(self, audio, beat, dt):
        f = dt * 60   # 1 at 60 fps, so movement doesn't depend on frame rate
        self.t += dt
        bass, mid, high = (float(v) for v in audio.level)

        self.hue += dt * (8 + 30 * mid)
        if beat.new_bar:
            self.hue += 50
            if beat.count % 16 == 0:
                self.spin = -self.spin

        stacked = len(self.styles) > 1
        for s in self.styles:
            layer = self.layers[s]
            hue = self.hue + (STACK_HUE[s] if stacked else 0)
            self.warp(layer, bass, mid, high, beat.pulse, f)
            self.draw(layer, audio, beat, bass, beat.pulse, hue)
        return self.frame()

    # ----- the feedback warp --------------------------------------------

    def warp(self, layer, bass, mid, high, pulse, f):
        t = self.t
        zoom, turn, swirl, decay = layer.motion(t, bass, mid, pulse, self.spin, f)

        r_src = self.r / zoom
        # Highs add a fine ripple that travels outwards.
        if high > 0.05:
            r_src = r_src * (1 + 0.006 * high * np.sin(self.r * 14 - t * 6))
        th_src = self.theta - turn
        if swirl:
            th_src = th_src - swirl * self.r
        size = (self.w, self.h)
        map_x = cv2.resize((self.cx + r_src * np.cos(th_src) * self.unit).astype(np.float32), size)
        map_y = cv2.resize((self.cy + r_src * np.sin(th_src) * self.unit).astype(np.float32), size)

        buf = cv2.remap(layer.buf, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        buf = cv2.GaussianBlur(buf, (3, 3), 0.7)
        # Fade, with blue lasting a touch longer, so old trails cool as they go.
        k = decay ** f
        layer.buf = cv2.transform(buf, np.diag([k ** 0.85, k, k ** 1.1]).astype(np.float32))

    # ----- what gets drawn on top ---------------------------------------

    def draw(self, layer, audio, beat, bass, pulse, hue):
        ink = layer.ink
        ink[:] = 0
        u, cx, cy = self.unit, self.cx, self.cy
        colour = hue_colour(hue)
        accent = hue_colour(hue + 150)
        wave = audio.wave[::8]  # 128 points is plenty for a line
        n = len(wave)

        if layer.style == "Tunnel":
            # Waveform bent into a ring that swells with the bass.
            radius = 0.28 + 0.12 * bass + 0.08 * pulse
            ang = np.linspace(0, 2 * np.pi, n, endpoint=False) + self.t * 0.4 * self.spin
            rr = radius + wave * 0.10
            pts = np.stack([cx + rr * np.cos(ang) * u, cy + rr * np.sin(ang) * u], 1)
            self.line(ink, pts, colour, closed=True, width=2)
            if beat.new_beat:
                k = 12
                a = np.linspace(0, 2 * np.pi, k, endpoint=False) + self.t
                for x, y in zip(cx + 0.55 * np.cos(a) * u, cy + 0.55 * np.sin(a) * u):
                    cv2.circle(ink, (int(x), int(y)), 4, bgr8(accent), -1, cv2.LINE_AA)
            gain = 1.0

        elif layer.style == "Swirl":
            # Oscilloscope across the middle, and the same line turned half round.
            xs = np.linspace(-1, 1, n) * (self.w / 2) * 0.9
            ys = wave * u * (0.25 + 0.25 * bass)
            a = self.t * 0.2 * self.spin
            for turn, c in ((a, colour), (a + math.pi, accent)):
                ca, sa = math.cos(turn), math.sin(turn)
                pts = np.stack([cx + xs * ca - ys * sa, cy + xs * sa + ys * ca], 1)
                self.line(ink, pts, c, width=2)
            if pulse > 0.6:
                cv2.circle(ink, (int(cx), int(cy)), int(u * 0.05 * pulse), bgr8(colour), -1, cv2.LINE_AA)
            gain = 0.45   # lines pile up near the centre, so each adds less

        else:  # Bloom: spectrum as spokes from the centre, mirrored
            bars = audio.spectrum
            k = len(bars)
            ang = np.concatenate([np.linspace(0, np.pi, k), np.linspace(np.pi, 2 * np.pi, k)[::-1]])
            ang = ang + self.t * 0.15 * self.spin - np.pi / 2
            lengths = np.concatenate([bars, bars])
            r0 = 0.06 + 0.05 * pulse
            for i, (a, length) in enumerate(zip(ang, lengths)):
                if length < 0.05:
                    continue
                c = hue_colour(hue + 120 * (i % k) / k)
                r1 = r0 + 0.65 * length
                p0 = (int(cx + r0 * math.cos(a) * u), int(cy + r0 * math.sin(a) * u))
                p1 = (int(cx + r1 * math.cos(a) * u), int(cy + r1 * math.sin(a) * u))
                cv2.line(ink, p0, p1, bgr8(c * (0.4 + 0.6 * length)), 2, cv2.LINE_AA)
                cv2.circle(ink, p1, 3, bgr8(c), -1, cv2.LINE_AA)
            gain = 0.55   # everything falls back into the centre and piles up

        # Added rather than pasted, so overlaps glow towards white.
        cv2.scaleAdd(ink.astype(np.float32), gain / 255, layer.buf, layer.buf)
        np.minimum(layer.buf, 1.0, out=layer.buf)

    @staticmethod
    def line(ink, pts, colour, closed=False, width=2):
        pts = np.round(pts).astype(np.int32).reshape(-1, 1, 2)
        # Soft wide stroke underneath, sharp bright one on top.
        cv2.polylines(ink, [pts], closed, bgr8(colour * 0.35), width * 4, cv2.LINE_AA)
        cv2.polylines(ink, [pts], closed, bgr8(np.minimum(colour * 1.2, 1)), width, cv2.LINE_AA)

    def frame(self):
        # Blend the layers like light: 1 - (1 - a)(1 - b). Bright adds up, black adds nothing.
        out = None
        for s in self.styles:
            buf = self.layers[s].buf
            out = buf.copy() if out is None else out + buf - out * buf
        return (np.clip(out, 0, 1) * 255).astype(np.uint8)
