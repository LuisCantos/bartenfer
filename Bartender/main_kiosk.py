import sys

# Fix consola Windows UTF-8 (igual que main.py/server.py)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from assistant import VoiceAssistant
from touch_ui import TouchUI

if __name__ == "__main__":
    mia = VoiceAssistant()
    ui = TouchUI(mia)  # toma el control de on_state_change
    mia.start()
    ui.run()  # bloquea en el mainloop de Tkinter (hilo principal)
