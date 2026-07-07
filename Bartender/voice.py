import asyncio
import base64
import ctypes
import os
import platform
import subprocess
import tempfile
import threading

import edge_tts

from config import VOICE_RATE, VOICE_VOLUME

# Edge-TTS espera 'rate'/'volume' como porcentaje relativo ("+10%", "-5%"),
# no wpm/0-1 como config.py. Estos valores de referencia sirven para convertir.
_REFERENCE_WPM = 175
_VOICE_NAME = "es-MX-DaliaNeural"  # Voz neural en español, gratis vía Edge-TTS


def _rate_to_percent(wpm):
    pct = round((wpm - _REFERENCE_WPM) / _REFERENCE_WPM * 100)
    return f"{'+' if pct >= 0 else ''}{pct}%"


def _volume_to_percent(volume):
    pct = round((volume - 1.0) * 100)
    return f"{'+' if pct >= 0 else ''}{pct}%"


class Voice:
    """Text-to-Speech vía Edge-TTS (gratis, sin API key).

    speak_async() genera el audio en un hilo aparte y:
    - lo reproduce localmente por las bocinas del equipo (modo consola / anti-eco), y
    - si hay un listener en on_audio_ready(text, audio_b64), le entrega el
      audio en base64 (usado por server.py para mandarlo al navegador/celular).
    """

    def __init__(self):
        self.is_speaking = False
        self.on_audio_ready = None
        self._rate = _rate_to_percent(VOICE_RATE)
        self._volume = _volume_to_percent(VOICE_VOLUME)

    # ------------------------------------------------------------------
    # Síntesis
    # ------------------------------------------------------------------

    def speak_async(self, text):
        if not text or not text.strip():
            return
        threading.Thread(target=self._speak, args=(text,), daemon=True).start()

    def _speak(self, text):
        self.is_speaking = True
        try:
            audio_bytes = self._synthesize(text)
            if not audio_bytes:
                return

            if self.on_audio_ready:
                audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                self.on_audio_ready(text, audio_b64)

            self._play_locally(audio_bytes)
        except Exception as e:
            print(f"❌ Error en Voice (Edge-TTS): {e}")
        finally:
            self.is_speaking = False

    def _synthesize(self, text):
        async def _run():
            communicate = edge_tts.Communicate(text, _VOICE_NAME, rate=self._rate, volume=self._volume)
            chunks = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.extend(chunk["data"])
            return bytes(chunks)

        return asyncio.run(_run())

    # ------------------------------------------------------------------
    # Reproducción local (bocinas del equipo)
    # ------------------------------------------------------------------

    def _play_locally(self, audio_bytes):
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(audio_bytes)
                tmp_path = f.name

            if platform.system() == "Windows":
                self._play_windows(tmp_path)
            else:
                self._play_unix(tmp_path)
        except Exception as e:
            print(f"🔇 No se pudo reproducir audio localmente: {e}")
        finally:
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    @staticmethod
    def _play_windows(path):
        """Reproduce el mp3 usando MCI (winmm.dll), sin dependencias externas."""
        winmm = ctypes.windll.winmm
        alias = "mia_voice"

        def mci(cmd):
            buf = ctypes.create_unicode_buffer(255)
            err = winmm.mciSendStringW(cmd, buf, 254, 0)
            if err:
                raise RuntimeError(f"MCI error {err} en comando: {cmd}")

        mci(f'open "{path}" type mpegvideo alias {alias}')
        try:
            mci(f"play {alias} wait")
        finally:
            mci(f"close {alias}")

    @staticmethod
    def _play_unix(path):
        """Reproduce el mp3 con mpg123 (liviano, recomendado en el Pi) o ffplay como fallback."""
        players = [
            ["mpg123", "-q", path],
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path],
        ]
        for player_cmd in players:
            try:
                subprocess.run(player_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
        print("🔇 No se encontró reproductor de audio. Instala mpg123: sudo apt install mpg123")

    def stop(self):
        self.is_speaking = False
