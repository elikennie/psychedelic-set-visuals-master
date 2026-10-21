"""
Listening side: reads an audio input (the mixer's booth/record out through an
audio interface, or a loopback device like BlackHole) and turns it into a few
smoothed numbers the visuals use every frame. Also the beat clock, which
follows Ableton Link when rekordbox is sharing it, or the kick drum otherwise.
"""

import math
import sys
import threading
import time

import numpy as np
import sounddevice as sd

RING = 16384       # samples kept from the input (about a third of a second)
# Samples per spectrum. Levels follow the sound averaged over this window, so a
# shorter one reacts sooner: 1024 is about 21 ms at 48 kHz, half the old 2048.
FFT_SIZE = 1024
WAVE_SIZE = 1024   # samples in the drawn waveform
BLOCK = 256        # samples per delivery from the input (about 5 ms)
BANDS = ((20, 150), (150, 2000), (2000, 10000))  # bass, mid, high (Hz)
SILENCE_RMS = 0.0005   # about -66 dBFS; quieter than this counts as no signal


def input_devices():
    """(index, name) for every input. Windows lists each device once per audio
    system (MME, DirectSound, WASAPI...), so only WASAPI ones are kept there."""
    keep_api = None
    if sys.platform.startswith("win"):
        for i, api in enumerate(sd.query_hostapis()):
            if "WASAPI" in api["name"]:
                keep_api = i
    devices = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] < 1:
            continue
        if keep_api is not None and d["hostapi"] != keep_api:
            continue
        devices.append((i, d["name"]))
    return devices


def default_input():
    try:
        return sd.default.device[0]
    except Exception:
        return None


class AudioInput:
    """One input stream plus the levels worked out from it."""

    def __init__(self):
        self.stream = None
        self.device = None
        self.error = ""
        self.latency = 0.0   # seconds the input itself holds sound before we see it
        self.rate = 48000
        self.lock = threading.Lock()
        self.ring = np.zeros(RING, np.float32)
        self.pos = 0
        self.window = np.hanning(FFT_SIZE).astype(np.float32)
        self.reset_levels()

    def reset_levels(self):
        self.level = np.zeros(3, np.float32)        # bass, mid, high: 0..1, smoothed
        self.band_peak = np.full(3, 1e-3, np.float32)
        self.wave = np.zeros(WAVE_SIZE, np.float32)  # -1..1, auto-gained
        self.amp_peak = 0.05
        self.bass_avg = 0.0
        self.last_kick = 0.0
        self.kick = False
        self.db = -120.0

    def open(self, device):
        self.close()
        self.device = device
        self.reset_levels()
        with self.lock:
            self.ring[:] = 0
        try:
            info = sd.query_devices(device)
            self.rate = int(info["default_samplerate"])
            channels = min(2, info["max_input_channels"])
            # "low" asks the audio system for its smallest safe buffer.
            self.stream = sd.InputStream(device=device, channels=channels, samplerate=self.rate,
                                         blocksize=BLOCK, latency="low", dtype="float32",
                                         callback=self._callback)
            self.stream.start()
            self.latency = float(self.stream.latency)
            self.error = ""
        except Exception as e:
            self.stream = None
            self.error = str(e).split("\n")[0]

    def close(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
        self.stream = None

    def _callback(self, indata, frames, time_info, status):
        mono = indata.mean(axis=1)
        n = min(len(mono), RING)
        with self.lock:
            idx = (np.arange(n) + self.pos) % RING
            self.ring[idx] = mono[-n:]
            self.pos = (self.pos + n) % RING

    def latest(self, n):
        with self.lock:
            idx = (np.arange(-n, 0) + self.pos) % RING
            return self.ring[idx]

    def analyse(self, dt):
        """Update levels, waveform and kick from the newest samples."""
        x = self.latest(FFT_SIZE)
        rms = float(np.sqrt(np.mean(x * x)))
        self.db = 20 * math.log10(max(rms, 1e-6))
        silent = rms < SILENCE_RMS

        spec = np.abs(np.fft.rfft(x * self.window))
        hz = self.rate / FFT_SIZE
        raw = np.array([spec[max(1, int(lo / hz)):int(hi / hz)].mean() for lo, hi in BANDS], np.float32)

        # Auto gain: each band is measured against its own recent peak, so a
        # quiet booth out and a hot record out both fill the range.
        self.band_peak = np.maximum(raw, self.band_peak * 0.5 ** (dt / 6))
        self.band_peak = np.maximum(self.band_peak, 1e-3)
        target = np.zeros(3, np.float32) if silent else np.clip(raw / self.band_peak, 0, 1) ** 1.5
        # Rise fast, fall slowly, so hits punch and then ease off.
        rise = 1 - 0.5 ** (dt / 0.02)
        fall = 1 - 0.5 ** (dt / 0.18)
        self.level += (target - self.level) * np.where(target > self.level, rise, fall)

        wave = x[-WAVE_SIZE:]
        self.amp_peak = max(float(np.abs(wave).max()), self.amp_peak * 0.5 ** (dt / 3), 0.02)
        self.wave = np.zeros(WAVE_SIZE, np.float32) if silent else np.clip(wave / self.amp_peak, -1, 1)

        # Kick: bass jumps well above its recent average.
        now = time.monotonic()
        self.kick = (not silent and raw[0] > self.bass_avg * 1.45
                     and raw[0] > self.band_peak[0] * 0.35 and now - self.last_kick > 0.28)
        if self.kick:
            self.last_kick = now
        self.bass_avg += (raw[0] - self.bass_avg) * (1 - 0.5 ** (dt / 0.4))

    @property
    def silent(self):
        return self.db < 20 * math.log10(SILENCE_RMS)


class LinkClock:
    """Ableton Link session (rekordbox shares its tempo and beat this way)."""

    def __init__(self):
        try:
            import link
            self.link = link.Link(120.0)
            self.error = ""
        except Exception:
            self.link = None
            self.error = "not installed"

    @property
    def available(self):
        return self.link is not None

    def set_enabled(self, on):
        if self.link is not None:
            self.link.enabled = on

    def read(self):
        """(beat, tempo, peers). Beats count up continuously; 4 beats to a bar."""
        state = self.link.captureSessionState()
        beat = state.beatAtTime(self.link.clock().micros(), 4)
        return beat, state.tempo(), self.link.numPeers()


class BeatClock:
    """Beat pulses from Link when it has peers, otherwise from the kick drum."""

    def __init__(self, link):
        self.link = link
        self.use_link = False
        self.count = 0
        self.pulse = 0.0
        self.new_beat = False
        self.new_bar = False
        self.source = "KICK"
        self.tempo = 0.0
        self.peers = 0
        self._last_link_beat = None

    def set_use_link(self, on):
        self.use_link = on and self.link.available
        self.link.set_enabled(self.use_link)
        self._last_link_beat = None

    def update(self, audio, dt):
        self.new_beat = False
        if self.use_link:
            beat, self.tempo, self.peers = self.link.read()
            if self.peers > 0:
                self.source = "LINK"
                whole = math.floor(beat)
                if self._last_link_beat is not None and whole != self._last_link_beat:
                    self.new_beat = True
                    self.count = whole
                self._last_link_beat = whole
            else:
                self.source = "KICK"
        else:
            self.source = "KICK"
        if self.source == "KICK" and audio.kick:
            self.new_beat = True
            self.count += 1
        self.new_bar = self.new_beat and self.count % 4 == 0
        self.pulse = 1.0 if self.new_beat else self.pulse * 0.5 ** (dt / 0.09)

    def status(self):
        if not self.use_link:
            return "BEAT: KICK DRUM"
        if self.peers == 0:
            return "LINK: NO PEERS (USING KICK)"
        noun = "PEER" if self.peers == 1 else "PEERS"
        return f"LINK: {self.peers} {noun} · {self.tempo:.1f} BPM"
