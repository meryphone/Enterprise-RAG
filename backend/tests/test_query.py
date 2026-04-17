# backend/tests/test_query.py
from unittest.mock import MagicMock, patch
from app.servicios.retrieval import ChunkRecuperado
from app.servicios.query import _expandir_parents, _construir_contexto


def _chunk(chunk_id, texto, nivel="child", parent_id="pid-1", score=0.9,
           nombre_fichero="doc.pdf", titulo="TITULO", seccion="3. PROC",
           pagina_inicio=4, pagina_fin=5, dentro_de_anexo=False):
    return ChunkRecuperado(
        chunk_id=chunk_id,
        texto=texto,
        score=score,
        metadatos={
            "nivel": nivel,
            "parent_id": parent_id,
            "nombre_fichero": nombre_fichero,
            "titulo_documento": titulo,
            "seccion": seccion,
            "pagina_inicio": pagina_inicio,
            "pagina_fin": pagina_fin,
            "dentro_de_anexo": dentro_de_anexo,
        },
    )


def test_expandir_parents_child_con_parent():
    """Un child con parent_id se sustituye por el texto del parent."""
    chunk = _chunk("child-1", "texto child", nivel="child", parent_id="parent-1")

    mock_col = MagicMock()
    mock_col.get.return_value = {
        "ids": ["parent-1"],
        "documents": ["texto expandido del parent"],
        "metadatas": [chunk.metadatos],
    }
    mock_chroma = MagicMock()
    mock_chroma.get_collection.return_value = mock_col

    with patch("app.servicios.query.get_chroma", return_value=mock_chroma):
        resultado = _expandir_parents([chunk], coleccion="intecsa")

    assert len(resultado) == 1
    assert resultado[0].texto == "texto expandido del parent"


def test_expandir_parents_tabla_pasa_directa():
    """Una tabla (parent_id=='') no se expande."""
    tabla = _chunk("tabla-1", "| col1 | col2 |", nivel="child", parent_id="")

    with patch("app.servicios.query.get_chroma"):
        resultado = _expandir_parents([tabla], coleccion="intecsa")

    assert len(resultado) == 1
    assert resultado[0].texto == "| col1 | col2 |"


def test_expandir_parents_deduplica_mismo_parent():
    """Dos children con el mismo parent_id producen un solo chunk expandido."""
    c1 = _chunk("c1", "child 1", parent_id="shared-parent")
    c2 = _chunk("c2", "child 2", parent_id="shared-parent")

    mock_col = MagicMock()
    mock_col.get.return_value = {
        "ids": ["shared-parent"],
        "documents": ["texto del parent compartido"],
        "metadatas": [c1.metadatos],
    }
    mock_chroma = MagicMock()
    mock_chroma.get_collection.return_value = mock_col

    with patch("app.servicios.query.get_chroma", return_value=mock_chroma):
        resultado = _expandir_parents([c1, c2], coleccion="intecsa")

    assert len(resultado) == 1


def test_construir_contexto_formato():
    """El contexto tiene cabecera numerada y texto del chunk."""
    chunk = _chunk("c1", "El manómetro debe calibrarse a 6 bar.",
                   nombre_fichero="PR-08.pdf", seccion="3. PROCEDIMIENTO",
                   pagina_inicio=4, pagina_fin=4)

    contexto = _construir_contexto([chunk])

    assert "[1]" in contexto
    assert "PR-08.pdf" in contexto
    assert "3. PROCEDIMIENTO" in contexto
    assert "El manómetro debe calibrarse a 6 bar." in contexto
