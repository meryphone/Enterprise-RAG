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
import asyncio
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

from openai import OpenAI  # noqa: E402

from app.config import SETTINGS  # noqa: E402
from app.procesamiento.prompts import SYSTEM_PROMPT  # noqa: E402
from app.servicios.query import _construir_contexto, _expandir_parents  # noqa: E402
from app.servicios.retrieval import recuperar  # noqa: E402
from app.servicios.vector_store import nombre_coleccion  # noqa: E402

# ── Banco de queries de prueba ────────────────────────────────────────────────

QUERIES: list[dict] = [
    # Corpus global Intecsa
    {
        "pregunta": "¿Cuál es el objetivo del procedimiento de gestión de proyectos?",
        "proyecto_id": None,
        "empresa": "intecsa",
    },
    {
        "pregunta": "¿Cómo se estructura la documentación de un proyecto EPC?",
        "proyecto_id": None,
        "empresa": "intecsa",
    },
    {
        "pregunta": "¿Qué permisos de directorio tiene el rol JDAP en Mecánica?",
        "proyecto_id": None,
        "empresa": "intecsa",
    },
    {
        "pregunta": "¿Cuáles son las fases del ciclo de vida de un proyecto?",
        "proyecto_id": None,
        "empresa": "intecsa",
    },
    {
        "pregunta": "¿Qué documentos se requieren para la evaluación de una oferta comercial?",
        "proyecto_id": None,
        "empresa": "intecsa",
    },
    {
        "pregunta": "¿Cuál es el procedimiento para la revisión de documentos técnicos?",
        "proyecto_id": None,
        "empresa": "intecsa",
    },
    {
        "pregunta": "¿Qué edición es el procedimiento PR-01?",
        "proyecto_id": None,
        "empresa": "intecsa",
    },
    {
        "pregunta": "¿Cómo se gestionan los cambios en el alcance de un proyecto?",
        "proyecto_id": None,
        "empresa": "intecsa",
    },
    # Proyecto Repsol 13187
    {
        "pregunta": "¿Cuáles son las especificaciones técnicas de la instrucción de trabajo 13187?",
        "proyecto_id": "13187",
        "empresa": "repsol",
    },
    {
        "pregunta": "¿Qué materiales se especifican en la instrucción de trabajo?",
        "proyecto_id": "13187",
        "empresa": "repsol",
    },
]


# ── Pipeline instrumentable ───────────────────────────────────────────────────

try:
    from trulens.apps.custom import instrument
except ImportError:
    # Fallback: decorador vacío si TruLens no está instalado
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
            return []
        coleccion = nombre_coleccion(self.empresa, self.proyecto_id)
        chunks_exp = _expandir_parents(chunks, coleccion)
        return [c.texto for c in chunks_exp]

    @instrument
    def generar_respuesta(self, query: str, contextos: list[str]) -> str:
        """Llama al LLM con el contexto y devuelve la respuesta completa."""
        if not contextos:
            return "No he encontrado documentación relevante para esta consulta."

        # Reutilizamos el mismo formato que usa el endpoint /query
        from app.servicios.retrieval import ChunkRecuperado
        chunks_mock = [
            ChunkRecuperado(
                chunk_id=str(i),
                texto=texto,
                score=1.0,
                metadatos={},
                score_vector=1.0,
                score_bm25=0.0,
                score_fusion=1.0,
            )
            for i, texto in enumerate(contextos)
        ]
        contexto_fmt = _construir_contexto(chunks_mock)

        resp = self._openai.chat.completions.create(
            model=SETTINGS.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Contexto:\n\n{contexto_fmt}\n\nPregunta: {query}"},
            ],
        )
        return resp.choices[0].message.content or ""

    @instrument
    def query(self, pregunta: str) -> str:
        """Punto de entrada principal: recupera contexto y genera respuesta."""
        contextos = self.recuperar_contexto(pregunta)
        return self.generar_respuesta(pregunta, contextos)


# ── Evaluación ────────────────────────────────────────────────────────────────

def ejecutar_evaluacion(
    proyecto_id: str | None,
    empresa: str,
    reset: bool,
    dashboard: bool,
) -> None:
    try:
        from trulens.core import TruSession
        from trulens.apps.custom import TruCustomApp
        from trulens.core.feedback import Feedback
        from trulens.providers.openai import OpenAI as TruOpenAI
        import numpy as np
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

    # Tríada RAG
    f_context_rel = (
        Feedback(proveedor.context_relevance, name="Context Relevance")
        .on_input()
        .on(TruCustomApp.select_context())
        .aggregate(np.mean)
    )
    f_answer_rel = (
        Feedback(proveedor.relevance, name="Answer Relevance")
        .on_input()
        .on_output()
    )
    f_groundedness = (
        Feedback(proveedor.groundedness_measure_with_cot_reasons, name="Groundedness")
        .on(TruCustomApp.select_context().collect())
        .on_output()
        .aggregate(np.mean)
    )

    pipeline = RAGPipeline(proyecto_id=proyecto_id, empresa=empresa)

    scope_label = f"{empresa}" + (f"/{proyecto_id}" if proyecto_id else "")
    app_name = f"IntecsaRAG-{scope_label}"

    tru_app = TruCustomApp(
        pipeline,
        app_name=app_name,
        app_version="beta",
        feedbacks=[f_context_rel, f_answer_rel, f_groundedness],
    )

    queries_scope = [
        q for q in QUERIES
        if q["proyecto_id"] == proyecto_id and q["empresa"] == empresa
    ]

    if not queries_scope:
        print(f"[WARN] No hay queries para scope {scope_label}.", file=sys.stderr)
        return

    print(f"\nEvaluando {len(queries_scope)} queries para scope '{scope_label}'...\n")

    with tru_app as recording:
        for q in queries_scope:
            print(f"  → {q['pregunta'][:70]}...")
            pipeline.query(q["pregunta"])

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
    args = parser.parse_args()

    ejecutar_evaluacion(
        proyecto_id=args.proyecto,
        empresa=args.empresa,
        reset=args.reset,
        dashboard=not args.no_dashboard,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
