import sys

# Fix consola Windows UTF-8 (necesario para los emojis en los prints, igual que en server.py)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from assistant import VoiceAssistant

if __name__ == "__main__":
    mia = VoiceAssistant()
    mia.run_interactive()
