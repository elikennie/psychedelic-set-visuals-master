# master-viz

DJ master out → an iTunes-classic style visualizer (tunnels, swirls, spectrum
blooms) in its own window, ready to go full screen on a projector.

A launcher opens first. Pick the audio input, the style, where the beat comes
from, and window or full screen. Check the live preview and level meters, then
press **Play**. The launcher stays open as a control panel, so you can switch
styles mid-set while the visualizer plays on the projector.

## Setup

Needs Python 3.10+ (python.org). Run these from this folder.

### macOS
```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python viz.py
```
First run: allow microphone access for your terminal app
(System Settings → Privacy & Security → Microphone), then run again. macOS
asks for this for any audio input, including an audio interface's line in.

### Windows
```
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python viz.py
```
If no sound comes in: Settings → Privacy & security → Microphone →
allow desktop apps to access your microphone.

## Getting the master into the computer

The visualizer only listens. If it crashes, the music keeps playing.

- **Best: a cable.** Run the controller's or mixer's **booth out** or
  **rec out** into a USB audio interface (any cheap 2-in interface works) and
  pick that interface under **Input**. This works on macOS and Windows, with
  rekordbox or FL Studio, and shows exactly what the crowd hears.
- **macOS, no cable:** install [BlackHole 2ch](https://existential.audio/blackhole/),
  then send the audio to it: in rekordbox (Preferences → Audio) or FL Studio
  (Options → Audio settings) pick an output that includes BlackHole, or set up
  a Multi-Output Device in Audio MIDI Setup. Then pick **BlackHole 2ch** here.
- **Windows, no cable:** rekordbox usually drives DJ controllers through ASIO,
  which bypasses Windows' sound system, so nothing here can hear it. Use the
  cable route, or the controller's own record input if its driver has one.

The first two channels of the input are used. Levels set themselves: a quiet
booth out and a hot rec out both fill the meters after a few seconds.

## Launcher

| Section | Does |
|---------|------|
| Input   | Which audio input to listen to. **Refresh list** after plugging something in. |
| Style   | **Tunnel**: waveform ring flying towards you. **Swirl**: twin oscilloscope lines twisting into spirals. **Bloom**: spectrum spokes collapsing into the centre. |
| Beat    | **Kick drum**: beats come from the bass in the audio. **Ableton Link**: beats come from rekordbox's tempo (see below). |
| Open in | Whether Play opens a window or goes straight to full screen. |

The header shows the input level (or NO SIGNAL) and the beat source. Your
choices are saved in `settings.json` and come back next time.

### Ableton Link (rekordbox)

Detecting kicks from audio wobbles during long blends and breakdowns. With
Link, every pulse lands exactly on rekordbox's beat grid:

1. In rekordbox (PERFORMANCE mode), turn on **LINK**.
2. Pick **Ableton Link** under Beat. The header shows the peers and BPM.

Both programs need to be on the same computer or the same network. With no
Link peers it falls back to the kick drum. When DJing from FL Studio, use
Kick drum unless the header shows FL as a Link peer.

## Playing out

1. Press Play, drag the visualizer window onto the projector or second
   screen, then press `f` (or double-click it) for full screen.
2. Keep the launcher on the laptop screen to switch styles.
3. To stop, press Space, or close the visualizer window.

If it runs on the DJ laptop and rekordbox ever crackles, lower the drawing size
with `--width 640` (the window still fills the screen, just softer), or run the
visualizer on a second laptop with the cable route.

## Keys (either window)

| Key | Does |
|-----|------|
| `Space` / `Enter` | play / stop |
| `1` `2` `3` | style: Tunnel / Swirl / Bloom |
| `f` | visualizer full screen on/off (`Esc` leaves it) |
| `h` | info line on the visualizer (style, beat, level, fps) |
| `q` | quit |

## Options

- `--list` lists the audio inputs and their numbers.
- `--device "USB Audio"` picks an input by name (or part of it) or number.
- `--style Bloom`, `--link`, `--full` set the launcher choices.
- `--play` starts playing straight away (e.g. from a startup script).
- `--width 1280` draws sharper but slower (default 960).

## How it works

Every frame the previous picture is zoomed, turned and swirled a little,
faded and softened, then the newest sound is drawn on top (`visuals.py`).
Repeating the warp drags each waveform into tunnels and spirals until it fades,
the same trick the old iTunes and MilkDrop visualizers use. Bass drives the
zoom, mids the turn, highs a ripple, and each beat gives a kick. The colour
drifts with the music and jumps every bar.
