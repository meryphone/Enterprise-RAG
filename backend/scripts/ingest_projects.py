import sys
import subprocess
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from scripts.ingest_beta import _manifiesto_proyectos

def main():
    proyectos = _manifiesto_proyectos()
    print(f"==================================================")
    print(f"Iniciando ingesta de {len(proyectos)} documentos de clientes...")
    print(f"==================================================")
    
    python_bin = sys.executable
    script_one = str(BACKEND_DIR / "scripts" / "ingest_one.py")
    
    errores = 0
    for i, p in enumerate(proyectos, 1):
        print(f"\n[{i:3d}/{len(proyectos)}] Ingestando: {p.ruta_pdf.name}")
        
        cmd = [python_bin, script_one, str(p.ruta_pdf)]
        # Esto lanzará ingest_one.py como proceso independiente, 
        # limpiando la memoria tras cada pdf
        result = subprocess.run(cmd)
        
        if result.returncode != 0:
            print(f"Error ingestando: {p.ruta_pdf.name}")
            errores += 1
            
    print(f"\n==================================================")
    print(f"Ingesta finalizada. Total completados: {len(proyectos) - errores}, Errores: {errores}")
    print(f"==================================================")

if __name__ == "__main__":
    main()
