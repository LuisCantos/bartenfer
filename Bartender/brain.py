from google import genai
from google.genai import types
from google.genai.errors import APIError

from config import (
    GEMINI_API_KEY, GEMINI_TEXT_MODEL,
    LLM_CONTEXT_SIZE, LLM_TEMPERATURE,
    MAX_HISTORY_TURNS, MIA_SYSTEM_PROMPT,
    MEMORY_ENABLED, BRAIN_TIMEOUT
)
from memory import Memory


class Brain:
    """Genera respuestas usando la API gratuita de Gemini (Google).

    Reemplaza al backend Ollama remoto (S25/laptop) por una llamada HTTP
    a la nube de Google — no requiere hardware propio de inferencia.

    Memoria dual:
    - Corto plazo: historial de la sesión actual (últimos N turnos)
    - Largo plazo: memoria ligera basada en embeddings (ver memory.py)
    """

    def __init__(self):
        if not GEMINI_API_KEY:
            print("⚠️ GEMINI_API_KEY no está configurada (variable de entorno).")
            print("   Consigue una gratis en https://aistudio.google.com/apikey")

        self.model = GEMINI_TEXT_MODEL
        self.client = genai.Client(api_key=GEMINI_API_KEY)

        # Historial de sesión actual (corto plazo)
        self._history = []

        # Memoria a largo plazo
        self.memory = None
        if MEMORY_ENABLED:
            try:
                self.memory = Memory()
            except Exception as e:
                print(f"⚠️ Error inicializando memoria: {e}")
                print("   MIA funcionará sin memoria a largo plazo")

        self._test_connection()

    # ------------------------------------------------------------------
    # Conexión
    # ------------------------------------------------------------------

    def _test_connection(self):
        """Verifica que la API de Gemini responda con la key configurada"""
        print(f"🧠 Conectando con Gemini API ({self.model})...")
        try:
            self.client.models.generate_content(
                model=self.model,
                contents="ping",
                config=types.GenerateContentConfig(max_output_tokens=5),
            )
            print("✅ Conexión con Gemini exitosa")
        except APIError as e:
            print(f"⚠️ Error conectando con Gemini: {e}")
            print("   Verifica GEMINI_API_KEY y tu conexión a internet")

    def is_connected(self):
        """Verifica si la API de Gemini está disponible"""
        try:
            self.client.models.generate_content(
                model=self.model,
                contents="ping",
                config=types.GenerateContentConfig(max_output_tokens=5),
            )
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Historial de sesión (corto plazo)
    # ------------------------------------------------------------------

    def _add_to_history(self, role, content):
        """Agrega un mensaje al historial de sesión"""
        self._history.append({"role": role, "content": content})

        # Mantener solo los últimos N turnos (1 turno = user + assistant)
        max_messages = MAX_HISTORY_TURNS * 2
        if len(self._history) > max_messages:
            self._history = self._history[-max_messages:]

    def _format_history(self):
        """Formatea el historial como texto para incluir en el prompt"""
        if not self._history:
            return ""

        lines = []
        for msg in self._history:
            if msg["role"] == "user":
                lines.append(f"Fernando: {msg['content']}")
            else:
                lines.append(f"MIA: {msg['content']}")

        return "\n".join(lines)

    def clear_history(self):
        """Limpia el historial de sesión"""
        self._history.clear()

    # ------------------------------------------------------------------
    # Generación de respuestas
    # ------------------------------------------------------------------

    def think_about_vision(self, visual_description):
        """MIA observa algo y hace un comentario proactivo (sarcástico)"""
        print("🧠 MIA observa y piensa...")

        prompt = f"""{MIA_SYSTEM_PROMPT}

Tu nervio óptico te informa que Fernando está haciendo esto: '{visual_description}'

Haz un comentario breve y sarcástico (1-2 oraciones máximo) sobre lo que ves.
No des explicaciones largas, solo el comentario directo."""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=LLM_TEMPERATURE,
                    max_output_tokens=150,
                ),
            )
            text = (response.text or "").strip()
        except APIError as e:
            print(f"❌ Error en Gemini: {e}")
            text = ""

        if text:
            print(f"🧠 MIA piensa: {text}")
        else:
            text = "Hmm, estoy teniendo problemas para pensar..."

        return text

    def respond_to_user(self, user_input, visual_context=""):
        """Responde a un comando/pregunta del usuario con memoria dual.

        1. Busca recuerdos relevantes en la memoria (largo plazo)
        2. Incluye historial de sesión (corto plazo)
        3. Genera respuesta en streaming con Gemini
        4. Almacena la interacción en memoria
        """
        print("🧠 MIA procesa tu pregunta...")

        # --- Buscar recuerdos relevantes (largo plazo) SOLO si se solicita ---
        memory_context = ""
        if self.memory and "recuerda" in user_input.lower():
            memory_context = self.memory.format_memories_for_prompt(user_input)
            if memory_context:
                print("🧬 Recuerdos relevantes encontrados (Búsqueda activa)")
        else:
            print("⚡ Optimización activa: Flujo directo sin memoria pesada.")

        # --- Historial de sesión (corto plazo) ---
        history_text = self._format_history()

        # --- Construir prompt enriquecido ---
        prompt = f"""{MIA_SYSTEM_PROMPT}

{f'[MEMORIA A LARGO PLAZO]{chr(10)}{memory_context}{chr(10)}' if memory_context else ''}
{f'[CONVERSACIÓN ACTUAL]{chr(10)}{history_text}{chr(10)}' if history_text else ''}
{f'[CONTEXTO VISUAL]{chr(10)}{visual_context}{chr(10)}' if visual_context else ''}
Fernando te dice: '{user_input}'

Responde de forma breve, inteligente y con sarcasmo cuando sea apropiado. Máximo 2-3 oraciones.
Si tienes recuerdos relevantes de conversaciones pasadas, puedes hacer referencia sutil a ellos."""

        full_response = ""
        current_chunk = ""
        delimiters = [". ", "?", "!", "\n"]

        try:
            response_stream = self.client.models.generate_content_stream(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=LLM_TEMPERATURE,
                    max_output_tokens=LLM_CONTEXT_SIZE,
                ),
            )

            for chunk in response_stream:
                text = chunk.text or ""
                current_chunk += text
                full_response += text

                # Yield si encuentra fin de frase y tiene sustancia
                if any(current_chunk.endswith(d) for d in delimiters):
                    if len(current_chunk.strip()) > 2:
                        yield current_chunk.strip()
                        current_chunk = ""
                # Si es muy larga y encuentra coma, también partirla para acelerar respuesta inicial
                elif ", " in current_chunk and len(current_chunk.split(",")[-2].strip()) > 25:
                    parts = current_chunk.rsplit(",", 1)
                    yield (parts[0].strip() + ",")
                    current_chunk = parts[1]

        except APIError as e:
            print(f"❌ Error en Gemini API: {e}")
            if not full_response.strip():
                yield "Se me cortó la conexión con Gemini. Intenta de nuevo en un momento, creador."
                return

        # Último pedazo sobrante
        if current_chunk.strip():
            yield current_chunk.strip()

        if full_response.strip():
            self._add_to_history("user", user_input)
            self._add_to_history("assistant", full_response)

            if self.memory:
                self.memory.store_conversation(user_input, full_response, visual_context)

    # ------------------------------------------------------------------
    # Gestión de conocimiento (enseñar a MIA)
    # ------------------------------------------------------------------

    def learn_fact(self, fact, category="general"):
        """Enseña un dato nuevo a MIA para que lo recuerde permanentemente."""
        if not self.memory:
            print("⚠️ Memoria no disponible")
            return False

        self.memory.store_knowledge(fact, category)
        return True

    def get_memory_stats(self):
        """Retorna estadísticas de la memoria"""
        if not self.memory:
            return {"conversations": 0, "knowledge": 0, "enabled": False}

        stats = self.memory.get_stats()
        stats["enabled"] = True
        return stats
