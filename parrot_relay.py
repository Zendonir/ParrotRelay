r"""
ParrotRelay - Transparent launch proxy for TeknoParrotUi.exe

Purpose:
    Lives NEXT TO TeknoParrotUi.exe in the same folder. Called by
    HyperSpin 2 instead of TeknoParrotUi.exe directly, forwards all
    command-line arguments 1:1 to TeknoParrotUi.exe (same working
    directory, so no more path issues) and:

    1. Shows its own fullscreen loading screen with a progress bar (replacement for
       HyperOverlay's loading screen, which turned out to be the
       cause of the original focus problem) with the real game name
       (from the UserProfiles XML, GameNameInternal) and optionally a
       game-specific background image from the LoadingBG folder,
       while no real game window exists yet. Closes automatically
       once the game window is found.

       The bar is driven by how long this game took the last times:
       every launch stores the time from starting TeknoParrot until
       the game window appeared in the game's .cfg, as
       (new time + stored time) / 2, so it settles on a realistic
       value and follows a changed machine.

       Stored load time plus the extra delay (see below) is the
       expected total, one percent of it is one step of the bar, and
       the bar simply follows the clock. It stops at 99% as long as
       the game window has not appeared, and once it has, it runs
       from wherever it got to up to 100%, arriving exactly when the
       loading screen closes. The first launch of a game has nothing
       to predict and runs indeterminate.
    2. Closes a TeknoParrotUi.exe that is still running from an
       earlier launch before starting the new one - a leftover
       instance keeps its profile locked, steals the foreground or
       stops the new one from starting at all. Politely first
       (WM_CLOSE), then terminate, then kill.
    3. Lets ESC cancel a launch while the loading screen is up:
       TeknoParrot and every process it started are ended, so a
       cancelled launch doesn't leave a half-started game behind.
    4. Actively hides TeknoParrot's own windows (main window, "Game is
       running") AS SOON AS they become visible - before they can
       ever take focus/foreground. This is the core fix: with
       exclusive fullscreen (e.g. BlazBlue), a single focus change
       away from the game is enough for it to drop out of fullscreen
       - refocusing afterwards is already too late.
    5. Additionally, as a safety net, continuously focuses the real
       game window in case some other window (HyperOverlay etc.)
       briefly comes to the foreground.
    6. Stays alive until the ACTUAL game has closed - not just until
       TeknoParrotUi.exe (a pure launcher stub that exits by itself
       shortly after starting the game) disappears. Otherwise HyperHQ
       (which watches this proxy as "the emulator") would wrongly
       report "game closed" as soon as the TP launcher stub is gone,
       even though the game is still running.

Requirements:
    The Microsoft Visual C++ 2015-2022 Redistributable (x64) must be
    installed on the machine:
    https://aka.ms/vs/17/release/vc_redist.x64.exe
    Windows searches System32 before the current directory and before
    PATH, so with it installed every program - ParrotRelay, RPCS3, any
    other emulator - loads that one copy. Without it, programs pick up
    whatever copy they can find, and RPCS3 refuses to start when the
    one it loaded is not the properly installed one ("The module
    vcruntime140.dll was incorrectly installed at ..."). ParrotRelay
    logs a warning when it is missing.

    pip install pywin32 psutil
    (tkinter is part of the Python standard library, no extra
    install needed. For background images in formats other than
    PNG/GIF, additionally: pip install pillow)

Background images (optional):
    Create a "LoadingBG" folder in the TeknoParrot folder, e.g.
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

Copy the whole "ParrotRelay" folder from dist\ into
D:\ROM\TeknoParrot\, so that TeknoParrotUi.exe and the ParrotRelay
folder sit side by side.

HyperSpin 2 configuration:
    Platform Path: D:\ROM\TeknoParrot\ParrotRelay\ParrotRelay.exe
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
      - per game, permanently, in the settings window or in
            ParrotRelay\GameConfigs\<profile>.cfg
            splash_extra_delay_ms=4000

    Command line beats the game .cfg, which beats the global
    defaults, which beat the built-in default (0). Values are capped
    at 60000 ms.

Settings window:
    Starting ParrotRelay.exe WITHOUT arguments (i.e. double-clicking
    it instead of letting HyperSpin call it) opens a settings window
    instead of launching anything. It lists every TeknoParrot game and
    edits the same .cfg files that can also be edited by hand:

      - global defaults that apply to every game
      - per-game overrides; a game only stores what actually differs,
        so changing a default still reaches every game that never
        overrode it
      - preview of the loading screen (checks the background image)
      - "Apply to all games" for cabinet-wide settings
      - shortcuts to the log and the data folder

Folder layout:
    ParrotRelay lives in its own folder inside the TeknoParrot folder:

      TeknoParrot\ParrotRelay\ParrotRelay.exe
      TeknoParrot\ParrotRelay\RelayData\        - the runtime files
          that belong to the exe (DLLs and the like). Never needs to
          be opened.
      TeknoParrot\ParrotRelay\GameConfigs\      - one .cfg per game,
          written the first time a game is launched, containing what
          was detected for it (profile, game name, background image)
          plus every available setting with its explanation. Lines
          starting with # follow the global defaults; removing the #
          pins that value for this game.
      TeknoParrot\ParrotRelay\ParrotRelay.cfg   - global defaults
      TeknoParrot\ParrotRelay\parrot_relay_log.txt - the log
          (appended, not overwritten, so runs can be compared)

    An exe sitting directly next to TeknoParrotUi.exe (the layout of
    older versions) still works: TeknoParrotUi.exe is looked for next
    to the exe first, then one level up, and a "ParrotRelay" folder is
    used for the data in that case. Files written by older versions
    are moved to their new place automatically.

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


# Version of this build. The "Build new Release" workflow rewrites
# this line when it cuts a release, so the number in the GUI, in the
# log and on the release tag are always the same one.
VERSION = "1.4.1"

# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------

if getattr(sys, "frozen", False):
    # As a PyInstaller EXE: its own location, not __file__.
    EXE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    EXE_DIR = os.path.dirname(os.path.abspath(__file__))

# The exe normally lives in a "ParrotRelay" folder inside the
# TeknoParrot folder, with its runtime files one level below that in
# "RelayData". Older installs put the exe right next to
# TeknoParrotUi.exe, so both placements are accepted: look for
# TeknoParrotUi.exe next to the exe first, then one level up.
if os.path.isfile(os.path.join(EXE_DIR, "TeknoParrotUi.exe")):
    TP_DIR = EXE_DIR
elif os.path.isfile(os.path.join(os.path.dirname(EXE_DIR),
                                 "TeknoParrotUi.exe")):
    TP_DIR = os.path.dirname(EXE_DIR)
else:
    # Nothing found - assume the current layout so the settings window
    # can still start and say what is missing.
    TP_DIR = os.path.dirname(EXE_DIR) if os.path.basename(EXE_DIR).lower() \
        == "parrotrelay" else EXE_DIR

TP_EXE = os.path.join(TP_DIR, "TeknoParrotUi.exe")

# Where ParrotRelay's own files live. With the exe in its own folder
# that IS the exe folder, so the layout ends up as
#
#   TeknoParrot\ParrotRelay\ParrotRelay.exe
#   TeknoParrot\ParrotRelay\RelayData\        <- runtime files
#   TeknoParrot\ParrotRelay\GameConfigs\      <- one .cfg per game
#   TeknoParrot\ParrotRelay\parrot_relay_log.txt
#
# With the exe sitting directly next to TeknoParrotUi.exe (the older
# layout) a "ParrotRelay" folder is used instead, so nothing is
# scattered into TeknoParrot's own folder.
RELAY_ROOT = EXE_DIR if EXE_DIR != TP_DIR \
    else os.path.join(TP_DIR, "ParrotRelay")
DATA_DIR = RELAY_ROOT
GAME_CONFIG_DIR = os.path.join(DATA_DIR, "GameConfigs")

try:
    os.makedirs(GAME_CONFIG_DIR, exist_ok=True)
    _DATA_DIR_OK = True
except OSError:
    # e.g. read-only folder - fall back rather than failing the launch.
    _DATA_DIR_OK = False
    RELAY_ROOT = TP_DIR
    DATA_DIR = TP_DIR
    GAME_CONFIG_DIR = TP_DIR

LOG_PATH = os.path.join(DATA_DIR, "parrot_relay_log.txt")
GLOBAL_CONFIG_PATH = os.path.join(DATA_DIR, "ParrotRelay.cfg")


def resource_path(name: str) -> str | None:
    """
    Finds a file that ships WITH ParrotRelay (as opposed to one the
    user provides). PyInstaller puts bundled files in sys._MEIPASS -
    the RelayData folder in a onedir build, the unpack folder in a
    onefile build - while running from source they sit next to the
    script. Returns None if the file isn't there.
    """
    candidates = [
        getattr(sys, "_MEIPASS", None),
        os.path.dirname(os.path.abspath(__file__)),
        EXE_DIR,
        RELAY_ROOT,
        TP_DIR,
    ]
    for base in candidates:
        if not base:
            continue
        candidate = os.path.join(base, name)
        if os.path.isfile(candidate):
            return candidate
    return None


def _migrate_old_locations() -> None:
    """
    Moves data written by earlier versions to where it lives now: the
    log used to sit next to TeknoParrotUi.exe, later among the runtime
    files, then in a RelayData subfolder. Best effort - a failed move
    is never worth aborting a game launch for.
    """
    if not _DATA_DIR_OK:
        return

    old_roots = [
        TP_DIR,
        os.path.join(TP_DIR, "ParrotRelay"),
        os.path.join(TP_DIR, "ParrotRelay", "RelayData"),
        os.path.join(RELAY_ROOT, "RelayData"),
    ]

    for old_root in old_roots:
        if os.path.abspath(old_root) == os.path.abspath(DATA_DIR):
            continue

        old_log = os.path.join(old_root, "parrot_relay_log.txt")
        if os.path.isfile(old_log) and not os.path.exists(LOG_PATH):
            try:
                os.replace(old_log, LOG_PATH)
            except OSError:
                pass

        old_global = os.path.join(old_root, "ParrotRelay.cfg")
        if os.path.isfile(old_global) and not os.path.exists(GLOBAL_CONFIG_PATH):
            try:
                os.replace(old_global, GLOBAL_CONFIG_PATH)
            except OSError:
                pass

        old_configs = os.path.join(old_root, "GameConfigs")
        if os.path.isdir(old_configs) and os.path.abspath(old_configs) != \
                os.path.abspath(GAME_CONFIG_DIR):
            try:
                for entry in os.listdir(old_configs):
                    target = os.path.join(GAME_CONFIG_DIR, entry)
                    if not os.path.exists(target):
                        os.replace(os.path.join(old_configs, entry), target)
                os.rmdir(old_configs)
            except OSError:
                pass


_migrate_old_locations()

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

# How long to wait per step when closing a leftover TeknoParrotUi.exe
# (politely, then terminate, then kill).
TP_CLOSE_GRACE_SECONDS = 3.0

# How long the splash stays up AFTER the game window was found, in
# milliseconds. 0 = old behaviour (close immediately). Overridable
# per game via the .cfg file and per launch via --relay-delay=<ms>.
DEFAULT_SPLASH_EXTRA_DELAY_MS = 0
# Sanity cap so a typo like --relay-delay=400000 can't freeze the
# cabinet behind a splash screen for minutes.
MAX_SPLASH_EXTRA_DELAY_MS = 60_000


# DLLs that an emulator must never pick up from our folder. RPCS3 in
# particular refuses to run when it finds a VC runtime outside the
# proper Microsoft installation, and aborts with a fatal error.
RUNTIME_DLL_NAMES = (
    "vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll",
    "concrt140.dll",
)


def _canonical_path(path: str) -> str:
    """
    Normalises a path for comparison: expands 8.3 short names
    (D:\\ROM\\TEKNOP~1) to the long form, then normcase/normpath.
    Without the short-name step two spellings of the same folder
    would compare as different.
    """
    path = path.strip().strip('"')
    if not path:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.kernel32.GetLongPathNameW(path, buffer, 32768):
            path = buffer.value
    except Exception:
        pass
    try:
        return os.path.normcase(os.path.normpath(path))
    except Exception:
        return path


def _own_directories() -> list[str]:
    """
    Every folder that belongs to ParrotRelay itself. A child process
    must not find DLLs in any of them.
    """
    directories = [
        getattr(sys, "_MEIPASS", None),
        os.path.dirname(os.path.abspath(sys.executable))
        if getattr(sys, "frozen", False) else None,
        RELAY_ROOT,
        DATA_DIR,
    ]
    return [_canonical_path(d) for d in directories if d]


def _report_runtime_dlls_on_path(path_value: str) -> None:
    """
    Logs which PATH entries actually hold a VC runtime DLL. When an
    emulator still loads the wrong one, this says exactly which
    directory it came from instead of leaving us guessing.
    """
    seen = 0
    for entry in path_value.split(os.pathsep):
        entry = entry.strip().strip('"')
        if not entry:
            continue
        try:
            names = {name.lower() for name in os.listdir(entry)}
        except OSError:
            continue
        hit = names.intersection(RUNTIME_DLL_NAMES)
        if hit:
            log(f"NOTE: child PATH offers {sorted(hit)[0]} from {entry}")
            seen += 1
        if seen >= 5:
            log("NOTE: (more entries not checked)")
            return


def system_vc_runtime_present() -> bool | None:
    """
    True if the VC runtime is properly installed in System32.

    This matters more than it looks: Windows searches System32 BEFORE
    the current directory and before PATH, so a properly installed
    runtime is always found first and our own copy is never even
    looked at. If an emulator loads OUR VCRUNTIME140.dll, that is
    proof the Microsoft redistributable is missing on this machine -
    no amount of cleaning up the environment can substitute for it.

    None on non-Windows (where the question is meaningless).
    """
    system_root = os.environ.get("SystemRoot")
    if not system_root:
        return None
    system32 = os.path.join(system_root, "System32")
    try:
        # Listing rather than isfile(): the file name's case is not
        # guaranteed, and comparing lower-cased names is exact on
        # every filesystem.
        names = {name.lower() for name in os.listdir(system32)}
    except OSError:
        return None
    return "vcruntime140.dll" in names


def log_dll_environment() -> None:
    """
    One block in the log that answers the "which VC runtime does an
    emulator get" question outright, instead of having to guess from
    an error dialog.
    """
    present = system_vc_runtime_present()
    if present is None:
        return
    if present:
        log("VC runtime: properly installed in System32 - emulators will "
            "use that one")
        return

    log("WARNING: no VCRUNTIME140.dll in System32 - the Microsoft Visual "
        "C++ 2015-2022 Redistributable is NOT installed.")
    log("WARNING: emulators such as RPCS3 will then pick up whatever copy "
        "they can find (possibly ParrotRelay's own) and refuse to start. "
        "Install it from https://aka.ms/vs/17/release/vc_redist.x64.exe")


def build_child_environment() -> dict[str, str]:
    """
    Builds the environment for TeknoParrotUi.exe (and thus for every
    game process started underneath it).

    Background: ParrotRelay ships its own copies of the Python and VC
    runtime DLLs (VCRUNTIME140.dll, python3xx.dll, ...) - in a onefile
    build in a temp folder, in a onedir build in the runtime folder.
    Child processes inherit our environment, so if one of those
    folders is on PATH, an emulator like RPCS3 loads OUR
    VCRUNTIME140.dll instead of the properly installed one and
    aborts ("The module vcruntime140.dll was incorrectly installed
    at ...").

    So the child gets a cleaned copy: every PATH entry pointing into a
    folder of ours is dropped - no matter who put it there - and
    PyInstaller's internal variables go too.
    """
    env = os.environ.copy()

    if not getattr(sys, "frozen", False):
        return env

    own = set(_own_directories())
    path = env.get("PATH", "")
    entries = path.split(os.pathsep)
    cleaned = [e for e in entries if _canonical_path(e) not in own]

    if len(cleaned) != len(entries):
        removed = [e for e in entries if _canonical_path(e) in own]
        for entry in removed:
            log(f"Removed own folder from child PATH: {entry}")
    env["PATH"] = os.pathsep.join(cleaned)

    # PyInstaller's own bookkeeping - a child must not inherit it,
    # otherwise a nested bootloader would reuse our unpack folder.
    for var in ("_MEIPASS2", "_PYI_APPLICATION_HOME_DIR",
                "_PYI_ARCHIVE_FILE", "_PYI_PARENT_PROCESS_LEVEL",
                "PYTHONPATH", "PYTHONHOME"):
        env.pop(var, None)

    _report_runtime_dlls_on_path(env["PATH"])
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


def load_image_native_size(path: str):
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

    def __init__(self, game_name: str, bg_image_path: str | None,
                 visible: bool = True):
        self.visible = visible
        self.root = tk.Tk()
        self.root.overrideredirect(True)  # no title bar/border
        self.root.attributes("-topmost", True)
        self.root.configure(bg="black")

        # With the splash turned off the window still exists (it drives
        # the monitoring loop via root.after) - it is simply never
        # shown.
        if not visible:
            self.root.withdraw()

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
            self._bg_photo = load_image_native_size(bg_image_path)
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
        gap_status_to_bar = 25
        name_line_h = 55   # approx line height at font size 40
        status_line_h = 30  # approx line height at font size 20
        bar_w = max(320, min(int(screen_w * 0.35), 900))
        bar_h = 12

        total_h = (
            (image_h + gap_image_to_name if image_h else 0)
            + name_line_h + gap_name_to_status + status_line_h
            + gap_status_to_bar + bar_h
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
        y += status_line_h + gap_status_to_bar

        # Progress bar: an outlined track with a filled part. Drawn on
        # the same canvas rather than as a ttk widget, so it inherits
        # the background image instead of sitting on a grey rectangle.
        self._bar_left = screen_w // 2 - bar_w // 2
        self._bar_right = self._bar_left + bar_w
        self._bar_top = y
        self._bar_bottom = y + bar_h
        self.canvas.create_rectangle(
            self._bar_left, self._bar_top, self._bar_right, self._bar_bottom,
            outline="#666666", width=1,
        )
        self.bar_fill_id = self.canvas.create_rectangle(
            self._bar_left, self._bar_top, self._bar_left, self._bar_bottom,
            outline="", fill="#e0e0e0",
        )
        self._indeterminate_pos = 0.0

        self.root.update_idletasks()
        # The splash is topmost anyway; grabbing the keyboard as well is
        # what lets it react to ESC.
        if visible:
            try:
                self.root.focus_force()
            except tk.TclError:
                pass
        self.root.update()

    def set_status(self, text: str) -> None:
        try:
            self.canvas.itemconfig(self.status_text_id, text=text)
        except tk.TclError:
            pass

    def set_progress(self, fraction: float | None) -> None:
        """
        Moves the bar. A fraction of 0..1 fills it accordingly; None
        means "no idea how long this takes" (no measured time yet) and
        runs a block back and forth instead, so the screen still looks
        alive without claiming a progress it cannot know.
        """
        if not self.visible:
            return

        try:
            if fraction is None:
                width = self._bar_right - self._bar_left
                block = width * 0.2
                self._indeterminate_pos = (self._indeterminate_pos + 0.012) % 1.0
                # Ping-pong: 0..1..0 instead of jumping back at the end.
                offset = self._indeterminate_pos * 2
                if offset > 1:
                    offset = 2 - offset
                left = self._bar_left + offset * (width - block)
                self.canvas.coords(self.bar_fill_id, left, self._bar_top,
                                   left + block, self._bar_bottom)
                return

            fraction = max(0.0, min(1.0, fraction))
            right = self._bar_left + (self._bar_right - self._bar_left) * fraction
            self.canvas.coords(self.bar_fill_id, self._bar_left, self._bar_top,
                               right, self._bar_bottom)
        except tk.TclError:
            pass

    def keep_on_top(self) -> None:
        """
        Re-asserts topmost while the splash is deliberately kept up
        after the game window appeared - otherwise the game window,
        which is already being drawn, would cover it.
        """
        if not self.visible:
            return
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


class Setting:
    """
    One configurable option. Kept as data rather than scattered
    literals, because the same list drives three things: the defaults
    used at runtime, the comments written into a fresh .cfg, and the
    input fields in the settings window.
    """

    def __init__(self, key: str, kind: str, default, label: str,
                 help_text: str, minimum: int = 0, maximum: int = 0):
        self.key = key
        self.kind = kind          # "bool", "int_ms" or "path"
        self.default = default
        self.label = label
        self.help_text = help_text
        self.minimum = minimum
        self.maximum = maximum


SETTINGS: tuple[Setting, ...] = (
    Setting(
        "splash_enabled", "bool", True,
        "Show loading screen",
        "Off: no loading screen for this game at all. The window\n"
        "handling (hiding TeknoParrot's windows, focusing the game)\n"
        "keeps working.",
    ),
    Setting(
        "splash_extra_delay_ms", "int_ms", 0,
        "Keep loading screen up for (ms)",
        "How much longer the loading screen stays after the game\n"
        "window appeared. For games that show their window early but\n"
        "keep loading. Example: 4000 = four extra seconds.",
        minimum=0, maximum=60_000,
    ),
    Setting(
        "splash_timeout_ms", "int_ms", 0,
        "Give up after (ms, 0 = never)",
        "Safety net: if no game window shows up within this time,\n"
        "the loading screen closes anyway instead of covering the\n"
        "screen forever. 0 keeps waiting.",
        minimum=0, maximum=600_000,
    ),
    Setting(
        "background", "path", "",
        "Background image",
        "Overrides the automatic search in LoadingBG\\ and Icons\\.\n"
        "Leave empty for the automatic choice.",
    ),
    Setting(
        "esc_cancels_launch", "bool", True,
        "ESC cancels the launch",
        "While the loading screen is up, ESC aborts: TeknoParrot and\n"
        "everything it started are ended and ParrotRelay quits. Turn\n"
        "off if ESC is wired to a cabinet button that players reach.",
    ),
    Setting(
        "close_running_teknoparrot", "bool", True,
        "Close a running TeknoParrot first",
        "Before starting a game, any TeknoParrotUi.exe that is still\n"
        "running is closed - a leftover instance from a previous game\n"
        "otherwise blocks the new one or steals the foreground.",
    ),
    Setting(
        "focus_guard", "bool", True,
        "Keep game window focused",
        "Keeps pulling the game window back to the foreground if\n"
        "something else steals focus. Turn off if it fights with the\n"
        "game (rare, e.g. games with their own launcher window).",
    ),
    Setting(
        "suppress_tp_windows", "bool", True,
        "Hide TeknoParrot windows",
        "Hides TeknoParrot's own windows before they can take focus.\n"
        "This is the actual fix for games dropping out of exclusive\n"
        "fullscreen - only turn it off for troubleshooting.",
    ),
)

SETTINGS_BY_KEY = {setting.key: setting for setting in SETTINGS}


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


def read_config_file(path: str) -> dict[str, str]:
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
    except FileNotFoundError:
        pass
    except OSError:
        log(f"Could not read config: {path}")
    except Exception:
        log("ERROR reading config:\n" + traceback.format_exc())
    return values


def parse_setting_value(setting: Setting, raw: str, source: str):
    """
    Turns a raw string from a .cfg into a real value. Anything
    unparseable is logged and reported as None, so the caller falls
    back to the next level instead of the launch failing over a typo.
    """
    raw = raw.strip().strip('"')

    if setting.kind == "bool":
        if raw.lower() in ("1", "true", "yes", "on"):
            return True
        if raw.lower() in ("0", "false", "no", "off"):
            return False
        log(f"Ignoring invalid value for {setting.key} in {source} "
            f"(expected true/false).")
        return None

    if setting.kind == "int_ms":
        try:
            value = int(float(raw))
        except (TypeError, ValueError):
            log(f"Ignoring invalid value for {setting.key} in {source} "
                f"(expected a number in milliseconds).")
            return None
        if value < setting.minimum:
            log(f"{setting.key} in {source} below {setting.minimum} - clamped.")
            return setting.minimum
        if value > setting.maximum:
            log(f"{setting.key} in {source} above {setting.maximum} - clamped.")
            return setting.maximum
        return value

    return raw  # "path" and anything else: taken as-is


def format_setting_value(setting: Setting, value) -> str:
    if setting.kind == "bool":
        return "true" if value else "false"
    return str(value)


def render_config_file(values: dict, header_lines: list[str],
                       active_keys: set[str] | None = None,
                       stats: dict | None = None) -> str:
    """
    Renders a .cfg with the header, then every setting preceded by its
    explanation. Written the same way for the global defaults and for
    a game, so both files look familiar.

    Keys not in active_keys are written as commented-out lines. That
    is how inheritance stays intact: a game only pins what actually
    differs, everything else keeps following the global defaults.
    Passing None means "all keys active".
    """
    out = [f"# {line}" if line else "#" for line in header_lines]
    out.append("#")
    out.append("# " + "-" * 66)
    out.append("# Settings")
    out.append("# " + "-" * 66)

    for setting in SETTINGS:
        out.append("#")
        out.append(f"# {setting.key}")
        for help_line in setting.help_text.splitlines():
            out.append(f"#   {help_line}")
        value = values.get(setting.key, setting.default)
        line = f"{setting.key}={format_setting_value(setting, value)}"
        if active_keys is not None and setting.key not in active_keys:
            out.append(f"#   (inherited - remove the # to pin it here)")
            line = "#" + line
        out.append(line)

    if stats:
        out.append("")
        out.append("# " + "-" * 66)
        out.append("# Measured values - written by ParrotRelay itself")
        out.append("# " + "-" * 66)
        out.append("#")
        out.append("# measured_load_ms")
        out.append("#   How long this game took from the launch until its")
        out.append("#   window appeared, in milliseconds. Written after every")
        out.append("#   launch as (new time + stored time) / 2, so it settles")
        out.append("#   on a realistic value and follows changes to the")
        out.append("#   machine. It drives the progress bar on the loading")
        out.append("#   screen. Delete the line to start measuring afresh.")
        for key, value in stats.items():
            out.append(f"{key}={value}")

    return "\n".join(out) + "\n"


def write_config_file(path: str, values: dict, header_lines: list[str],
                      active_keys: set[str] | None = None,
                      stats: dict | None = None) -> bool:
    """Writes a .cfg, replacing an existing one. True on success."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(render_config_file(values, header_lines, active_keys, stats))
        return True
    except OSError:
        log(f"Could not write config: {path}")
        return False


def game_config_header(profile_name: str, game_name: str,
                       bg_image_path: str | None) -> list[str]:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return [
        f'ParrotRelay - settings for "{game_name}"',
        f"Written on {stamp} by ParrotRelay {VERSION}.",
        "",
        'Safe to edit by hand - only the "key=value" lines are read,',
        "everything else is ignored. The settings window (start",
        "ParrotRelay.exe without arguments) edits this file too.",
        "",
        "Detected for this game:",
        f"  profile    = {profile_name}.xml",
        f"  game_name  = {game_name}",
        f"  background = {bg_image_path or '(none - plain black splash)'}",
        "",
        "Lines starting with # follow the global defaults in",
        "..\\ParrotRelay.cfg - remove the # to pin a value for this",
        "game only.",
    ]


def global_config_header() -> list[str]:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return [
        "ParrotRelay - global defaults",
        f"Written on {stamp} by ParrotRelay {VERSION}.",
        "",
        "These values apply to every game that does not set them",
        "itself in GameConfigs\\<profile>.cfg - a value set there always",
        "wins over the one here.",
    ]


def launch_progress_fraction(elapsed_ms: float, expected_load_ms: int,
                             delay_ms: int, fraction_when_found: float | None,
                             remaining_delay_ms: float) -> float:
    """
    How full the progress bar should be, quantised to whole percent -
    the bar advances in 100 steps, one per percent.

    The expected total is the stored load time plus the extra delay,
    so one percent is total/100 and the bar simply follows the clock:

        fraction = elapsed / (load time + delay)

    Two things the plain clock can't know are handled on top:

      - while the game window has not appeared, the bar stops at 99%
        instead of claiming to be done. A launch that takes longer
        than usual keeps creeping towards it rather than sitting at
        100% while nothing has happened.
      - once the window IS there, the remaining time is known exactly
        (it is the delay), so the bar runs from wherever it got to up
        to 100%, arriving precisely when the loading screen closes.
        That also covers a launch that was faster than predicted.
    """
    total_ms = expected_load_ms + delay_ms
    if total_ms <= 0:
        return 1.0

    if fraction_when_found is None:
        return min(int(elapsed_ms / total_ms * 100), 99) / 100

    if delay_ms > 0:
        delay_done = 1.0 - min(1.0, max(0.0, remaining_delay_ms) / delay_ms)
        fraction = fraction_when_found + delay_done * (1.0 - fraction_when_found)
        return int(fraction * 100) / 100

    return 1.0


MEASURED_LOAD_KEY = "measured_load_ms"

# A measured load time is only believable within these bounds: below
# that the window came from something other than the game starting,
# above it the launch clearly went wrong (crash dialog, missing ROM)
# and would poison the average for every following launch.
MIN_MEASURED_LOAD_MS = 200
MAX_MEASURED_LOAD_MS = 600_000


def read_measured_load_ms(profile_name: str | None) -> int | None:
    """
    The stored load time for this game, or None if there isn't one
    yet (first launch, or the line was deleted to start afresh).
    """
    path = game_config_path(profile_name)
    if not path or not os.path.isfile(path):
        return None

    raw = read_config_file(path).get(MEASURED_LOAD_KEY)
    if raw is None:
        return None
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        log(f"Ignoring invalid {MEASURED_LOAD_KEY} in {os.path.basename(path)}")
        return None
    return value if value > 0 else None


def pinned_setting_keys(path: str) -> set[str]:
    """Which setting keys a game's file actually pins (non-commented)."""
    return {key for key in read_config_file(path) if key in SETTINGS_BY_KEY}


def store_measured_load_ms(profile_name: str | None, game_name: str,
                           measured_ms: int) -> None:
    """
    Folds the time this launch took into the game's config:
    nothing stored yet -> the measured time as-is, otherwise the
    average of the measured and the stored one. Two launches in a row
    therefore move the value halfway towards reality, which tracks a
    changed machine without a single odd launch throwing it off.

    The user's own settings in that file are kept exactly as they
    are, pinned lines included.
    """
    path = game_config_path(profile_name)
    if not path:
        return

    if not MIN_MEASURED_LOAD_MS <= measured_ms <= MAX_MEASURED_LOAD_MS:
        log(f"Load time of {measured_ms} ms is outside the believable range "
            f"({MIN_MEASURED_LOAD_MS}-{MAX_MEASURED_LOAD_MS} ms) - not stored")
        return

    stored = read_measured_load_ms(profile_name)
    new_value = measured_ms if stored is None else (measured_ms + stored) // 2

    values = {setting.key: setting.default for setting in SETTINGS}
    active: set[str] = set()
    if os.path.isfile(path):
        raw_values = read_config_file(path)
        for key, raw in raw_values.items():
            setting = SETTINGS_BY_KEY.get(key)
            if setting is None:
                continue
            parsed = parse_setting_value(setting, raw, os.path.basename(path))
            if parsed is not None:
                values[key] = parsed
                active.add(key)

    if write_config_file(path, values,
                         game_config_header(profile_name or "?", game_name,
                                            find_background_image(profile_name)),
                         active_keys=active,
                         stats={MEASURED_LOAD_KEY: new_value}):
        if stored is None:
            log(f"Load time measured: {measured_ms} ms (first one, stored as is)")
        else:
            log(f"Load time measured: {measured_ms} ms, stored was {stored} ms "
                f"-> new average {new_value} ms")


def resolve_settings(profile_name: str | None, game_name: str,
                     bg_image_path: str | None,
                     cli_delay_ms: int | None) -> dict:
    """
    Builds the effective settings for this launch and makes sure the
    game's .cfg exists.

    Precedence, most specific first:
        command line  >  game .cfg  >  global .cfg  >  built-in default

    The command line wins because it is the per-launch statement (one
    HyperSpin entry that needs more time), the game file beats the
    global one for the obvious reason.
    """
    values = {setting.key: setting.default for setting in SETTINGS}
    sources = {setting.key: "default" for setting in SETTINGS}

    def apply(raw_values: dict[str, str], source_label: str) -> None:
        for key, raw in raw_values.items():
            setting = SETTINGS_BY_KEY.get(key)
            if setting is None:
                continue  # unknown key - leave it alone, it's the user's file
            parsed = parse_setting_value(setting, raw, source_label)
            if parsed is not None:
                values[key] = parsed
                sources[key] = source_label

    if os.path.isfile(GLOBAL_CONFIG_PATH):
        apply(read_config_file(GLOBAL_CONFIG_PATH), "ParrotRelay.cfg")

    path = game_config_path(profile_name)
    if path is not None:
        if not os.path.isfile(path):
            # Fresh file: every value is still inherited, so nothing is
            # pinned yet - the file documents the options and shows
            # what is currently in effect.
            if write_config_file(path, values,
                                 game_config_header(profile_name or "?",
                                                    game_name, bg_image_path),
                                 active_keys=set()):
                log(f"Game config created: {path}")
        else:
            apply(read_config_file(path), os.path.basename(path))

    if cli_delay_ms is not None:
        values["splash_extra_delay_ms"] = cli_delay_ms
        sources["splash_extra_delay_ms"] = "command line"

    for setting in SETTINGS:
        if sources[setting.key] != "default":
            log(f"Setting {setting.key} = "
                f"{format_setting_value(setting, values[setting.key])} "
                f"(from {sources[setting.key]})")

    return values


# ---------------------------------------------------------------------
# Settings window (shown when started without arguments)
# ---------------------------------------------------------------------

def list_known_games() -> list[tuple[str, str]]:
    """
    Every game the settings window can offer: all TeknoParrot user
    profiles, plus profiles that only exist as a ParrotRelay config
    (e.g. a game removed from TP again). Returns (profile, game name)
    sorted by game name.
    """
    profiles: set[str] = set()

    for directory, suffix in ((USER_PROFILES_DIR, ".xml"),
                              (GAME_CONFIG_DIR, ".cfg")):
        try:
            for entry in os.listdir(directory):
                if entry.lower().endswith(suffix):
                    profiles.add(entry[: -len(suffix)])
        except OSError:
            pass

    games = [(profile, lookup_game_name(profile)) for profile in profiles]
    games.sort(key=lambda item: item[1].lower())
    return games


def open_in_explorer(path: str) -> None:
    """Opens a file or folder in Explorer. Windows-only, by design."""
    try:
        os.startfile(path)  # type: ignore[attr-defined]
    except Exception:
        log(f"Could not open: {path}\n" + traceback.format_exc())


class SettingsWindow:
    """
    The window that comes up when ParrotRelay.exe is started without
    arguments - i.e. by double-clicking it, rather than by HyperSpin.

    Edits the same .cfg files that can be edited by hand: the global
    defaults on the left-hand entry, one file per game below it. A
    game only stores what actually differs from the global defaults,
    so changing a default still reaches every game that never
    overrode it.
    """

    GLOBAL_ITEM = "— Global defaults —"

    def __init__(self) -> None:
        from tkinter import ttk

        self.root = tk.Tk()
        self.root.title(f"ParrotRelay {VERSION} - Settings")
        self._default_geometry = (980, 620)
        # default=... so every window of this app gets the icon, the
        # preview window included - not just the main one.
        icon = resource_path("icon.ico")
        if icon:
            try:
                self.root.iconbitmap(default=icon)
            except tk.TclError:
                log(f"Could not apply the window icon: {icon}")

        # Created in _build_layout; the search box's change callback can
        # fire before that, so it must be able to tell.
        self.tree = None
        self.games = list_known_games()
        self.current_profile: str | None = None   # None = global defaults
        self.vars: dict[str, tk.Variable] = {}
        self.dirty = False

        self.style = ttk.Style()
        try:
            self.style.theme_use("vista")
        except tk.TclError:
            pass

        self._build_layout()
        self._refresh_game_list()
        self._select_global()

        # Don't let the window be dragged smaller than its contents
        # need - that is what used to cut the buttons off at the
        # bottom. Capped to the screen so it stays usable on a small
        # cabinet display.
        self.root.update_idletasks()
        min_w = min(max(820, self.root.winfo_reqwidth()),
                    self.root.winfo_screenwidth())
        min_h = min(self.root.winfo_reqheight(),
                    self.root.winfo_screenheight() - 60)
        self.root.minsize(min_w, min_h)
        self.root.geometry(f"{max(self._default_geometry[0], min_w)}x"
                           f"{max(self._default_geometry[1], min_h)}")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- layout --------------------------------------------------------

    def _build_layout(self) -> None:
        from tkinter import ttk

        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)

        # Packing order is allocation order: whatever is packed first
        # keeps its height when the window gets too small. So the
        # footer and the status line go in first (from the bottom up),
        # and the stretching panes take whatever is left - otherwise
        # shrinking the window cuts the buttons off.
        # wraplength keeps the long paths in these lines from dictating
        # how wide the window has to be.
        self.status_var = tk.StringVar(value=self._environment_summary())
        ttk.Label(outer, textvariable=self.status_var, foreground="#555555",
                  wraplength=780, justify="left").pack(
            side="bottom", anchor="w", pady=(8, 0))

        footer = ttk.Frame(outer)
        footer.pack(side="bottom", fill="x", pady=(10, 0))
        ttk.Separator(outer, orient="horizontal").pack(
            side="bottom", fill="x", pady=(6, 0))

        ttk.Button(footer, text="Open ParrotRelay folder",
                   command=lambda: open_in_explorer(DATA_DIR)).pack(side="left")
        ttk.Button(footer, text="Open log",
                   command=self._open_log).pack(side="left", padx=6)
        ttk.Button(footer, text="Apply to all games...",
                   command=self._apply_to_all).pack(side="left")
        ttk.Button(footer, text="Close",
                   command=self._on_close).pack(side="right")

        panes = ttk.PanedWindow(outer, orient="horizontal")
        panes.pack(fill="both", expand=True)

        # Left: search + game list
        left = ttk.Frame(panes, padding=(0, 0, 8, 0))
        panes.add(left, weight=1)

        ttk.Label(left, text="Game").pack(anchor="w")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_game_list())
        search = ttk.Entry(left, textvariable=self.search_var)
        search.pack(fill="x", pady=(2, 6))
        self._add_placeholder(search, "Search...")

        list_frame = ttk.Frame(left)
        list_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            list_frame, columns=("configured",), show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Game")
        self.tree.heading("configured", text="Configured")
        self.tree.column("#0", width=220)
        self.tree.column("configured", width=90, anchor="center", stretch=False)
        self.tree.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(list_frame, orient="vertical",
                               command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # Right: the settings for whatever is selected
        right = ttk.Frame(panes, padding=(8, 0, 0, 0))
        panes.add(right, weight=2)

        header = ttk.Frame(right)
        header.pack(fill="x")

        self.title_var = tk.StringVar()
        ttk.Label(header, textvariable=self.title_var,
                  font=("Segoe UI", 13, "bold")).pack(side="left")
        ttk.Label(header, text=f"ParrotRelay {VERSION}",
                  foreground="#888888").pack(side="right")

        self.subtitle_var = tk.StringVar()
        ttk.Label(right, textvariable=self.subtitle_var, foreground="#555555",
                  wraplength=460, justify="left").pack(anchor="w",
                                                       pady=(0, 10))

        # Buttons for the current entry - packed before the form for
        # the same reason as the footer above.
        actions = ttk.Frame(right)
        actions.pack(side="bottom", fill="x", pady=(10, 0))

        self.form = ttk.Frame(right)
        self.form.pack(fill="both", expand=True)
        self._build_form()
        ttk.Button(actions, text="Save",
                   command=self._save).pack(side="left")
        ttk.Button(actions, text="Revert",
                   command=self._load_current).pack(side="left", padx=6)
        self.inherit_button = ttk.Button(
            actions, text="Use global defaults", command=self._inherit_all)
        self.inherit_button.pack(side="left")
        self.pin_button = ttk.Button(
            actions, text="Pin all values", command=self._pin_all)
        self.pin_button.pack(side="left", padx=6)
        ttk.Button(actions, text="Preview loading screen",
                   command=self._preview).pack(side="right")


    def _build_form(self) -> None:
        from tkinter import ttk

        for row, setting in enumerate(SETTINGS):
            ttk.Label(self.form, text=setting.label).grid(
                row=row * 2, column=0, sticky="w", pady=(6, 0))

            if setting.kind == "bool":
                var: tk.Variable = tk.BooleanVar()
                widget = ttk.Checkbutton(self.form, variable=var,
                                         command=self._mark_dirty)
                widget.grid(row=row * 2, column=1, sticky="w", pady=(6, 0))
            elif setting.kind == "int_ms":
                var = tk.StringVar()
                var.trace_add("write", lambda *_: self._mark_dirty())
                widget = ttk.Spinbox(
                    self.form, textvariable=var, width=12,
                    from_=setting.minimum, to=setting.maximum, increment=500,
                )
                widget.grid(row=row * 2, column=1, sticky="w", pady=(6, 0))
            else:
                var = tk.StringVar()
                var.trace_add("write", lambda *_: self._mark_dirty())
                box = ttk.Frame(self.form)
                box.grid(row=row * 2, column=1, sticky="ew", pady=(6, 0))
                ttk.Entry(box, textvariable=var, width=30).pack(
                    side="left", fill="x", expand=True)
                ttk.Button(box, text="Browse...", width=10,
                           command=self._browse_background).pack(
                    side="left", padx=(6, 0))

            # wraplength so a long explanation re-flows instead of
            # forcing the whole window to be that wide.
            ttk.Label(self.form, text=setting.help_text.replace("\n", " "),
                      foreground="#555555", wraplength=380,
                      justify="left").grid(
                row=row * 2 + 1, column=0, columnspan=2, sticky="w")

            self.vars[setting.key] = var

        self.form.columnconfigure(1, weight=1)

    def _add_placeholder(self, entry, text: str) -> None:
        """Grey hint text that disappears on focus. Purely cosmetic."""
        def on_focus_in(_):
            if entry.get() == text:
                entry.delete(0, "end")
                entry.configure(foreground="")

        def on_focus_out(_):
            if not entry.get():
                entry.insert(0, text)
                entry.configure(foreground="#888888")

        entry.insert(0, text)
        entry.configure(foreground="#888888")
        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)
        self._search_placeholder = text

    # -- data ----------------------------------------------------------

    def _search_text(self) -> str:
        text = self.search_var.get().strip()
        if text == getattr(self, "_search_placeholder", None):
            return ""
        return text.lower()

    def _refresh_game_list(self) -> None:
        if self.tree is None:
            return
        needle = self._search_text()
        selected = self.current_profile

        self.tree.delete(*self.tree.get_children())
        self.tree.insert("", "end", iid="__global__", text=self.GLOBAL_ITEM,
                         values=("",))

        for profile, name in self.games:
            if needle and needle not in name.lower() and \
                    needle not in profile.lower():
                continue
            path = game_config_path(profile)
            pinned = ""
            if path and os.path.isfile(path):
                pinned = str(len(self._pinned_keys(path))) or ""
                pinned = pinned if pinned != "0" else "-"
            self.tree.insert("", "end", iid=profile,
                             text=f"{name}  ({profile})", values=(pinned,))

        target = selected if selected and self.tree.exists(selected) \
            else "__global__"
        self.tree.selection_set(target)

    def _pinned_keys(self, path: str) -> set[str]:
        """Keys a game's file actually pins (i.e. non-commented)."""
        return pinned_setting_keys(path)

    def _stats_of(self, profile: str | None) -> dict | None:
        """
        The measured values stored for a game, so saving from here
        keeps them instead of throwing the measurement away.
        """
        measured = read_measured_load_ms(profile) if profile else None
        return {MEASURED_LOAD_KEY: measured} if measured else None

    def _global_values(self) -> dict:
        values = {setting.key: setting.default for setting in SETTINGS}
        for key, raw in read_config_file(GLOBAL_CONFIG_PATH).items():
            setting = SETTINGS_BY_KEY.get(key)
            if setting is None:
                continue
            parsed = parse_setting_value(setting, raw, "ParrotRelay.cfg")
            if parsed is not None:
                values[key] = parsed
        return values

    def _effective_values(self, profile: str | None) -> dict:
        values = self._global_values()
        if profile is None:
            return values
        path = game_config_path(profile)
        if path and os.path.isfile(path):
            for key, raw in read_config_file(path).items():
                setting = SETTINGS_BY_KEY.get(key)
                if setting is None:
                    continue
                parsed = parse_setting_value(setting, raw,
                                             os.path.basename(path))
                if parsed is not None:
                    values[key] = parsed
        return values

    # -- selection / loading -------------------------------------------

    def _on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        if self.dirty and not self._confirm_discard():
            # Put the selection back where it was.
            target = self.current_profile or "__global__"
            if self.tree.exists(target):
                self.tree.selection_set(target)
            return

        item = selection[0]
        self.current_profile = None if item == "__global__" else item
        self._load_current()

    def _select_global(self) -> None:
        self.current_profile = None
        self.tree.selection_set("__global__")
        self._load_current()

    def _load_current(self) -> None:
        profile = self.current_profile
        values = self._effective_values(profile)

        for setting in SETTINGS:
            var = self.vars[setting.key]
            if setting.kind == "bool":
                var.set(bool(values[setting.key]))
            else:
                var.set(str(values[setting.key]))

        if profile is None:
            self.title_var.set("Global defaults")
            self.subtitle_var.set(
                f"Applies to every game that does not override it  -  "
                f"{GLOBAL_CONFIG_PATH}")
            self.inherit_button.state(["disabled"])
            self.pin_button.state(["disabled"])
        else:
            name = dict(self.games).get(profile, profile)
            path = game_config_path(profile) or "?"
            pinned = self._pinned_keys(path) if os.path.isfile(path) else set()
            bg = find_background_image(profile)
            self.title_var.set(name)
            measured = read_measured_load_ms(profile)
            measured_text = (f"{measured / 1000:.1f} s measured load time"
                             if measured else "load time not measured yet")
            self.subtitle_var.set(
                f"Profile {profile}.xml   -   "
                f"{len(pinned)} of {len(SETTINGS)} settings set for this game"
                f"   -   {measured_text}"
                f"   -   background: {bg or 'none found'}")
            self.inherit_button.state(["!disabled"])
            self.pin_button.state(["!disabled"])

        self.dirty = False

    def _mark_dirty(self) -> None:
        self.dirty = True

    # -- actions -------------------------------------------------------

    def _collect_values(self) -> dict | None:
        from tkinter import messagebox

        values = {}
        for setting in SETTINGS:
            raw = self.vars[setting.key].get()
            if setting.kind == "bool":
                values[setting.key] = bool(raw)
                continue
            if setting.kind == "int_ms":
                try:
                    number = int(float(str(raw).strip() or 0))
                except ValueError:
                    messagebox.showerror(
                        "ParrotRelay",
                        f"{setting.label}: \"{raw}\" is not a number.",
                        parent=self.root)
                    return None
                if not setting.minimum <= number <= setting.maximum:
                    messagebox.showerror(
                        "ParrotRelay",
                        f"{setting.label}: must be between "
                        f"{setting.minimum} and {setting.maximum}.",
                        parent=self.root)
                    return None
                values[setting.key] = number
                continue
            values[setting.key] = str(raw).strip()
        return values

    def _save(self) -> None:
        from tkinter import messagebox

        values = self._collect_values()
        if values is None:
            return

        if self.current_profile is None:
            ok = write_config_file(GLOBAL_CONFIG_PATH, values,
                                   global_config_header())
            target = GLOBAL_CONFIG_PATH
        else:
            profile = self.current_profile
            # Only pin what actually differs from the global defaults,
            # so a later change to those still reaches this game.
            inherited = self._global_values()
            active = {key for key, value in values.items()
                      if value != inherited[key]}
            name = dict(self.games).get(profile, profile)
            ok = write_config_file(
                game_config_path(profile), values,
                game_config_header(profile, name,
                                   find_background_image(profile)),
                active_keys=active, stats=self._stats_of(profile))
            target = game_config_path(profile) or "?"

        if not ok:
            messagebox.showerror(
                "ParrotRelay", f"Could not write:\n{target}",
                parent=self.root)
            return

        self.dirty = False
        self._refresh_game_list()
        self._load_current()
        self.status_var.set(f"Saved: {target}")

    def _inherit_all(self) -> None:
        """Drops every value pinned for this game."""
        from tkinter import messagebox

        profile = self.current_profile
        if profile is None:
            return
        name = dict(self.games).get(profile, profile)
        if not messagebox.askyesno(
                "ParrotRelay",
                f"Drop all settings stored for \"{name}\" and follow the "
                f"global defaults again?", parent=self.root):
            return

        values = self._global_values()
        write_config_file(game_config_path(profile), values,
                          game_config_header(profile, name,
                                             find_background_image(profile)),
                          active_keys=set(), stats=self._stats_of(profile))
        self._refresh_game_list()
        self._load_current()
        self.status_var.set(f"\"{name}\" follows the global defaults again")

    def _pin_all(self) -> None:
        """
        Writes every value as an explicit line for this game, even the
        ones that currently match the global defaults. For when a game
        should be nailed down as it is and stay that way no matter
        what the defaults do later.
        """
        values = self._collect_values()
        if values is None:
            return
        profile = self.current_profile
        if profile is None:
            return

        name = dict(self.games).get(profile, profile)
        if not write_config_file(
                game_config_path(profile), values,
                game_config_header(profile, name,
                                   find_background_image(profile)),
                active_keys={setting.key for setting in SETTINGS},
                stats=self._stats_of(profile)):
            return

        self.dirty = False
        self._refresh_game_list()
        self._load_current()
        self.status_var.set(f"All values pinned for \"{name}\"")

    def _apply_to_all(self) -> None:
        """
        Writes the values currently shown to every listed game. Handy
        for a cabinet where all games want the same extra delay.
        """
        from tkinter import messagebox

        values = self._collect_values()
        if values is None:
            return
        if not messagebox.askyesno(
                "ParrotRelay",
                f"Write these settings to all {len(self.games)} games?\n\n"
                f"This overwrites what is stored for each game.",
                parent=self.root):
            return

        inherited = self._global_values()
        active = {key for key, value in values.items()
                  if value != inherited[key]}
        written = 0
        for profile, name in self.games:
            if write_config_file(
                    game_config_path(profile), values,
                    game_config_header(profile, name,
                                       find_background_image(profile)),
                    active_keys=active, stats=self._stats_of(profile)):
                written += 1

        self._refresh_game_list()
        self._load_current()
        self.status_var.set(f"Settings written to {written} games")

    def _browse_background(self) -> None:
        from tkinter import filedialog

        exts = NATIVE_IMAGE_EXTS + (PILLOW_IMAGE_EXTS if _PILLOW_AVAILABLE
                                    else ())
        path = filedialog.askopenfilename(
            parent=self.root, title="Choose background image",
            initialdir=LOADING_BG_DIR if os.path.isdir(LOADING_BG_DIR)
            else TP_DIR,
            filetypes=[("Images", " ".join(f"*{ext}" for ext in exts)),
                       ("All files", "*.*")],
        )
        if path:
            self.vars["background"].set(os.path.normpath(path))

    def _preview(self) -> None:
        """
        Shows the loading screen exactly as it will look at launch,
        for three seconds - the quickest way to check whether the
        background image is the right one.
        """
        values = self._collect_values()
        if values is None:
            return

        profile = self.current_profile
        name = dict(self.games).get(profile, "Game") if profile else "Game"
        background = values["background"].strip() or \
            (find_background_image(profile) if profile else None)

        preview = tk.Toplevel(self.root)
        preview.overrideredirect(True)
        preview.attributes("-topmost", True)
        preview.configure(bg="black")
        width = preview.winfo_screenwidth()
        height = preview.winfo_screenheight()
        preview.geometry(f"{width}x{height}+0+0")

        canvas = tk.Canvas(preview, width=width, height=height, bg="black",
                           highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        photo = None
        if background and os.path.isfile(background):
            photo = load_image_native_size(background)
        offset = 0
        if photo:
            offset = photo.height() // 2 + 20
            canvas.create_image(width // 2, height // 2 - 40, image=photo,
                                anchor="center")
        canvas.create_text(width // 2, height // 2 + offset, text=name,
                           fill="white", font=("Segoe UI", 40, "bold"))
        canvas.create_text(width // 2, height // 2 + offset + 60,
                           text="Loading...  (preview closes in 3 s)",
                           fill="#cccccc", font=("Segoe UI", 18))
        preview.bind("<Escape>", lambda _: preview.destroy())
        preview.after(3000, preview.destroy)
        preview._photo = photo  # keep a reference alive

    def _open_log(self) -> None:
        from tkinter import messagebox

        if not os.path.isfile(LOG_PATH):
            messagebox.showinfo(
                "ParrotRelay",
                "No log yet - it is written the first time a game is "
                "launched through ParrotRelay.", parent=self.root)
            return
        open_in_explorer(LOG_PATH)

    def _environment_summary(self) -> str:
        tp = "TeknoParrotUi.exe found" if os.path.isfile(TP_EXE) \
            else "WARNING: TeknoParrotUi.exe NOT found next to ParrotRelay.exe"
        parts = [f"ParrotRelay {VERSION}", tp, f"{len(self.games)} games"]
        if system_vc_runtime_present() is False:
            parts.append("WARNING: Visual C++ 2015-2022 Redistributable "
                         "missing - emulators may refuse to start")
        parts.append(f"data: {DATA_DIR}")
        return "   |   ".join(parts)

    def _confirm_discard(self) -> bool:
        from tkinter import messagebox
        return messagebox.askyesno(
            "ParrotRelay", "Discard unsaved changes?", parent=self.root)

    def _on_close(self) -> None:
        if self.dirty and not self._confirm_discard():
            return
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def run_settings_gui() -> None:
    log("Started without arguments - opening the settings window")
    try:
        SettingsWindow().run()
    except Exception:
        log("ERROR in the settings window:\n" + traceback.format_exc())
        raise


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


def terminate_processes(procs: list, what: str) -> list:
    """
    Ends the given processes: WM_CLOSE to their windows first, then
    terminate, then kill - each step only for what is still alive
    after the previous one. Returns whatever survived all of it.

    A process we are not allowed to touch (running elevated while
    ParrotRelay is not) is logged rather than silently ignored: the
    user needs to know why it is still there.
    """
    if not procs:
        return []

    pids = {proc.pid for proc in procs}
    for hwnd in find_windows_of_pids(pids):
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception:
            pass

    _, alive = psutil.wait_procs(procs, timeout=TP_CLOSE_GRACE_SECONDS)

    for proc in alive:
        try:
            proc.terminate()
        except psutil.NoSuchProcess:
            pass
        except psutil.AccessDenied:
            log(f"WARNING: not allowed to close {what} (PID {proc.pid}) - is "
                f"it running as administrator while ParrotRelay is not?")

    _, alive = psutil.wait_procs(alive, timeout=TP_CLOSE_GRACE_SECONDS)

    for proc in alive:
        try:
            proc.kill()
            log(f"{what} (PID {proc.pid}) did not react - killed")
        except psutil.NoSuchProcess:
            pass
        except psutil.AccessDenied:
            pass

    _, still_alive = psutil.wait_procs(alive, timeout=TP_CLOSE_GRACE_SECONDS)
    return still_alive


def close_running_teknoparrot() -> None:
    """
    Closes every TeknoParrotUi.exe that is still running before a new
    one is started. A leftover instance from a previous game keeps its
    profile locked, pops its window into the foreground, or simply
    refuses to let a second one start.

    Asks politely first (WM_CLOSE to its windows), then terminates,
    then kills - each step only for what is still alive afterwards.
    A process we are not allowed to touch (TP running elevated while
    ParrotRelay is not) is logged rather than silently ignored: the
    user needs to know why the leftover is still there.
    """
    victims = []
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name != "teknoparrotui.exe":
                continue
            if proc.pid == os.getpid():
                continue
            victims.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not victims:
        return

    for proc in victims:
        log(f"TeknoParrotUi.exe already running (PID {proc.pid}, "
            f"{proc.info.get('exe') or 'path unknown'}) - closing it first")

    still_alive = terminate_processes(victims, "TeknoParrotUi.exe")
    if still_alive:
        log(f"WARNING: {len(still_alive)} TeknoParrotUi.exe process(es) could "
            f"not be closed - starting the new one anyway")
    else:
        log("Previous TeknoParrotUi.exe closed")


def collect_launch_processes(tp_pid: int, game_pid: int | None) -> list:
    """
    The whole tree belonging to this launch: TeknoParrotUi.exe, every
    process below it, and the detected game (which TP may have
    reparented away, so it is looked up separately).
    """
    procs = {}

    def add(pid: int) -> None:
        try:
            proc = psutil.Process(pid)
            procs[proc.pid] = proc
            for child in proc.children(recursive=True):
                procs[child.pid] = child
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    add(tp_pid)
    if game_pid is not None:
        add(game_pid)
    return list(procs.values())


def find_windows_of_pids(pids: set[int]) -> list[int]:
    """All visible top-level windows belonging to any of these PIDs."""
    windows = []

    def callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            return
        if pid in pids:
            windows.append(hwnd)

    try:
        win32gui.EnumWindows(callback, None)
    except Exception:
        log("ERROR in EnumWindows (windows of PIDs):\n" + traceback.format_exc())

    return windows


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
    log(f"ParrotRelay {VERSION} started")
    log(f"TP_DIR   = {TP_DIR}")
    log(f"TP_EXE   = {TP_EXE}")
    log(f"Args     = {sys.argv[1:]}")
    log(f"Elevated = {is_admin()}")
    log(f"Runtime  = {describe_runtime_mode()}")
    log(f"Workdir  = {os.getcwd()}")
    log_dll_environment()
    cleanup_stale_runtime_dirs()

    if not os.path.isfile(TP_EXE) and sys.argv[1:]:
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

    # Started by hand (double-click) rather than by HyperSpin: there is
    # no game to launch, so show the settings window instead.
    if not args:
        run_settings_gui()
        return
    profile_name = extract_profile_name(args)
    game_name = lookup_game_name(profile_name)
    bg_image_path = find_background_image(profile_name)
    settings = resolve_settings(profile_name, game_name, bg_image_path,
                                cli_delay_ms)

    # An explicit background from the config wins over the automatic
    # search - that's the whole point of the setting.
    configured_bg = settings["background"].strip()
    if configured_bg:
        if os.path.isfile(configured_bg):
            bg_image_path = configured_bg
        else:
            log(f"Configured background not found: {configured_bg}")

    splash_extra_delay_ms = settings["splash_extra_delay_ms"]
    splash_timeout_ms = settings["splash_timeout_ms"]

    if settings["close_running_teknoparrot"]:
        close_running_teknoparrot()

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
    launch_started_at = time.monotonic()
    log(f"TeknoParrotUi.exe started, PID={tp_pid}")

    # What the progress bar aims at: the stored load time for this game
    # plus the extra delay, since the bar is meant to run out exactly
    # when the loading screen disappears. Without a stored time the bar
    # has nothing to predict and runs indeterminate instead.
    expected_load_ms = read_measured_load_ms(profile_name)
    if expected_load_ms:
        log(f"Expected load time for this game: {expected_load_ms} ms "
            f"(+ {splash_extra_delay_ms} ms extra delay)")
    else:
        log("No load time measured for this game yet - the progress bar "
            "runs indeterminate and the time is stored after this launch")

    splash = SplashScreen(game_name, bg_image_path,
                          visible=settings["splash_enabled"])
    if settings["splash_enabled"]:
        log(f"Splash screen shown for '{game_name}' "
            f"(profile: {profile_name or '?'})")
    else:
        log(f"Splash screen disabled for '{game_name}' "
            f"(profile: {profile_name or '?'}) - window handling only")

    def update_progress() -> None:
        """
        Feeds the bar. With no measured time for this game there is
        nothing to predict, so it runs indeterminate instead.
        """
        elapsed_ms = (time.monotonic() - launch_started_at) * 1000

        if not expected_load_ms:
            splash.set_progress(None)
            return

        remaining_delay_ms = 0.0
        if state["splash_close_at"] is not None:
            remaining_delay_ms = max(
                0.0, (state["splash_close_at"] - time.monotonic()) * 1000)

        fraction = launch_progress_fraction(
            elapsed_ms, expected_load_ms, splash_extra_delay_ms,
            state["progress_when_found"], remaining_delay_ms)

        splash.set_progress(fraction)
        splash.set_status(f"Loading...  {int(fraction * 100)}%")

    def cancel_launch(_event=None) -> None:
        """
        ESC on the loading screen: stop the whole launch. Ending just
        ParrotRelay would leave TeknoParrot and a half-started game
        behind, which is exactly the mess this is meant to get out of.
        """
        if state["cancelled"]:
            return
        state["cancelled"] = True

        log("ESC pressed - cancelling the launch")
        splash.set_status("Cancelling...")
        try:
            splash.root.update()
        except tk.TclError:
            pass

        procs = collect_launch_processes(tp_pid, state["game_pid_seen"])
        log(f"Ending {len(procs)} process(es) belonging to this launch")
        still_alive = terminate_processes(procs, "launched process")
        if still_alive:
            log(f"WARNING: {len(still_alive)} process(es) survived the "
                f"cancellation")

        if not state["splash_closed"]:
            splash.close()
            state["splash_closed"] = True
        splash.root.quit()

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
        # Deadline for the "no game window ever showed up" safety net.
        "give_up_at": (time.monotonic() + splash_timeout_ms / 1000.0
                       if splash_timeout_ms > 0 else None),
        "cancelled": False,
        # Filled in the moment the game window shows up: that is the
        # load time, without the extra delay that follows it.
        "measured_load_ms": None,
        # Where the bar stood at that moment - the delay phase runs
        # from there to 100%.
        "progress_when_found": None,
    }

    if settings["esc_cancels_launch"] and settings["splash_enabled"]:
        splash.root.bind("<Escape>", cancel_launch)
        log("ESC cancels the launch while the loading screen is up")

    def tick() -> None:
        if state["cancelled"]:
            return
        tp_launcher_running = proc.poll() is None

        if not tp_launcher_running and not state["tp_launcher_exited_logged"]:
            log(f"TeknoParrotUi.exe (launcher stub) exited, "
                f"exit code={proc.returncode} - proxy stays alive as "
                f"long as the actual game is still running.")
            state["tp_launcher_exited_logged"] = True

        # 1) Actively hide TP-owned windows (main window, "Game is
        #    running") BEFORE they can ever take focus/foreground.
        if tp_launcher_running and settings["suppress_tp_windows"]:
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

            if state["measured_load_ms"] is None:
                state["measured_load_ms"] = int(
                    (time.monotonic() - launch_started_at) * 1000)
                if expected_load_ms:
                    state["progress_when_found"] = launch_progress_fraction(
                        state["measured_load_ms"], expected_load_ms,
                        splash_extra_delay_ms, None, 0.0)
                store_measured_load_ms(profile_name, game_name,
                                       state["measured_load_ms"])

            if state["splash_closed"] and settings["focus_guard"]:
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

            # Safety net: never leave the screen covered forever if a
            # game window simply never appears.
            if state["give_up_at"] is not None and \
                    time.monotonic() >= state["give_up_at"]:
                splash.close()
                state["splash_closed"] = True
                log(f"No game window after {splash_timeout_ms} ms - "
                    f"loading screen closed (splash_timeout_ms).")

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

        if not state["splash_closed"]:
            update_progress()

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
