import threading
import time
from queue import Empty
from eye import Eye
from ear import Ear
from voice import Voice
from brain import Brain
from config import (
    VISUAL_COMMENT_COOLDOWN, VISION_CHECK_INTERVAL,
    VISION_POST_COMMENT_PAUSE, HEALTH_CHECK_INTERVAL,
    PROACTIVE_VISION, VISION_KEYWORDS, DRINK_KEYWORDS
)
try:
    from pump_controller import PumpController
except ImportError:
    PumpController = None  # Permite correr MIA sin hardware de bombas conectado


class VoiceAssistant:
    """Orquesta visión, audio y respuestas de MIA.

    Flujo:
    - Thread de audio: escucha 'Hey MIA' → captura comando → responde
    - Thread de visión (opcional): detecta cambios visuales → comenta
    - Thread de salud: monitorea conexión al S25 Ultra

    Anti-eco: El oído se silencia mientras MIA habla.
    Cámara on-demand: Solo se enciende cuando se necesita.
    """

    def __init__(self):
        print("=" * 50)
        print("🤖 Inicializando MIA...")
        print("=" * 50)

        self.eye = Eye()
        self.ear = Ear()
        self.voice = Voice()
        self.brain = Brain()

        self.pump_controller = PumpController() if PumpController else None
        if self.pump_controller is None:
            print("🍹 Bartender 3.0: hardware de bombas no disponible (modo solo-voz)")

        self.is_running = False
        self._last_visual_comment = 0
        self._threads = []

        # Estado del sistema (para la UI Web)
        self.state = "idle"
        self.on_state_change = None

        # Lock para evitar que MIA hable de visión mientras responde al usuario
        self._speaking_lock = threading.Lock()

        # Anti-eco y prevención de conflictos de audio:
        self.ear.set_mute_check(lambda: self._speaking_lock.locked() or self.voice.is_speaking)

        # Confirmación auditiva: cuando detecta "Hey MIA", dice "¿Sí?"
        # para que el usuario sepa que debe hablar
        self.ear.set_wake_callback(lambda: self.voice.speak_async("¿Sí?"))

        print("=" * 50)
        print("✅ MIA lista para funcionar")
        print("=" * 50)

    # ------------------------------------------------------------------
    # Thread: Visión proactiva (OPCIONAL)
    # ------------------------------------------------------------------

    def _react_to_vision(self):
        """Monitorea cambios visuales y comenta automáticamente.
        Solo se ejecuta si PROACTIVE_VISION = True en config.
        """
        print("👁️ Thread de visión proactiva iniciado")

        while self.is_running:
            try:
                time.sleep(VISION_CHECK_INTERVAL)

                if not self.is_running:
                    break

                # No comentar si está en cooldown
                if time.time() - self._last_visual_comment < VISUAL_COMMENT_COOLDOWN:
                    continue

                # No comentar si está atendiendo al usuario o hablando
                if self._speaking_lock.locked() or self.voice.is_speaking:
                    continue

                # Detectar cambio visual
                if not self.eye.detect_change():
                    continue

                # Capturar y describir lo que ve
                image_base64 = self.eye.capture_image()
                if not image_base64:
                    continue

                visual_desc = self.eye.describe_image(image_base64)
                if not visual_desc:
                    continue

                # Generar comentario sarcástico
                with self._speaking_lock:
                    mia_comment = self.brain.think_about_vision(visual_desc)
                    if mia_comment:
                        self.voice.speak_async(mia_comment)
                        self._last_visual_comment = time.time()
                        # Pausa larga después de comentar para no saturar
                        time.sleep(VISION_POST_COMMENT_PAUSE)

            except Exception as e:
                print(f"❌ Error en thread de visión: {e}")
                time.sleep(10)  # Pausa larga tras error

    def _needs_vision(self, text):
        """Determina si el comando requiere usar la cámara.

        'Hey MIA di hola' → False (solo hablar, rápido)
        'Hey MIA mira esto' → True (usar cámara + Moondream)
        """
        text_lower = text.lower()
        return any(kw in text_lower for kw in VISION_KEYWORDS)

    def _needs_drink(self, text):
        """Determina si el comando pide que se sirva una bebida (Bartender 3.0)."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in DRINK_KEYWORDS)

    def set_state(self, new_state, data=None):
        """Actualiza el estado de MIA y notifica a los listeners (servidor web)"""
        self.state = new_state
        if self.on_state_change:
            self.on_state_change(new_state, data)

    def _listen_for_commands(self):
        """Escucha comandos del usuario activados por wake word 'Hey MIA'

        Routing inteligente:
        - Comando con palabra visual (mira, observa, etc.) → cámara + Moondream + cerebro
        - Comando normal (di hola, cuéntame, etc.) → solo cerebro (rápido)
        """
        print("🎤 Thread de audio iniciado")

        # Configurar callback cuando Ear.py entra en modo activo "escuchando" (Para la Laptop/Pantalla Gigante)
        self.ear.set_wake_callback(lambda: [
            self.set_state("listening"), 
            self.voice.speak_async("¿Sí?")
        ])

        # Iniciar escucha continua hibrida (El PTT Web también inyectará a esta misma cola)
        self.ear.start_listening_thread()
        print("🎧 Sistema Híbrido Activado: Escuchando micrófono Windows y Web PTT simultáneamente.")

        while self.is_running:
            try:
                # Esperar comando transcrito (de PTT Web o de Ear.py)
                user_input = self.ear.audio_queue.get(timeout=1)

                print(f"👤 Usuario dice: {user_input}")

                with self._speaking_lock:
                    visual_context = ""

                    # Bartender 3.0: si pide una bebida, resolver por match de texto
                    # ANTES de tocar al LLM — activar bombas es una decisión determinística.
                    if self.pump_controller and self._needs_drink(user_input):
                        drink = self.pump_controller.find_drink(user_input)
                        if drink:
                            self.set_state("pouring", data=drink["name"])
                            self.voice.speak_async(f"Marchando un {drink['name']}, creador.")
                            ok, error = self.pump_controller.make_drink(
                                drink,
                                on_progress=lambda pct: self.set_state("pouring_progress", pct)
                            )
                            if ok:
                                self.voice.speak_async(f"Listo, tu {drink['name']} está servido.")
                            else:
                                self.voice.speak_async(f"No pude prepararlo: {error}")
                            self.set_state("idle")
                            continue
                        else:
                            self.voice.speak_async("No reconocí esa bebida en el menú.")
                            self.set_state("idle")
                            continue

                    # Solo usar cámara si el usuario lo pide explícitamente
                    if self._needs_vision(user_input):
                        self.set_state("vision", data=user_input)
                        print("👁️ Modo VISIÓN activado")
                        image_base64 = self.eye.capture_image()
                        if image_base64:
                            visual_context = self.eye.describe_image(image_base64)
                    else:
                        print("⚡ Modo RÁPIDO (sin cámara)")

                    # Generar respuesta (ahora devuelve un Generador)
                    self.set_state("thinking", data=user_input)
                    response_gen = self.brain.respond_to_user(
                        user_input, visual_context
                    )

                    # Reproducir respuesta chunk por chunk
                    if response_gen:
                        import server # Para usar de forma segura la flag del server principal
                        server.audio_playback_done.clear()
                        
                        is_first = True
                        for chunk_text in response_gen:
                            if is_first:
                                self.set_state("speaking", data={"text": chunk_text})
                                is_first = False
                            
                            # Callback en-sitio que el generador de Audio llama cuando tiene el pedazo mp3
                            def push_audio_chunk(text_resp, b64_audio):
                                self.set_state("audio_payload_chunk", {"text": text_resp, "audio": b64_audio})
                                
                            self.voice.on_audio_ready = push_audio_chunk
                            self.voice.speak_async(chunk_text)
                            
                        # El backend ya procesó e inyectó todo el texto a Edge-TTS.
                        # Ahora bloqueamos la reactivación de listening local del orquestador 
                        # hasta que el celular confirme que la COLA EN JavaScript terminó de sonar.
                        server.audio_playback_done.wait(timeout=60.0)
                        
                        self.set_state("idle")

            except Empty:
                # Si estamos escuchando, no hay comando en la cola, y el micro de Windows está inactivo, volver a dormir.
                if self.state == "listening" and not self.ear.is_activated:
                    self.set_state("idle")
                continue
            except Exception as e:
                print(f"❌ Error en thread de audio: {e}")
                time.sleep(1)


    # Control del asistente
    # ------------------------------------------------------------------

    def start(self):
        """Inicia todos los threads de MIA"""
        if self.is_running:
            print("⚠️ MIA ya está en ejecución")
            return

        self.is_running = True
        print("\n🟢 MIA activada — Di 'Hey MIA' para hablarme\n")

        # Crear y lanzar threads
        thread_targets = [
            ("Audio", self._listen_for_commands),
        ]

        # Visión proactiva solo si está habilitada
        if PROACTIVE_VISION:
            thread_targets.insert(0, ("Vision", self._react_to_vision))
            print("👁️ Visión proactiva ACTIVADA")
        else:
            print("👁️ Visión en modo ON-DEMAND (solo cuando hablas)")

        for name, target in thread_targets:
            t = threading.Thread(target=target, daemon=True, name=f"MIA-{name}")
            t.start()
            self._threads.append(t)

    def stop(self):
        """Detiene MIA y libera todos los recursos"""
        print("\n🔴 Deteniendo MIA...")
        self.is_running = False

        # Detener subsistemas
        self.ear.stop_listening()
        self.voice.stop()
        self.eye.cleanup()
        if self.pump_controller:
            self.pump_controller.cleanup()

        # Esperar a que terminen threads
        for t in self._threads:
            t.join(timeout=3)

        self._threads.clear()
        print("✅ MIA desactivada\n")

    def run_interactive(self):
        """Ejecución interactiva con control por teclado"""
        self.start()

        try:
            while self.is_running:
                cmd = input(
                    "\n📋 Comandos: 'salir' | 'estado' | 'historial' | 'memoria' | 'enseñar' | 'recuerdos'\n> "
                ).strip().lower()

                if cmd == "salir":
                    self.stop()
                    break
                elif cmd == "estado":
                    connected = self.brain.is_connected()
                    active = len([t for t in self._threads if t.is_alive()])
                    mem_stats = self.brain.get_memory_stats()
                    print(f"  🧠 S25 Ultra: {'Conectado' if connected else 'Desconectado'}")
                    print(f"  🧵 Hilos activos: {active}/{len(self._threads)}")
                    print(f"  📷 Cámara: On-demand ({'proactiva' if PROACTIVE_VISION else 'solo al hablar'})")
                    print(f"  🎤 Wake word: {'escuchando comando' if self.ear.is_activated else 'esperando Hey MIA'}")
                    print(f"  🔇 Anti-eco: {'MUTED (MIA hablando)' if self.voice.is_speaking else 'escuchando'}")
                    print(f"  🧬 Memoria: {'Activa' if mem_stats['enabled'] else 'Desactivada'}"
                          f" — {mem_stats['conversations']} conversaciones, {mem_stats['knowledge']} conocimientos")
                elif cmd == "historial":
                    history = self.brain._format_history()
                    if history:
                        print(f"\n📜 Historial de sesión:\n{history}")
                    else:
                        print("📜 Sin historial en esta sesión")
                elif cmd == "memoria":
                    stats = self.brain.get_memory_stats()
                    if stats["enabled"]:
                        print(f"\n🧬 Memoria a largo plazo (ChromaDB):")
                        print(f"  📝 Conversaciones almacenadas: {stats['conversations']}")
                        print(f"  📚 Conocimientos almacenados: {stats['knowledge']}")
                    else:
                        print("⚠️ Memoria a largo plazo desactivada")
                elif cmd.startswith("enseñar") or cmd.startswith("ensenar"):
                    fact = input("📚 ¿Qué quieres que MIA recuerde? > ").strip()
                    if fact:
                        category = input("📂 Categoría (preferencia/dato_personal/general/instruccion) [general] > ").strip() or "general"
                        if self.brain.learn_fact(fact, category):
                            print("✅ MIA recordará esto permanentemente")
                        else:
                            print("❌ No se pudo guardar")
                elif cmd.startswith("recuerdos"):
                    query = input("🔍 ¿Qué quieres buscar en la memoria? > ").strip()
                    if query and self.brain.memory:
                        memories = self.brain.memory.recall_conversations(query, n_results=5)
                        if memories:
                            print(f"\n🧬 {len(memories)} recuerdos encontrados:")
                            for i, mem in enumerate(memories, 1):
                                print(f"  {i}. Fernando: \"{mem['user_message']}\"")
                                print(f"     MIA: \"{mem['mia_response']}\"")
                        else:
                            print("🧬 No encontré recuerdos relacionados")
                    elif not self.brain.memory:
                        print("⚠️ Memoria no disponible")
                elif cmd:
                    print("❓ Comando no reconocido")

        except KeyboardInterrupt:
            print("\n⏹️ Interrupción del usuario")
            self.stop()