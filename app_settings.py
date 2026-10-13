import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


def data_directory():
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MSFS-SimRateMonitor"


@dataclass
class Settings:
    start_minimized: bool = False
    overlay_size: str = "hide"
    overlay_x: int = 50
    overlay_y: int = 50


def load_settings(path=None):
    path = Path(path) if path else data_directory() / "settings.json"
    settings = Settings()
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(values, dict):
            return settings
        if isinstance(values.get("start_minimized"), bool):
            settings.start_minimized = values["start_minimized"]
        if values.get("overlay_size") in ("hide", "s", "m", "l"):
            settings.overlay_size = values["overlay_size"]
        for key in ("overlay_x", "overlay_y"):
            value = values.get(key)
            if type(value) is int and -100000 < value < 100000:
                setattr(settings, key, value)
    except (OSError, ValueError):
        pass
    return settings


def save_settings(settings, path=None):
    path = Path(path) if path else data_directory() / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    temporary.replace(path)
