#!/bin/bash

# Directorio principal donde están los documentos
DOCS_DIR="$(dirname "$0")/docs"

if [ ! -d "$DOCS_DIR" ]; then
  echo "Error: El directorio $DOCS_DIR no existe."
  exit 1
fi

echo "Iniciando conversión a PDF en $DOCS_DIR ..."

converted=0
skipped=0
failed=0

# Busca .doc, .docx, .xls, .xlsx, .ppt, .pptx — excluye ficheros de bloqueo (.~lock.*)
while IFS= read -r archivo; do
    dir=$(dirname "$archivo")
    base=$(basename "$archivo")
    nombre_sin_ext="${base%.*}"
    pdf_destino="$dir/$nombre_sin_ext.pdf"

    # Si ya existe el PDF, saltar y borrar el original
    if [ -f "$pdf_destino" ]; then
        echo "[SKIP] Ya existe PDF para: $base"
        rm "$archivo"
        ((skipped++))
        continue
    fi

    echo "[CONV] Convirtiendo: $archivo"
    error_output=$( libreoffice --headless --convert-to pdf --outdir "$dir" "$archivo" 2>&1)
    exit_code=$?

    if [ -f "$pdf_destino" ]; then
        rm "$archivo"
        ((converted++))
        echo "       -> OK: $pdf_destino"
    else
        ((failed++))
        if [ $exit_code -eq 124 ]; then
            echo "       -> ERROR: timeout (>60s) al convertir $base"
        else
            echo "       -> ERROR: no se generó $pdf_destino"
            [ -n "$error_output" ] && echo "          Detalle: $error_output"
        fi
    fi

done < <(find "$DOCS_DIR" -type f \( -iname "*.doc" -o -iname "*.docx" -o -iname "*.xls" -o -iname "*.xlsx" -o -iname "*.ppt" -o -iname "*.pptx" \) ! -name ".~lock.*")

echo ""
echo "Resumen: $converted convertidos, $skipped ya tenían PDF (original borrado), $failed errores."
