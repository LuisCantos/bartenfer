from flask import Flask, render_template
from flask_socketio import SocketIO
import threading
import time
import sys
import io
from assistant import VoiceAssistant

# Fix consola Windows UTF-8 (Método seguro para Python 3.7+)
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

app = Flask(__name__)
# Inicializar SocketIO usando threading estándar para evitar alertas de obsolescencia
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

mia = None

# Variable global para notificar cuando la UI termina de hablar
audio_playback_done = threading.Event()

def start_mia_backend():
    """Inicia MIA en un hilo separado"""
    global mia
    mia = VoiceAssistant()
    
    # Cada vez que MIA cambia de estado, se emite al Socket
    def on_mia_state_change(new_state, data=None):
        if new_state == "audio_payload_chunk":
            # Hemos recibido un MP3 en base64 de Edge-TTS (Stream chunk)
            socketio.emit('play_audio_chunk', {
                'text': data['text'],
                'audio_b64': data['audio']
            })
            # IMPORTANTE: No bloqueamos aquí para permitir que los chunks fluyan asíncronamente a la UI
            
        else:
            socketio.emit('state_update', {
                "state": new_state,
                "text": data if data else ""
            })
            
    mia.on_state_change = on_mia_state_change
    mia.start()

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('audio_finished')
def handle_audio_finished():
    """El navegador web avisa que terminó de reproducir toda la cola de audios"""
    audio_playback_done.set()

@socketio.on('user_command')
def handle_text_command(data):
    """Comandos enviados desde el PTT de la página web nativa"""
    if mia and mia.ear:
        text = data.get("text", "").strip()
        if text:
            print(f"🌐 Recibido PTT Web: {text}")
            mia.ear.audio_queue.put(text)
            mia.set_state("listening")

@socketio.on('request_vision')
def handle_request_vision():
    """Botón explícito de 'Analizar Entorno' desde el navegador"""
    if mia and mia.ear:
        print("🌐 Solicitud Manual de Visión recibida")
        # Inyectar un comando simulado que tiene las palabras clave de visión
        mia.ear.audio_queue.put("mira esto y dime qué ves")
        mia.set_state("listening")

# Bartender 3.0 (control de bombas) ya está integrado — ver pump_controller.py
# y el routing por DRINK_KEYWORDS en assistant.py._listen_for_commands

if __name__ == '__main__':
    mia_thread = threading.Thread(target=start_mia_backend, daemon=True)
    mia_thread.start()
    
    time.sleep(2)
    print("\n" + "="*50)
    print("🌐 SERVIDOR SOCKET.IO INICIADO")
    print("👉 Abre http://[IP_DE_TU_LAPTOP]:5000 en tu celular o ingresa en localhost:5000 en el navegador")
    print("="*50 + "\n")
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False)
