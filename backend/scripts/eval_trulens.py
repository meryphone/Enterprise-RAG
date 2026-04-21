"""Evaluación del sistema RAG con TruLens.

Instrumenta el pipeline de query, ejecuta el banco de queries de prueba
y lanza el dashboard TruLens en http://localhost:8501

Requisitos:
    pip install trulens trulens-providers-openai

Uso:
    # Evaluar y lanzar dashboard
    python scripts/eval_trulens.py

    # Evaluar sin lanzar dashboard (solo imprime resultados)
    python scripts/eval_trulens.py --no-dashboard

    # Borrar evaluaciones anteriores y volver a evaluar
    python scripts/eval_trulens.py --reset

    # Filtrar por proyecto (None = corpus global Intecsa)
    python scripts/eval_trulens.py --proyecto 13187 --empresa repsol

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
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
# Desactivar OTEL tracing experimental — incompatible con la API Lens/Feedback
os.environ["TRULENS_OTEL_TRACING"] = "0"

from openai import OpenAI  # noqa: E402

from app.config import SETTINGS  # noqa: E402
from app.ingestion.prompts import SYSTEM_PROMPT_EVAL as SYSTEM_PROMPT  # noqa: E402
from app.rag.query import _construir_contexto, _expandir_parents  # noqa: E402
from app.rag.retrieval import recuperar  # noqa: E402
from app.rag.vector_store import nombre_coleccion  # noqa: E402

# ── Banco de queries de prueba ────────────────────────────────────────────────

QUERIES: list[dict] = [
    # ── Corpus global Intecsa (7 queries) ────────────────────────────────────
    # PR-01: organización matricial, Jefe de Proyecto
    {
        "pregunta": "¿Qué tipo de organización se usa para gestionar proyectos?",
        "proyecto_id": None,
        "empresa": "intecsa",
    },
    # PR-02: aprobación por Dirección General, distribución grupos A-J
    {
        "pregunta": "¿Quién aprueba los Procedimientos Generales?",
        "proyecto_id": None,
        "empresa": "intecsa",
    },
    # PR-05: umbral 5 millones de pesetas para firma de Dirección General
    {
        "pregunta": "¿A partir de qué coste de preparación de oferta se necesita la firma de Dirección General?",
        "proyecto_id": None,
        "empresa": "intecsa",
    },
    # PR-08: umbral 12.000 € / 1.200.000 € para aprobación, servidor DATOSPR
    {
        "pregunta": "¿Dónde se almacenan los ficheros de los proyectos en las oficinas locales?",
        "proyecto_id": None,
        "empresa": "intecsa",
    },
    # PR-08-ANEXO-III: permisos por rol
    {
        "pregunta": "¿Qué permisos tiene DRA en la disciplina de Mecánica?",
        "proyecto_id": None,
        "empresa": "intecsa",
    },
    # PR-09: residuos, fluorescentes máximo 6 meses, pilas hasta 30 kg
    {
        "pregunta": "¿Cuánto tiempo pueden almacenarse los fluorescentes antes de su retirada?",
        "proyecto_id": None,
        "empresa": "intecsa",
    },
    # PR-09: variación consumo eléctrico
    {
        "pregunta": "¿Qué variación en el consumo eléctrico obliga a investigar su causa?",
        "proyecto_id": None,
        "empresa": "intecsa",
    },

    # ── Proyecto Repsol 13187 (3 queries) ────────────────────────────────────
    # IT-01: acceso Intranet equipo / Internet proveedores, copia diaria
    {
        "pregunta": "¿Qué usuarios acceden al portal por Internet y cuáles por Intranet?",
        "proyecto_id": "13187",
        "empresa": "repsol",
    },
    # IT-02: estados ASC, ACC, No Aprobado
    {
        "pregunta": "¿Qué significa que un documento tiene el estado ACC?",
        "proyecto_id": "13187",
        "empresa": "repsol",
    },
    # IT-02: documentos Tipiel Colombia auto-aprobados
    {
        "pregunta": "¿Cuándo se auto-aprueba un documento sin necesidad de aprobación del cliente?",
        "proyecto_id": "13187",
        "empresa": "repsol",
    },
]


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
    """Pipeline RAG sincrónico instrumentable por TruLens."""

    def __init__(self, proyecto_id: str | None, empresa: str) -> None:
        self.proyecto_id = proyecto_id
        self.empresa = empresa
        self._openai = OpenAI(api_key=SETTINGS.openai_api_key)

    @instrument
    def recuperar_contexto(self, query: str) -> list[str]:
        """Recupera y expande parents. Devuelve lista de textos de contexto."""
        chunks = recuperar(query, self.proyecto_id, self.empresa)
        if not chunks:
            self._last_chunks: list = []
            return []
        coleccion = nombre_coleccion(self.empresa, self.proyecto_id)
        chunks_exp = _expandir_parents(chunks, coleccion)
        self._last_chunks = chunks_exp  # conservar metadatos para generar_respuesta
        return [c.texto for c in chunks_exp]

    @instrument
    def generar_respuesta(self, query: str, contextos: list[str]) -> str:
        """Llama al LLM con el contexto y devuelve la respuesta completa."""
        if not contextos:
            return "No he encontrado documentación relevante para esta consulta."

        # Usar los chunks completos (con metadatos doc/sección/páginas) si están disponibles
        chunks = getattr(self, "_last_chunks", None)
        if chunks:
            contexto_fmt = _construir_contexto(chunks)
        else:
            from app.rag.retrieval import ChunkRecuperado
            contexto_fmt = _construir_contexto([
                ChunkRecuperado(chunk_id=str(i), texto=t, score=1.0, metadatos={})
                for i, t in enumerate(contextos)
            ])

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

# Con 30k TPM y ~15-20k tokens por query (respuesta + 3 feedbacks de TruLens),
# solo cabe 1 query a la vez. El sleep deja que la ventana de 1 min se renueve.
_N_WORKERS = 1
_DELAY_ENTRE_QUERIES = 18  # segundos


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
    proyecto_id: str | None,
    empresa: str,
    reset: bool,
    dashboard: bool,
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

    proveedor = TruOpenAI(api_key=SETTINGS.openai_api_key, model_engine=SETTINGS.llm_model)

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

    pipeline = RAGPipeline(proyecto_id=proyecto_id, empresa=empresa)

    scope_label = f"{empresa}" + (f"/{proyecto_id}" if proyecto_id else "")
    app_name = f"IntecsaRAG-{scope_label}"

    try:
        from trulens.core.schema.feedback import FeedbackMode
        feedback_mode = FeedbackMode.WITH_APP_THREAD
    except ImportError:
        feedback_mode = "with_app_thread"

    tru_app = TruCustomApp(
        pipeline,
        app_name=app_name,
        app_version="beta",
        feedbacks=[f_context_rel, f_answer_rel, f_groundedness],
        feedback_mode=feedback_mode,
    )

    queries_scope = [
        q for q in QUERIES
        if q["proyecto_id"] == proyecto_id and q["empresa"] == empresa
    ]

    if not queries_scope:
        print(f"[WARN] No hay queries para scope {scope_label}.", file=sys.stderr)
        return

    print(f"\nEvaluando {len(queries_scope)} queries para scope '{scope_label}'...\n")

    for idx, q in enumerate(queries_scope):
        print(f"  [{idx+1}/{len(queries_scope)}] {q['pregunta'][:70]}...")
        try:
            with tru_app as recording:
                _ejecutar_con_retry(pipeline.query, q["pregunta"])
        except Exception as exc:
            print(f"  [ERROR] '{q['pregunta'][:60]}': {exc}", file=sys.stderr)
        if idx < len(queries_scope) - 1:
            time.sleep(_DELAY_ENTRE_QUERIES)

    # Esperar a que todos los feedbacks en background terminen antes de leer resultados
    if hasattr(session, "wait_for_evaluations"):
        print("Esperando evaluaciones pendientes...")
        session.wait_for_evaluations()

    # Resumen de resultados
    leaderboard = session.get_leaderboard(app_ids=[tru_app.app_id])
    print("\n── Resultados ──────────────────────────────────────────────────────")
    print(leaderboard.to_string())

    if dashboard:
        print("\nLanzando dashboard TruLens en http://localhost:8501 ...")
        session.run_dashboard()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--proyecto",      default=None)
    parser.add_argument("--empresa",       default="intecsa")
    parser.add_argument("--reset",         action="store_true", help="Borrar evaluaciones previas")
    parser.add_argument("--no-dashboard",  action="store_true", help="No lanzar dashboard web")
    parser.add_argument("--debug",         action="store_true", help="Mostrar queries reescritas, chunks y contexto")
    args = parser.parse_args()

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
        proyecto_id=args.proyecto,
        empresa=args.empresa,
        reset=args.reset,
        dashboard=not args.no_dashboard,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
