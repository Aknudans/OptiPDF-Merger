"""
test_optimizer.py

Pruebas unitarias para optimizer.py.
Se usa monkeypatch sobre optimizer.pymupdf para simular la presencia o
ausencia de la librería, sin depender de tener PyMuPDF real instalado
(salvo en los casos de integración marcados explícitamente).
"""

import pytest
from pathlib import Path

from src import optimizer
from src.optimizer import (
    is_pymupdf_available,
    deduplicate_pdf,
    deduplicate_if_available,
)


@pytest.fixture
def dummy_input(tmp_path):
    input_path = tmp_path / "input.pdf"
    input_path.write_bytes(b"contenido de prueba")
    return input_path


class FakeDoc:
    def __init__(self):
        self.saved_with = None

    def save(self, path, garbage=0, deflate=False):
        self.saved_with = {"path": path, "garbage": garbage, "deflate": deflate}
        Path(path).write_bytes(b"contenido optimizado")

    def close(self):
        pass


class FakePyMuPDF:
    def __init__(self):
        self.opened_path = None
        self.doc = FakeDoc()

    def open(self, path):
        self.opened_path = path
        return self.doc


def test_is_pymupdf_available_true_cuando_la_libreria_esta_presente(monkeypatch):
    monkeypatch.setattr(optimizer, "pymupdf", FakePyMuPDF())
    assert is_pymupdf_available() is True


def test_is_pymupdf_available_false_cuando_la_libreria_no_esta_instalada(monkeypatch):
    monkeypatch.setattr(optimizer, "pymupdf", None)
    assert is_pymupdf_available() is False


def test_deduplicate_pdf_lanza_import_error_si_no_esta_instalado(dummy_input, tmp_path, monkeypatch):
    monkeypatch.setattr(optimizer, "pymupdf", None)
    output_path = tmp_path / "output.pdf"

    with pytest.raises(ImportError):
        deduplicate_pdf(str(dummy_input), str(output_path))


def test_deduplicate_pdf_llama_a_save_con_garbage_4_y_deflate(dummy_input, tmp_path, monkeypatch):
    fake = FakePyMuPDF()
    monkeypatch.setattr(optimizer, "pymupdf", fake)

    output_path = tmp_path / "output.pdf"
    result = deduplicate_pdf(str(dummy_input), str(output_path))

    assert result == output_path
    assert output_path.exists()
    assert fake.opened_path == str(dummy_input)
    assert fake.doc.saved_with["path"] == str(output_path)
    assert fake.doc.saved_with["garbage"] == 4
    assert fake.doc.saved_with["deflate"] is True


def test_deduplicate_if_available_omite_el_paso_si_no_hay_pymupdf(dummy_input, tmp_path, monkeypatch):
    monkeypatch.setattr(optimizer, "is_pymupdf_available", lambda: False)

    called = False

    def fake_deduplicate_pdf(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(optimizer, "deduplicate_pdf", fake_deduplicate_pdf)

    output_path = tmp_path / "output.pdf"
    result = deduplicate_if_available(str(dummy_input), str(output_path))

    assert result == output_path
    assert output_path.exists()
    assert output_path.read_bytes() == dummy_input.read_bytes()
    assert not called


def test_deduplicate_if_available_llama_a_deduplicate_pdf_si_hay_pymupdf(dummy_input, tmp_path, monkeypatch):
    monkeypatch.setattr(optimizer, "is_pymupdf_available", lambda: True)

    called_with = {}

    def fake_deduplicate_pdf(input_path, output_path):
        called_with["args"] = (input_path, output_path)
        return Path(output_path)

    monkeypatch.setattr(optimizer, "deduplicate_pdf", fake_deduplicate_pdf)

    output_path = tmp_path / "output.pdf"
    result = deduplicate_if_available(str(dummy_input), str(output_path))

    assert result == output_path
    assert called_with["args"] == (str(dummy_input), str(output_path))


# ---------- Prueba de integración real con PyMuPDF instalado ----------

def test_integracion_real_deduplica_un_pdf_valido(tmp_path):
    pytest.importorskip("pymupdf")
    from pypdf import PdfWriter

    input_path = tmp_path / "input.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(input_path, "wb") as f:
        writer.write(f)

    output_path = tmp_path / "output.pdf"
    result = deduplicate_pdf(str(input_path), str(output_path))

    assert result == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_deduplicate_pdf_overwrites_existing_output(dummy_input, tmp_path, monkeypatch):
    """Deduplicate debe sobrescribir un archivo de salida existente."""
    fake = FakePyMuPDF()
    monkeypatch.setattr(optimizer, "pymupdf", fake)

    output_path = tmp_path / "output.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"contenido viejo")

    result = deduplicate_pdf(str(dummy_input), str(output_path))

    assert result == output_path
    assert output_path.exists()
    assert output_path.read_bytes() != b"contenido viejo"


def test_deduplicate_pdf_propagates_pymupdf_errors(dummy_input, tmp_path, monkeypatch):
    """Si PyMuPDF lanza un error al abrir, debe propagarse."""
    class BadPyMuPDF:
        def open(self, path):
            raise RuntimeError("error al abrir")

    monkeypatch.setattr(optimizer, "pymupdf", BadPyMuPDF())
    output_path = tmp_path / "output.pdf"

    with pytest.raises(RuntimeError):
        deduplicate_pdf(str(dummy_input), str(output_path))


def test_is_pymupdf_available_parametrized():
    # Comprueba True/False según el valor de la variable interna
    optimizer.pymupdf = None
    assert is_pymupdf_available() is False

    optimizer.pymupdf = FakePyMuPDF()
    assert is_pymupdf_available() is True
