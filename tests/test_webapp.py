"""
test_webapp.py

Pruebas para la interfaz web (webapp.py) usando el test client de Flask.
Se monkeypatchea merge_pdfs/deduplicate_if_available/compress_pdf en el
propio módulo webapp (no en merger/optimizer/compressor), ya que webapp.py
los importa por nombre (`from src.merger import merge_pdfs`, etc.), igual
que compressor.py hace con optimizer.py.
"""

import base64
import io
from pathlib import Path

import pytest

from src import webapp
from src.webapp import _clean_console_log


@pytest.fixture
def client():
    webapp.app.config["TESTING"] = True
    return webapp.app.test_client()


def fake_merge_pdfs(input_dir, output_path):
    print("Fusionando: a.pdf, b.pdf")
    Path(output_path).write_bytes(b"contenido fusionado")
    return Path(output_path)


def fake_deduplicate_if_available(input_path, output_path):
    print("Optimizando con qpdf...")
    Path(output_path).write_bytes(Path(input_path).read_bytes())
    return Path(output_path)


def fake_compress_pdf(input_path, output_path, max_size_mb):
    print("Fase 1: comprimiendo con calidad /prepress...")
    Path(output_path).write_bytes(Path(input_path).read_bytes() + b"_comprimido")
    return Path(output_path)


def _extract_data_uri_bytes(response_html: str) -> bytes:
    marker = "data:application/pdf;base64,"
    start = response_html.index(marker) + len(marker)
    end = response_html.index('"', start)
    return base64.b64decode(response_html[start:end])


# ---------- _clean_console_log ----------

def test_clean_console_log_conserva_lineas_simples():
    assert _clean_console_log("hola\nmundo") == "hola\nmundo"


def test_clean_console_log_resuelve_retornos_de_carro():
    # Simula una barra de progreso de tqdm: cada \r reinicia la línea actual.
    raw = "avance: 10%\ravance: 100%\ndone"
    assert _clean_console_log(raw) == "avance: 100%\ndone"


def test_clean_console_log_descarta_lineas_vacias():
    assert _clean_console_log("\n\nmensaje real\n\n") == "mensaje real"


# ---------- Página de inicio ----------

def test_home_page_ofrece_ambas_opciones(client):
    response = client.get("/")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'href="/fusion"' in body
    assert 'href="/compresion"' in body


# ---------- Fusión ----------

def test_fusion_form_permite_multiples_archivos(client):
    response = client.get("/fusion")

    assert response.status_code == 200
    assert "multiple" in response.get_data(as_text=True)


def test_fusion_submit_rechaza_menos_de_dos_archivos(client):
    response = client.post(
        "/fusion",
        data={"pdfs": [(io.BytesIO(b"%PDF-1.4 uno"), "a.pdf")]},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "al menos 2 documentos" in response.get_data(as_text=True).lower()


def test_fusion_submit_rechaza_archivos_sin_extension_pdf(client):
    # No se monkeypatchea merge_pdfs: se deja que la implementación real
    # detecte que, tras filtrar los .txt, no quedó ningún PDF que fusionar.
    response = client.post(
        "/fusion",
        data={
            "pdfs": [
                (io.BytesIO(b"no es un pdf"), "a.txt"),
                (io.BytesIO(b"tampoco"), "b.txt"),
            ]
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "no se encontraron archivos pdf" in response.get_data(as_text=True).lower()


def test_fusion_submit_exitoso_muestra_descarga_y_registro(client, monkeypatch):
    monkeypatch.setattr(webapp, "merge_pdfs", fake_merge_pdfs)
    monkeypatch.setattr(webapp, "deduplicate_if_available", fake_deduplicate_if_available)
    monkeypatch.setattr(webapp, "compress_pdf", fake_compress_pdf)

    response = client.post(
        "/fusion",
        data={
            "pdfs": [
                (io.BytesIO(b"%PDF-1.4 uno"), "a.pdf"),
                (io.BytesIO(b"%PDF-1.4 dos"), "b.pdf"),
            ]
        },
        content_type="multipart/form-data",
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert 'download="fusionado_comprimido.pdf"' in body
    assert _extract_data_uri_bytes(body) == b"contenido fusionado_comprimido"
    # El registro del proceso (stdout capturado) debe mostrarse en la página.
    assert "fusionando" in body.lower()
    assert "optimizando con qpdf" in body.lower()
    assert "fase 1" in body.lower()


# ---------- Compresión ----------

def test_compresion_form_solo_un_archivo(client):
    response = client.get("/compresion")

    assert response.status_code == 200
    assert "multiple" not in response.get_data(as_text=True)


def test_compresion_submit_rechaza_si_no_hay_archivo(client):
    response = client.post("/compresion", data={}, content_type="multipart/form-data")

    assert response.status_code == 200
    assert "elija un documento" in response.get_data(as_text=True).lower()


def test_compresion_submit_rechaza_archivo_no_pdf(client):
    response = client.post(
        "/compresion",
        data={"pdf": (io.BytesIO(b"no es un pdf"), "documento.txt")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "debe ser un .pdf" in response.get_data(as_text=True).lower()


def test_compresion_submit_exitoso_muestra_descarga_y_registro(client, monkeypatch):
    monkeypatch.setattr(webapp, "deduplicate_if_available", fake_deduplicate_if_available)
    monkeypatch.setattr(webapp, "compress_pdf", fake_compress_pdf)

    response = client.post(
        "/compresion",
        data={"pdf": (io.BytesIO(b"%PDF-1.4 contenido"), "contrato.pdf")},
        content_type="multipart/form-data",
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert 'download="contrato_comprimido.pdf"' in body
    assert _extract_data_uri_bytes(body) == b"%PDF-1.4 contenido_comprimido"
    assert "optimizando con qpdf" in body.lower()
    assert "fase 1" in body.lower()


def test_compresion_submit_maneja_ghostscript_faltante(client, monkeypatch):
    monkeypatch.setattr(webapp, "deduplicate_if_available", fake_deduplicate_if_available)

    def fake_compress_raises(input_path, output_path, max_size_mb):
        raise webapp.GhostScriptNotFoundError("GhostScript no está instalado.")

    monkeypatch.setattr(webapp, "compress_pdf", fake_compress_raises)

    response = client.post(
        "/compresion",
        data={"pdf": (io.BytesIO(b"%PDF-1.4 contenido"), "contrato.pdf")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "ghostscript" in response.get_data(as_text=True).lower()
