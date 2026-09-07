# ParrotRelay

A transparent launch proxy for [TeknoParrot](https://github.com/teknogods/TeknoParrotUI), built for use with **HyperSpin 2 / HyperHQ**.

It sits between HyperHQ and `TeknoParrotUi.exe`, forwards the command line unchanged, and takes care of everything that makes a TeknoParrot game look unpolished on a cabinet: the loading screen, the focus, and the cleanup afterwards.

![ParrotRelay loading screen](screenshot.png)

## Why

TeknoParrot games launched through HyperHQ sometimes lose their exclusive fullscreen mode shortly after starting: `TeknoParrotUi.exe` brings its own "Game is running" window back to the foreground itself, while the actual game keeps running behind it. You end up looking at TP's window instead of the game, and clicking back on it no longer restores fullscreen properly.

ParrotRelay fixes that without touching TeknoParrot itself.

## What it does

**A fullscreen loading screen** with the real game name (read from TeknoParrot's profile XML), a game-specific background image, and a progress bar. It closes the moment the real game window appears.

**A progress bar that learns each game.** Every launch stores how long the game took from start until its window appeared, in the game's config as `measured_load_ms`. The next launch predicts from it and then stores `(new time + stored time) / 2`, so the estimate settles on a realistic value within a few launches and follows a changed machine on its own.

Stored load time plus any extra delay is the expected total; one percent of it is one step of the bar, which simply follows the clock. Two things the clock cannot know are handled on top: while the game window has not appeared the bar stops at 99% instead of claiming to be done, and once the window is there the remaining time is known exactly, so the bar runs up to 100% and arrives precisely when the loading screen closes. A game with no measured time yet runs indeterminate rather than showing a made-up percentage.

**Hides TeknoParrot's own windows** ("Game is running") as soon as they appear, before they can take the foreground. This is the actual fullscreen fix — refocusing after the fact is already too late.

**Keeps focus on the game window** as a safety net, in case something else briefly steals the foreground.

**Closes a leftover TeknoParrot** before starting a new game. A `TeknoParrotUi.exe` still running from an earlier launch keeps its profile locked, steals the foreground, or stops the new one from starting at all.

**ESC cancels a launch.** While the loading screen is up, ESC ends TeknoParrot and every process it started, instead of leaving a half-started game behind.

**Stays alive until the game itself closes** — not just until TeknoParrot's launcher stub exits, which it does by design shortly after starting the game. Otherwise HyperHQ would report "game closed" while the game is still running.

**A settings window** for all of it, so nothing has to be configured by hand.

## Installation

1. Open [Releases](../../releases) and download the zip.
2. Unpack it into the TeknoParrot folder, so that `TeknoParrotUi.exe` and the `ParrotRelay` folder sit side by side.
3. In HyperSpin 2, edit the TeknoParrot platform:
   - **Platform Path:** `D:\ROM\TeknoParrot\ParrotRelay\ParrotRelay.exe`
   - **Command Line:** leave unchanged, e.g. `--startMinimized --profile=%rom.filename%.xml`

No admin rights setup required. The **[Microsoft Visual C++ 2015-2022 Redistributable (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe)** has to be installed — see [Requirements](#requirements) for why.

Double-click `ParrotRelay.exe` once afterwards: the settings window opens and its status line tells you whether TeknoParrot and your games were found.

## Settings window

Start `ParrotRelay.exe` **without arguments** — double-click it instead of letting HyperSpin call it — and it opens the settings window instead of launching anything.

![ParrotRelay settings window](settings-window.png)

- every TeknoParrot game is listed, with a search box; the *Configured* column shows how many values a game has of its own
- **Global defaults** (the first entry) apply to every game; a game only stores what actually differs from them, so changing a default still reaches every game that never overrode it
- **Pin all values** writes every value as an explicit line for one game, so it keeps them whatever the defaults do later; **Use global defaults** is the opposite and drops everything stored for that game
- **Apply to all games** writes one set of values to every game at once, for cabinet-wide settings
- **Preview loading screen** shows the splash exactly as it will look at launch — the quickest way to check a background image
- **Open ParrotRelay folder** and **Open log** for everything else

Everything the window writes is a plain text file you can also edit by hand.

| Setting | What it does |
|---|---|
| Show loading screen | Off = no splash for this game; the window handling keeps working |
| Keep loading screen up for (ms) | Extra time after the game window appeared, for games that show their window early but keep loading |
| Give up after (ms) | Safety net: closes the splash if no game window ever appears (`0` = wait forever) |
| Background image | Overrides the automatic search in `LoadingBG\` and `Icons\` |
| ESC cancels the launch | Turn off if ESC is wired to a cabinet button players can reach |
| Close a running TeknoParrot first | Ends any leftover `TeknoParrotUi.exe` before starting the new one |
| Keep game window focused | The continuous refocus safety net |
| Hide TeknoParrot windows | The actual fullscreen fix — only turn off for troubleshooting |

## Background images

Create a `LoadingBG` folder in the TeknoParrot folder:

```
D:\ROM\TeknoParrot\LoadingBG\BBCF.png
```

The filename (without extension) must match the profile name from `--profile=<name>.xml`. Supported: `.png` and `.gif` natively, plus `.jpg`/`.jpeg`/`.bmp`/`.webp` when [Pillow](https://pypi.org/project/Pillow/) is available.

If no custom image is found, ParrotRelay falls back to TeknoParrot's own icon (`Icons\<profile>.png`), which is what the screenshot above shows. Without either, the splash stays black.

## Loading screen delay from HyperSpin

Besides the settings window, the delay can be set per launch straight from the command line, in milliseconds:

```
--startMinimized --profile=%rom.filename%.xml --relay-delay=4000
```

`--relaydelay=` and `--splash-delay=` are accepted as well. The switch is consumed by ParrotRelay and never forwarded to TeknoParrot.

Precedence: command line &rarr; game config &rarr; global defaults &rarr; built-in default (`0`). Values are capped at 60000 ms.

## Folder layout and config files

ParrotRelay lives in its own folder inside the TeknoParrot folder:

```
D:\ROM\TeknoParrot\ParrotRelay\ParrotRelay.exe
D:\ROM\TeknoParrot\ParrotRelay\RelayData\             <- runtime files of the exe
D:\ROM\TeknoParrot\ParrotRelay\GameConfigs\BBCF.cfg   <- one per game
D:\ROM\TeknoParrot\ParrotRelay\ParrotRelay.cfg        <- global defaults
D:\ROM\TeknoParrot\ParrotRelay\parrot_relay_log.txt
```

`RelayData` holds everything that belongs to the exe — DLLs and the like — and never needs to be opened. What is left is yours: the configs and the log.

An exe sitting directly next to `TeknoParrotUi.exe` (the layout of older versions) still works: `TeknoParrotUi.exe` is looked for next to the exe first, then one level up. Files written by older versions are moved to their new place automatically on the next start.

A game's `.cfg` is written the first time that game is launched. It contains what was detected for it (profile, game name, background image) plus every available setting with its explanation, and is never overwritten afterwards:

- lines starting with `#` follow the global defaults
- removing the `#` pins that value for this game — a pinned line always wins over the global defaults, and keeps winning when those change later
- `measured_load_ms` is written by ParrotRelay itself after every launch; delete the line to start measuring that game afresh

## Requirements

The **[Microsoft Visual C++ 2015-2022 Redistributable (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe)** must be installed on the machine.

ParrotRelay deliberately does **not** ship its own copies of `VCRUNTIME140.dll`, `MSVCP140.dll` and friends. An emulator started underneath it could otherwise end up loading ParrotRelay's copy instead of the properly installed one — RPCS3 refuses to run in that case:

> The module vcruntime140.dll was incorrectly installed at '...\RelayData\VCRUNTIME140.dll'

With the redistributable installed, every program — ParrotRelay, RPCS3, any other emulator — uses the one copy in `System32` and the question never comes up. ParrotRelay writes a warning into its log and shows one in the settings window if it is missing.

## Building from source

```bash
pip install -r requirements.txt
pyinstaller ParrotRelay.spec
```

This produces `dist\ParrotRelay\` containing `ParrotRelay.exe` plus its `RelayData` folder. Copy the whole `ParrotRelay` folder into the TeknoParrot folder:

```
D:\ROM\TeknoParrot\TeknoParrotUi.exe
D:\ROM\TeknoParrot\ParrotRelay\ParrotRelay.exe
D:\ROM\TeknoParrot\ParrotRelay\RelayData\   <- runtime files
```

The runtime files stay where they are and are used directly on every launch — nothing is ever unpacked into `%TEMP%`, startup is faster, and no temp folder can be left behind.

### Automated builds

Two [GitHub Actions workflows](.github/workflows) build on a Windows runner (PyInstaller cannot cross-compile) and pack the complete output into one zip containing `ParrotRelay.exe`, its `RelayData` folder, `README.md` and `LICENSE` — unpack it straight into the TeknoParrot folder.

**Build** runs on every push and pull request and attaches `ParrotRelay-<commit>.zip` to the workflow run (Actions tab &rarr; run &rarr; *Artifacts*). It never creates a release.

**Build new Release** cuts a release on demand: Actions tab &rarr; *Build new Release* &rarr; *Run workflow*. Pick how to bump the version (`patch`/`minor`/`major`, or type an exact one like `1.5.0`) and it does the rest:

1. works out the next version from the highest existing `v*` tag
2. writes it into `parrot_relay.py`, so the number shows up in the settings window, in the log and in every config file the tool writes
3. builds and zips
4. commits the version bump, creates the tag `v<version>` and pushes both
5. publishes the release with `ParrotRelay-v<version>.zip` attached and auto-generated notes

Tick *prerelease* to mark it as one. The version bump commit carries `[skip ci]`, so it does not trigger a second CI build.

### One-file build

Set `ONEFILE = True` at the top of `ParrotRelay.spec` for a single `dist\ParrotRelay.exe`. Note that a one-file build unpacks its whole runtime into a fresh folder on **every** launch and deletes it afterwards — existing files are never reused, that is how PyInstaller's one-file mode works. `RUNTIME_TMPDIR` in the spec can at least move that unpack folder out of `%TEMP%` and next to the exe (absolute path required). ParrotRelay cleans up `_MEI*` leftovers there on the next start.

## Logging

`ParrotRelay\parrot_relay_log.txt` is created on first start and appended to on every run, so launches can be compared afterwards. It records which windows were detected, suppressed and focused, the measured load time, and warnings such as a missing Visual C++ redistributable or a TeknoParrot instance that could not be closed.

## License

MIT — see [LICENSE](LICENSE).
