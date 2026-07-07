import json
import os
import time
import numpy as np
from google import genai
from config import (
    MEMORY_DIR, MEMORY_FILE, MEMORY_RESULTS_LIMIT,
    GEMINI_API_KEY, GEMINI_EMBEDDING_MODEL
)


class Memory:
    """Memoria a largo plazo de MIA — versión ligera para Raspberry Pi (1GB RAM).

    Reemplaza a ChromaDB (que cargaba onnxruntime/duckdb/hnswlib localmente,
    ~300-500MB solo para inicializar) por:
    - Embeddings generados de forma REMOTA vía Ollama en el S25 Ultra
      (modelo 'nomic-embed-text', ~270MB, vive en el celular, no en el Pi)
    - Almacenamiento en un JSON plano en disco
    - Búsqueda por similitud coseno con numpy (ya es dependencia del proyecto)

    Para volúmenes de cientos/miles de recuerdos esto es más que suficiente
    y el costo en RAM del Pi es prácticamente nulo (solo el JSON en memoria).
    """

    def __init__(self):
        os.makedirs(MEMORY_DIR, exist_ok=True)
        self._path = MEMORY_FILE

        print(f"🧬 Inicializando memoria ligera en: {self._path}")

        # Cliente Gemini solo para generar embeddings
        self._gemini = genai.Client(api_key=GEMINI_API_KEY)
        self._embed_model = GEMINI_EMBEDDING_MODEL

        self._data = {"conversations": [], "knowledge": []}
        self._load()

        conv_count = len(self._data["conversations"])
        know_count = len(self._data["knowledge"])
        print(f"🧬 Memoria lista — {conv_count} conversaciones, {know_count} conocimientos almacenados")

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------

    def _load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                self._data.setdefault("conversations", [])
                self._data.setdefault("knowledge", [])
            except Exception as e:
                print(f"⚠️ Error leyendo memoria en disco, empezando limpio: {e}")

    def _save(self):
        try:
            tmp_path = self._path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False)
            os.replace(tmp_path, self._path)  # escritura atómica
        except Exception as e:
            print(f"⚠️ Error guardando memoria en disco: {e}")

    # ------------------------------------------------------------------
    # Embeddings remotos
    # ------------------------------------------------------------------

    def _embed(self, text):
        """Pide el embedding a la API de Gemini. Retorna None si falla,
        para no tumbar el flujo si no hay red/cuota."""
        try:
            response = self._gemini.models.embed_content(
                model=self._embed_model,
                contents=text,
            )
            return response.embeddings[0].values if response.embeddings else None
        except Exception as e:
            print(f"⚠️ Error generando embedding con Gemini ({self._embed_model}): {e}")
            return None

    @staticmethod
    def _cosine_sim_matrix(query_vec, matrix):
        """Similitud coseno de un vector contra una matriz (n, dim)."""
        if matrix.size == 0:
            return np.array([])
        q = query_vec / (np.linalg.norm(query_vec) + 1e-8)
        norms = np.linalg.norm(matrix, axis=1) + 1e-8
        m = matrix / norms[:, None]
        return m @ q

    def _top_matches(self, query, records, n_results):
        """records: lista de dicts con clave 'embedding'. Retorna los top-N con mayor similitud."""
        if not records:
            return []

        query_vec = self._embed(query)
        if query_vec is None:
            # Sin conexión a Gemini: fallback simple, devolver los más recientes
            return sorted(records, key=lambda r: r.get("timestamp", 0), reverse=True)[:n_results]

        valid = [r for r in records if r.get("embedding")]
        if not valid:
            return sorted(records, key=lambda r: r.get("timestamp", 0), reverse=True)[:n_results]

        matrix = np.array([r["embedding"] for r in valid], dtype=np.float32)
        sims = self._cosine_sim_matrix(np.array(query_vec, dtype=np.float32), matrix)

        order = np.argsort(-sims)[:n_results]
        results = []
        for idx in order:
            r = dict(valid[idx])
            r["relevance"] = float(sims[idx])
            results.append(r)
        return results

    # ------------------------------------------------------------------
    # Conversaciones
    # ------------------------------------------------------------------

    def store_conversation(self, user_message, mia_response, visual_context=""):
        timestamp = time.time()
        text_for_embedding = f"Fernando preguntó: {user_message}\nMIA respondió: {mia_response}"
        embedding = self._embed(text_for_embedding)

        record = {
            "id": f"conv_{int(timestamp * 1000)}",
            "user_message": user_message[:500],
            "mia_response": mia_response[:500],
            "visual_context": visual_context[:300] if visual_context else "",
            "timestamp": timestamp,
            "embedding": embedding,
        }
        self._data["conversations"].append(record)
        self._save()

    def recall_conversations(self, query, n_results=None):
        if n_results is None:
            n_results = MEMORY_RESULTS_LIMIT

        matches = self._top_matches(query, self._data["conversations"], n_results)
        return [
            {
                "user_message": m.get("user_message", ""),
                "mia_response": m.get("mia_response", ""),
                "visual_context": m.get("visual_context", ""),
                "timestamp": m.get("timestamp", 0),
                "relevance": m.get("relevance", 0),
            }
            for m in matches
        ]

    # ------------------------------------------------------------------
    # Base de conocimiento
    # ------------------------------------------------------------------

    def store_knowledge(self, fact, category="general"):
        timestamp = time.time()
        embedding = self._embed(fact)

        record = {
            "id": f"know_{int(timestamp * 1000)}",
            "fact": fact,
            "category": category,
            "timestamp": timestamp,
            "embedding": embedding,
        }
        self._data["knowledge"].append(record)
        self._save()
        print(f"🧬 Conocimiento almacenado [{category}]: {fact[:80]}...")

    def recall_knowledge(self, query, n_results=None):
        if n_results is None:
            n_results = MEMORY_RESULTS_LIMIT

        matches = self._top_matches(query, self._data["knowledge"], n_results)
        return [
            {
                "fact": m.get("fact", ""),
                "category": m.get("category", "general"),
                "timestamp": m.get("timestamp", 0),
            }
            for m in matches
        ]

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def get_stats(self):
        return {
            "conversations": len(self._data["conversations"]),
            "knowledge": len(self._data["knowledge"]),
        }

    def format_memories_for_prompt(self, query):
        sections = []

        conversations = self.recall_conversations(query, n_results=3)
        if conversations:
            conv_lines = [
                f"- Fernando dijo: \"{mem['user_message']}\" → Respondiste: \"{mem['mia_response']}\""
                for mem in conversations
            ]
            sections.append("Recuerdos de conversaciones pasadas:\n" + "\n".join(conv_lines))

        knowledge = self.recall_knowledge(query, n_results=3)
        if knowledge:
            fact_lines = [f"- {k['fact']}" for k in knowledge]
            sections.append("Datos que recuerdas:\n" + "\n".join(fact_lines))

        return "\n\n".join(sections) if sections else ""
