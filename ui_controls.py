import tkinter as tk


def blend_colors(first, second, weight=0.85):
    first = tuple(int(first[index:index + 2], 16) for index in (1, 3, 5))
    second = tuple(int(second[index:index + 2], 16) for index in (1, 3, 5))
    channels = (int(a * (1 - weight) + b * weight) for a, b in zip(first, second))
    return "#{:02X}{:02X}{:02X}".format(*channels)


class SegmentedRadio(tk.Frame):
    def __init__(self, parent, variable, options, theme, command=None, **kwargs):
        super().__init__(parent, bg=theme["control_bg"], **kwargs)
        self.variable = variable
        self.command = command
        self.theme = theme
        self.selected_bg = blend_colors(theme["accent"], theme["control_bg"], 0.82)
        self.hover_bg = blend_colors(theme["accent"], theme["control_bg"], 0.90)
        self.labels = {}
        container = tk.Frame(self, bg=theme["control_bg"], highlightthickness=1,
                             highlightbackground=theme["divider"], bd=0)
        container.pack(fill="x")
        for column, (value, text) in enumerate(options):
            container.columnconfigure(column, weight=1, uniform="segments")
            label = tk.Label(container, text=text, bg=theme["control_bg"], fg=theme["fg"],
                             font=("Segoe UI", 10), padx=12, pady=6, cursor="hand2")
            label.grid(row=0, column=column, sticky="nsew")
            label.bind("<Button-1>", lambda event, option=value: self._select(option))
            label.bind("<Enter>", lambda event, option=value: self._hover(option, True))
            label.bind("<Leave>", lambda event, option=value: self._hover(option, False))
            self.labels[value] = label
        self.variable.trace_add("write", lambda *_: self._sync())
        self._sync()

    def _select(self, value):
        self.variable.set(value)
        if self.command:
            self.command()

    def _hover(self, value, entering):
        if self.variable.get() != value:
            self.labels[value].configure(bg=self.hover_bg if entering else self.theme["control_bg"])

    def _sync(self):
        for value, label in self.labels.items():
            selected = value == self.variable.get()
            label.configure(bg=self.selected_bg if selected else self.theme["control_bg"],
                            fg=self.theme["accent"] if selected else self.theme["fg"],
                            font=("Segoe UI", 10, "bold" if selected else "normal"))
