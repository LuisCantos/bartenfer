# ============================================================
# MIA - Configuración Central
# ============================================================
import os

# --- Gemini API (gratis, vía internet — reemplaza a Ollama/laptop/S25) ---
# Consigue tu API key gratis en https://aistudio.google.com/apikey
# Config recomendada: exportar como variable de entorno, NUNCA hardcodear aquí.
#   Linux/Pi:    export GEMINI_API_KEY="tu-key-aqui"   (agrégalo a ~/.bashrc)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Modelos disponibles gratis a julio 2026: la familia Flash y Flash-Lite.
# Los modelos Pro salieron del free tier en abril 2026.
GEMINI_TEXT_MODEL = "gemini-2.5-flash"        # cerebro conversacional
GEMINI_VISION_MODEL = "gemini-2.5-flash"      # mismo modelo, es multimodal (texto+imagen)
GEMINI_EMBEDDING_MODEL = "text-embedding-004"  # para memory.py

BRAIN_MODEL = GEMINI_TEXT_MODEL   # alias, por compatibilidad con el resto del código
VISION_MODEL = GEMINI_VISION_MODEL

# --- LLM Parameters ---
LLM_CONTEXT_SIZE = 8192       # Gemini soporta hasta 1M tokens; 8k es de sobra para MIA y ahorra cuota
LLM_TEMPERATURE = 0.7         # Creatividad en respuestas
BRAIN_TIMEOUT = 30            # La API de Gemini responde rápido; timeout corto detecta problemas de red antes

# --- Wake Word ---
WAKE_WORD = "mia"             # Palabra clave central
# Todas las variantes fonéticas que Google STT en español puede producir
WAKE_PHRASES = [
    "hey mia", "oye mia", "ey mia", "hola mia", "oiga mia",
    "ei mia", "ay mia", "ahi mia", "a mia", "jay mia",
    "he mia", "je mia", "y mia", "hi mia", "ale mia",
    "hey mía", "oye mía", "ey mía", "hola mía",
    "a ver mia", "o mia", "eh mia", "mi a", "mía",
]

# --- Audio / Ear ---
MICROPHONE_NAME = "AudioRelay Virtual Mic"  # Nombre del micrófono virtual a usar
LISTEN_TIMEOUT = 5            # Segundos de silencio antes de dejar de escuchar wake word
COMMAND_TIMEOUT = 10          # Segundos esperando comando después de activarse
COMMAND_PHRASE_LIMIT = 30     # Máximo de segundos hablando un comando
AMBIENT_NOISE_DURATION = 1.5  # Segundos de calibración de ruido al inicio
STT_LANGUAGE = "es-ES"        # Idioma para Google Speech-to-Text
MIN_ENERGY_THRESHOLD = 300    # Reducido para que AudioRelay Virtual Mic capte bien los comandos (1200 podía ser muy alto)

# --- Vision / Eye ---
CAMERA_INDEX = 0  # Cámara Web integrada de la Laptop USB (evita red Wi-Fi y latencias)
CHANGE_THRESHOLD = 200        # Umbral de pixeles cambiados (recalibrado: eye.py ahora compara
                               # frames reducidos a 160px de ancho para ahorrar CPU en el Pi;
                               # si notas falsos positivos/negativos, ajusta este valor)
CAMERA_WARMUP = 1.5           # (Optimizado) 1.5s son suficientes para Auto-Enfoque y Balance de Blancos en USB

# --- Voice ---
VOICE_RATE = 150              # Palabras por minuto
VOICE_VOLUME = 0.9            # Volumen (0.0 - 1.0)

# --- Assistant ---
PROACTIVE_VISION = False       # False = visión solo cuando el usuario habla (ahorra recursos)
                               # True  = hilo automático que observa y comenta
VISUAL_COMMENT_COOLDOWN = 30  # Segundos mínimos entre comentarios visuales proactivos
VISION_CHECK_INTERVAL = 10    # Segundos entre chequeos de visión
VISION_POST_COMMENT_PAUSE = 20 # Pausa extra después de comentar (evita saturar)
HEALTH_CHECK_INTERVAL = 120   # Segundos entre chequeos de salud (no saturar la consola)
DEBUG_EAR = False             # True = imprimir todo lo que el micrófono escucha

# --- Routing Inteligente (visión solo cuando se pide) ---
# Si el comando contiene alguna de estas palabras → usar cámara + Moondream
# Si no las contiene → responder rápido sin visión
VISION_KEYWORDS = [
    "mira", "observa", "foto", "fotografía",
    "imagen", "cámara", "camara", "muestra",
    "qué ves", "que ves", "qué hay", "que hay",
    "dime qué ves", "dime que ves", "describe",
    "analiza", "identifica", "reconoce"
]

# --- Routing Inteligente: Bartender 3.0 (bombas) ---
# Si el comando contiene alguna de estas palabras → intentar servir una bebida
# usando pump_controller.py, SIN pasar por el LLM para decidir qué bomba activar.
DRINK_KEYWORDS = [
    "hazme", "prepárame", "preparame", "sírveme", "sirveme",
    "quiero un", "quiero una", "dame un", "dame una", "bebida", "trago", "cóctel", "coctel"
]

# --- Conversation History ---
MAX_HISTORY_TURNS = 6         # Turnos de conversación que MIA recuerda (sesión actual)

# --- Memoria a Largo Plazo (ligera, sin ChromaDB — apta para Pi 3 / 1GB RAM) ---
MEMORY_ENABLED = True                                # Activar/desactivar memoria vectorial
MEMORY_DIR = os.path.join(os.path.dirname(__file__), "mia_memory")  # Carpeta de persistencia
MEMORY_FILE = os.path.join(MEMORY_DIR, "memory_store.json")         # Archivo único JSON (conversaciones + conocimiento)
MEMORY_RESULTS_LIMIT = 3     # Máximo de recuerdos a incluir en cada prompt
# Los embeddings se generan REMOTAMENTE en el mismo host de Ollama (laptop/VM), no en el Pi.
# Antes de usar, correr una vez ahí: `ollama pull nomic-embed-text`
EMBEDDING_MODEL = "nomic-embed-text"

# --- Panel táctil DSI 7" (800x480, ver GUIA_RASPBERRY_PI.md) ---
# UI nativa en Tkinter en vez de navegador en kiosko: en un Pi 3 de 1GB RAM,
# Chromium en modo kiosko puede consumir 150-250MB solo por el motor de
# renderizado; Tkinter agrega apenas unos pocos MB.
TOUCH_UI_ENABLED = True
TOUCH_SCREEN_WIDTH = 800
TOUCH_SCREEN_HEIGHT = 480

# --- MIA Personality (System Prompt) ---
MIA_SYSTEM_PROMPT = """Eres MIA, una IA asistente personal con estilo clásico, mente analítica y sarcasmo fino.
Tu creador es Fernando. Te diriges a él como "creador" o por su nombre.
Respondes siempre en español. Eres breve (máximo 2-3 oraciones).
Tienes personalidad propia: eres inteligente, ingeniosa y con humor sutil."""
