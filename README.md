# ParrotRelay

Ein transparenter Start-Proxy für [TeknoParrot](https://github.com/teknogods/TeknoParrotUI), gedacht für den Einsatz mit **HyperSpin 2 / HyperHQ**.

![ParrotRelay Ladebildschirm](screenshot.png)

## Warum

TeknoParrot-Spiele, die über HyperHQ gestartet werden, verlieren teils nach dem Start ihren exklusiven Vollbildmodus: `TeknoParrotUi.exe` holt sein eigenes "Spiel läuft"-Fenster selbst wieder in den Vordergrund, während das Spiel im Hintergrund weiterläuft — mit dem Effekt, dass man auf das TP-Fenster statt aufs Spiel schaut, und ein Zurückklicken den Vollbildmodus nicht mehr sauber herstellt.

ParrotRelay setzt sich zwischen HyperHQ und TeknoParrotUi.exe und behebt das, ohne TeknoParrot selbst anzufassen.

## Was es macht

1. **Eigener Vollbild-Ladebildschirm** — zeigt den echten Spielnamen (aus der TeknoParrot-Profil-XML) und optional ein spielspezifisches Hintergrundbild, solange geladen wird. Schließt sich automatisch, sobald das echte Spielfenster da ist.
2. **Unterdrückt TeknoParrots eigenes "Spiel läuft"-Fenster** aktiv, bevor es überhaupt Fokus bekommen kann.
3. **Hält als Sicherheitsnetz kontinuierlich den Fokus** auf dem echten Spielfenster, falls doch mal etwas anderes kurz in den Vordergrund kommt.
4. **Bleibt am Leben, bis das Spiel wirklich beendet ist** — nicht nur bis TeknoParrots eigener Launcher-Stub sich (wie designed) selbst beendet. Sonst würde HyperHQ fälschlich "Spiel beendet" melden.

## Installation

1. [Releases](../../releases) öffnen, `ParrotRelay.exe` herunterladen.
2. Direkt neben `TeknoParrotUi.exe` legen (z. B. `D:\ROM\TeknoParrot\ParrotRelay.exe`).
3. In HyperSpin 2 die TeknoParrot-Plattform bearbeiten:
   - **Platform Path:** `D:\ROM\TeknoParrot\ParrotRelay.exe`
   - **Command Line:** bleibt unverändert, z. B. `--startMinimized --profile=%rom.filename%.xml`

Kein Admin-Rechte-Setup nötig.

## Hintergrundbilder (optional)

Ordner `LoadingBG` neben `ParrotRelay.exe` anlegen:

```
D:\ROM\TeknoParrot\LoadingBG\BBCF.png
```

Der Dateiname (ohne Endung) muss exakt dem Profilnamen aus `--profile=<Name>.xml` entsprechen. Unterstützt: `.png`, `.gif` nativ; `.jpg`/`.jpeg`/`.bmp`/`.webp` zusätzlich, falls [Pillow](https://pypi.org/project/Pillow/) installiert ist.

Ohne eigenes Bild fällt ParrotRelay automatisch auf TeknoParrots eigenes Icon zurück (`Icons\<Profil>.png`), falls vorhanden.

## Aus dem Quellcode bauen

```bash
pip install -r requirements.txt
pyinstaller --onefile --noconsole --icon=icon.ico --name ParrotRelay parrot_relay.py
```

Die fertige `ParrotRelay.exe` liegt danach in `dist\`.

## Logging

`parrot_relay_log.txt` wird im selben Ordner wie die exe angelegt und bei jedem Start ergänzt — nützlich zum Debuggen, welches Fenster wann erkannt/unterdrückt/fokussiert wurde.

## Lizenz

MIT — siehe [LICENSE](LICENSE).
