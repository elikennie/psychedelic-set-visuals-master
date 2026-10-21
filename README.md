# psychedelic-set-visuals-master

DJ master out → **Swirl**, an iTunes-classic style visualizer (twin
oscilloscope lines twisting into spirals) in its own window, ready to go full
screen on a projector.

A launcher opens first. Pick the audio input, where the beat comes from, and
window or full screen. Check the live preview and level meters, then press
**Play**. The launcher stays open as a control panel while the visualizer
plays on the projector.

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
| Beat    | **Kick drum**: beats come from the bass in the audio. **Ableton Link**: beats come from rekordbox's tempo (see below). |
| Open in | Whether Play opens a window or goes straight to full screen. |

The header shows the input level (or NO SIGNAL) and the beat source. Under
the preview, **delay** is the measured part of the lag (see below). Your
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
2. Keep the launcher on the laptop screen to watch the levels.
3. To stop, press Space, or close the visualizer window.

If it runs on the DJ laptop and rekordbox ever crackles, lower the drawing size
with `--width 640` (the window still fills the screen, just softer), or run the
visualizer on a second laptop with the cable route.

## Keys (either window)

| Key | Does |
|-----|------|
| `Space` / `Enter` | play / stop |
| `f` | visualizer full screen on/off (`Esc` leaves it) |
| `h` | info line on the visualizer (beat, level, fps, delay) |
| `q` | quit |

## Options

- `--list` lists the audio inputs and their numbers.
- `--device "USB Audio"` picks an input by name (or part of it) or number.
- `--link`, `--full` set the launcher choices.
- `--play` starts playing straight away (e.g. from a startup script).
- `--width 1280` draws sharper but slower (default 960).

## Lag

From a sound happening to it showing on screen, these add up:

| Step | Typical |
|------|---------|
| Input buffer (the audio system holds sound before handing it over) | built-in mic ~37 ms; USB interface ~5–15 ms |
| Waiting for the next frame, then drawing it | one frame, ~25–30 ms at 35 fps |
| The screen showing the new frame (macOS compositor, projector) | one or two refreshes, ~15–35 ms; some projectors add more |

The **delay** readout adds up the first two. Already done to keep it low: the
input asks for the smallest safe buffer (`latency="low"`, 5 ms blocks), the
levels come from the newest 21 ms of sound, and the launcher only redraws every
third frame while playing. The Swirl trails fade over about a quarter of a
second: the newest line is drawn the moment sound arrives, but the trail
behind it can read as lag.

At a gig, the room helps: sound travels about 1 m every 3 ms, so 10 m from the
speakers the crowd hears the music about 30 ms late, which hides much of this.

## How it works

Every frame the previous picture is zoomed, turned and swirled a little,
faded and softened, then the newest sound is drawn on top (`visuals.py`): an
oscilloscope line across the middle and the same line turned half round.
Repeating the warp twists each waveform into spirals until it fades, the same
trick the old iTunes and MilkDrop visualizers use. Bass drives the zoom and
line height, mids the swirl, highs a ripple, and each beat gives a kick.
`DECAY` and `GAIN` at the top of `visuals.py` set trail length and brightness. The colour
drifts with the music and jumps every bar.
