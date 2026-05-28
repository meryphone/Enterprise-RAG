"""Evaluación del sistema RAG con TruLens.

Instrumenta el pipeline de query, ejecuta el banco de queries de prueba
y lanza el dashboard TruLens en http://localhost:8501

Las preguntas se cargan desde eval_questions.json (junto a este script)
o desde la ruta indicada con --questions.

Requisitos:
    pip install trulens trulens-providers-openai

Uso:
    # Evaluar y lanzar dashboard
    python scripts/eval_trulens.py

    # Evaluar sin lanzar dashboard (solo imprime resultados)
    python scripts/eval_trulens.py --no-dashboard

    # Borrar evaluaciones anteriores y volver a evaluar
    python scripts/eval_trulens.py --reset

    # Seleccionar la colección a evaluar (por defecto: intecsa = corpus global)
    python scripts/eval_trulens.py --coleccion 13187_repsol

    # Usar un fichero de preguntas alternativo
    python scripts/eval_trulens.py --questions /ruta/mis_preguntas.json

Métricas evaluadas (tríada RAG):
    context_relevance  ¿es el contexto recuperado relevante para la pregunta?
    answer_relevance   ¿es la respuesta relevante para la pregunta?
    groundedness       ¿está la respuesta fundamentada en el contexto?
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
QUESTIONS_FILE = Path(__file__).resolve().parent / "rag_evaluation_questions.json"
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
# Desactivar OTEL tracing experimental — incompatible con la API Lens/Feedback
os.environ["TRULENS_OTEL_TRACING"] = "0"

from openai import OpenAI  # noqa: E402

from app.config import SETTINGS  # noqa: E402
from app.ingestion.prompts import SYSTEM_PROMPT_EVAL as SYSTEM_PROMPT  # noqa: E402  — variante sin marcadores [N] para no penalizar Groundedness
from app.rag.context_builder import (  # noqa: E402
    construir_contexto,
    expandir_parents,
    fusionar_partes_tabla,
)
from app.rag.retrieval import recuperar  # noqa: E402
from app.rag.vector_store import nombre_coleccion  # noqa: E402


def _parsear_coleccion(coleccion: str) -> tuple[str | None, str]:
    """Convierte un nombre de colección en (proyecto_id, empresa) para `recuperar()`.

    - "intecsa" → (None, "intecsa")
    - "13189_dow" → ("13189", "dow")
    - "14112_cepsa_fcc" → ("14112", "cepsa_fcc")
    """
    if "_" not in coleccion:
        return None, coleccion
    proyecto_id, empresa = coleccion.split("_", 1)
    return proyecto_id, empresa

# ── Banco de queries de prueba ────────────────────────────────────────────────

def _cargar_queries(ruta: Path = QUESTIONS_FILE) -> list[dict]:
    """Carga las queries desde el fichero JSON. Cada entrada debe tener
    al menos 'query', o bien ser una simple string que se normalizará."""
    if not ruta.exists():
        print(
            f"[ERROR] Fichero de preguntas no encontrado: {ruta}\n"
            f"Crea el fichero o pasa --questions para indicar otra ruta.",
            file=sys.stderr,
        )
        sys.exit(1)
    with ruta.open(encoding="utf-8") as fh:
        datos = json.load(fh)
    if not isinstance(datos, list):
        print("[ERROR] El fichero de preguntas debe ser un array JSON.", file=sys.stderr)
        sys.exit(1)
    
    # Normalizamos a una lista de diccionarios con 'query'
    rutas_normalizadas = []
    for item in datos:
        if isinstance(item, str):
            rutas_normalizadas.append({"query": item})
        elif isinstance(item, dict) and ("query" in item or "pregunta" in item):
            if "pregunta" in item and "query" not in item:
                item["query"] = item.pop("pregunta")
            rutas_normalizadas.append(item)
        else:
            print("[ERROR] El formato de preguntas en el JSON no es válido. Debe contener la clave 'query' o ser cadenas simples.", file=sys.stderr)
            sys.exit(1)

    return rutas_normalizadas


QUERIES: list[dict] = _cargar_queries()


# ── Pipeline instrumentable ───────────────────────────────────────────────────

try:
    from trulens.apps.app import instrument
except ImportError:
    try:
        from trulens.apps.custom import instrument  # versiones antiguas
    except ImportError:
        def instrument(func):  # type: ignore[misc]
            return func


class RAGPipeline:
    """Pipeline RAG sincrónico instrumentable por TruLens.

    Replica la fase de retrieval/contexto de `ejecutar_query` (recuperar →
    expandir_parents → fusionar_partes_tabla → construir_contexto), pero usa
    SYSTEM_PROMPT_EVAL para la generación: omite los marcadores [N] de cita
    que TruLens penaliza como afirmaciones no verificables (Groundedness).
    """

    def __init__(self, coleccion: str) -> None:
        self.coleccion = coleccion
        self.proyecto_id, self.empresa = _parsear_coleccion(coleccion)
        self._openai = OpenAI(api_key=SETTINGS.openai_api_key)

    @instrument
    def recuperar_contexto(self, query: str) -> list[str]:
        """Replica la fase de retrieval de ``ejecutar_query`` del backend:
        recuperar → expandir_parents → fusionar_partes_tabla.
        """
        chunks = recuperar(query, self.proyecto_id, self.empresa)
        if not chunks:
            self._last_chunks: list = []
            return []
        coleccion = nombre_coleccion(self.empresa, self.proyecto_id)
        chunks = expandir_parents(chunks, coleccion)
        chunks = fusionar_partes_tabla(chunks)
        self._last_chunks = chunks  # conservar metadatos para generar_respuesta
        return [c.texto for c in chunks]

    @instrument
    def generar_respuesta(self, query: str, contextos: list[str]) -> str:
        """Llama al LLM con el contexto construido como en el backend."""
        chunks = getattr(self, "_last_chunks", None)
        if not chunks:
            contexto_fmt = "(No se han encontrado fragmentos relevantes en la documentación indexada.)"
        else:
            contexto_fmt = construir_contexto(chunks)

        resp = self._openai.chat.completions.create(
            model=SETTINGS.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Contexto:\n\n{contexto_fmt}\n\nPregunta: {query}"},
            ],
            temperature=0.0,
        )
        return resp.choices[0].message.content or ""

    @instrument
    def query(self, pregunta: str) -> str:
        """Punto de entrada principal: recupera contexto y genera respuesta."""
        contextos = self.recuperar_contexto(pregunta)
        return self.generar_respuesta(pregunta, contextos)


# ── Rate limit helpers ────────────────────────────────────────────────────────

# Con juez gpt-4o-mini, la mayor parte del coste TPM la asume mini (200k TPM).
# La generación principal sigue siendo gpt-4o (30k TPM) → ~3-5k por query, así que
# 10s de gap da margen para que no se solapen dos generaciones en la ventana de 1 min.
_N_WORKERS = 1
_DELAY_ENTRE_QUERIES = 10  # segundos


def _ejecutar_con_retry(func, *args, max_reintentos: int = 5, **kwargs):
    """Ejecuta func con reintentos exponenciales si hay RateLimitError."""
    import openai
    espera = 15
    for intento in range(max_reintentos):
        try:
            return func(*args, **kwargs)
        except openai.RateLimitError as e:
            if intento == max_reintentos - 1:
                raise
            print(f"    [rate limit] esperando {espera}s... ({e})")
            time.sleep(espera)
            espera *= 2


# ── Evaluación ────────────────────────────────────────────────────────────────

def ejecutar_evaluacion(
    coleccion: str | None,
    reset: bool,
    dashboard: bool,
    version: str = "beta",
) -> None:
    import warnings
    try:
        from trulens.core import TruSession
        from trulens.core.schema.select import Select
        from trulens.providers.openai import OpenAI as TruOpenAI
        import numpy as np
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from trulens.core.feedback import Feedback
            try:
                from trulens.apps.custom import TruCustomApp
            except ImportError:
                from trulens.apps.app import TruApp as TruCustomApp
    except ImportError as e:
        print(
            f"[ERROR] TruLens no instalado: {e}\n"
            "Instala con: pip install trulens trulens-providers-openai",
            file=sys.stderr,
        )
        sys.exit(1)

    session = TruSession()
    if reset:
        session.reset_database()
        print("[INFO] Base de datos de evaluaciones borrada.")

    # Juez = gpt-4o-mini: misma fiabilidad para feedbacks RAG, ~10× más TPM y ~15× más barato
    # que gpt-4o. Evita 429s al solaparse con la siguiente query.
    proveedor = TruOpenAI(api_key=SETTINGS.openai_api_key, model_engine="gpt-4o-mini")

    # Selector del contexto: salida de recuperar_contexto()
    contexto_selector = Select.RecordCalls.recuperar_contexto.rets[:]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        f_context_rel = (
            Feedback(proveedor.context_relevance, name="Context Relevance")
            .on_input()
            .on(contexto_selector)
            .aggregate(np.mean)
        )
        f_answer_rel = (
            Feedback(proveedor.relevance, name="Answer Relevance")
            .on_input()
            .on_output()
        )
        f_groundedness = (
            Feedback(proveedor.groundedness_measure_with_cot_reasons, name="Groundedness")
            .on(contexto_selector.collect())
            .on_output()
            .aggregate(np.mean)
        )

    try:
        from trulens.core.schema.feedback import FeedbackMode
        feedback_mode = FeedbackMode.WITH_APP_THREAD
    except ImportError:
        feedback_mode = "with_app_thread"

    # Colecciones a evaluar: la indicada por CLI o todas las presentes en el JSON
    if coleccion is not None:
        colecciones = [coleccion]
    else:
        seen: set[str] = set()
        colecciones = [
            q["coleccion"] for q in QUERIES
            if q.get("coleccion") and not (q["coleccion"] in seen or seen.add(q["coleccion"]))  # type: ignore[func-returns-value]
        ]

    app_ids: list[str] = []

    for col in colecciones:
        queries_scope = [q for q in QUERIES if q.get("coleccion") == col]
        if not queries_scope:
            print(f"[WARN] No hay queries en el JSON para la colección: {col}.", file=sys.stderr)
            continue

        pipeline = RAGPipeline(coleccion=col)
        tru_app = TruCustomApp(
            pipeline,
            app_name=f"IntecsaRAG-{col}",
            app_version=version,
            feedbacks=[f_context_rel, f_answer_rel, f_groundedness],
            feedback_mode=feedback_mode,
        )
        app_ids.append(tru_app.app_id)

        print(f"\nEvaluando {len(queries_scope)} queries para la colección '{col}'...\n")

        for idx, q in enumerate(queries_scope):
            print(f"  [{idx+1}/{len(queries_scope)}] {q['query'][:70]}...")
            try:
                with tru_app as recording:
                    _ejecutar_con_retry(pipeline.query, q["query"])
            except Exception as exc:
                print(f"  [ERROR] '{q['query'][:60]}': {exc}", file=sys.stderr)
            if idx < len(queries_scope) - 1:
                time.sleep(_DELAY_ENTRE_QUERIES)

        # Esperar a que todos los feedbacks en background terminen antes de leer resultados
        if hasattr(session, "wait_for_evaluations"):
            print("Esperando evaluaciones pendientes...")
            session.wait_for_evaluations()

        leaderboard = session.get_leaderboard(app_ids=[tru_app.app_id])
        print(f"\n── Resultados {col} ──────────────────────────────────────────────")
        print(leaderboard.to_string())

        _persistir_resultados(session, tru_app.app_id, col)

    if dashboard:
        print("\nLanzando dashboard TruLens en http://localhost:8501 ...")
        session.run_dashboard()


def _persistir_resultados(session, app_id: str, coleccion: str) -> None:
    """Escribe leaderboard y per-query records en CSV listos para Jupyter/pandas.

    - ``leaderboard_<coleccion>_<ts>.csv``: una fila con la media de cada métrica.
    - ``records_<coleccion>_<ts>.csv``: una fila por query con prompt, respuesta y
      scores de Context Relevance, Answer Relevance y Groundedness.
    """
    from datetime import datetime

    out_dir = BACKEND_DIR / "eval_results"
    out_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    leaderboard = session.get_leaderboard(app_ids=[app_id])
    lb_path = out_dir / f"leaderboard_{coleccion}_{ts}.csv"
    leaderboard.to_csv(lb_path, index=True)

    records_df, _ = session.get_records_and_feedback(app_ids=[app_id])
    rec_path = out_dir / f"records_{coleccion}_{ts}.csv"
    records_df.to_csv(rec_path, index=False)

    print(f"\n[CSV] Leaderboard → {lb_path.relative_to(BACKEND_DIR)}")
    print(f"[CSV] Records     → {rec_path.relative_to(BACKEND_DIR)}")
    print(f"      Cárgalo en Jupyter con: pd.read_csv('{rec_path.name}')")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--coleccion",     default=None,
                        help="Colección ChromaDB a evaluar (p.ej. 'intecsa', '13189_dow'). Sin valor: evalúa todas las colecciones del JSON.")
    parser.add_argument("--questions",     default=None, metavar="RUTA",
                        help="Ruta al fichero JSON de preguntas (por defecto: eval_questions.json junto a este script)")
    parser.add_argument("--version",        default="beta", metavar="ETIQUETA",
                        help="Etiqueta de versión para esta ejecución en el dashboard (p.ej. 'top_k18_top_n4')")
    parser.add_argument("--reset",         action="store_true", help="Borrar evaluaciones previas")
    parser.add_argument("--no-dashboard",  action="store_true", help="No lanzar dashboard web")
    parser.add_argument("--debug",         action="store_true", help="Mostrar queries reescritas, chunks y contexto")
    args = parser.parse_args()

    if args.questions:
        global QUERIES
        QUERIES = _cargar_queries(Path(args.questions))

    if args.debug:
        import logging as _logging
        _logging.basicConfig(
            level=_logging.DEBUG,
            format="%(name)s | %(levelname)s | %(message)s",
            handlers=[_logging.StreamHandler()],
        )
        # Solo módulos propios para no inundar con logs de Chroma/OpenAI/TruLens
        for _mod in ("app.rag.retrieval", "app.rag.query", "app.ingestion.prompts"):
            _logging.getLogger(_mod).setLevel(_logging.DEBUG)

    ejecutar_evaluacion(
        coleccion=args.coleccion,
        reset=args.reset,
        dashboard=not args.no_dashboard,
        version=args.version,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
