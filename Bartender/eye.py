import cv2
import base64
import numpy as np
import time
from google import genai
from google.genai import types
from config import (
    GEMINI_API_KEY, GEMINI_VISION_MODEL, CAMERA_INDEX,
    CHANGE_THRESHOLD, CAMERA_WARMUP
)


class Eye:
    """Responsable de captura de imágenes y análisis visual via webcam + Moondream.

    Modo on-demand: la cámara se abre solo cuando se necesita y se cierra después.
    Esto evita que la luz de la cámara se quede encendida permanentemente.
    """

    def __init__(self):
        self.gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        self.vision_model = GEMINI_VISION_MODEL

        # Frame anterior para detección de cambios
        self._previous_frame_gray = None

        # Cámara on-demand (NO se abre al iniciar)
        self._cap = None
        print("📷 Cámara en modo on-demand (se activa solo cuando se necesita)")

    # ------------------------------------------------------------------
    # Cámara on-demand
    # ------------------------------------------------------------------

    def _open_camera(self):
        """(Legacy) Abre webcam local.

        En Linux/Raspberry Pi forzamos el backend V4L2 explícitamente:
        sin esto, OpenCV a veces prueba varios backends (GStreamer, FFMPEG)
        antes de encontrar el correcto, lo que agrega latencia/CPU extra
        en cada apertura de cámara on-demand.
        """
        if str(CAMERA_INDEX).isdigit():
            if self._cap is not None and self._cap.isOpened():
                return True
            self._cap = cv2.VideoCapture(int(CAMERA_INDEX), cv2.CAP_V4L2)
            if not self._cap.isOpened():
                # Fallback por si V4L2 no está disponible (ej. no-Linux)
                self._cap = cv2.VideoCapture(int(CAMERA_INDEX))
            if not self._cap.isOpened():
                return False
            time.sleep(CAMERA_WARMUP)
            return True
        return False

    def _close_camera(self):
        if self._cap is not None and self._cap.isOpened():
            self._cap.release()
        self._cap = None

    def capture_frame(self):
        """Captura un frame. Para IP Webcam, es infinitamente mejor usar /shot.jpg"""
        import urllib.request
        url_str = str(CAMERA_INDEX)

        if url_str.startswith("http"):
            # Reemplazar /video por /shot.jpg para capturas instantáneas sin cargar streams TCP
            cache_busting = f"?t={int(time.time())}"
            if "/video" in url_str:
                shot_url = url_str.replace("/video", "/shot.jpg") + cache_busting
            else:
                shot_url = url_str + cache_busting
                
            try:
                print(f"📷 Descargando Snapshot HTTP de la cámara...")
                req = urllib.request.urlopen(shot_url, timeout=6.0)
                arr = np.asarray(bytearray(req.read()), dtype=np.uint8)
                frame = cv2.imdecode(arr, -1)
                return frame
            except Exception as e:
                print(f"❌ Error descargando Snapshot Red: {e}")
                return None
        else:
            # Cámara USB Local (Fallback)
            if not self._open_camera():
                return None
            ret, frame = self._cap.read()
            return frame if ret else None

    def capture_image(self):
        """Captura una imagen, la guarda en disco y la convierte a base64."""
        frame = self.capture_frame()
        if frame is None:
            return None

        # --- NUEVO: REDIMENSIONAR PARA EVITAR FATIGA Y CORRUPCIÓN DE MOONDREAM (!!!IMAGE!!!) ---
        max_size = 800
        height, width = frame.shape[:2]
        if max(height, width) > max_size:
            scale = max_size / max(height, width)
            frame = cv2.resize(frame, (int(width * scale), int(height * scale)))

        # --- RECOMENDACIÓN APLICADA: GUARDAR EN DISCO ---
        try:
            cv2.imwrite("temp_vision.jpg", frame)
            print("💾 Foto física guardada como temp_vision.jpg a buena resolución.")
        except Exception as e:
            print("Fallo menor al guardar temp_vision.jpg:", e)
            
        _, buffer = cv2.imencode('.jpg', frame)
        image_b64 = base64.b64encode(buffer).decode('utf-8')

        # Cerrar cámara después de capturar (apaga la luz)
        self._close_camera()

        return image_b64

    # ------------------------------------------------------------------
    # Detección de cambios
    # ------------------------------------------------------------------

    def detect_change(self, threshold=None):
        """Detecta si hubo un cambio visual significativo entre el frame actual y el anterior"""
        if threshold is None:
            threshold = CHANGE_THRESHOLD

        frame = self.capture_frame()
        if frame is None:
            return False

        # Convertir a escala de grises y reducir tamaño para comparación eficiente.
        # No hace falta resolución completa para detectar "algo se movió":
        # una imagen de 160px de ancho ya es suficiente y es ~25x más liviana
        # de procesar que un frame de 800px en la CPU limitada de un Pi 3.
        gray_full = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray_full.shape[:2]
        diff_width = 160
        scale = diff_width / w
        current_gray = cv2.resize(gray_full, (diff_width, int(h * scale)))

        # Primera captura: guardar referencia y retornar False
        if self._previous_frame_gray is None:
            self._previous_frame_gray = current_gray
            self._close_camera()
            return False

        # Calcular diferencia absoluta entre frames
        diff = cv2.absdiff(self._previous_frame_gray, current_gray)
        change_magnitude = cv2.countNonZero(diff)

        # Actualizar frame de referencia DESPUÉS de comparar
        self._previous_frame_gray = current_gray

        # Cerrar cámara después de comparar
        self._close_camera()

        return change_magnitude > threshold

    # ------------------------------------------------------------------
    # Análisis visual con Moondream
    # ------------------------------------------------------------------

    def describe_image(self, image_base64):
        """Usa Gemini (multimodal) para describir una imagen en texto"""
        print("👁️ Gemini analizando imagen...")

        try:
            image_bytes = base64.b64decode(image_base64)
            response = self.gemini_client.models.generate_content(
                model=self.vision_model,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    "¿Qué hay en esta imagen? Descríbelo brevemente en español.",
                ],
                config=types.GenerateContentConfig(max_output_tokens=200),
            )
            description = (response.text or "").strip()

            if not description:
                description = "(Gemini vio la imagen pero no devolvió descripción. Ignóralo.)"

            print(f"👁️ Gemini ve: {description}")
            return description
        except Exception as e:
            print(f"❌ Error Crítico en Gemini Vision (¿sin conexión o cuota agotada?): {e}")
            return "(No se pudo analizar la imagen: problema de conexión o cuota de la API)"

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self):
        """Libera la cámara de forma segura"""
        self._close_camera()
        print("📷 Cámara liberada")
