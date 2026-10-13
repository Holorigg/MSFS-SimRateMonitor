import tkinter as tk
from tkinter import font as tkfont

from PIL import Image, ImageDraw, ImageTk


SIZE_CONFIGS = {"s": (96, 30, 10), "m": (128, 40, 16), "l": (164, 52, 20)}


class RateOverlay(tk.Toplevel):
    TRANSPARENT_COLOR = "#010203"

    def __init__(self, parent, size, rate_text, on_press, on_drag, on_release):
        super().__init__(parent)
        self.withdraw()
        self.title("MSFS Sim Rate Overlay")
        width, height, font_size = SIZE_CONFIGS[size]
        self.width, self.height = width, height
        self.overrideredirect(True)
        self.resizable(False, False)
        self.configure(bg=self.TRANSPARENT_COLOR)
        self.geometry(f"{width}x{height}+50+50")
        self.wm_attributes("-topmost", True)
        self.wm_attributes("-transparentcolor", self.TRANSPARENT_COLOR)
        self.wm_attributes("-alpha", 0.92)
        self.canvas = tk.Canvas(self, width=width, height=height, bd=0,
                                 highlightthickness=0, bg=self.TRANSPARENT_COLOR,
                                 cursor="fleur")
        self.canvas.pack(fill="both", expand=True)

        scale = 4
        background = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
        ImageDraw.Draw(background).rounded_rectangle(
            (0, 0, width * scale - 1, height * scale - 1),
            radius=int(height * 0.36 * scale), fill="#202A27", outline="#46554D", width=scale)
        background = background.resize((width, height), Image.Resampling.LANCZOS)
        # Keep the exact transparency key outside the rounded outline.
        silhouette = background.getchannel("A").point(lambda value: 255 if value >= 128 else 0)
        keyed_background = Image.new("RGB", (width, height), self.TRANSPARENT_COLOR)
        keyed_background.paste(background.convert("RGB"), mask=silhouette)
        self._background = ImageTk.PhotoImage(keyed_background)
        self.canvas.create_image(0, 0, anchor="nw", image=self._background)
        self._font = tkfont.Font(self, family="Segoe UI Semibold", size=font_size)
        self._unit_font = tkfont.Font(self, family="Segoe UI", size=max(9, font_size - 2))
        self._number = self.canvas.create_text(0, 0, anchor="w", font=self._font, fill="#EFF4F0")
        self._unit = self.canvas.create_text(0, 0, anchor="w", font=self._unit_font, fill="#94C7AB")
        self._dot = self.canvas.create_oval(0, 0, 0, 0, outline="", fill="#94C7AB")
        for event, callback in (("<Button-1>", on_press), ("<B1-Motion>", on_drag),
                                ("<ButtonRelease-1>", on_release)):
            self.canvas.bind(event, callback)
        self.set_rate(rate_text)

    def set_rate(self, text):
        connected = not text.startswith("--")
        number = text.replace("×", "").replace("x", "").strip() if connected else "—"
        if connected and "." in number:
            number = number.rstrip("0").rstrip(".")
        unit = "×" if connected else ""
        radius = 2 if self.height <= 30 else 3
        gap = 10 if self.height <= 30 else 12
        unit_gap = 2
        number_width = self._font.measure(number)
        unit_width = self._unit_font.measure(unit)
        total_width = radius * 2 + gap + number_width + (unit_gap + unit_width if unit else 0)
        left = (self.width - total_width) / 2
        center = self.height / 2
        self.canvas.coords(self._dot, left, center - radius, left + radius * 2, center + radius)
        self.canvas.itemconfigure(self._dot, fill="#94C7AB" if connected else "#75877B")
        number_x = left + radius * 2 + gap
        self.canvas.coords(self._number, number_x, center)
        self.canvas.itemconfigure(self._number, text=number, fill="#EFF4F0" if connected else "#A2AEA6")
        self.canvas.coords(self._unit, number_x + number_width + unit_gap, center + 1)
        self.canvas.itemconfigure(self._unit, text=unit)
