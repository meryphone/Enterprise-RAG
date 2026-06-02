#!/usr/bin/env bash
# Ejecuta eval_trulens.py para cada configuración CONF1-CONF6 de forma secuencial.
# Los app_names en TruLens quedan como CONF1-<coleccion>, CONF2-<coleccion>, ...
#
# Uso:
#   cd backend
#   bash scripts/run_eval_configs.sh
#
# Logs por configuración en eval_results/CONFX.log
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$BACKEND_DIR/eval_results"
mkdir -p "$LOG_DIR"

run_config() {
    local config_name="$1"; shift
    local log_file="$LOG_DIR/${config_name}.log"

    echo ""
    echo "════════════════════════════════════════════════════"
    echo "  Iniciando $config_name  (log: eval_results/${config_name}.log)"
    echo "════════════════════════════════════════════════════"

    # Ejecutar en subshell para que las variables no se filtren entre configs
    (
        export "$@"
        python "$SCRIPT_DIR/eval_trulens.py" \
            --config-name "$config_name" \
            --no-dashboard \
            2>&1 | tee "$log_file"
    )

    echo ""
    echo "  ✓ $config_name completado."
}

cd "$BACKEND_DIR"

# ── CONF1 ──────────────────────────────────────────────────────────────────
# TOP_K=20, TOP_N=5, VECTOR=0.5, BM25=0.5, CHILD=128, PARENT=512
run_config "CONF1" \
    RETRIEVAL_TOP_K=20 \
    RETRIEVAL_TOP_N=5 \
    RETRIEVAL_PESO_VECTOR=0.5 \
    RETRIEVAL_PESO_BM25=0.5 \

# ── CONF2 ──────────────────────────────────────────────────────────────────
# TOP_K=20, TOP_N=5, VECTOR=0.5, BM25=0.5, CHILD=512, PARENT=1024
run_config "CONF2" \
    RETRIEVAL_TOP_K=20 \
    RETRIEVAL_TOP_N=5 \
    RETRIEVAL_PESO_VECTOR=0.6 \
    RETRIEVAL_PESO_BM25=0.4 \


# ── CONF3 ──────────────────────────────────────────────────────────────────
# TOP_K=20, TOP_N=5, VECTOR=0.5, BM25=0.5, CHILD=128, PARENT=1024
run_config "CONF3" \
    RETRIEVAL_TOP_K=20 \
    RETRIEVAL_TOP_N=8 \
    RETRIEVAL_PESO_VECTOR=0.6 \
    RETRIEVAL_PESO_BM25=0.4 \

# ── CONF4 ──────────────────────────────────────────────────────────────────
# TOP_K=20, TOP_N=5, VECTOR=0.6, BM25=0.4, CHILD=128, PARENT=1024
run_config "CONF4" \
    RETRIEVAL_TOP_K=25 \
    RETRIEVAL_TOP_N=8 \
    RETRIEVAL_PESO_VECTOR=0.6 \
    RETRIEVAL_PESO_BM25=0.4 \

# ── CONF5 ──────────────────────────────────────────────────────────────────
# TOP_K=20, TOP_N=8, VECTOR=0.6, BM25=0.4, CHILD=128, PARENT=1024
#run_config "CONF5" \
#    RETRIEVAL_TOP_K=20 \
#    RETRIEVAL_TOP_N= \
#    RETRIEVAL_PESO_VECTOR=0.6 \
#    RETRIEVAL_PESO_BM25=0.4 \

# ── CONF6 ──────────────────────────────────────────────────────────────────
# TOP_K=25, TOP_N=8, VECTOR=0.6, BM25=0.4, CHILD=128, PARENT=1024
#run_config "CONF6" \
#    RETRIEVAL_TOP_K=25 \
#   RETRIEVAL_TOP_N=8 \
#   RETRIEVAL_PESO_VECTOR=0.6 \
#   RETRIEVAL_PESO_BM25=0.4 \

echo ""
echo "════════════════════════════════════════════════════"
echo "  Todas las configuraciones completadas."
echo "  Lanza el dashboard con:"
echo "    cd backend && python scripts/eval_trulens.py --no-dashboard"
echo "  O con Streamlit directamente: trulens-dashboard"
echo "════════════════════════════════════════════════════"
