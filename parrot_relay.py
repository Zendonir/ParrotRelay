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
    pyinstaller --onefile --noconsole --icon=icon.ico --name ParrotRelay parrot_relay.py

Note on admin rights: TeknoParrotUi.exe itself starts fine without
elevating the proxy, and HyperHQ (not elevated) can't spawn an
elevated proxy via spawn() anyway (Windows refuses with EACCES).
That's why --uac-admin is deliberately NOT used.

Copy the finished ParrotRelay.exe from dist\ to D:\ROM\TeknoParrot\
(i.e. right next to TeknoParrotUi.exe).

HyperSpin 2 configuration:
    Platform Path: D:\ROM\TeknoParrot\ParrotRelay.exe
    Command Line:  --startMinimized --profile=%rom.filename%.xml
    (unchanged - the proxy passes it through 1:1)

Log:
    parrot_relay_log.txt is created in the same folder as the exe and
    appended to on every run (not overwritten), so multiple runs can
    be compared afterwards.
"""

import sys
import os
import re
import subprocess
import time
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
LOG_PATH = os.path.join(TP_DIR, "parrot_relay_log.txt")
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

    if not os.path.isfile(TP_EXE):
        log(f"ERROR: {TP_EXE} not found - aborting.")
        ctypes.windll.user32.MessageBoxW(
            0,
            f"TeknoParrotUi.exe not found in:\n{TP_DIR}",
            "ParrotRelay",
            0x10,
        )
        return

    args = sys.argv[1:]
    profile_name = extract_profile_name(args)
    game_name = lookup_game_name(profile_name)
    bg_image_path = find_background_image(profile_name)

    try:
        proc = subprocess.Popen([TP_EXE] + args, cwd=TP_DIR)
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

            # Only close the splash screen now - the real game window
            # provably exists, so the loading screen can go.
            if not state["splash_closed"]:
                splash.close()
                state["splash_closed"] = True
                log(f"Splash screen closed - target window found: "
                    f"{describe_hwnd(hwnd)}")

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
