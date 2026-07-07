import tkinter as tk

from config import TOUCH_SCREEN_WIDTH, TOUCH_SCREEN_HEIGHT

STATE_LABELS = {
    "idle": "🍹 Di 'Hey MIA'",
    "listening": "🎤 Escuchando...",
    "thinking": "🧠 Pensando...",
    "speaking": "🗣️ Hablando...",
    "vision": "👁️ Mirando...",
    "pouring": "🍸 Preparando bebida...",
    "pouring_progress": "🍸 Sirviendo...",
}


class TouchUI:
    """Interfaz táctil nativa para el panel DSI 7'' (800x480).

    Reemplaza a un navegador en modo kiosko: corre en el mismo proceso de
    Python sin motor de renderizado web, clave para no exceder la RAM
    disponible en un Raspberry Pi 3 (1GB) al usarlo junto con el resto de
    MIA (Gemini, memoria, visión).

    Los botones inyectan directo en Ear.audio_queue / lo activan, igual que
    lo hace el push-to-talk de server.py — no dependen de la wake word ni
    del micrófono para funcionar.
    """

    def __init__(self, assistant):
        self.assistant = assistant

        self.root = tk.Tk()
        self.root.title("MIA")
        self.root.configure(bg="black")
        self.root.geometry(f"{TOUCH_SCREEN_WIDTH}x{TOUCH_SCREEN_HEIGHT}")
        self.root.attributes("-fullscreen", True)
        self.root.config(cursor="none")  # sin cursor de mouse: la entrada es táctil
        self.root.bind("<Escape>", lambda e: self._on_exit())  # salida rápida en pruebas de escritorio

        self.state_var = tk.StringVar(value=STATE_LABELS["idle"])
        self.response_var = tk.StringVar(value="")

        self._build_ui()

        assistant.on_state_change = self._on_state_change

    # ------------------------------------------------------------------
    # Construcción de widgets
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.state_label = tk.Label(
            self.root, textvariable=self.state_var,
            font=("DejaVu Sans", 28, "bold"), fg="white", bg="black",
        )
        self.state_label.pack(pady=(30, 10))

        self.response_label = tk.Label(
            self.root, textvariable=self.response_var,
            font=("DejaVu Sans", 16), fg="#cccccc", bg="black",
            wraplength=TOUCH_SCREEN_WIDTH - 40, justify="center",
        )
        self.response_label.pack(pady=10, padx=20)

        button_frame = tk.Frame(self.root, bg="black")
        button_frame.pack(side="bottom", pady=30)

        tk.Button(
            button_frame, text="🎤 Hablar", font=("DejaVu Sans", 20),
            width=10, height=2, command=self._on_talk_pressed,
        ).pack(side="left", padx=15)

        tk.Button(
            button_frame, text="👁️ Mirar", font=("DejaVu Sans", 20),
            width=10, height=2, command=self._on_vision_pressed,
        ).pack(side="left", padx=15)

        tk.Button(
            button_frame, text="✕", font=("DejaVu Sans", 20),
            width=4, height=2, command=self._on_exit,
        ).pack(side="left", padx=15)

    # ------------------------------------------------------------------
    # Botones táctiles
    # ------------------------------------------------------------------

    def _on_talk_pressed(self):
        """Simula la wake word: activa a Ear para que capture el próximo comando."""
        self.assistant.set_state("listening")
        self.assistant.ear.is_activated = True

    def _on_vision_pressed(self):
        self.assistant.ear.audio_queue.put("mira esto y dime qué ves")

    def _on_exit(self):
        self.assistant.stop()
        self.root.quit()

    # ------------------------------------------------------------------
    # Estado — assistant.py llama esto desde sus propios hilos, así que
    # se reenvía al hilo de Tkinter con root.after() antes de tocar widgets.
    # ------------------------------------------------------------------

    def _on_state_change(self, new_state, data=None):
        self.root.after(0, self._update_ui, new_state, data)

    def _update_ui(self, new_state, data):
        label = STATE_LABELS.get(new_state, new_state)
        if new_state == "pouring" and data:
            label = f"🍸 Preparando {data}..."
        elif new_state == "pouring_progress" and data is not None:
            label = f"🍸 Sirviendo... {data}%"
        self.state_var.set(label)

        if new_state == "speaking" and isinstance(data, dict):
            self.response_var.set(data.get("text", ""))
        elif new_state == "thinking" and isinstance(data, str):
            self.response_var.set(f"Tú: {data}")
        elif new_state == "idle":
            self.response_var.set("")

    def run(self):
        self.root.mainloop()
