"""Manual Windows smoke test: real Tk/tray, simulated simulator connection."""

import ctypes
import sys
import tempfile
import threading
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import ImageGrab
from loguru import logger
from mini_gui import SimRateMonitor
from sim_rate import SimRateWorker
from test_monitor import FakeConnection, FakeRequests

logger.remove()


def simulated_worker(messages):
    return SimRateWorker(messages, FakeConnection, FakeRequests, poll_interval=0.03)


def wait(app, predicate, description, seconds=4):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.root.update()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(description)


def close(app):
    app.on_closing()
    app.worker.join(timeout=2)
    if app.tray_thread:
        app.tray_thread.join(timeout=2)
        assert not app.tray_thread.is_alive(), "Tray did not exit"
    assert not app.worker.is_alive(), "Worker did not exit"


def screenshot(app, path):
    user32 = ctypes.windll.user32
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    rectangle = wintypes.RECT()
    window = user32.GetAncestor(app.root.winfo_id(), 2)
    previous_topmost = app.root.wm_attributes("-topmost")
    app.root.wm_attributes("-topmost", True)

    def capture():
        user32.GetWindowRect(window, ctypes.byref(rectangle))
        dwm = ctypes.windll.dwmapi
        dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                              ctypes.c_void_p, wintypes.DWORD]
        dwm.DwmGetWindowAttribute(window, 9, ctypes.byref(rectangle), ctypes.sizeof(rectangle))
        ImageGrab.grab(bbox=(rectangle.left, rectangle.top, rectangle.right, rectangle.bottom),
                       all_screens=True, include_layered_windows=True).save(path)
        app.root.quit()

    app.root.after(500, capture)
    app.root.mainloop()
    app.root.wm_attributes("-topmost", previous_topmost)


def main():
    output = Path(__file__).resolve().parents[1] / "dist"
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        preferences = Path(directory) / "settings.json"
        app = SimRateMonitor(settings_path=preferences, worker_factory=simulated_worker)
        try:
            wait(app, lambda: app.tray_ready and app.connected, "Tray/connection not ready")
            assert app.tray_icon.visible
            assert all(str(button["state"]) == "normal" for button in app.rate_buttons.values())
            app.rate_buttons["increase"].invoke()
            wait(app, lambda: app.sim_rate.get() == "2.00×", "+ button failed")
            # Native tray callbacks arrive on a non-Tk thread.
            callback = threading.Thread(target=lambda: app.tray_icon.menu.items[4](app.tray_icon))
            callback.start()
            callback.join()
            wait(app, lambda: app.sim_rate.get() == "1.00×", "Tray decrease failed")
            app.rate_buttons["increase"].invoke()
            wait(app, lambda: app.sim_rate.get() == "2.00×", "Second increase failed")
            app.rate_buttons["normal"].invoke()
            wait(app, lambda: app.sim_rate.get() == "1.00×" and app.worker.controls_available,
                 "1x button failed")
            app.overlay_size.set("m")
            app.on_size_change()
            app._position_overlay(240, 180)
            app._save_preferences()
            wait(app, lambda: app.overlay_window.winfo_viewable(), "Overlay not visible")
            assert str(app.overlay_window.wm_attributes("-transparentcolor")) == "#010203"
            assert app.overlay_window.canvas.itemcget(app.overlay_window._number, "text") == "1"
            app.overlay_window.canvas.event_generate("<Button-1>", x=20, y=15)
            app.overlay_window.canvas.event_generate("<B1-Motion>", x=35, y=25)
            app.overlay_window.canvas.event_generate("<ButtonRelease-1>", x=35, y=25)
            app.root.update()
            assert abs(app.overlay_window.winfo_x() - 255) <= 2, "Overlay drag failed"
            app._position_overlay(240, 180)
            app._save_preferences()
            app.root.update()
            app.overlay_window.withdraw()
            app.root.update()
            time.sleep(0.2)
            screenshot(app, output / "monitor-preview.png")
            app.overlay_window.deiconify()
            app.root.update()
            assert abs(app.overlay_window.winfo_x() - 240) <= 2, "Overlay position failed"
            app.options_menu.invoke(1)
            wait(app, lambda: app.root.state() == "withdrawn", "Hide to tray failed")
            assert app.overlay_window.winfo_viewable(), "Hiding main window hid the overlay"
            app.tray_icon.menu.items[0](app.tray_icon)
            wait(app, lambda: app.root.state() == "normal", "Tray restore failed")
            app.root.iconify()
            wait(app, lambda: app.root.state() == "withdrawn", "Native minimize did not hide to tray")
            app.options_menu.invoke(0)
            assert app.settings.start_minimized
        finally:
            close(app)

        app = SimRateMonitor(settings_path=preferences, worker_factory=simulated_worker)
        try:
            wait(app, lambda: app.tray_ready and app.connected, "Minimized launch not ready")
            assert app.root.state() == "withdrawn", "Saved minimized preference ignored"
            assert app.overlay_size.get() == "m", "Overlay preference lost"
            assert app.overlay_window.winfo_viewable(), "Overlay lost on minimized launch"
            app.tray_icon.stop()
            wait(app, lambda: app.root.state() == "normal", "Unexpected tray exit stranded the window")
        finally:
            close(app)

        def broken_tray(*args):
            raise OSError("Simulated unavailable tray")

        app = SimRateMonitor(settings_path=preferences, worker_factory=simulated_worker,
                             tray_factory=broken_tray)
        try:
            wait(app, lambda: app.root.state() == "normal", "Tray failure stranded minimized app")
            assert not app.tray_ready
            assert str(app.options_menu.entrycget(1, "state")) == "disabled"
        finally:
            close(app)
    print("PASS: buttons, actual Windows tray, callbacks, overlay, minimized launch, fallback and exit")
    print(f"Preview: {output / 'monitor-preview.png'}")


if __name__ == "__main__":
    main()
