"""Verify the packaged Windows executable without changing simulator speed."""

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                              wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def windows_for(executable):
    windows = []

    @callback_type
    def callback(window, parameter):
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(window, ctypes.byref(process_id))
        process = kernel32.OpenProcess(0x1000, False, process_id.value)
        if process:
            try:
                name = ctypes.create_unicode_buffer(32768)
                size = wintypes.DWORD(len(name))
                if kernel32.QueryFullProcessImageNameW(process, 0, name, ctypes.byref(size)):
                    if os.path.normcase(name.value) == os.path.normcase(str(executable)):
                        title, class_name = ctypes.create_unicode_buffer(256), ctypes.create_unicode_buffer(256)
                        user32.GetWindowTextW(window, title, len(title))
                        user32.GetClassNameW(window, class_name, len(class_name))
                        windows.append((window, title.value, class_name.value,
                                        bool(user32.IsWindowVisible(window))))
            finally:
                kernel32.CloseHandle(process)
        return True

    user32.EnumWindows(callback, 0)
    return windows


def wait(predicate, description, process, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"Executable exited early: {process.returncode}")
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError(description)


def main():
    executable = (Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else
                  Path(__file__).resolve().parents[1] / "dist" / "MSFS-SimRate-Monitor.exe")
    with tempfile.TemporaryDirectory() as directory:
        environment = os.environ.copy()
        environment["LOCALAPPDATA"] = directory
        preferences = Path(directory) / "MSFS-SimRateMonitor" / "settings.json"
        preferences.parent.mkdir()
        preferences.write_text(json.dumps({"start_minimized": True, "overlay_size": "m"}))
        process = subprocess.Popen([str(executable)], env=environment, cwd=directory)
        try:
            def tray_windows():
                return [item for item in windows_for(executable) if "SystemTrayIcon" in item[2]]

            tray = wait(tray_windows, "Packaged tray did not appear", process)
            time.sleep(0.5)
            assert not any(item[1] == "MSFS Sim Rate Monitor" and item[3]
                           for item in windows_for(executable)), "Minimized launch showed a window"
            assert any(item[1] == "MSFS Sim Rate Overlay" and item[3]
                       for item in windows_for(executable)), "Minimized launch lost the overlay"
            for item in tray:
                user32.PostMessageW(item[0], 0x400 + 11, 0, 0x0202)

            def visible_window():
                return next((item[0] for item in windows_for(executable)
                             if item[1] == "MSFS Sim Rate Monitor" and item[3]), None)

            window = wait(visible_window, "Packaged tray did not restore the window", process)
            user32.PostMessageW(window, 0x0112, 0xF020, 0)  # WM_SYSCOMMAND / minimize.
            wait(lambda: not visible_window(), "Packaged minimize did not hide", process)
            for item in tray_windows():
                user32.PostMessageW(item[0], 0x400 + 11, 0, 0x0202)
            window = wait(visible_window, "Packaged restore after minimize failed", process)
            user32.PostMessageW(window, 0x0010, 0, 0)  # WM_CLOSE on this executable only.
            assert process.wait(timeout=10) == 0, "Packaged exit failed"
            assert not windows_for(executable), "Packaged process left windows behind"
            assert json.loads(preferences.read_text())["start_minimized"] is True
            log = preferences.with_name("msfs_mini_gui.log")
            assert log.exists(), "Windowless executable did not write its log"
            assert "SimConnect cleanup failed" not in log.read_text(encoding="utf-8")
        finally:
            if process.poll() is None:
                for window, title, class_name, visible in windows_for(executable):
                    if title == "MSFS Sim Rate Monitor":
                        user32.PostMessageW(window, 0x0010, 0, 0)
                process.wait(timeout=10)
    print("PASS: packaged exe starts minimized, creates tray, restores, minimizes, saves, logs and exits")


if __name__ == "__main__":
    main()
