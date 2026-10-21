"""
Master visualizer: listens to the DJ master (through an audio input) and
plays Swirl, an iTunes-classic style feedback visualizer, in its own window.

The launcher opens first: pick the input, beat source and window or full screen, check the preview and meters, then press Play. The launcher
stays open as a control panel; drag the visualizer window to the projector.

Run:   python viz.py
       python viz.py --device "USB Audio CODEC" --link --play

Keys (either window):
       space / enter   play / stop
       f               visualizer full screen on/off (Esc leaves it)
       h               info line on the visualizer on/off
       q               quit
Double-click the visualizer to switch full screen too.
"""

import argparse
import json
import os
import sys
import time

import cv2
import sounddevice as sd

import ui as page
from audio import AudioInput, BeatClock, LinkClock, default_input, input_devices
from ui import Launcher
from visuals import Visualizer

LAUNCHER = "Master"
VISUALIZER = "Master Visualizer"
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")


def load_settings():
    settings = {"device": None, "link": False, "fullscreen": False}
    try:
        with open(SETTINGS_FILE) as f:
            saved = json.load(f)
        settings.update({k: saved[k] for k in settings if k in saved})
    except (OSError, ValueError):
        pass
    return settings


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
    except OSError:
        pass


def pick_device(devices, wanted):
    """Device index for a saved name, a --device name/number, or the default input."""
    if wanted is not None:
        for i, name in devices:
            if str(wanted) == str(i) or str(wanted).lower() == name.lower():
                return i, name
        for i, name in devices:
            if str(wanted).lower() in name.lower():
                return i, name
    default = default_input()
    for i, name in devices:
        if i == default:
            return i, name
    return devices[0] if devices else (None, None)


def window_open(name):
    try:
        return cv2.getWindowProperty(name, cv2.WND_PROP_VISIBLE) >= 1
    except cv2.error:
        return False


def draw_info(img, beat, audio, fps):
    delay = audio.latency * 1000 + 1000 / max(fps, 1)
    text = f"{beat.status()}  {audio.db:.0f} dB  {fps:.0f} fps  delay ~{delay:.0f} ms"
    cv2.putText(img, text, (14, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, text, (14, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)


class App:
    def __init__(self, args):
        self.settings = load_settings()
        if args.link:
            self.settings["link"] = True
        if args.full:
            self.settings["fullscreen"] = True

        self.audio = AudioInput()
        self.link = LinkClock()
        self.beat = BeatClock(self.link)
        self.beat.set_use_link(self.settings["link"])
        self.viz = Visualizer(args.width, args.width * 9 // 16)
        self.launcher = Launcher(self.settings)

        self.devices = input_devices()
        self.launcher.set_devices(self.devices)
        index, name = pick_device(self.devices, args.device or self.settings["device"])
        self.select_device(index, name)

        self.playing = False
        self.viz_shown = False
        self.fullscreen = False
        self.show_info = False

    def select_device(self, index, name):
        self.settings["device"] = name
        if index is None:
            self.audio.close()
            self.audio.error = "No audio inputs found"
            return
        self.audio.open(index)

    def refresh_devices(self):
        # PortAudio only scans for devices when it starts, so restart it.
        self.audio.close()
        sd._terminate()
        sd._initialize()
        self.devices = input_devices()
        self.launcher.set_devices(self.devices)
        index, name = pick_device(self.devices, self.settings["device"])
        self.select_device(index, name)

    # ----- the visualizer window ---------------------------------------

    def play(self):
        self.playing = True
        self.viz_shown = False   # macOS reports a new window as hidden for its first frames
        self.viz.clear()
        cv2.namedWindow(VISUALIZER, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        cv2.resizeWindow(VISUALIZER, 1280, 720)
        cv2.setMouseCallback(VISUALIZER, self.on_viz_mouse)
        self.set_fullscreen(self.settings["fullscreen"])

    def stop(self):
        self.playing = False
        self.fullscreen = False
        if window_open(VISUALIZER):
            cv2.destroyWindow(VISUALIZER)
            cv2.waitKey(1)

    def set_fullscreen(self, on):
        if not self.playing:
            return
        self.fullscreen = on
        cv2.setWindowProperty(VISUALIZER, cv2.WND_PROP_FULLSCREEN,
                              cv2.WINDOW_FULLSCREEN if on else cv2.WINDOW_NORMAL)
        if not on:
            cv2.resizeWindow(VISUALIZER, 1280, 720)

    def on_viz_mouse(self, event, x, y, flags, _param):
        if event == cv2.EVENT_LBUTTONDBLCLK:
            self.launcher.actions.append(("toggle_full", None))

    # ----- controls ------------------------------------------------------

    def handle(self, action, value):
        s = self.settings
        if action == "play":
            self.stop() if self.playing else self.play()
        elif action == "device":
            index = next((i for i, n in self.devices if n == value), None)
            self.select_device(index, value)
        elif action == "refresh":
            self.refresh_devices()
        elif action == "link":
            if value and not self.link.available:
                return
            s["link"] = value
            self.beat.set_use_link(value)
        elif action == "fullscreen":
            s["fullscreen"] = value
        elif action == "toggle_full":
            self.set_fullscreen(not self.fullscreen)
        save_settings(s)

    def handle_key(self, key):
        """False when it's time to quit."""
        if key == ord("q"):
            return False
        if key in (ord(" "), 13, 10):
            self.handle("play", None)
        elif key == ord("f"):
            self.handle("toggle_full", None)
        elif key == 27 and self.fullscreen:
            self.set_fullscreen(False)
        elif key == ord("h"):
            self.show_info = not self.show_info
        return True

    def run(self):
        cv2.namedWindow(LAUNCHER, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        cv2.resizeWindow(LAUNCHER, page.W, page.H)
        cv2.setMouseCallback(LAUNCHER, self.launcher.on_mouse)
        fps, last = 0.0, time.perf_counter()
        count = 0

        while True:
            count += 1
            now = time.perf_counter()
            dt, last = min(now - last, 0.1), now
            fps = 0.9 * fps + 0.1 * (1 / max(dt, 1e-6))

            self.audio.analyse(dt)
            self.beat.update(self.audio, dt)
            frame = self.viz.step(self.audio, self.beat, dt)

            # The launcher's text is slow to draw, so while the visualizer plays
            # it only refreshes every third frame.
            if not self.playing or count % 3 == 0 or self.launcher.actions:
                cv2.imshow(LAUNCHER, self.launcher.render(frame, self.audio, self.beat, self.playing,
                                                          self.link.error, 1000 / max(fps, 1)))
            if self.playing:
                out = frame.copy() if self.show_info else frame
                if self.show_info:
                    draw_info(out, self.beat, self.audio, fps)
                cv2.imshow(VISUALIZER, out)

            key = cv2.waitKey(1) & 0xFF
            if key != 255 and not self.handle_key(key):
                break
            for action, value in self.launcher.take_actions():
                self.handle(action, value)

            # Closing the visualizer stops it; closing the launcher quits.
            if self.playing:
                if window_open(VISUALIZER):
                    self.viz_shown = True
                elif self.viz_shown:
                    self.stop()
            if not window_open(LAUNCHER):
                break

        self.audio.close()
        self.link.set_enabled(False)
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description="iTunes-classic style visualizer for the DJ master out.")
    parser.add_argument("--device", help="audio input name (or part of it) or number")
    parser.add_argument("--link", action="store_true", help="follow Ableton Link for the beat")
    parser.add_argument("--full", action="store_true", help="open the visualizer full screen")
    parser.add_argument("--play", action="store_true", help="start playing straight away")
    parser.add_argument("--width", type=int, default=960,
                        help="width the visuals are drawn at (default 960; the window scales it)")
    parser.add_argument("--list", action="store_true", help="list audio inputs and exit")
    args = parser.parse_args()

    if args.list:
        for i, name in input_devices():
            print(f"{i:3d}  {name}")
        return

    app = App(args)
    if args.play:
        app.play()
    app.run()


if __name__ == "__main__":
    main()
