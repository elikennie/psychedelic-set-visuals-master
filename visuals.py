"""
Swirl: a feedback visual, the way the old iTunes / MilkDrop visualizers work.
Every frame the previous picture is zoomed, turned and swirled a little,
faded and softened, and then the newest sound is drawn on top: an
oscilloscope line across the middle and the same line turned half round. The
repeated warp twists each waveform into spirals until it fades out.

The audio decides how hard everything moves: bass drives the zoom and the
line height, mids the swirl and colour speed, highs a ripple, and each beat
gives a kick.
"""

import math

import cv2
import numpy as np

DECAY = 0.955   # brightness kept per frame at 60 fps; lower = shorter trails
GAIN = 0.45     # how bright each new line is; lines pile up near the centre


def hue_colour(hue, sat=0.85, val=1.0):
    """Hue in degrees -> BGR floats 0..1."""
    hsv = np.uint8([[[int(hue % 360) // 2, int(sat * 255), int(val * 255)]]])
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0].astype(np.float32) / 255


def bgr8(c):
    return tuple(int(v * 255) for v in c)


class Visualizer:
    def __init__(self, width=960, height=540):
        self.w, self.h = width, height
        self.buf = np.zeros((height, width, 3), np.float32)
        self.ink = np.zeros((height, width, 3), np.uint8)
        self.t = 0.0
        self.hue = 200.0
        self.spin = 1.0   # turn direction; flips every 16 beats

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
        self.buf[:] = 0

    def step(self, audio, beat, dt):
        f = dt * 60   # 1 at 60 fps, so movement doesn't depend on frame rate
        self.t += dt
        bass, mid, high = (float(v) for v in audio.level)

        self.hue += dt * (8 + 30 * mid)
        if beat.new_bar:
            self.hue += 50
            if beat.count % 16 == 0:
                self.spin = -self.spin

        self.warp(bass, mid, high, beat.pulse, f)
        self.draw(audio, bass, beat.pulse)
        return (np.clip(self.buf, 0, 1) * 255).astype(np.uint8)

    def warp(self, bass, mid, high, pulse, f):
        t = self.t
        zoom = 1 + (0.004 + 0.02 * bass + 0.015 * pulse) * f
        turn = 0.006 * math.sin(t * 0.37) * f
        swirl = (0.015 + 0.04 * mid) * math.sin(t * 0.23) * self.spin * f

        r_src = self.r / zoom
        # Highs add a fine ripple that travels outwards.
        if high > 0.05:
            r_src = r_src * (1 + 0.006 * high * np.sin(self.r * 14 - t * 6))
        # The turn grows with distance from the centre, which is what makes spirals.
        th_src = self.theta - turn - swirl * self.r
        size = (self.w, self.h)
        map_x = cv2.resize((self.cx + r_src * np.cos(th_src) * self.unit).astype(np.float32), size)
        map_y = cv2.resize((self.cy + r_src * np.sin(th_src) * self.unit).astype(np.float32), size)

        buf = cv2.remap(self.buf, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        buf = cv2.GaussianBlur(buf, (3, 3), 0.7)
        # Fade, with blue lasting a touch longer, so old trails cool as they go.
        k = DECAY ** f
        self.buf = cv2.transform(buf, np.diag([k ** 0.85, k, k ** 1.1]).astype(np.float32))

    def draw(self, audio, bass, pulse):
        ink = self.ink
        ink[:] = 0
        u, cx, cy = self.unit, self.cx, self.cy
        colour = hue_colour(self.hue)
        accent = hue_colour(self.hue + 150)
        wave = audio.wave[::8]  # 128 points is plenty for a line
        n = len(wave)

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

        # Added rather than pasted, so overlaps glow towards white.
        cv2.scaleAdd(ink.astype(np.float32), GAIN / 255, self.buf, self.buf)
        np.minimum(self.buf, 1.0, out=self.buf)

    @staticmethod
    def line(ink, pts, colour, width=2):
        pts = np.round(pts).astype(np.int32).reshape(-1, 1, 2)
        # Soft wide stroke underneath, sharp bright one on top.
        cv2.polylines(ink, [pts], False, bgr8(colour * 0.35), width * 4, cv2.LINE_AA)
        cv2.polylines(ink, [pts], False, bgr8(np.minimum(colour * 1.2, 1)), width, cv2.LINE_AA)
