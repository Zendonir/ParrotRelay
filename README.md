# ParrotRelay

A transparent launch proxy for [TeknoParrot](https://github.com/teknogods/TeknoParrotUI), built for use with **HyperSpin 2 / HyperHQ**.

![ParrotRelay loading screen](screenshot.png)

## Why

TeknoParrot games launched through HyperHQ sometimes lose their exclusive fullscreen mode shortly after starting: `TeknoParrotUi.exe` brings its own "Game is running" window back to the foreground itself, while the actual game keeps running behind it. The result is that you end up looking at TP's window instead of the game, and clicking back on it no longer restores fullscreen properly.

ParrotRelay sits between HyperHQ and TeknoParrotUi.exe and fixes this without touching TeknoParrot itself.

## What it does

1. **Its own fullscreen loading screen** — shows the real game name (read from TeknoParrot's profile XML) and, optionally, a game-specific background image while the game loads. Closes automatically as soon as the real game window appears.
2. **Actively suppresses TeknoParrot's own "Game is running" window**, before it can ever take focus.
3. **Continuously keeps focus on the real game window** as a safety net, in case something else briefly steals the foreground.
4. **Settings window** — double-click `ParrotRelay.exe` and you get a UI to configure all of this per game, no manual file editing needed.
5. **Stays alive until the game itself actually closes** — not just until TeknoParrot's own launcher stub exits (which it does by design shortly after launching the game). Otherwise HyperHQ would wrongly report "game closed" while the game is still running.

## Installation

1. Open [Releases](../../releases) and download the zip.
2. Unpack it right next to `TeknoParrotUi.exe`, so you end up with `D:\ROM\TeknoParrot\ParrotRelay.exe` and the `ParrotRelay` folder beside it.
3. In HyperSpin 2, edit the TeknoParrot platform:
   - **Platform Path:** `D:\ROM\TeknoParrot\ParrotRelay.exe`
   - **Command Line:** leave unchanged, e.g. `--startMinimized --profile=%rom.filename%.xml`

No admin rights setup required. Double-click `ParrotRelay.exe` once to open the settings window and check that it finds your games.

## Background images (optional)

Create a `LoadingBG` folder next to `ParrotRelay.exe`:

```
D:\ROM\TeknoParrot\LoadingBG\BBCF.png
```

The filename (without extension) must exactly match the profile name from `--profile=<name>.xml`. Supported: `.png`, `.gif` natively; `.jpg`/`.jpeg`/`.bmp`/`.webp` additionally if [Pillow](https://pypi.org/project/Pillow/) is installed.

If no custom image is found, ParrotRelay automatically falls back to TeknoParrot's own icon (`Icons\<profile>.png`), if present.

## Settings window

Start `ParrotRelay.exe` **without arguments** — i.e. double-click it instead of letting HyperSpin call it — and a settings window opens instead of launching anything:

- lists every TeknoParrot game, with a search box
- **Global defaults** apply to every game; per-game entries override them. A game only stores what actually differs, so changing a default still reaches every game that never overrode it
- **Preview loading screen** shows the splash exactly as it will appear at launch — the quickest way to check a background image
- **Apply to all games** for cabinet-wide settings
- **Use global defaults** drops everything stored for one game; **Pin all values** does the opposite and writes every value as an explicit line, so the game keeps them no matter what the defaults do later
- shortcuts to the log and the `RelayData` folder

Everything it writes is a plain text file you can also edit by hand.

| Setting | What it does |
|---|---|
| Show loading screen | Off = no splash for this game, window handling keeps working |
| Keep loading screen up for (ms) | Extra time after the game window appeared |
| Give up after (ms) | Safety net: closes the splash if no game window ever shows up (0 = wait forever) |
| Background image | Overrides the automatic search in `LoadingBG\` and `Icons\` |
| Keep game window focused | The continuous refocus safety net |
| Hide TeknoParrot windows | The actual fullscreen fix — only turn off for troubleshooting |

## Loading screen delay from HyperSpin

Besides the settings window, the delay can be set per launch straight from the command line (milliseconds):

```
--startMinimized --profile=%rom.filename%.xml --relay-delay=4000
```

`--relaydelay=` and `--splash-delay=` are accepted as well. The switch is consumed by ParrotRelay and never forwarded to TeknoParrot.

Precedence: command line &rarr; game config &rarr; global defaults &rarr; built-in default (`0`). Values are capped at 60000 ms.

## Data folder

On first start ParrotRelay creates a `RelayData` folder for everything it writes:

```
D:\ROM\TeknoParrot\ParrotRelay\RelayData\parrot_relay_log.txt
D:\ROM\TeknoParrot\ParrotRelay\RelayData\ParrotRelay.cfg          <- global defaults
D:\ROM\TeknoParrot\ParrotRelay\RelayData\GameConfigs\BBCF.cfg     <- per game
```

It sits one level below the runtime files on purpose — that folder is full of DLLs and mixing your own files into it is just confusing. Data written by older versions is moved here automatically.

A game's `.cfg` is written the first time it is launched and contains everything detected for it plus every available setting with its explanation. Lines starting with `#` follow the global defaults; removing the `#` pins that value for this game. A pinned line always wins over the global defaults — that is the whole point of the file — and keeps winning when the defaults change later. Existing files are never overwritten.

## Building from source

```bash
pip install -r requirements.txt
pyinstaller ParrotRelay.spec
```

This produces `dist\ParrotRelay\` containing `ParrotRelay.exe` plus a `ParrotRelay` folder with the runtime files. Copy **both** into the TeknoParrot folder:

```
D:\ROM\TeknoParrot\ParrotRelay.exe
D:\ROM\TeknoParrot\ParrotRelay\           <- runtime files
D:\ROM\TeknoParrot\ParrotRelay\RelayData\ <- log and configs
```

The runtime files stay where they are and are used directly on every launch — nothing is ever unpacked into `%TEMP%`, startup is faster, and no temp folder can be left behind. Everything ParrotRelay writes goes into `RelayData` below it, so there is exactly one extra folder next to `TeknoParrotUi.exe`.

### Automated builds

A [GitHub Actions workflow](.github/workflows/build.yml) builds ParrotRelay on a Windows runner and packs the complete output into one zip:

- every push and pull request attaches `ParrotRelay-<commit>.zip` to the workflow run (Actions tab &rarr; run &rarr; *Artifacts*)
- pushing a tag like `v1.2.0` additionally creates a release with `ParrotRelay-v1.2.0.zip` attached
- *Run workflow* in the Actions tab builds on demand

The zip contains `ParrotRelay.exe`, the `ParrotRelay` runtime folder, `README.md` and `LICENSE` — unpack it straight into the TeknoParrot folder.

### One-file build

Set `ONEFILE = True` at the top of `ParrotRelay.spec` for a single `dist\ParrotRelay.exe`. Note that a one-file build unpacks its whole runtime into a fresh folder on **every** launch and deletes it afterwards — existing files are never reused, that is how PyInstaller's one-file mode works. `RUNTIME_TMPDIR` in the spec can at least move that unpack folder out of `%TEMP%` and next to the exe (absolute path required). ParrotRelay cleans up `_MEI*` leftovers there on the next start.

## Logging

`ParrotRelay\RelayData\parrot_relay_log.txt` is created on first start and appended to on every run — useful for debugging which window was detected/suppressed/focused and when.

## License

MIT — see [LICENSE](LICENSE).
