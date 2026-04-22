import argparse
import chromadb
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# ── Configuración ──────────────────────────────────────────────
CHROMA_TENANT    = os.getenv("CHROMA_TENANT")
CHROMA_DATABASE  = os.getenv("CHROMA_DATABASE")
CHROMA_API_KEY   = os.getenv("CHROMA_API_KEY")
COLLECTION_NAME  = os.getenv("CHROMA_COLLECTION", "intecsa")

FILTRO_CAMPO  = "nombre_fichero"

def main():
    parser = argparse.ArgumentParser(description="Borrar chunks de un fichero en ChromaDB")
    parser.add_argument("nombre_fichero", help="Nombre del fichero a borrar (ej. PR-07.pdf)")
    args = parser.parse_args()

    filtro_valor = args.nombre_fichero

    # ── Conexión a Chroma Cloud ────────────────────────────────────
    try:
        client = chromadb.CloudClient(
            tenant=CHROMA_TENANT,
            database=CHROMA_DATABASE,
            api_key=CHROMA_API_KEY
        )
    except Exception as e:
        print(f"❌ Error al conectar con ChromaDB: {e}")
        sys.exit(1)

    # Intecsa utiliza dos colecciones: la normal para children y la '__parents'
    colecciones_a_borrar = [COLLECTION_NAME, f"{COLLECTION_NAME}__parents"]
    
    total_borrados = 0
    for coll_name in colecciones_a_borrar:
        print(f"\n📂 Conectado a colección: {coll_name}")
        try:
            collection = client.get_collection(coll_name)
        except Exception:
            print(f"⚠️  La colección {coll_name} no existe o no se puede acceder, omitiendo...")
            continue

        # ── Verificar antes de borrar ─────────────────────────────────
        try:
            resultado = collection.get(
                where={FILTRO_CAMPO: {"$eq": filtro_valor}},
                include=["metadatas"]
            )
            total = len(resultado.get("ids", []))
            
            if total == 0:
                print(f"⚠️  No se encontraron chunks con {FILTRO_CAMPO} = '{filtro_valor}' en {coll_name}")
                continue

            print(f"📄 Chunks encontrados con {FILTRO_CAMPO} = '{filtro_valor}' en {coll_name}: {total}")
            
            # ── Confirmación manual ───────────────────────────────────────
            confirmacion = input(f"¿Confirmas el borrado de {total} chunks en {coll_name}? (s/n): ").strip().lower()

            if confirmacion != "s":
                print("❌ Borrado cancelado para esta colección.")
                continue

            # ── Borrar ────────────────────────────────────────────────────
            collection.delete(where={FILTRO_CAMPO: {"$eq": filtro_valor}})

            # ── Verificar después ─────────────────────────────────────────
            verificacion = collection.get(where={FILTRO_CAMPO: {"$eq": filtro_valor}})
            if len(verificacion.get("ids", [])) == 0:
                print(f"✅ Borrado completado en {coll_name}. {total} chunks eliminados correctamente.")
                total_borrados += total
            else:
                print(f"⚠️  Aún quedan {len(verificacion['ids'])} chunks en {coll_name}. Revisa manualmente.")
        except Exception as e:
            print(f"Error procesando {coll_name}: {e}")

    print(f"\nProceso finalizado. Total de chunks borrados: {total_borrados}")

if __name__ == "__main__":
    main()
