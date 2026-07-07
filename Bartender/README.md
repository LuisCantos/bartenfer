# MIA — Asistente de Voz con Visión y Bartender 3.0

MIA es un asistente de voz personal que corre en una Raspberry Pi (recomendado: Pi 3, 1GB RAM), con:

- **Wake word** ("Hey MIA") y comandos por voz en español
- **Visión bajo demanda** vía webcam (Gemini multimodal describe lo que ve)
- **Memoria a largo plazo** ligera (embeddings + búsqueda por similitud, sin bases de datos pesadas)
- **Interfaz web** opcional (Flask + SocketIO) para push-to-talk y estado en tiempo real desde el celular
- **Bartender 3.0**: control de bombas peristálticas para preparar bebidas por comando de voz

El "cerebro" (generación de texto, visión y embeddings) corre en la **API gratuita de Gemini** de Google — no necesitas GPU propia, servidor remoto, ni mantener un backend de inferencia encendido.

---

## Arquitectura

```
┌─────────────────────┐        HTTPS         ┌──────────────────┐
│   Raspberry Pi       │ ───────────────────▶ │   Gemini API      │
│  (MIA orquesta todo) │ ◀─────────────────── │  (Google, gratis) │
└─────────┬────────────┘                      └──────────────────┘
          │
          ├── ear.py     → wake word + STT (Google Speech-to-Text)
          ├── eye.py     → captura webcam + describe imagen (Gemini)
          ├── voice.py   → TTS (Edge-TTS, gratis)
          ├── brain.py   → conversación + memoria (Gemini)
          ├── memory.py  → embeddings (Gemini) + similitud coseno (numpy)
          ├── pump_controller.py → bombas del Bartender 3.0 (GPIO)
          └── server.py  → interfaz web (opcional)
```

Todo lo "pesado" (LLM, visión, embeddings) vive en la nube de Google. El Pi solo orquesta: escucha, decide qué hacer, y habla — por eso funciona en un equipo de 1GB de RAM.

---

## Requisitos previos

### Hardware
- Raspberry Pi 3 (o superior) con Raspberry Pi OS
- Micrófono (se usó un micrófono virtual vía AudioRelay, pero cualquier micrófono USB/analógico funciona)
- Webcam USB
- *(Opcional, Bartender 3.0)*: bombas peristálticas + relés conectados a GPIO, según `pump_config.json`

### Cuenta y API key de Gemini
1. Ve a [aistudio.google.com/apikey](https://aistudio.google.com/apikey) y genera una API key gratis (no requiere tarjeta).
2. Expórtala como variable de entorno en el Pi:
   ```bash
   echo 'export GEMINI_API_KEY="tu-key-aqui"' >> ~/.bashrc
   source ~/.bashrc
   ```

⚠️ **Nota de privacidad**: en el free tier, Google puede usar tus prompts/respuestas para mejorar sus productos. Si esto te preocupa (MIA guarda conversaciones personales en su memoria), considera habilitar billing — Gemini Flash es muy barato incluso de pago, y salir del free tier cambia ese trato de datos.

⚠️ **Límites del free tier**: cambian seguido. A julio 2026, los modelos gratis son la familia Flash/Flash-Lite (los modelos Pro salieron del free tier en abril 2026), con límites de ~10-15 solicitudes/minuto y ~1000-1500/día según el modelo. Revisa los límites vigentes en [ai.google.dev/gemini-api/docs/rate-limits](https://ai.google.dev/gemini-api/docs/rate-limits).

---

## Instalación

```bash
# Clona/copia el proyecto en el Pi
cd ~/mia

# Instala dependencias (usa --break-system-packages en Raspberry Pi OS moderno)
pip install -r requirements.txt --break-system-packages
```

Si `opencv-python-headless` o `pyaudio` intentan compilar desde código fuente y tarda muchísimo o se cuelga por RAM, instala las versiones del sistema en su lugar:

```bash
sudo apt install python3-opencv python3-pyaudio python3-numpy
```

Verifica que `pip.conf` apunte a [piwheels.org](https://www.piwheels.org) (viene por defecto en Raspberry Pi OS) para obtener wheels prearmados para ARM en vez de compilar.

### Habilitar hardware (si usas OLED/GPIO del Bartender 3.0)

```bash
sudo raspi-config
```
Navega a `Interfacing Options` → habilita `SPI` e `I2C` si tu configuración de hardware los requiere, y reinicia.

---

## Configuración

Todo se ajusta en `config.py`:

| Variable | Qué hace |
|---|---|
| `GEMINI_API_KEY` | Se lee de la variable de entorno, no la hardcodees aquí |
| `GEMINI_TEXT_MODEL` / `GEMINI_VISION_MODEL` | Modelo de Gemini a usar (default: `gemini-2.5-flash`) |
| `MICROPHONE_NAME` | Nombre (parcial) del micrófono a usar |
| `CAMERA_INDEX` | Índice de la webcam, o URL `http://.../video` para IP Webcam |
| `PROACTIVE_VISION` | `True` = MIA comenta sola lo que ve; `False` = solo cuando se le pide (recomendado en Pi) |
| `MEMORY_ENABLED` | Activa/desactiva la memoria a largo plazo |
| `DRINK_KEYWORDS` | Palabras que activan el routing al Bartender 3.0 |
| `MIA_SYSTEM_PROMPT` | Personalidad de MIA |

---

## Uso

### Modo consola (interactivo)

```bash
python3 main.py
```

Di **"Hey MIA"** para activarla, o usa estos comandos de texto en la consola:

| Comando | Qué hace |
|---|---|
| `estado` | Muestra conexión, hilos activos, memoria |
| `historial` | Muestra el historial de la sesión actual |
| `memoria` | Estadísticas de la memoria a largo plazo |
| `enseñar` | Le enseña un dato nuevo a MIA para que lo recuerde siempre |
| `recuerdos` | Busca en la memoria a largo plazo |
| `salir` | Detiene MIA y libera hardware |

### Modo servidor web (recomendado para uso diario)

```bash
python3 server.py
```

Abre `http://<IP_DEL_PI>:5000` desde tu celular en la misma red para usar push-to-talk, ver el estado de MIA en vivo, y disparar el análisis de visión manualmente.

### Ejecutar al iniciar el Pi

Agrega a `/etc/rc.local` (antes de la última línea):

```bash
cd /home/pi/mia
sudo python3 server.py &
```

---

## Comandos de voz de ejemplo

| Dices | MIA hace |
|---|---|
| "Hey MIA, ¿cómo estás?" | Responde por texto/voz (rápido, sin cámara) |
| "Hey MIA, mira esto y dime qué ves" | Activa la cámara, describe la imagen con Gemini |
| "Hey MIA, hazme un Gin & Tonic" | Enruta a Bartender 3.0, sirve la bebida por las bombas |
| "Hey MIA, recuerda que no me gusta el vodka" | Guarda el dato en memoria a largo plazo |

---

## Bartender 3.0 — Configuración de bombas

`pump_config.json` mapea cada bomba a un pin GPIO y a un ingrediente:

```json
"pump_1": { "name": "Pump 1", "pin": 17, "value": "gin" }
```

Las recetas viven en `drinks.py` (`drink_list`, en mililitros por ingrediente). MIA solo puede preparar bebidas cuyos ingredientes tengan **todas** sus bombas asignadas — si falta una, la reconocerá pero avisará que no puede prepararla.

Para enjuagar las mangueras (limpieza), llama a `pump_controller.clean()` — coloca todas las mangueras en agua primero.

⚠️ La decisión de qué bomba activar **nunca** pasa por el LLM: es un match de texto determinístico (`pump_controller.find_drink`), para que la preparación de bebidas sea predecible y auditable.

---

## Estructura del proyecto

```
mia/
├── main.py              # Punto de entrada modo consola
├── server.py            # Punto de entrada modo servidor web
├── assistant.py         # Orquestador: audio + visión + routing de comandos
├── brain.py             # Conversación con Gemini API
├── eye.py               # Captura y análisis de imágenes (Gemini)
├── ear.py                # Wake word + Speech-to-Text
├── voice.py             # Text-to-Speech (Edge-TTS)
├── memory.py            # Memoria a largo plazo (embeddings + numpy)
├── pump_controller.py   # Control de bombas del Bartender 3.0
├── drinks.py            # Recetas de bebidas
├── pump_config.json     # Mapeo de bombas ↔ pines GPIO ↔ ingredientes
├── config.py            # Configuración central
└── requirements.txt
```

---

## Solución de problemas

**"GEMINI_API_KEY no está configurada"** → revisa `echo $GEMINI_API_KEY` en la misma terminal donde corres MIA; si usas `sudo python3`, el entorno de root puede no tener la variable — considera agregarla también a `/etc/environment` o exportarla justo antes del comando con `sudo`.

**Error 429 / cuota agotada** → llegaste al límite del free tier de Gemini. Espera al reinicio de cuota (medianoche hora del Pacífico) o revisa si necesitas subir a billing.

**El micrófono no se encuentra** → corre este snippet para listar los dispositivos disponibles y ajusta `MICROPHONE_NAME` en `config.py`:
```python
import speech_recognition as sr
print(sr.Microphone.list_microphone_names())
```

**La cámara no abre / da error V4L2** → confirma el índice correcto con `ls /dev/video*` y ajusta `CAMERA_INDEX`.

**Las bombas no activan / error de GPIO** → confirma que los pines en `pump_config.json` coincidan con tu cableado físico, y que ningún otro proceso tenga los pines GPIO reservados (`sudo pkill -f pump` o reinicia el Pi si quedaron "atascados").
