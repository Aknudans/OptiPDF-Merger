"""
test_merger.py

Pruebas unitarias para merger.py.
Usa pytest y genera PDFs de prueba dinámicamente (no dependemos de
archivos reales guardados en el repo).
"""

import pytest
from pathlib import Path
from pypdf import PdfWriter, PdfReader

from src.merger import get_pdf_files, merge_pdfs


def create_dummy_pdf(path: Path, num_pages: int = 1) -> None:
    """
    Crea un PDF de prueba con la cantidad de páginas indicada.
    Útil para no depender de archivos PDF reales en los tests.
    """
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=200, height=200)

    with open(path, "wb") as f:
        writer.write(f)


@pytest.fixture
def pdf_folder(tmp_path):
    """
    Fixture que crea una carpeta temporal con 3 PDFs de prueba:
    a.pdf (1 pág.), b.pdf (2 pág.), c.pdf (1 pág.)
    tmp_path es una fixture nativa de pytest: se limpia sola después del test.
    """
    folder = tmp_path / "input_pdfs"
    folder.mkdir()

    create_dummy_pdf(folder / "b.pdf", num_pages=2)
    create_dummy_pdf(folder / "a.pdf", num_pages=1)
    create_dummy_pdf(folder / "c.pdf", num_pages=1)

    return folder


# ---------- Tests para get_pdf_files ----------

def test_get_pdf_files_encuentra_todos_los_pdfs(pdf_folder):
    result = get_pdf_files(str(pdf_folder))
    nombres = [p.name for p in result]

    assert len(result) == 3
    assert set(nombres) == {"a.pdf", "b.pdf", "c.pdf"}


def test_get_pdf_files_orden_alfabetico(pdf_folder):
    result = get_pdf_files(str(pdf_folder))
    nombres = [p.name for p in result]

    assert nombres == ["a.pdf", "b.pdf", "c.pdf"]


def test_get_pdf_files_ignora_archivos_no_pdf(pdf_folder):
    # Creamos un archivo que no es PDF, no debería aparecer en el resultado
    (pdf_folder / "notas.txt").write_text("esto no es un pdf")

    result = get_pdf_files(str(pdf_folder))
    nombres = [p.name for p in result]

    assert "notas.txt" not in nombres
    assert len(result) == 3


def test_get_pdf_files_carpeta_inexistente():
    with pytest.raises(FileNotFoundError):
        get_pdf_files("carpeta/que/no/existe")


def test_get_pdf_files_carpeta_vacia(tmp_path):
    carpeta_vacia = tmp_path / "vacia"
    carpeta_vacia.mkdir()

    with pytest.raises(ValueError):
        get_pdf_files(str(carpeta_vacia))


# ---------- Tests para merge_pdfs ----------

def test_merge_pdfs_genera_archivo_de_salida(pdf_folder, tmp_path):
    output_path = tmp_path / "output" / "merged.pdf"

    result = merge_pdfs(str(pdf_folder), str(output_path))

    assert result.exists()
    assert result == output_path


def test_merge_pdfs_cantidad_total_de_paginas(pdf_folder, tmp_path):
    # a.pdf (1) + b.pdf (2) + c.pdf (1) = 4 páginas en total
    output_path = tmp_path / "output" / "merged.pdf"

    merge_pdfs(str(pdf_folder), str(output_path))

    reader = PdfReader(str(output_path))
    assert len(reader.pages) == 4


def test_merge_pdfs_crea_carpeta_output_si_no_existe(pdf_folder, tmp_path):
    # output/ ni siquiera existe todavía antes de correr la función
    output_path = tmp_path / "carpeta_nueva" / "merged.pdf"
    assert not output_path.parent.exists()

    merge_pdfs(str(pdf_folder), str(output_path))

    assert output_path.parent.exists()
    assert output_path.exists()


def test_merge_pdfs_falla_si_no_hay_pdfs(tmp_path):
    carpeta_vacia = tmp_path / "vacia"
    carpeta_vacia.mkdir()
    output_path = tmp_path / "output" / "merged.pdf"

    with pytest.raises(ValueError):
        merge_pdfs(str(carpeta_vacia), str(output_path))