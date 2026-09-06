r"""
ParrotRelay - Transparent launch proxy for TeknoParrotUi.exe

Purpose:
    Lives NEXT TO TeknoParrotUi.exe in the same folder. Called by
    HyperSpin 2 instead of TeknoParrotUi.exe directly, forwards all
    command-line arguments 1:1 to TeknoParrotUi.exe (same working
    directory, so no more path issues) and:

    1. Shows its own fullscreen loading screen (replacement for
       HyperOverlay's loading screen, which turned out to be the
       cause of the original focus problem) with the real game name
       (from the UserProfiles XML, GameNameInternal) and optionally a
       game-specific background image from the LoadingBG folder,
       while no real game window exists yet. Closes automatically
       once the game window is found.
    2. Actively hides TeknoParrot's own windows (main window, "Game is
       running") AS SOON AS they become visible - before they can
       ever take focus/foreground. This is the core fix: with
       exclusive fullscreen (e.g. BlazBlue), a single focus change
       away from the game is enough for it to drop out of fullscreen
       - refocusing afterwards is already too late.
    3. Additionally, as a safety net, continuously focuses the real
       game window in case some other window (HyperOverlay etc.)
       briefly comes to the foreground.
    4. Stays alive until the ACTUAL game has closed - not just until
       TeknoParrotUi.exe (a pure launcher stub that exits by itself
       shortly after starting the game) disappears. Otherwise HyperHQ
       (which watches this proxy as "the emulator") would wrongly
       report "game closed" as soon as the TP launcher stub is gone,
       even though the game is still running.

Requirements:
    pip install pywin32 psutil
    (tkinter is part of the Python standard library, no extra
    install needed. For background images in formats other than
    PNG/GIF, additionally: pip install pillow)

Background images (optional):
    Create a "LoadingBG" folder NEXT TO ParrotRelay.exe, e.g.
    D:\ROM\TeknoParrot\LoadingBG\BBCF.png
    The filename (without extension) must exactly match the
    --profile=<name>.xml from the command line. Supported
    extensions: .png, .gif natively; .jpg/.jpeg/.bmp/.webp
    additionally if Pillow is installed. No image found -> plain
    black background as before.

Game name:
    Read from D:\ROM\TeknoParrot\UserProfiles\<profile>.xml (field
    GameNameInternal, e.g. "BlazBlue: Central Fiction"). If the file
    is missing or the field isn't found, the splash falls back to
    the raw profile filename (e.g. "BBCF").

Build (as EXE, WITHOUT admin requirement - see note below):
    pyinstaller ParrotRelay.spec

    The spec builds in onedir mode by default: ParrotRelay.exe plus a
    "ParrotRelay" folder with the runtime files, both of which go into
    the TeknoParrot folder. Those files are then used directly on
    every launch - nothing is unpacked into %TEMP%, so startup is
    faster, nothing can be left behind, and it is the same folder that
    holds the log and the per-game configs.

    Set ONEFILE = True in the spec for a single exe. Be aware that
    onefile unpacks its whole runtime again on EVERY launch and never
    reuses what is already there; RUNTIME_TMPDIR can only move that
    unpack folder next to the exe, not avoid it.

Note on admin rights: TeknoParrotUi.exe itself starts fine without
elevating the proxy, and HyperHQ (not elevated) can't spawn an
elevated proxy via spawn() anyway (Windows refuses with EACCES).
That's why --uac-admin is deliberately NOT used.

Copy the build output from dist\ParrotRelay\ (the exe AND the
ParrotRelay folder next to it; just the exe for a onefile build) to
D:\ROM\TeknoParrot\, i.e. right next to TeknoParrotUi.exe.

HyperSpin 2 configuration:
    Platform Path: D:\ROM\TeknoParrot\ParrotRelay.exe
    Command Line:  --startMinimized --profile=%rom.filename%.xml
    (unchanged - the proxy passes it through 1:1; only ParrotRelay's
    own --relay-delay= switch, see below, is filtered out)

Loading screen delay (optional):
    By default the splash disappears the moment the game window is
    found. Games that create their window early but keep loading
    afterwards can keep it up longer, in milliseconds:

      - per launch, from HyperSpin:
            --relay-delay=4000
        (also accepted: --relaydelay= / --splash-delay=). The switch
        is consumed by ParrotRelay and never forwarded to TP.
      - per game, permanently:
            ParrotRelay\GameConfigs\<profile>.cfg
            splash_extra_delay_ms=4000

    Command line beats the .cfg, the .cfg beats the default (0).
    Values are capped at 60000 ms.

Data folder and per-game configs:
    On first start a "ParrotRelay" folder is created next to the exe:

      ParrotRelay\               - in a onedir build, this is also
          where the runtime files live (see Build above).
      ParrotRelay\parrot_relay_log.txt   - the log (appended, not
          overwritten, so multiple runs can be compared). A log file
          from an older version still sitting next to the exe is
          moved here automatically.
      ParrotRelay\GameConfigs\<profile>.cfg - written the first time
          a game is launched, containing what was detected for it
          (profile, game name, background image) plus the settings
          block. The file is yours afterwards: edit it, and
          ParrotRelay picks the values up on the next launch. It is
          never overwritten once it exists.
"""

import sys
import os
import re
import subprocess
import time
import shutil
import traceback
import ctypes
import xml.etree.ElementTree as ET
from datetime import datetime

import psutil
import win32api
import win32con
import win32gui
import win32process
import tkinter as tk

try:
    from PIL import Image, ImageTk
    _PILLOW_AVAILABLE = True
except ImportError:
    _PILLOW_AVAILABLE = False


# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------

if getattr(sys, "frozen", False):
    # As a PyInstaller EXE: use its own location instead of __file__
    TP_DIR = os.path.dirname(sys.executable)
else:
    TP_DIR = os.path.dirname(os.path.abspath(__file__))

TP_EXE = os.path.join(TP_DIR, "TeknoParrotUi.exe")

# Own data folder next to the exe. Created on first start; holds the
# log file and one .cfg per game. Everything ParrotRelay writes lives
# here, so TeknoParrot's own folder stays clean.
DATA_DIR = os.path.join(TP_DIR, "ParrotRelay")
GAME_CONFIG_DIR = os.path.join(DATA_DIR, "GameConfigs")

try:
    os.makedirs(GAME_CONFIG_DIR, exist_ok=True)
    _DATA_DIR_OK = True
except OSError:
    # e.g. read-only folder - fall back to the old behaviour rather
    # than failing the launch.
    _DATA_DIR_OK = False
    DATA_DIR = TP_DIR
    GAME_CONFIG_DIR = TP_DIR

LOG_PATH = os.path.join(DATA_DIR, "parrot_relay_log.txt")
_LEGACY_LOG_PATH = os.path.join(TP_DIR, "parrot_relay_log.txt")
if _DATA_DIR_OK and os.path.isfile(_LEGACY_LOG_PATH) and not os.path.exists(LOG_PATH):
    # Keep the history from older versions that logged next to the exe.
    try:
        os.replace(_LEGACY_LOG_PATH, LOG_PATH)
    except OSError:
        pass

USER_PROFILES_DIR = os.path.join(TP_DIR, "UserProfiles")
LOADING_BG_DIR = os.path.join(TP_DIR, "LoadingBG")
ICONS_DIR = os.path.join(TP_DIR, "Icons")

# Supported image extensions for the splash background. .png/.gif can
# be loaded by Tkinter itself (PhotoImage); for everything else,
# Pillow is used if installed.
NATIVE_IMAGE_EXTS = (".png", ".gif")
PILLOW_IMAGE_EXTS = (".jpg", ".jpeg", ".bmp", ".webp")

# How often (seconds) the focus loop polls.
# Deliberately kept short: the faster a newly appearing TP-owned
# window is detected and hidden, the smaller the window of time in
# which the game could lose its exclusive fullscreen mode.
POLL_INTERVAL = 0.05
# Minimum size (pixel area) so tiny helper windows (tooltips, TP's
# own small "Game is running" window) don't accidentally get treated
# as "the game window". Adjust if needed.
MIN_WINDOW_AREA = 200 * 150

# How long the splash stays up AFTER the game window was found, in
# milliseconds. 0 = old behaviour (close immediately). Overridable
# per game via the .cfg file and per launch via --relay-delay=<ms>.
DEFAULT_SPLASH_EXTRA_DELAY_MS = 0
# Sanity cap so a typo like --relay-delay=400000 can't freeze the
# cabinet behind a splash screen for minutes.
MAX_SPLASH_EXTRA_DELAY_MS = 60_000


def build_child_environment() -> dict[str, str]:
    """
    Builds the environment for TeknoParrotUi.exe (and thus for every
    game process started underneath it).

    Background: as a PyInstaller onefile EXE, ParrotRelay unpacks
    itself into a temp folder (C:\\...\\Temp\\_MEIxxxxxx) that also
    contains PyInstaller's own runtime DLLs (VCRUNTIME140.dll,
    python3xx.dll, ...). The bootloader puts that folder at the FRONT
    of PATH. Since child processes inherit our environment, an
    emulator like RPCS3 would then load OUR VCRUNTIME140.dll instead
    of its own - which it rejects with a fatal error ("The module
    vcruntime140.dll was incorrectly installed at ...\\_MEIxxxx\\...").
    It also keeps the DLL locked, so the temp folder can't be cleaned
    up on exit ("Failed to remove temporary directory").

    So we hand the child a cleaned copy: the _MEI folder is removed
    from PATH and PyInstaller's internal variables are dropped.
    Outside of a frozen build this is a plain copy of os.environ.
    """
    env = os.environ.copy()

    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return env

    def is_bundle_dir(entry: str) -> bool:
        entry = entry.strip().strip('"')
        if not entry:
            return False
        try:
            return os.path.normcase(os.path.normpath(entry)) == \
                os.path.normcase(os.path.normpath(meipass))
        except Exception:
            return False

    path = env.get("PATH", "")
    cleaned = [e for e in path.split(os.pathsep) if not is_bundle_dir(e)]
    env["PATH"] = os.pathsep.join(cleaned)

    # PyInstaller's own bookkeeping - a child must not inherit it,
    # otherwise a nested bootloader would reuse our unpack folder.
    for var in ("_MEIPASS2", "_PYI_APPLICATION_HOME_DIR",
                "_PYI_ARCHIVE_FILE", "_PYI_PARENT_PROCESS_LEVEL"):
        env.pop(var, None)

    if len(cleaned) != len(path.split(os.pathsep)):
        log(f"PyInstaller bundle dir removed from child PATH: {meipass}")

    return env


def extract_profile_name(args: list[str]) -> str | None:
    """
    Extracts the raw profile filename from --profile=XYZ.xml (e.g.
    'BBCF.xml' -> 'BBCF'). Used both to look up the real
    GameNameInternal in the UserProfiles XML and to find the matching
    background image.
    """
    for arg in args:
        m = re.match(r"--profile=(.+)\.xml$", arg, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def lookup_game_name(profile_name: str | None) -> str:
    r"""
    Reads GameNameInternal from UserProfiles\<profile_name>.xml (e.g.
    "BlazBlue: Central Fiction" instead of just "BBCF"). On any error
    (file missing, field missing, XML broken) falls back to the raw
    profile name - the splash then just shows "BBCF" instead of the
    nice name, but never breaks because of it.
    """
    if not profile_name:
        return "Game"

    xml_path = os.path.join(USER_PROFILES_DIR, f"{profile_name}.xml")
    try:
        tree = ET.parse(xml_path)
        name_elem = tree.getroot().find("GameNameInternal")
        if name_elem is not None and name_elem.text:
            return name_elem.text.strip()
    except (ET.ParseError, FileNotFoundError, OSError):
        pass
    except Exception:
        log("ERROR reading GameNameInternal:\n" + traceback.format_exc())

    return profile_name


def find_background_image(profile_name: str | None) -> str | None:
    r"""
    First looks for LoadingBG\<profile_name>.<ext>. If nothing is
    found, falls back to TP's own icon at Icons\<profile_name>.png
    (which TeknoParrot already has per game anyway, e.g. via
    IconName in the profile XML -
    <IconName>Icons/BBCF.png</IconName>).
    Returns None if that doesn't exist either (the splash then stays
    black without an image).
    """
    if not profile_name:
        return None

    all_exts = NATIVE_IMAGE_EXTS + (PILLOW_IMAGE_EXTS if _PILLOW_AVAILABLE else ())

    for ext in all_exts:
        candidate = os.path.join(LOADING_BG_DIR, f"{profile_name}{ext}")
        if os.path.isfile(candidate):
            return candidate

    for ext in all_exts:
        candidate = os.path.join(ICONS_DIR, f"{profile_name}{ext}")
        if os.path.isfile(candidate):
            return candidate

    return None


class SplashScreen:
    """
    Own fullscreen loading screen (replacement for HyperOverlay's
    loading screen) that shows what's currently starting. Closes
    automatically once the real game window has been found.

    Runs on the main thread via Tkinter's own event loop - the
    complete proxy monitoring logic (suppress TP windows, find/focus
    game window) is hooked in as a recurring callback via
    root.after(), instead of running in a separate time.sleep loop.
    """

    def __init__(self, game_name: str, bg_image_path: str | None):
        self.root = tk.Tk()
        self.root.overrideredirect(True)  # no title bar/border
        self.root.attributes("-topmost", True)
        self.root.configure(bg="black")

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.root.geometry(f"{screen_w}x{screen_h}+0+0")

        self.canvas = tk.Canvas(
            self.root, width=screen_w, height=screen_h,
            bg="black", highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        # self._bg_photo must be kept as an attribute, otherwise
        # Python's garbage collector removes the PhotoImage object
        # again as soon as __init__ returns, and the image disappears.
        self._bg_photo = None
        image_h = 0
        if bg_image_path:
            self._bg_photo = self._load_image_native_size(bg_image_path)
            if self._bg_photo:
                image_h = self._bg_photo.height()
                log(f"Image loaded (native size "
                    f"{self._bg_photo.width()}x{image_h}): {bg_image_path}")
            else:
                log(f"Could not load image: {bg_image_path}")

        # Vertical stack of [image] -> game name -> status, centered
        # as a whole on the screen. anchor="n" anchors each element
        # at its top edge, so the y-position just needs to keep
        # increasing downward.
        gap_image_to_name = 30
        gap_name_to_status = 15
        name_line_h = 55   # approx line height at font size 40
        status_line_h = 30  # approx line height at font size 20

        total_h = (
            (image_h + gap_image_to_name if image_h else 0)
            + name_line_h + gap_name_to_status + status_line_h
        )
        y = screen_h // 2 - total_h // 2

        if self._bg_photo:
            self.canvas.create_image(
                screen_w // 2, y, image=self._bg_photo, anchor="n",
            )
            y += image_h + gap_image_to_name

        self.canvas.create_text(
            screen_w // 2, y,
            text=game_name, fill="white",
            font=("Segoe UI", 40, "bold"), anchor="n",
        )
        y += name_line_h + gap_name_to_status

        self.status_text_id = self.canvas.create_text(
            screen_w // 2, y,
            text="Loading...", fill="#cccccc",
            font=("Segoe UI", 20), anchor="n",
        )

        self.root.update_idletasks()
        self.root.update()

    def _load_image_native_size(self, path: str):
        """
        Loads an image at its ORIGINAL SIZE (no scaling). Uses
        Pillow if available (more supported formats), otherwise
        Tkinter's own PhotoImage (PNG/GIF only).
        """
        ext = os.path.splitext(path)[1].lower()

        if _PILLOW_AVAILABLE:
            try:
                img = Image.open(path)
                return ImageTk.PhotoImage(img)
            except Exception:
                log("ERROR loading image with Pillow:\n"
                    + traceback.format_exc())
                return None

        if ext in NATIVE_IMAGE_EXTS:
            try:
                return tk.PhotoImage(file=path)
            except Exception:
                log("ERROR loading image without Pillow:\n"
                    + traceback.format_exc())
                return None

        log(f"Image format {ext} requires Pillow (not installed) - "
            f"skipping image.")
        return None

    def set_status(self, text: str) -> None:
        try:
            self.canvas.itemconfig(self.status_text_id, text=text)
        except tk.TclError:
            pass

    def keep_on_top(self) -> None:
        """
        Re-asserts topmost while the splash is deliberately kept up
        after the game window appeared - otherwise the game window,
        which is already being drawn, would cover it.
        """
        try:
            self.root.attributes("-topmost", True)
            self.root.lift()
        except tk.TclError:
            pass

    def close(self) -> None:
        try:
            self.root.destroy()
        except tk.TclError:
            pass


# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------

_log_file = open(LOG_PATH, "a", buffering=1, encoding="utf-8")


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}"
    print(line)
    _log_file.write(line + "\n")


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ---------------------------------------------------------------------
# Runtime / build mode
# ---------------------------------------------------------------------

def describe_runtime_mode() -> str:
    """
    Says how this build is running - useful in the log, because the
    two PyInstaller modes behave very differently:

    onedir  - the runtime files sit permanently in the ParrotRelay
              folder and are used directly. Nothing is unpacked, so
              a launch reuses exactly the files that are already
              there.
    onefile - the bootloader unpacks the whole runtime into a fresh
              folder on every launch and deletes it on exit. That is
              inherent to onefile; existing files are never reused.
    """
    if not getattr(sys, "frozen", False):
        return "script (not frozen)"

    bundle_dir = getattr(sys, "_MEIPASS", None)
    if not bundle_dir:
        return "frozen (unknown mode)"

    exe_dir = os.path.dirname(sys.executable)
    try:
        inside_exe_dir = os.path.commonpath(
            [os.path.abspath(bundle_dir), os.path.abspath(exe_dir)]
        ) == os.path.abspath(exe_dir)
    except ValueError:  # different drives
        inside_exe_dir = False

    if inside_exe_dir and not os.path.basename(bundle_dir).startswith("_MEI"):
        return f"onedir - runtime files reused from {bundle_dir}"
    return f"onefile - runtime unpacked to {bundle_dir} (fresh copy per launch)"


def cleanup_stale_runtime_dirs() -> None:
    """
    Removes _MEI* leftovers from a onefile build that was pointed at
    our own folder via --runtime-tmpdir. Those only exist if a
    previous run was killed before the bootloader could clean up (or
    a child process still held a DLL open). Anything still in use
    fails to delete, which is fine - we skip it silently.

    Only ever touches _MEI* folders inside our own data folder;
    the real %TEMP% is none of our business.
    """
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if not bundle_dir or not os.path.basename(bundle_dir).startswith("_MEI"):
        return

    parent = os.path.dirname(os.path.abspath(bundle_dir))
    try:
        if os.path.commonpath([parent, os.path.abspath(DATA_DIR)]) != \
                os.path.abspath(DATA_DIR):
            return
    except ValueError:
        return

    removed = 0
    try:
        entries = os.listdir(parent)
    except OSError:
        return

    for entry in entries:
        if not entry.startswith("_MEI"):
            continue
        candidate = os.path.join(parent, entry)
        if os.path.abspath(candidate) == os.path.abspath(bundle_dir):
            continue  # that's us
        try:
            shutil.rmtree(candidate)
            removed += 1
        except OSError:
            pass  # still locked by a running process - leave it alone

    if removed:
        log(f"Removed {removed} stale runtime folder(s) in {parent}")


# ---------------------------------------------------------------------
# Own command line arguments and per-game config files
# ---------------------------------------------------------------------

# Accepted spellings for the launch-time delay override. Everything
# that is NOT one of ours is forwarded to TeknoParrotUi.exe untouched.
_RELAY_DELAY_ARG_NAMES = ("relay-delay", "relaydelay", "splash-delay")


def split_relay_args(args: list[str]) -> tuple[list[str], int | None]:
    """
    Separates ParrotRelay's own arguments from those meant for
    TeknoParrot.

    Currently supported (all equivalent, value in milliseconds):
        --relay-delay=4000   --relaydelay=4000   --splash-delay=4000

    Returns (args_for_teknoparrot, delay_ms_or_None). An unparseable
    or out-of-range value is logged and ignored instead of aborting
    the launch - a broken HyperSpin command line should never stop a
    game from starting.
    """
    forwarded: list[str] = []
    delay_ms: int | None = None

    for arg in args:
        m = re.match(r"--(" + "|".join(_RELAY_DELAY_ARG_NAMES) + r")=(.*)$",
                     arg, re.IGNORECASE)
        if not m:
            forwarded.append(arg)
            continue

        raw = m.group(2).strip().strip('"')
        parsed = _parse_delay_ms(raw, source=arg)
        if parsed is not None:
            delay_ms = parsed

    return forwarded, delay_ms


def _parse_delay_ms(raw: str, source: str) -> int | None:
    """
    Parses a delay value in milliseconds and clamps it to
    0..MAX_SPLASH_EXTRA_DELAY_MS. Returns None if it isn't a number.
    """
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        log(f"Ignoring invalid delay value in '{source}' "
            f"(expected a number in milliseconds).")
        return None

    if value < 0:
        log(f"Negative delay in '{source}' - using 0.")
        return 0
    if value > MAX_SPLASH_EXTRA_DELAY_MS:
        log(f"Delay in '{source}' exceeds the maximum of "
            f"{MAX_SPLASH_EXTRA_DELAY_MS} ms - capped.")
        return MAX_SPLASH_EXTRA_DELAY_MS
    return value


def game_config_path(profile_name: str | None) -> str | None:
    """Path of the .cfg belonging to a profile, or None without one."""
    if not profile_name:
        return None
    # Profile names come from a filename on disk, but be strict anyway
    # so a crafted --profile= can't write outside GameConfigs.
    safe = os.path.basename(profile_name)
    if not safe or safe in (".", ".."):
        return None
    return os.path.join(GAME_CONFIG_DIR, f"{safe}.cfg")


def read_game_config(path: str) -> dict[str, str]:
    """
    Reads a simple "key=value" file. Lines starting with # or ; and
    blank lines are ignored, keys are lower-cased and trimmed. Kept
    deliberately dumb so the file stays hand-editable.
    """
    values: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line[0] in "#;":
                    continue
                key, sep, value = line.partition("=")
                if not sep:
                    continue
                values[key.strip().lower()] = value.strip()
    except OSError:
        log(f"Could not read game config: {path}")
    except Exception:
        log("ERROR reading game config:\n" + traceback.format_exc())
    return values


def write_default_game_config(path: str, profile_name: str,
                              game_name: str, bg_image_path: str | None) -> None:
    """
    Creates the .cfg on a game's first launch, pre-filled with what
    ParrotRelay knows about it. The settings block is written with
    real (default) values, so tweaking a game only means editing a
    number - no need to remember key names.
    """
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = f"""# ParrotRelay - settings for "{game_name}"
# Created automatically on {stamp}. Safe to edit; ParrotRelay only
# reads the "key=value" lines below and ignores everything else.
#
# Detected on first launch:
#   profile    = {profile_name}.xml
#   game_name  = {game_name}
#   background = {bg_image_path or "(none - plain black splash)"}
#
# ------------------------------------------------------------------
# Settings
# ------------------------------------------------------------------
#
# splash_extra_delay_ms
#   How much longer the loading screen stays up AFTER the game window
#   has appeared, in milliseconds. Useful for games that show their
#   window early but keep loading (or flicker) for a few more
#   seconds. Example: 4000 = four extra seconds.
#   A --relay-delay=<ms> on the command line overrides this value.
splash_extra_delay_ms={DEFAULT_SPLASH_EXTRA_DELAY_MS}
"""
    try:
        with open(path, "x", encoding="utf-8") as f:
            f.write(content)
        log(f"Game config created: {path}")
    except FileExistsError:
        pass
    except OSError:
        log(f"Could not create game config: {path}")


def resolve_splash_extra_delay(profile_name: str | None, game_name: str,
                               bg_image_path: str | None,
                               cli_delay_ms: int | None) -> int:
    """
    Determines how long the splash lingers after the game window
    showed up, and makes sure the game's .cfg exists.

    Precedence: command line > .cfg > built-in default. The command
    line wins because it is the more specific, per-launch statement
    (e.g. one HyperSpin entry that needs extra time).
    """
    path = game_config_path(profile_name)
    if path is not None and not os.path.isfile(path):
        write_default_game_config(path, profile_name or "?", game_name,
                                  bg_image_path)

    cfg_delay_ms: int | None = None
    if path is not None and os.path.isfile(path):
        cfg = read_game_config(path)
        if "splash_extra_delay_ms" in cfg:
            cfg_delay_ms = _parse_delay_ms(
                cfg["splash_extra_delay_ms"],
                source=f"{os.path.basename(path)} (splash_extra_delay_ms)",
            )

    if cli_delay_ms is not None:
        log(f"Splash extra delay: {cli_delay_ms} ms (from command line)")
        return cli_delay_ms
    if cfg_delay_ms is not None:
        log(f"Splash extra delay: {cfg_delay_ms} ms (from game config)")
        return cfg_delay_ms
    return DEFAULT_SPLASH_EXTRA_DELAY_MS



# ---------------------------------------------------------------------
# Window/process helper functions
# ---------------------------------------------------------------------

def get_descendant_pids(root_pid: int) -> set[int]:
    """Returns root_pid plus all (recursive) child process PIDs."""
    try:
        root = psutil.Process(root_pid)
    except psutil.NoSuchProcess:
        log(f"WARNING: root process {root_pid} no longer exists")
        return set()

    pids = {root_pid}
    try:
        for child in root.children(recursive=True):
            pids.add(child.pid)
    except psutil.AccessDenied:
        log("WARNING: AccessDenied while listing child processes "
            "(is the proxy not running as admin while TP is?)")
    except Exception:
        log("ERROR listing child processes:\n" + traceback.format_exc())
    return pids


def find_candidate_windows(pids: set[int], exclude_pid: int) -> list[int]:
    """
    Finds visible top-level windows whose process belongs to 'pids',
    except exclude_pid (= TeknoParrotUi.exe itself). Sorted by window
    area descending; windows smaller than MIN_WINDOW_AREA are
    filtered out.
    """
    candidates = []

    def callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            return
        if pid not in pids or pid == exclude_pid:
            return
        try:
            rect = win32gui.GetWindowRect(hwnd)
        except Exception:
            return
        area = (rect[2] - rect[0]) * (rect[3] - rect[1])
        if area < MIN_WINDOW_AREA:
            return
        candidates.append((area, hwnd))

    try:
        win32gui.EnumWindows(callback, None)
    except Exception:
        log("ERROR in EnumWindows:\n" + traceback.format_exc())

    candidates.sort(reverse=True)
    return [hwnd for _, hwnd in candidates]


def find_tp_own_windows(tp_pid: int) -> list[int]:
    """
    Finds visible top-level windows that belong to TeknoParrotUi.exe
    ITSELF AND whose title exactly matches one of the known, harmless
    TP-owned runtime windows (e.g. "Game is running").

    IMPORTANT: Deliberately does NOT suppress every TP window on
    principle - otherwise TP error dialogs (crash, missing DLL,
    profile error etc.) would also become invisible, which would make
    troubleshooting impossible and, in the worst case, lead to a
    plain black screen with no feedback at all if the game itself
    hangs or crashes.
    """
    # Known, harmless runtime window titles of TeknoParrotUi.exe.
    # Anything else (error dialogs, unknown titles) stays visible.
    KNOWN_HARMLESS_TITLES = {"Spiel läuft", "Game is running"}

    windows = []

    def callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            return
        if pid != tp_pid:
            return
        try:
            title = win32gui.GetWindowText(hwnd)
        except Exception:
            return
        if title not in KNOWN_HARMLESS_TITLES:
            return
        windows.append(hwnd)

    try:
        win32gui.EnumWindows(callback, None)
    except Exception:
        log("ERROR in EnumWindows (TP-owned windows):\n" + traceback.format_exc())

    return windows


def suppress_window(hwnd: int) -> bool:
    """
    Hides a TP-owned window (minimize + remove from taskbar/Alt-Tab)
    so Windows never even offers it as a focus candidate. Returns
    True if something was actually changed (for logging), False
    otherwise.
    """
    if not win32gui.IsWindow(hwnd):
        return False
    try:
        was_visible = win32gui.IsWindowVisible(hwnd)
        win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
        return was_visible
    except win32gui.error as e:
        if len(e.args) >= 1 and e.args[0] == 1400:
            return False
        log("ERROR hiding TP window:\n" + traceback.format_exc())
        return False
    except Exception:
        log("ERROR hiding TP window:\n" + traceback.format_exc())
        return False


def force_focus(hwnd: int) -> None:
    """
    Forces focus onto hwnd, even when Windows' foreground lock would
    normally prevent it. Trick: briefly attach the currently active
    window's input thread to our own thread (AttachThreadInput) -
    this bypasses the lock, see e.g. the MSDN documentation for
    SetForegroundWindow.

    Some candidate windows (e.g. TeknoParrot's short-lived
    D3DProxyWindow during DirectX hooking) only exist for a fraction
    of a second. Between "found as a candidate" and "focusing here",
    the window may already be destroyed - this is normal and not a
    real error, so it's checked up front via IsWindow and, in that
    case, aborted silently (without an ERROR log).
    """
    if not win32gui.IsWindow(hwnd):
        log(f"Target window hwnd={hwnd} no longer exists (short-lived "
            f"transition window) - skipping.")
        return

    fg_thread = 0
    target_thread = 0
    attached_fg = False
    attached_target = False

    try:
        cur_thread = win32api.GetCurrentThreadId()
        fg_hwnd = win32gui.GetForegroundWindow()

        if fg_hwnd:
            fg_thread, _ = win32process.GetWindowThreadProcessId(fg_hwnd)
        target_thread, _ = win32process.GetWindowThreadProcessId(hwnd)

        if fg_thread and fg_thread != cur_thread:
            win32process.AttachThreadInput(cur_thread, fg_thread, True)
            attached_fg = True
        if target_thread and target_thread != cur_thread:
            win32process.AttachThreadInput(cur_thread, target_thread, True)
            attached_target = True

        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)

    except win32gui.error as e:
        if len(e.args) >= 1 and e.args[0] == 1400:
            # ERROR_INVALID_WINDOW_HANDLE - the window disappeared
            # between being found and being focused (race condition
            # with short-lived transition windows). Not a real error,
            # ignore briefly.
            log(f"Target window hwnd={hwnd} disappeared while "
                f"focusing - skipping.")
        else:
            log("ERROR while focusing:\n" + traceback.format_exc())
    except Exception:
        log("ERROR while focusing:\n" + traceback.format_exc())

    finally:
        try:
            if attached_fg:
                win32process.AttachThreadInput(cur_thread, fg_thread, False)
            if attached_target:
                win32process.AttachThreadInput(cur_thread, target_thread, False)
        except Exception:
            pass


def describe_hwnd(hwnd: int) -> str:
    try:
        title = win32gui.GetWindowText(hwnd)
        cls = win32gui.GetClassName(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            proc = psutil.Process(pid).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            proc = "?"
        return f"hwnd={hwnd} pid={pid} proc={proc} class={cls} title='{title}'"
    except Exception:
        return f"hwnd={hwnd} (details not readable)"


# ---------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------

def main() -> None:
    log("=" * 60)
    log("ParrotRelay started")
    log(f"TP_DIR   = {TP_DIR}")
    log(f"TP_EXE   = {TP_EXE}")
    log(f"Args     = {sys.argv[1:]}")
    log(f"Elevated = {is_admin()}")
    log(f"Runtime  = {describe_runtime_mode()}")
    cleanup_stale_runtime_dirs()

    if not os.path.isfile(TP_EXE):
        log(f"ERROR: {TP_EXE} not found - aborting.")
        ctypes.windll.user32.MessageBoxW(
            0,
            f"TeknoParrotUi.exe not found in:\n{TP_DIR}",
            "ParrotRelay",
            0x10,
        )
        return

    # Our own arguments are stripped here - TeknoParrot must never
    # see them, it would reject the unknown switch.
    args, cli_delay_ms = split_relay_args(sys.argv[1:])
    profile_name = extract_profile_name(args)
    game_name = lookup_game_name(profile_name)
    bg_image_path = find_background_image(profile_name)
    splash_extra_delay_ms = resolve_splash_extra_delay(
        profile_name, game_name, bg_image_path, cli_delay_ms)

    try:
        proc = subprocess.Popen(
            [TP_EXE] + args,
            cwd=TP_DIR,
            env=build_child_environment(),
        )
    except Exception:
        log("ERROR starting TeknoParrotUi.exe:\n" + traceback.format_exc())
        return

    tp_pid = proc.pid
    log(f"TeknoParrotUi.exe started, PID={tp_pid}")

    splash = SplashScreen(game_name, bg_image_path)
    log(f"Splash screen shown for '{game_name}' "
        f"(profile: {profile_name or '?'})")

    # Shared state for the recurring tick callback. A dict instead of
    # individual nonlocal variables, because tick() is a nested
    # function that gets called repeatedly via root.after(), so
    # keeping everything in one place is simpler.
    state = {
        "last_focused_hwnd": None,
        "suppressed_hwnds_logged": set(),
        "game_pid_seen": None,
        "tp_launcher_exited_logged": False,
        "splash_closed": False,
        # Monotonic timestamp at which the splash may close. Set once
        # the game window is found; with a delay of 0 that moment is
        # "right now", so the behaviour is unchanged by default.
        "splash_close_at": None,
    }

    def tick() -> None:
        tp_launcher_running = proc.poll() is None

        if not tp_launcher_running and not state["tp_launcher_exited_logged"]:
            log(f"TeknoParrotUi.exe (launcher stub) exited, "
                f"exit code={proc.returncode} - proxy stays alive as "
                f"long as the actual game is still running.")
            state["tp_launcher_exited_logged"] = True

        # 1) Actively hide TP-owned windows (main window, "Game is
        #    running") BEFORE they can ever take focus/foreground.
        if tp_launcher_running:
            tp_windows = find_tp_own_windows(tp_pid)
            for hwnd in tp_windows:
                changed = suppress_window(hwnd)
                if changed and hwnd not in state["suppressed_hwnds_logged"]:
                    log(f"TP-owned window suppressed: {describe_hwnd(hwnd)}")
                    state["suppressed_hwnds_logged"].add(hwnd)

        # 2) Find/focus the real game window.
        if tp_launcher_running:
            pids = get_descendant_pids(tp_pid)
        elif state["game_pid_seen"] is not None:
            pids = {state["game_pid_seen"]}
        else:
            pids = set()

        candidates = find_candidate_windows(pids, exclude_pid=tp_pid)

        if candidates:
            hwnd = candidates[0]
            if state["game_pid_seen"] is None:
                _, state["game_pid_seen"] = win32process.GetWindowThreadProcessId(hwnd)

            # The real game window provably exists, so the loading
            # screen may go - after the configured extra delay, for
            # games that show their window well before they are
            # actually done loading.
            if not state["splash_closed"]:
                if state["splash_close_at"] is None:
                    state["splash_close_at"] = (
                        time.monotonic() + splash_extra_delay_ms / 1000.0)
                    log(f"Target window found: {describe_hwnd(hwnd)} - "
                        f"closing splash in {splash_extra_delay_ms} ms")
                    if splash_extra_delay_ms > 0:
                        splash.set_status("Almost ready...")

                if time.monotonic() >= state["splash_close_at"]:
                    splash.close()
                    state["splash_closed"] = True
                    log("Splash screen closed")
                else:
                    # Hold the splash in front of the game window for
                    # the rest of the delay, and don't pull focus to
                    # the game yet - that happens once it's gone.
                    splash.keep_on_top()

            if state["splash_closed"]:
                if win32gui.GetForegroundWindow() != hwnd:
                    if hwnd != state["last_focused_hwnd"]:
                        log(f"New target window detected: {describe_hwnd(hwnd)}")
                    force_focus(hwnd)
                state["last_focused_hwnd"] = hwnd
        elif not state["splash_closed"]:
            # No target window found yet - update splash status
            # depending on launcher state, purely informational.
            if tp_launcher_running:
                splash.set_status("Loading...")
            else:
                splash.set_status("Starting...")

        # Exit condition: launcher gone AND (either no game was ever
        # detected, OR the detected game is provably no longer
        # running).
        if not tp_launcher_running:
            if state["game_pid_seen"] is None:
                log("No game process was ever detected and the "
                    "launcher has exited - proxy shutting down.")
                if not state["splash_closed"]:
                    splash.close()
                splash.root.quit()
                return
            if not psutil.pid_exists(state["game_pid_seen"]):
                log(f"Game process (PID {state['game_pid_seen']}) has "
                    f"exited - proxy shutting down.")
                splash.root.quit()
                return

        # Schedule the next tick (milliseconds).
        splash.root.after(int(POLL_INTERVAL * 1000), tick)

    # Kick off the first tick, then let Tkinter's own event loop take
    # over - it drives both the splash window and (via the recurring
    # after() calls) the complete monitoring logic.
    splash.root.after(0, tick)
    splash.root.mainloop()

    log("ParrotRelay stopped")
    log("=" * 60 + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("UNHANDLED ERROR:\n" + traceback.format_exc())
    finally:
        _log_file.close()
