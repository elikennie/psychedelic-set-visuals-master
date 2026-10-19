"""
Feedback visuals, the way the old iTunes / MilkDrop visualizers work: every
frame the previous picture is zoomed, turned and swirled a little, faded and
softened, and then the newest sound is drawn on top. The repeated warp drags
each waveform into tunnels and spirals until it fades out.

The audio decides how hard everything moves: bass drives the zoom, mids the
turn, highs the ripple, and each beat gives a kick.
"""

import math

import cv2
import numpy as np

STYLES = ("Tunnel", "Swirl", "Bloom")


def hue_colour(hue, sat=0.85, val=1.0):
    """Hue in degrees -> BGR floats 0..1."""
    hsv = np.uint8([[[int(hue % 360) // 2, int(sat * 255), int(val * 255)]]])
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0].astype(np.float32) / 255


class Visualizer:
    def __init__(self, width=960, height=540, style="Tunnel"):
        self.w, self.h = width, height
        self.style = style
        self.buf = np.zeros((height, width, 3), np.float32)
        self.t = 0.0
        self.hue = 200.0
        self.spin = 1.0   # turn direction; flips now and then on a bar

        # Every pixel's position around the centre, in units of half the
        # picture height, so the warp is round on any screen shape.
        self.cx, self.cy, self.unit = width / 2, height / 2, height / 2
        ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
        dx, dy = (xs - self.cx) / self.unit, (ys - self.cy) / self.unit
        self.r = np.hypot(dx, dy)
        self.theta = np.arctan2(dy, dx)
        self.layer = np.zeros((height, width, 3), np.uint8)

    def clear(self):
        self.buf[:] = 0

    def set_style(self, style):
        if style != self.style:
            self.style = style

    def step(self, audio, beat, dt):
        f = dt * 60   # 1 at 60 fps, so movement doesn't depend on frame rate
        self.t += dt
        bass, mid, high = (float(v) for v in audio.level)
        pulse = beat.pulse

        self.hue += dt * (8 + 30 * mid)
        if beat.new_bar:
            self.hue += 50
            if beat.count % 16 == 0:
                self.spin = -self.spin

        self.warp(bass, mid, high, pulse, f)
        self.draw(audio, beat, bass, mid, high, pulse)
        return self.frame()

    # ----- the feedback warp --------------------------------------------

    def warp(self, bass, mid, high, pulse, f):
        t = self.t
        if self.style == "Tunnel":
            zoom = 1 + (0.010 + 0.035 * bass + 0.03 * pulse) * f
            turn = (0.003 + 0.012 * mid) * self.spin * f
            swirl = 0.0
            decay = 0.935
        elif self.style == "Swirl":
            zoom = 1 + (0.004 + 0.02 * bass + 0.015 * pulse) * f
            turn = 0.006 * math.sin(t * 0.37) * f
            swirl = (0.015 + 0.04 * mid) * math.sin(t * 0.23) * self.spin * f
            decay = 0.955
        else:  # Bloom: zooms out, so everything falls back into the centre
            zoom = 1 - (0.008 + 0.025 * bass + 0.02 * pulse) * f
            turn = (0.002 + 0.006 * mid) * self.spin * f
            swirl = 0.008 * math.sin(t * 0.3) * f
            decay = 0.90

        r_src = self.r / zoom
        # Highs add a fine ripple that travels outwards.
        if high > 0.05:
            r_src = r_src * (1 + 0.006 * high * np.sin(self.r * 14 - t * 6))
        th_src = self.theta - turn
        if swirl:
            th_src = th_src - swirl * self.r
        map_x = (self.cx + r_src * np.cos(th_src) * self.unit).astype(np.float32)
        map_y = (self.cy + r_src * np.sin(th_src) * self.unit).astype(np.float32)

        buf = cv2.remap(self.buf, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        buf = cv2.GaussianBlur(buf, (3, 3), 0.7)
        # Fade, with blue lasting a touch longer, so old trails cool as they go.
        k = decay ** f
        buf *= np.array([k ** 0.85, k, k ** 1.1], np.float32)
        self.buf = buf

    # ----- what gets drawn on top ---------------------------------------

    def draw(self, audio, beat, bass, mid, high, pulse):
        layer = self.layer
        layer[:] = 0
        u, cx, cy = self.unit, self.cx, self.cy
        colour = hue_colour(self.hue)
        accent = hue_colour(self.hue + 150)
        wave = audio.wave[::8]  # 128 points is plenty for a line
        n = len(wave)

        if self.style == "Tunnel":
            # Waveform bent into a ring that swells with the bass.
            radius = 0.28 + 0.12 * bass + 0.08 * pulse
            ang = np.linspace(0, 2 * np.pi, n, endpoint=False) + self.t * 0.4 * self.spin
            rr = radius + wave * 0.10
            pts = np.stack([cx + rr * np.cos(ang) * u, cy + rr * np.sin(ang) * u], 1)
            self.line(layer, pts, colour, closed=True, width=2)
            if beat.new_beat:
                k = 12
                a = np.linspace(0, 2 * np.pi, k, endpoint=False) + self.t
                for x, y in zip(cx + 0.55 * np.cos(a) * u, cy + 0.55 * np.sin(a) * u):
                    cv2.circle(layer, (int(x), int(y)), 4, self.bgr8(accent), -1, cv2.LINE_AA)

        elif self.style == "Swirl":
            # Oscilloscope across the middle, and the same line turned half round.
            xs = np.linspace(-1, 1, n) * (self.w / 2) * 0.9
            ys = wave * u * (0.25 + 0.25 * bass)
            a = self.t * 0.2 * self.spin
            for turn, c in ((a, colour), (a + math.pi, accent)):
                ca, sa = math.cos(turn), math.sin(turn)
                pts = np.stack([cx + xs * ca - ys * sa, cy + xs * sa + ys * ca], 1)
                self.line(layer, pts, c, width=2)
            if pulse > 0.6:
                cv2.circle(layer, (int(cx), int(cy)), int(u * 0.05 * pulse), self.bgr8(colour), -1, cv2.LINE_AA)

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
                c = hue_colour(self.hue + 120 * (i % k) / k)
                r1 = r0 + 0.65 * length
                p0 = (int(cx + r0 * math.cos(a) * u), int(cy + r0 * math.sin(a) * u))
                p1 = (int(cx + r1 * math.cos(a) * u), int(cy + r1 * math.sin(a) * u))
                cv2.line(layer, p0, p1, self.bgr8(c * (0.4 + 0.6 * length)), 2, cv2.LINE_AA)
                cv2.circle(layer, p1, 3, self.bgr8(c), -1, cv2.LINE_AA)

        # Added rather than pasted, so overlaps glow towards white. Swirl and
        # Bloom pile new lines onto old ones near the centre, so they add less.
        gain = {"Tunnel": 1.0, "Swirl": 0.45, "Bloom": 0.55}[self.style]
        self.buf += layer.astype(np.float32) * (gain / 255)
        np.minimum(self.buf, 1.0, out=self.buf)

    @staticmethod
    def bgr8(c):
        return tuple(int(v * 255) for v in c)

    def line(self, layer, pts, colour, closed=False, width=2):
        pts = np.round(pts).astype(np.int32).reshape(-1, 1, 2)
        # Soft wide stroke underneath, sharp bright one on top.
        cv2.polylines(layer, [pts], closed, self.bgr8(colour * 0.35), width * 4, cv2.LINE_AA)
        cv2.polylines(layer, [pts], closed, self.bgr8(np.minimum(colour * 1.2, 1)), width, cv2.LINE_AA)

    def frame(self):
        return (np.clip(self.buf, 0, 1) * 255).astype(np.uint8)
