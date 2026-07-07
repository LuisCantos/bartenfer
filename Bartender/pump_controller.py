"""pump_controller.py — Control de bombas del "Bartender 3.0", portado del
proyecto original (bartender.py) a Python 3, sin navegación por botones/OLED.

MIA llama a make_drink(nombre) cuando detecta una intención de bebida en el
comando de voz. La decisión de qué bomba activar es un simple match de texto
contra pump_config.json — deliberadamente NO se delega al LLM, porque activar
relés de líquidos debe ser determinístico y auditable.
"""
import json
import os
import time
import threading
import difflib

import RPi.GPIO as GPIO

from drinks import drink_list

PUMP_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "pump_config.json")
FLOW_RATE = 60.0 / 100.0  # segundos por mL, igual que el original

GPIO.setmode(GPIO.BCM)


class PumpController:
    def __init__(self):
        self.pump_configuration = self._read_pump_configuration()
        for pump in self.pump_configuration.values():
            GPIO.setup(pump["pin"], GPIO.OUT, initial=GPIO.HIGH)
        self._busy_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------

    @staticmethod
    def _read_pump_configuration():
        with open(PUMP_CONFIG_PATH) as f:
            return json.load(f)

    def _write_pump_configuration(self):
        with open(PUMP_CONFIG_PATH, "w") as f:
            json.dump(self.pump_configuration, f, indent="\t")

    def reload_configuration(self):
        """Vuelve a leer pump_config.json (por si se editó a mano)."""
        self.pump_configuration = self._read_pump_configuration()

    # ------------------------------------------------------------------
    # Matching de bebidas por voz
    # ------------------------------------------------------------------

    def find_drink(self, spoken_text):
        """Busca en drink_list el nombre más parecido a lo que dijo el usuario.

        Retorna el dict de la bebida o None si no hay match razonable.
        Usa difflib (stdlib, sin dependencias) para tolerar variaciones
        del STT (ej. 'jintonic' -> 'Gin & Tonic').
        """
        spoken_lower = spoken_text.lower()
        names = [d["name"] for d in drink_list]
        names_lower = [n.lower() for n in names]

        # 1. Coincidencia directa (el nombre completo aparece en el texto)
        for i, name in enumerate(names_lower):
            if name in spoken_lower:
                return drink_list[i]

        # 2. Fuzzy match como fallback (STT imperfecto)
        matches = difflib.get_close_matches(spoken_lower, names_lower, n=1, cutoff=0.55)
        if matches:
            idx = names_lower.index(matches[0])
            return drink_list[idx]

        return None

    def can_make(self, drink):
        """Verifica que todos los ingredientes de la bebida tengan bomba asignada."""
        ingredients = drink["ingredients"].keys()
        assigned_values = {p["value"] for p in self.pump_configuration.values()}
        return all(ing in assigned_values for ing in ingredients)

    # ------------------------------------------------------------------
    # Control físico
    # ------------------------------------------------------------------

    def _pour(self, pin, wait_time):
        GPIO.output(pin, GPIO.LOW)
        time.sleep(wait_time)
        GPIO.output(pin, GPIO.HIGH)

    def make_drink(self, drink, on_progress=None):
        """Sirve una bebida. `drink` es un dict de drink_list (ya resuelto por find_drink).

        on_progress(percent) es un callback opcional para reportar avance
        (ej. para actualizar el estado en la UI web de MIA).
        Retorna (True, None) si sirvió, (False, motivo) si no pudo.
        """
        if self._busy_lock.locked():
            return False, "Ya estoy preparando otra bebida"

        if not self.can_make(drink):
            return False, "Faltan ingredientes configurados para esa bebida"

        with self._busy_lock:
            pump_threads = []
            max_time = 0
            for ing, amount_ml in drink["ingredients"].items():
                for pump in self.pump_configuration.values():
                    if pump["value"] == ing:
                        wait_time = amount_ml * FLOW_RATE
                        max_time = max(max_time, wait_time)
                        t = threading.Thread(target=self._pour, args=(pump["pin"], wait_time))
                        pump_threads.append(t)

            for t in pump_threads:
                t.start()

            if on_progress:
                interval = max_time / 20.0 if max_time else 0
                for step in range(1, 21):
                    time.sleep(interval)
                    on_progress(step * 5)

            for t in pump_threads:
                t.join()

        return True, None

    def clean(self, wait_time=20, on_progress=None):
        """Activa todas las bombas simultáneamente para enjuagar las mangueras."""
        if self._busy_lock.locked():
            return False, "Ya hay una operación de bombas en curso"

        with self._busy_lock:
            pump_threads = [
                threading.Thread(target=self._pour, args=(p["pin"], wait_time))
                for p in self.pump_configuration.values()
            ]
            for t in pump_threads:
                t.start()

            if on_progress:
                interval = wait_time / 20.0
                for step in range(1, 21):
                    time.sleep(interval)
                    on_progress(step * 5)

            for t in pump_threads:
                t.join()

        return True, None

    def cleanup(self):
        GPIO.cleanup()
