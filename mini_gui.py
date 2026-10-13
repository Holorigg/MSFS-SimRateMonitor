#!/usr/bin/env python3
import argparse
import ctypes
import queue
import sys
import threading
from pathlib import Path
import tkinter as tk

import pystray
from PIL import Image, ImageDraw
from loguru import logger

from app_settings import data_directory, load_settings, save_settings
from sim_rate import SimRateWorker
from ui_controls import SegmentedRadio, blend_colors
from overlay_ui import RateOverlay, SIZE_CONFIGS


THEME = {"bg": "#F7F7F7", "fg": "#2E2E2E", "accent": "#357C55",
         "control_bg": "#EDEDED", "divider": "#DFDFDF"}


def resource_path(name):
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / name


def configure_logging():
    logger.remove()
    if sys.stdout is not None:
        logger.add(sys.stdout, level="INFO")
    try:
        logger.add(data_directory() / "msfs_mini_gui.log", level="DEBUG",
                   rotation="1 MB", retention=1, encoding="utf-8")
    except OSError:
        pass


class SimRateMonitor:
    def __init__(self, start_minimized=False, settings_path=None,
                 worker_factory=SimRateWorker, tray_factory=pystray.Icon):
        self.settings_path = settings_path
        self.settings = load_settings(settings_path)
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("MSFS Sim Rate Monitor")
        self.root.resizable(False, False)
        self.root.configure(bg=THEME["bg"])
        try:
            self.root.iconbitmap(str(resource_path("mini_gui_icon.ico")))
        except tk.TclError:
            pass

        self.running = True
        self.connected = False
        self.messages = queue.Queue()
        self.sim_rate = tk.StringVar(value="-- x")
        self.status = tk.StringVar(value="Waiting for MSFS 2024...")
        self.overlay_size = tk.StringVar(value=self.settings.overlay_size)
        self.start_minimized = tk.BooleanVar(value=self.settings.start_minimized)
        self.overlay_window = None
        self.tray_icon = None
        self.tray_thread = None
        self.tray_ready = False
        self.tray_label = "Waiting for MSFS 2024"
        self._launch_hidden = start_minimized or self.settings.start_minimized
        self.worker = worker_factory(self.messages)
        self._poll_id = None
        self._startup_id = None
        self.setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.bind("<Unmap>", self._on_minimize, add="+")
        self.start_tray(tray_factory)
        self.worker.start()
        self.on_size_change(save=False)
        self._poll_id = self.root.after(50, self._poll_messages)
        if self._launch_hidden:
            self._startup_id = self.root.after(3000, self._tray_startup_timeout)
        else:
            self.show_window()

    def setup_ui(self):
        main = tk.Frame(self.root, bg=THEME["bg"], padx=16, pady=16)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        tk.Label(main, textvariable=self.sim_rate, bg=THEME["bg"], fg=THEME["accent"],
                 font=("Segoe UI", 28, "bold")).grid(row=0, column=0, pady=(6, 2))

        controls = tk.Frame(main, bg=THEME["bg"])
        controls.grid(row=1, column=0, pady=(0, 6))
        self.rate_buttons = {}
        for column, (command, text) in enumerate(
                (("decrease", "−"), ("normal", "1×"), ("increase", "+"))):
            button = tk.Button(controls, text=text, width=3, padx=8, pady=1, bd=0,
                               relief="flat", highlightthickness=0, bg=THEME["bg"],
                               fg=THEME["accent"], disabledforeground="#B5BCB8",
                               activebackground=blend_colors(THEME["accent"], THEME["bg"], 0.92),
                               activeforeground=THEME["accent"], font=("Segoe UI", 11),
                               cursor="hand2", command=lambda action=command: self.send_command(action),
                               state="disabled")
            button.grid(row=0, column=column, padx=2)
            button.bind("<Enter>", lambda event, item=button: item.configure(
                bg=blend_colors(THEME["accent"], THEME["bg"], 0.94)
                if str(item["state"]) == "normal" else THEME["bg"]))
            button.bind("<Leave>", lambda event, item=button: item.configure(bg=THEME["bg"]))
            self.rate_buttons[command] = button

        tk.Frame(main, height=1, bg=THEME["divider"]).grid(
            row=2, column=0, sticky="ew", pady=(4, 10))
        card = tk.Frame(main, bg=THEME["control_bg"], padx=12, pady=10)
        card.grid(row=3, column=0, sticky="ew")
        card.columnconfigure(0, weight=1)
        tk.Label(card, text="Overlay Size", bg=THEME["control_bg"], fg=THEME["fg"],
                 font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w")
        self.options_menu = tk.Menu(self.root, tearoff=False, font=("Segoe UI", 10))
        self.options_menu.add_checkbutton(label="Start minimized to tray", variable=self.start_minimized,
                                          command=self._save_preferences, state="disabled")
        self.options_menu.add_command(label="Hide to tray", command=self.hide_to_tray, state="disabled")
        self.options_menu.add_separator()
        self.options_menu.add_command(label="Exit", command=self.on_closing)
        self.options_button = tk.Button(
            card, text="⋯", bg=THEME["control_bg"], fg="#7D857F", bd=0,
            highlightthickness=0, padx=4, pady=0, font=("Segoe UI", 12), cursor="hand2",
            activebackground=THEME["control_bg"], activeforeground=THEME["accent"],
            command=self._show_options)
        self.options_button.grid(row=0, column=1, sticky="e")
        self.size_seg = SegmentedRadio(card, self.overlay_size,
                                       (("hide", "Hide"), ("s", "S"), ("m", "M"), ("l", "L")),
                                       theme=THEME, command=self.on_size_change)
        self.size_seg.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.status_label = tk.Label(main, textvariable=self.status, bg=THEME["bg"],
                                      fg="#8B6B47", font=("Segoe UI", 9), wraplength=280,
                                      anchor="center", justify="center")
        self.status_label.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.status_label.grid_remove()
        self.root.update_idletasks()
        self.root.geometry(f"{max(320, self.root.winfo_reqwidth())}x{max(230, self.root.winfo_reqheight())}")

    def _show_options(self):
        try:
            self.options_menu.tk_popup(self.options_button.winfo_rootx(),
                                        self.options_button.winfo_rooty() + self.options_button.winfo_height())
        finally:
            self.options_menu.grab_release()

    def _show_status_error(self):
        self.status_label.grid()
        self.root.update_idletasks()
        self.root.geometry(f"{max(320, self.root.winfo_reqwidth())}x{max(230, self.root.winfo_reqheight())}")

    def _post_action(self, action):
        def callback(icon, item):
            self.messages.put(("action", action))
        return callback

    def start_tray(self, factory):
        try:
            try:
                with Image.open(resource_path("mini_gui_icon.ico")) as source:
                    image = source.convert("RGBA")
            except OSError:
                image = Image.new("RGBA", (64, 64), THEME["accent"])
                ImageDraw.Draw(image).text((18, 22), "1x", fill="white")
            enabled = lambda item: self.worker.controls_available
            menu = pystray.Menu(
                pystray.MenuItem("Show monitor", self._post_action("show"), default=True),
                pystray.MenuItem(lambda item: self.tray_label, None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Increase speed (+)", self._post_action("increase"), enabled=enabled),
                pystray.MenuItem("Decrease speed (−)", self._post_action("decrease"), enabled=enabled),
                pystray.MenuItem("Normal speed (1×)", self._post_action("normal"), enabled=enabled),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", self._post_action("exit")),
            )
            self.tray_icon = factory("MSFS-SimRateMonitor", image,
                                     "MSFS Sim Rate Monitor", menu)

            def ready(icon):
                try:
                    if not self.running:
                        icon.stop()
                        return
                    icon.visible = True
                    self.messages.put(("tray_ready", None))
                except Exception as error:
                    self.messages.put(("tray_failed", str(error)))

            def run_tray():
                try:
                    self.tray_icon.run(setup=ready)
                except Exception as error:
                    self.messages.put(("tray_failed", str(error)))
                finally:
                    self.messages.put(("tray_stopped", None))

            self.tray_thread = threading.Thread(target=run_tray, name="System tray", daemon=True)
            self.tray_thread.start()
        except Exception as error:
            self.messages.put(("tray_failed", str(error)))

    def _poll_messages(self):
        if not self.running:
            return
        for _ in range(100):
            try:
                kind, value = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "action":
                if value == "show":
                    self.show_window()
                elif value == "exit":
                    self.on_closing()
                    return
                else:
                    self.send_command(value)
            elif kind == "tray_ready":
                self.tray_ready = True
                self.options_menu.entryconfigure(0, state="normal")
                self.options_menu.entryconfigure(1, state="normal")
                if self._launch_hidden:
                    self.hide_to_tray()
                self._launch_hidden = False
            elif kind in ("tray_failed", "tray_stopped"):
                self._handle_tray_failure(value)
            elif kind == "connected":
                self.connected = True
                self.status.set("Connected to MSFS 2024")
                self.status_label.grid_remove()
                self._set_controls(True)
            elif kind == "disconnected":
                self.connected = False
                self.status.set("Waiting for MSFS 2024...")
                self.status_label.grid_remove()
                self._set_controls(False)
                self._update_rate("-- x")
            elif kind == "rate":
                self._update_rate(f"{value:.2f}×")
            elif kind == "resetting":
                self.status.set("Returning to 1×...")
                self.status_label.grid_remove()
                self._set_controls(False)
            elif kind == "reset_done":
                self.status.set("Connected to MSFS 2024")
                self.status_label.grid_remove()
                self._set_controls(True)
            elif kind == "error":
                self.status.set(value)
                self._show_status_error()
                self._set_controls(self.worker.controls_available)
        self._poll_id = self.root.after(50, self._poll_messages)

    def _set_controls(self, enabled):
        for button in self.rate_buttons.values():
            button.configure(state="normal" if enabled else "disabled")
        self._update_tray()

    def send_command(self, command):
        if not self.worker.submit(command):
            if not self.connected:
                self.status.set("Waiting for MSFS 2024...")
            return False
        return True

    def _update_rate(self, text):
        self.sim_rate.set(text)
        if self.overlay_window:
            self.overlay_window.set_rate(text)
        label = f"Simulation rate: {text}" if self.connected else "Waiting for MSFS 2024"
        if label != self.tray_label:
            self.tray_label = label
            self._update_tray()

    def _update_tray(self):
        if self.tray_ready:
            try:
                self.tray_icon.title = f"MSFS Sim Rate Monitor | {self.tray_label}"
                self.tray_icon.update_menu()
            except Exception as error:
                self._handle_tray_failure(str(error))

    def _handle_tray_failure(self, error):
        if error:
            logger.warning("System tray unavailable: {}", error)
        self.tray_ready = False
        self._launch_hidden = False
        self.options_menu.entryconfigure(0, state="disabled")
        self.options_menu.entryconfigure(1, state="disabled")
        self.show_window()

    def _tray_startup_timeout(self):
        self._startup_id = None
        if self.running and not self.tray_ready:
            self._handle_tray_failure("Icon did not become ready in time")

    def show_window(self):
        if not self.running:
            return
        self._launch_hidden = False
        self.root.deiconify()
        self.root.lift()

    def hide_to_tray(self):
        if self.tray_ready:
            self.root.withdraw()

    def _on_minimize(self, event):
        if event.widget == self.root and self.running and self.root.state() == "iconic":
            self.hide_to_tray()

    def _save_preferences(self):
        self.settings.start_minimized = self.start_minimized.get()
        self.settings.overlay_size = self.overlay_size.get()
        try:
            save_settings(self.settings, self.settings_path)
        except OSError as error:
            logger.warning("Cannot save settings: {}", error)
            self.status.set("Could not save preferences. Check the log file.")
            self._show_status_error()

    def on_size_change(self, save=True):
        self.destroy_overlay()
        size = self.overlay_size.get()
        if size in SIZE_CONFIGS:
            self.overlay_window = RateOverlay(
                self.root, size, self.sim_rate.get(), self.start_move, self.do_move,
                lambda event: self._save_preferences())
            self.overlay_window.update_idletasks()
            self._position_overlay(self.settings.overlay_x, self.settings.overlay_y)
            self.overlay_window.deiconify()
        if save:
            self._save_preferences()

    def _position_overlay(self, x, y):
        # Native positioning preserves coordinates on monitors left of the
        # primary screen. Tk's negative geometry means a right-edge offset.
        user32 = ctypes.windll.user32
        left, top = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
        width, height = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
        overlay_width, overlay_height, _ = SIZE_CONFIGS[self.overlay_size.get()]
        x = max(left, min(x, left + width - overlay_width))
        y = max(top, min(y, top + height - overlay_height))
        from ctypes import wintypes
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.SetWindowPos.restype = wintypes.BOOL
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        window = user32.GetAncestor(self.overlay_window.winfo_id(), 2)
        user32.SetWindowPos(window, None, x, y, 0, 0, 0x0015)
        self.settings.overlay_x, self.settings.overlay_y = x, y

    def start_move(self, event):
        self._drag_x, self._drag_y = event.x, event.y

    def do_move(self, event):
        self._position_overlay(event.x_root - self._drag_x, event.y_root - self._drag_y)

    def destroy_overlay(self):
        if self.overlay_window:
            self.overlay_window.destroy()
            self.overlay_window = None

    def on_closing(self):
        if not self.running:
            return
        self._save_preferences()
        self.running = False
        self.worker.stop()
        for callback_id in (self._poll_id, self._startup_id):
            if callback_id:
                self.root.after_cancel(callback_id)
        if self.tray_icon:
            self.tray_icon.stop()
        self.destroy_overlay()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
        self.worker.join(timeout=2)
        if self.tray_thread:
            self.tray_thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description="MSFS Sim Rate Monitor")
    parser.add_argument("--minimized", action="store_true", help="Start in the system tray")
    args = parser.parse_args()
    configure_logging()
    SimRateMonitor(start_minimized=args.minimized).run()


if __name__ == "__main__":
    main()
