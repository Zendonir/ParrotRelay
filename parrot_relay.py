r"""
ParrotRelay - Transparenter Start-Proxy fuer TeknoParrotUi.exe

Zweck:
    Liegt NEBEN TeknoParrotUi.exe im selben Ordner. Wird von HyperSpin 2
    anstelle von TeknoParrotUi.exe aufgerufen, reicht alle Kommandozeilen-
    Argumente 1:1 an TeknoParrotUi.exe weiter (gleiches Arbeitsverzeichnis,
    also keine Pfadprobleme mehr) und:

    1. Zeigt einen eigenen Vollbild-Ladebildschirm (Ersatz fuer
       HyperOverlays Loading-Screen, der sich als Ursache des
       urspruenglichen Fokus-Problems herausgestellt hat) mit dem
       echten Spielnamen (aus der UserProfiles-XML, GameNameInternal)
       und optional einem spielspezifischen Hintergrundbild aus dem
       LoadingBG-Ordner, solange noch kein echtes Spielfenster
       existiert. Schliesst sich automatisch, sobald das Spielfenster
       gefunden wurde.
    2. TeknoParrots eigene Fenster (Hauptfenster, "Spiel laeuft") aktiv
       versteckt, SOBALD sie sichtbar werden - noch bevor sie ueberhaupt
       Fokus/Vordergrund bekommen koennen. Das ist der Kernfix: bei
       exklusivem Vollbild (z.B. BlazBlue) reicht ein einziger Fokus-
       wechsel weg vom Spiel, damit es den Vollbildmodus verliert -
       nachtraegliches Zurueckfokussieren kommt dann zu spaet.
    3. Zusaetzlich als Sicherheitsnetz kontinuierlich das echte Spiel-
       fenster fokussiert, falls trotzdem mal ein fremdes Fenster
       (HyperOverlay o.ae.) kurz in den Vordergrund kommt.
    4. Am Leben bleibt, bis das TATSAECHLICHE Spiel beendet ist - nicht
       nur bis TeknoParrotUi.exe (ein reiner Launcher-Stub, der sich
       nach dem Start des Spiels selbst beendet) verschwindet. Sonst
       wuerde HyperHQ (das ja diesen Proxy als "den Emulator"
       ueberwacht) faelschlich "Spiel beendet" melden, sobald nur der
       TP-Launcher-Stub weg ist, obwohl das Spiel noch laeuft.

Voraussetzungen:
    pip install pywin32 psutil
    (tkinter ist Teil der Python-Standardbibliothek, keine extra
    Installation noetig. Fuer Hintergrundbilder in Formaten ausser
    PNG/GIF zusaetzlich: pip install pillow)

Hintergrundbilder (optional):
    Ordner "LoadingBG" NEBEN ParrotRelay.exe anlegen, z.B.
    D:\ROM\TeknoParrot\LoadingBG\BBCF.png
    Der Dateiname (ohne Endung) muss exakt dem --profile=<Name>.xml
    aus der Kommandozeile entsprechen. Unterstuetzte Endungen:
    .png, .gif nativ; .jpg/.jpeg/.bmp/.webp zusaetzlich falls Pillow
    installiert ist. Kein Bild gefunden -> einfacher schwarzer
    Hintergrund wie bisher.

Spielname:
    Wird aus D:\ROM\TeknoParrot\UserProfiles\<Profil>.xml gelesen
    (Feld GameNameInternal, z.B. "BlazBlue: Central Fiction"). Falls
    die Datei fehlt oder das Feld nicht gefunden wird, faellt der
    Splash auf den rohen Profil-Dateinamen zurueck (z.B. "BBCF").

Build (als EXE, OHNE Admin-Anforderung - siehe Hinweis unten):
    pyinstaller --onefile --noconsole --icon=icon.ico --name ParrotRelay parrot_relay.py

Hinweis Admin-Rechte: TeknoParrotUi.exe selbst startet auch ohne
Admin-Elevation des Proxys problemlos, und HyperHQ (nicht elevated)
kann einen elevated Proxy per spawn() ohnehin nicht starten (Windows
verweigert das mit EACCES). Deshalb bewusst KEIN --uac-admin.

Die fertige ParrotRelay.exe aus dist\ nach D:\ROM\TeknoParrot\ kopieren
(also direkt neben TeknoParrotUi.exe).

HyperSpin-2-Konfiguration:
    Platform Path: D:\ROM\TeknoParrot\ParrotRelay.exe
    Command Line:  --startMinimized --profile=%rom.filename%.xml
    (unveraendert - der Proxy reicht das 1:1 durch)

Log:
    parrot_relay_log.txt wird im selben Ordner wie die exe angelegt und bei
    jedem Start ergaenzt (nicht ueberschrieben), damit man mehrere Laeufe
    im Nachhinein vergleichen kann.
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
# Pfade
# ---------------------------------------------------------------------

if getattr(sys, "frozen", False):
    # Als PyInstaller-EXE: eigener Speicherort statt __file__
    TP_DIR = os.path.dirname(sys.executable)
else:
    TP_DIR = os.path.dirname(os.path.abspath(__file__))

TP_EXE = os.path.join(TP_DIR, "TeknoParrotUi.exe")
LOG_PATH = os.path.join(TP_DIR, "parrot_relay_log.txt")
USER_PROFILES_DIR = os.path.join(TP_DIR, "UserProfiles")
LOADING_BG_DIR = os.path.join(TP_DIR, "LoadingBG")
ICONS_DIR = os.path.join(TP_DIR, "Icons")

# Unterstuetzte Bild-Endungen fuer den Splash-Hintergrund. .png/.gif
# koennen von Tkinter selbst geladen werden (PhotoImage), fuer den
# Rest wird - falls installiert - Pillow verwendet.
NATIVE_IMAGE_EXTS = (".png", ".gif")
PILLOW_IMAGE_EXTS = (".jpg", ".jpeg", ".bmp", ".webp")

# Wie oft (Sekunden) und wie lange die Fokus-Schleife pollt.
# Bewusst kurz gehalten: je schneller ein neu erscheinendes TP-eigenes
# Fenster erkannt und versteckt wird, desto kleiner das Zeitfenster,
# in dem das Spiel seinen exklusiven Vollbildmodus verlieren koennte.
POLL_INTERVAL = 0.05
# Mindestgroesse (Pixel-Flaeche), damit winzige Hilfsfenster (Tooltips,
# TPs eigenes kleines "Spiel laeuft"-Fenster) nicht versehentlich als
# "das Spielfenster" behandelt werden. Bei Bedarf anpassen.
MIN_WINDOW_AREA = 200 * 150


def extract_profile_name(args: list[str]) -> str | None:
    """
    Holt den rohen Profil-Dateinamen aus --profile=XYZ.xml (z.B.
    'BBCF.xml' -> 'BBCF'). Wird sowohl zum Nachschlagen der echten
    GameNameInternal in der UserProfiles-XML als auch zum Finden des
    passenden Hintergrundbilds verwendet.
    """
    for arg in args:
        m = re.match(r"--profile=(.+)\.xml$", arg, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def lookup_game_name(profile_name: str | None) -> str:
    r"""
    Liest GameNameInternal aus UserProfiles\<profile_name>.xml (z.B.
    "BlazBlue: Central Fiction" statt nur "BBCF"). Bei jedem Fehler
    (Datei fehlt, Feld fehlt, XML kaputt) wird auf den rohen
    Profilnamen zurueckgefallen - der Splash zeigt dann eben "BBCF"
    statt des schoenen Namens, aber bricht nie deswegen ab.
    """
    if not profile_name:
        return "Spiel"

    xml_path = os.path.join(USER_PROFILES_DIR, f"{profile_name}.xml")
    try:
        tree = ET.parse(xml_path)
        name_elem = tree.getroot().find("GameNameInternal")
        if name_elem is not None and name_elem.text:
            return name_elem.text.strip()
    except (ET.ParseError, FileNotFoundError, OSError):
        pass
    except Exception:
        log("FEHLER beim Lesen von GameNameInternal:\n" + traceback.format_exc())

    return profile_name


def find_background_image(profile_name: str | None) -> str | None:
    r"""
    Sucht zuerst LoadingBG\<profile_name>.<ext>. Falls nichts
    gefunden wird, faellt auf TPs eigenes Icon aus Icons\<profile_name>.png
    zurueck (das TeknoParrot pro Spiel ohnehin schon hat, z.B. per
    IconName in der Profil-XML - <IconName>Icons/BBCF.png</IconName>).
    Gibt None zurueck, wenn auch das nicht existiert (dann bleibt der
    Splash schwarz ohne Bild).
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
    Eigener Vollbild-Ladebildschirm (Ersatz fuer HyperOverlays Loading-
    Screen), der anzeigt was gerade gestartet wird. Wird automatisch
    geschlossen, sobald das echte Spielfenster gefunden wurde.

    Laeuft im Hauptthread ueber Tkinters eigene Ereignisschleife - die
    komplette Proxy-Ueberwachungslogik (TP-Fenster unterdruecken,
    Spielfenster suchen/fokussieren) wird per root.after() als
    wiederkehrender Callback eingehaengt, statt in einer separaten
    time.sleep-Schleife zu laufen.
    """

    def __init__(self, game_name: str, bg_image_path: str | None):
        self.root = tk.Tk()
        self.root.overrideredirect(True)  # keine Titelleiste/Rahmen
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

        # self._bg_photo muss als Attribut gehalten werden, sonst
        # entfernt Python das PhotoImage-Objekt per Garbage Collection
        # wieder, sobald __init__ zurueckkehrt, und das Bild verschwindet.
        self._bg_photo = None
        image_h = 0
        if bg_image_path:
            self._bg_photo = self._load_image_native_size(bg_image_path)
            if self._bg_photo:
                image_h = self._bg_photo.height()
                log(f"Bild geladen (Originalgroesse "
                    f"{self._bg_photo.width()}x{image_h}): {bg_image_path}")
            else:
                log(f"Bild konnte nicht geladen werden: {bg_image_path}")

        # Vertikaler Block aus [Bild] -> Spielname -> Status, als
        # Ganzes auf dem Bildschirm zentriert. anchor="n" verankert
        # jedes Element an seiner Oberkante, dadurch reicht es, die
        # y-Position einfach fortlaufend nach unten zu addieren.
        gap_image_to_name = 30
        gap_name_to_status = 15
        name_line_h = 55   # ungefaehre Zeilenhoehe bei Font-Groesse 40
        status_line_h = 30  # ungefaehre Zeilenhoehe bei Font-Groesse 20

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
        Laedt ein Bild in seiner ORIGINALGROESSE (keine Skalierung).
        Nutzt Pillow falls verfuegbar (mehr unterstuetzte Formate),
        sonst Tkinters eigenes PhotoImage (nur PNG/GIF).
        """
        ext = os.path.splitext(path)[1].lower()

        if _PILLOW_AVAILABLE:
            try:
                img = Image.open(path)
                return ImageTk.PhotoImage(img)
            except Exception:
                log("FEHLER beim Laden des Bilds mit Pillow:\n"
                    + traceback.format_exc())
                return None

        if ext in NATIVE_IMAGE_EXTS:
            try:
                return tk.PhotoImage(file=path)
            except Exception:
                log("FEHLER beim Laden des Bilds ohne Pillow:\n"
                    + traceback.format_exc())
                return None

        log(f"Bildformat {ext} benoetigt Pillow (nicht installiert) - "
            f"ueberspringe Bild.")
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
# Fenster-/Prozess-Hilfsfunktionen
# ---------------------------------------------------------------------

def get_descendant_pids(root_pid: int) -> set[int]:
    """Liefert root_pid plus alle (rekursiven) Kindprozess-PIDs."""
    try:
        root = psutil.Process(root_pid)
    except psutil.NoSuchProcess:
        log(f"WARNUNG: Root-Prozess {root_pid} existiert nicht mehr")
        return set()

    pids = {root_pid}
    try:
        for child in root.children(recursive=True):
            pids.add(child.pid)
    except psutil.AccessDenied:
        log("WARNUNG: AccessDenied beim Auflisten der Kindprozesse "
            "(laeuft der Proxy nicht als Admin, TP aber schon?)")
    except Exception:
        log("FEHLER beim Auflisten der Kindprozesse:\n" + traceback.format_exc())
    return pids


def find_candidate_windows(pids: set[int], exclude_pid: int) -> list[int]:
    """
    Sucht sichtbare Top-Level-Fenster, deren Prozess zu 'pids' gehoert,
    ausser exclude_pid (= TeknoParrotUi.exe selbst). Sortiert nach
    Fensterflaeche absteigend, kleine Fenster unterhalb MIN_WINDOW_AREA
    werden ausgefiltert.
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
        log("FEHLER in EnumWindows:\n" + traceback.format_exc())

    candidates.sort(reverse=True)
    return [hwnd for _, hwnd in candidates]


def find_tp_own_windows(tp_pid: int) -> list[int]:
    """
    Sucht sichtbare Top-Level-Fenster, die zu TeknoParrotUi.exe SELBST
    gehoeren UND deren Titel exakt einem der bekannten, harmlosen
    TP-eigenen Laufzeit-Fenster entspricht (z.B. "Spiel läuft").

    WICHTIG: Bewusst NICHT jedes TP-Fenster pauschal unterdruecken -
    sonst wuerden auch TP-Fehlerdialoge (Absturz, fehlende DLL, Profil-
    Fehler etc.) unsichtbar gemacht, was die Fehlersuche unmoeglich
    macht und im schlimmsten Fall zu einem rein schwarzen Bildschirm
    ohne jede Rueckmeldung fuehrt, falls das Spiel selbst haengt oder
    abstuerzt.
    """
    # Bekannte, unbedenkliche Laufzeit-Fenstertitel von TeknoParrotUi.exe.
    # Alles andere (Fehlerdialoge, unbekannte Titel) bleibt sichtbar.
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
        log("FEHLER in EnumWindows (TP-eigene Fenster):\n" + traceback.format_exc())

    return windows


def suppress_window(hwnd: int) -> bool:
    """
    Versteckt ein TP-eigenes Fenster (Minimieren + aus der Taskleiste/
    Alt-Tab entfernen), damit es Windows gar nicht erst als Fokus-
    Kandidat anbietet. Gibt True zurueck, wenn tatsaechlich etwas
    veraendert wurde (fuers Logging), sonst False.
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
        log("FEHLER beim Verstecken von TP-Fenster:\n" + traceback.format_exc())
        return False
    except Exception:
        log("FEHLER beim Verstecken von TP-Fenster:\n" + traceback.format_exc())
        return False


def force_focus(hwnd: int) -> None:
    """
    Erzwingt den Fokus auf hwnd, auch wenn Windows' Foreground-Lock das
    normalerweise verhindert. Trick: den Input-Thread des aktuell aktiven
    Fensters kurz an den eigenen Thread anhaengen (AttachThreadInput) -
    das umgeht die Sperre, siehe u.a. MSDN-Dokumentation zu
    SetForegroundWindow.

    Manche Kandidatenfenster (z.B. TeknoParrots kurzlebiges
    D3DProxyWindow waehrend des DirectX-Hookings) existieren nur fuer
    Sekundenbruchteile. Zwischen "als Kandidat gefunden" und "hier
    fokussieren" kann das Fenster also schon zerstoert sein - das ist
    normal und kein echter Fehler, deshalb vorab per IsWindow pruefen
    und in dem Fall still (ohne FEHLER-Log) abbrechen.
    """
    if not win32gui.IsWindow(hwnd):
        log(f"Zielfenster hwnd={hwnd} existiert nicht mehr (kurzlebiges "
            f"Uebergangsfenster) - ueberspringe.")
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
            # ERROR_INVALID_WINDOW_HANDLE - Fenster ist zwischen Fund und
            # Fokussierung verschwunden (Race Condition bei kurzlebigen
            # Uebergangsfenstern). Kein echter Fehler, kurz ignorieren.
            log(f"Zielfenster hwnd={hwnd} verschwand waehrend des "
                f"Fokussierens - ueberspringe.")
        else:
            log("FEHLER beim Fokussieren:\n" + traceback.format_exc())
    except Exception:
        log("FEHLER beim Fokussieren:\n" + traceback.format_exc())

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
        return f"hwnd={hwnd} (Details nicht lesbar)"


# ---------------------------------------------------------------------
# Hauptablauf
# ---------------------------------------------------------------------

def main() -> None:
    log("=" * 60)
    log("ParrotRelay gestartet")
    log(f"TP_DIR   = {TP_DIR}")
    log(f"TP_EXE   = {TP_EXE}")
    log(f"Args     = {sys.argv[1:]}")
    log(f"Elevated = {is_admin()}")

    if not os.path.isfile(TP_EXE):
        log(f"FEHLER: {TP_EXE} nicht gefunden - Abbruch.")
        ctypes.windll.user32.MessageBoxW(
            0,
            f"TeknoParrotUi.exe nicht gefunden in:\n{TP_DIR}",
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
        log("FEHLER beim Starten von TeknoParrotUi.exe:\n" + traceback.format_exc())
        return

    tp_pid = proc.pid
    log(f"TeknoParrotUi.exe gestartet, PID={tp_pid}")

    splash = SplashScreen(game_name, bg_image_path)
    log(f"Splash-Screen angezeigt fuer '{game_name}' "
        f"(Profil: {profile_name or '?'})")

    # Gemeinsamer Zustand fuer den wiederkehrenden Tick-Callback. Ein
    # dict statt einzelner nonlocal-Variablen, weil tick() als
    # geschachtelte Funktion mehrfach neu ueber root.after() aufgerufen
    # wird und so alles an einem Ort bleibt.
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
            log(f"TeknoParrotUi.exe (Launcher-Stub) beendet, "
                f"Exitcode={proc.returncode} - Proxy bleibt aktiv, "
                f"solange das eigentliche Spiel noch laeuft.")
            state["tp_launcher_exited_logged"] = True

        # 1) TP-eigene Fenster (Hauptfenster, "Spiel laeuft") aktiv
        #    verstecken, BEVOR sie ueberhaupt Fokus/Vordergrund
        #    bekommen koennen.
        if tp_launcher_running:
            tp_windows = find_tp_own_windows(tp_pid)
            for hwnd in tp_windows:
                changed = suppress_window(hwnd)
                if changed and hwnd not in state["suppressed_hwnds_logged"]:
                    log(f"TP-eigenes Fenster unterdrueckt: {describe_hwnd(hwnd)}")
                    state["suppressed_hwnds_logged"].add(hwnd)

        # 2) Echtes Spielfenster suchen/fokussieren.
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

            # Splash-Screen erst jetzt schliessen - das echte Spiel-
            # fenster existiert nachweislich, also kann der eigene
            # Ladebildschirm weg.
            if not state["splash_closed"]:
                splash.close()
                state["splash_closed"] = True
                log(f"Splash-Screen geschlossen - Zielfenster gefunden: "
                    f"{describe_hwnd(hwnd)}")

            if win32gui.GetForegroundWindow() != hwnd:
                if hwnd != state["last_focused_hwnd"]:
                    log(f"Neues Zielfenster erkannt: {describe_hwnd(hwnd)}")
                force_focus(hwnd)
            state["last_focused_hwnd"] = hwnd
        elif not state["splash_closed"]:
            # Noch kein Zielfenster gefunden - Splash-Status je nach
            # Launcher-Zustand aktualisieren, rein informativ.
            if tp_launcher_running:
                splash.set_status("Loading...")
            else:
                splash.set_status("Startet...")

        # Abbruchbedingung: Launcher weg UND (kein Spiel je erkannt ODER
        # das erkannte Spiel laeuft nachweislich nicht mehr).
        if not tp_launcher_running:
            if state["game_pid_seen"] is None:
                log("Kein Spielprozess wurde je erkannt und der Launcher "
                    "ist beendet - Proxy wird beendet.")
                if not state["splash_closed"]:
                    splash.close()
                splash.root.quit()
                return
            if not psutil.pid_exists(state["game_pid_seen"]):
                log(f"Spielprozess (PID {state['game_pid_seen']}) ist "
                    f"beendet - Proxy wird beendet.")
                splash.root.quit()
                return

        # Naechsten Tick einplanen (Millisekunden).
        splash.root.after(int(POLL_INTERVAL * 1000), tick)

    # Ersten Tick anstossen, dann Tkinters eigene Ereignisschleife
    # uebernehmen lassen - sie treibt sowohl das Splash-Fenster als
    # auch (ueber die wiederkehrenden after()-Aufrufe) die komplette
    # Ueberwachungslogik an.
    splash.root.after(0, tick)
    splash.root.mainloop()

    log("ParrotRelay beendet")
    log("=" * 60 + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("UNBEHANDELTER FEHLER:\n" + traceback.format_exc())
    finally:
        _log_file.close()
