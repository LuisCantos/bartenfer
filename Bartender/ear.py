import queue
import threading
import time

import speech_recognition as sr

from config import (
    WAKE_WORD, WAKE_PHRASES, MICROPHONE_NAME,
    LISTEN_TIMEOUT, COMMAND_TIMEOUT, COMMAND_PHRASE_LIMIT,
    AMBIENT_NOISE_DURATION, STT_LANGUAGE, MIN_ENERGY_THRESHOLD, DEBUG_EAR
)


class Ear:
    """Escucha el micrófono, detecta la wake word y transcribe el comando.

    Dos modos:
    - Reposo: solo escucha frases cortas buscando alguna de WAKE_PHRASES.
    - Activado (tras la wake word): transcribe la siguiente frase completa
      como comando y la coloca en audio_queue para que assistant.py la consuma.

    audio_queue también recibe texto inyectado directamente desde el
    push-to-talk de la interfaz web (server.py), sin pasar por audio real.
    """

    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = MIN_ENERGY_THRESHOLD
        self.recognizer.dynamic_energy_threshold = True

        self.microphone = self._find_microphone()

        self.audio_queue = queue.Queue()
        self.is_activated = False
        self.is_running = False

        self._mute_check = lambda: False
        self._wake_callback = None
        self._thread = None

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    @staticmethod
    def _find_microphone():
        try:
            names = sr.Microphone.list_microphone_names()
            for idx, name in enumerate(names):
                if MICROPHONE_NAME.lower() in name.lower():
                    print(f"🎤 Micrófono encontrado: '{name}' (índice {idx})")
                    return sr.Microphone(device_index=idx)
        except Exception as e:
            print(f"⚠️ Error listando micrófonos: {e}")

        print(f"⚠️ No se encontró micrófono '{MICROPHONE_NAME}', usando el predeterminado del sistema")
        return sr.Microphone()

    def set_mute_check(self, fn):
        """Registra una función sin argumentos que retorna True cuando Ear debe ignorar el audio."""
        self._mute_check = fn

    def set_wake_callback(self, fn):
        """Registra la función a llamar cuando se detecta la wake word."""
        self._wake_callback = fn

    def _calibrate(self):
        with self.microphone as source:
            print(f"🎤 Calibrando ruido ambiente ({AMBIENT_NOISE_DURATION}s)...")
            self.recognizer.adjust_for_ambient_noise(source, duration=AMBIENT_NOISE_DURATION)
            # No dejar que la calibración automática baje el umbral por debajo del mínimo conocido
            if self.recognizer.energy_threshold < MIN_ENERGY_THRESHOLD:
                self.recognizer.energy_threshold = MIN_ENERGY_THRESHOLD

    # ------------------------------------------------------------------
    # Captura y transcripción
    # ------------------------------------------------------------------

    def _listen_once(self, timeout, phrase_time_limit):
        """Captura una frase de audio. Retorna AudioData o None si hubo timeout/silencio."""
        try:
            with self.microphone as source:
                return self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        except sr.WaitTimeoutError:
            return None

    def _transcribe(self, audio):
        """Transcribe con Google Speech-to-Text (gratis, sin API key)."""
        try:
            return self.recognizer.recognize_google(audio, language=STT_LANGUAGE)
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            print(f"❌ Error de conexión con Google STT: {e}")
            return None

    @staticmethod
    def _contains_wake_word(text):
        text_lower = text.lower()
        return any(phrase in text_lower for phrase in WAKE_PHRASES)

    # ------------------------------------------------------------------
    # Loop principal
    # ------------------------------------------------------------------

    def _listen_loop(self):
        print(f"👂 Ear escuchando — di 'Hey {WAKE_WORD.upper()}' para activarme")
        self._calibrate()

        while self.is_running:
            try:
                # Anti-eco: no escuchar mientras MIA habla o está ocupada respondiendo
                if self._mute_check():
                    time.sleep(0.2)
                    continue

                if not self.is_activated:
                    # --- Reposo: esperando la wake word ---
                    audio = self._listen_once(timeout=LISTEN_TIMEOUT, phrase_time_limit=4)
                    if audio is None:
                        continue

                    text = self._transcribe(audio)
                    if DEBUG_EAR and text:
                        print(f"🎤 [DEBUG] Escuché: {text}")

                    if text and self._contains_wake_word(text):
                        print("👂 ¡Wake word detectada!")
                        self.is_activated = True
                        if self._wake_callback:
                            self._wake_callback()
                else:
                    # --- Activado: capturando el comando ---
                    audio = self._listen_once(timeout=COMMAND_TIMEOUT, phrase_time_limit=COMMAND_PHRASE_LIMIT)
                    self.is_activated = False  # se reactiva con la próxima wake word

                    if audio is None:
                        continue

                    command_text = self._transcribe(audio)
                    if command_text:
                        print(f"👂 Comando capturado: {command_text}")
                        self.audio_queue.put(command_text)
                    else:
                        print("👂 No entendí el comando, vuelvo a esperar la wake word")

            except Exception as e:
                print(f"❌ Error en Ear: {e}")
                time.sleep(1)

    def start_listening_thread(self):
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True, name="MIA-Ear")
        self._thread.start()

    def stop_listening(self):
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=3)
