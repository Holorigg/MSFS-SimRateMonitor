# MSFS Sim Rate Monitor

A small Windows utility that displays and controls the simulation rate in Microsoft Flight Simulator 2024. It connects through SimConnect and runs outside the simulator.

This fork adds speed controls, a system tray menu, saved preferences and a rounded overlay to [faker2048's original project](https://github.com/faker2048/MSFS-SimRateMonitor).

## Download

Download `MSFS-SimRate-Monitor.exe` from the [latest release](https://github.com/Holorigg/MSFS-SimRateMonitor/releases/latest) and run it. Python is included in the executable; no installation in the Community folder is needed.

The ZIP contains the same executable, this README and dependency licenses.

Requirements: Windows 10 or 11, 64-bit, and MSFS 2024.

## Controls

<img src="docs/images/monitor.png" alt="Monitor window" width="330">

| Control | Action |
| --- | --- |
| `−` | Decrease the simulation rate by one step. |
| `+` | Increase the simulation rate by one step. |
| `1×` | Return to normal speed. |
| Hide / S / M / L | Hide the overlay or select its size. |
| `⋯` | Open startup, tray and exit options. |

The simulator determines the available rate steps. Controls stay disabled until a valid rate is received. The displayed value comes from the simulator.

The `1×` command checks the result. If direct setting is ignored, the app tries rate steps for up to eight seconds, then reports an error if the rate is still different.

## Overlay

<img src="docs/images/overlay.png" alt="Small, medium and large overlays" width="320">

The overlay has a translucent dark background, rounded corners and three sizes. Drag it to move it; its position and size are saved. Values are shortened to `2×`, `0.5×`, etc. A muted dot and dash indicate that rate data is unavailable.

The images above show simulated rate data.

## System tray

Minimize the window or choose **⋯ → Hide to tray** to keep the app running in the notification area. The overlay remains visible.

Click the tray icon to restore the window. Right-click it for speed controls and **Exit**. Closing the main window also exits the app.

Enable **⋯ → Start minimized to tray** to apply that behavior on the next launch. For a single launch, use:

```powershell
.\MSFS-SimRate-Monitor.exe --minimized
```

If the tray cannot be created, the app opens its main window.

## Settings and logs

Files are stored in `%LOCALAPPDATA%\MSFS-SimRateMonitor`:

- `settings.json`: startup preference, overlay size and position.
- `msfs_mini_gui.log`: connection and command log, rotated at 1 MB.

You can start the app before MSFS. It retries the connection when the simulator is unavailable and reconnects after a restart.

If speed controls do nothing, check that a flight is active. MSFS can restrict rate changes in some states. When reporting a problem, include the MSFS version, aircraft and log file.

## Run from source

Use 64-bit Python 3.12 on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe mini_gui.py
```

## Build

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build.bat
.\.venv\Scripts\python.exe tools\package_release.py
```

Outputs in `dist`:

- `MSFS-SimRate-Monitor.exe`
- `MSFS-SimRate-Monitor-windows-x64.zip`
- `SHA256SUMS.txt`

GitHub Actions builds the Windows executable on pushes to `master`, pull requests and manual runs. Each successful build uploads the files above as an artifact. Pushing a tag beginning with `v` also publishes a release, using `.github/release-notes.md` for its description.

## License

MIT, retaining the original project's copyright notice. Dependency licenses are included in the release ZIP.
