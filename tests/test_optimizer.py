"""
test_optimizer.py

Pruebas unitarias para optimizer.py.
Se usa monkeypatch sobre optimizer.shutil.which y optimizer.subprocess.run
para simular la presencia o ausencia de qpdf sin depender de tener qpdf
instalado en el entorno.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from src import optimizer
from src.optimizer import (
    deduplicate_if_available,
    deduplicate_pdf,
    is_qpdf_available,
)


@pytest.fixture
def dummy_input(tmp_path):
    input_path = tmp_path / "input.pdf"
    input_path.write_bytes(b"contenido de prueba")
    return input_path


def test_is_qpdf_available_true_cuando_el_binario_esta_presente(monkeypatch):
    monkeypatch.setattr(optimizer.shutil, "which", lambda cmd: "/usr/bin/qpdf" if cmd == "qpdf" else None)
    assert is_qpdf_available() is True


def test_is_qpdf_available_false_cuando_el_binario_no_esta_instalado(monkeypatch):
    monkeypatch.setattr(optimizer.shutil, "which", lambda cmd: None)
    assert is_qpdf_available() is False


def test_deduplicate_pdf_lanza_import_error_si_no_esta_instalado(dummy_input, tmp_path, monkeypatch):
    monkeypatch.setattr(optimizer.shutil, "which", lambda cmd: None)
    output_path = tmp_path / "output.pdf"

    with pytest.raises(ImportError):
        deduplicate_pdf(str(dummy_input), str(output_path))


def test_deduplicate_pdf_llama_a_qpdf_con_opciones_correctas(dummy_input, tmp_path, monkeypatch):
    monkeypatch.setattr(optimizer.shutil, "which", lambda cmd: "/usr/bin/qpdf" if cmd == "qpdf" else None)

    calls = {}

    def fake_run(cmd, check, capture_output, text):
        calls["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"contenido optimizado")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(optimizer.subprocess, "run", fake_run)

    output_path = tmp_path / "output.pdf"
    result = deduplicate_pdf(str(dummy_input), str(output_path))

    assert result == output_path
    assert output_path.exists()
    assert calls["cmd"] == [
        "qpdf",
        "--stream-data=compress",
        "--object-streams=generate",
        str(dummy_input),
        str(output_path),
    ]


def test_deduplicate_if_available_omite_el_paso_si_no_hay_qpdf(dummy_input, tmp_path, monkeypatch):
    monkeypatch.setattr(optimizer, "is_qpdf_available", lambda: False)

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


def test_deduplicate_if_available_llama_a_deduplicate_pdf_si_hay_qpdf(dummy_input, tmp_path, monkeypatch):
    monkeypatch.setattr(optimizer, "is_qpdf_available", lambda: True)

    called_with = {}

    def fake_deduplicate_pdf(input_path, output_path):
        called_with["args"] = (input_path, output_path)
        return Path(output_path)

    monkeypatch.setattr(optimizer, "deduplicate_pdf", fake_deduplicate_pdf)

    output_path = tmp_path / "output.pdf"
    result = deduplicate_if_available(str(dummy_input), str(output_path))

    assert result == output_path
    assert called_with["args"] == (str(dummy_input), str(output_path))


def test_integracion_real_deduplica_un_pdf_valido(tmp_path):
    if shutil.which("qpdf") is None:
        pytest.skip("qpdf no está instalado en el sistema")

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
    monkeypatch.setattr(optimizer.shutil, "which", lambda cmd: "/usr/bin/qpdf" if cmd == "qpdf" else None)

    def fake_run(cmd, check, capture_output, text):
        Path(cmd[-1]).write_bytes(b"contenido optimizado")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(optimizer.subprocess, "run", fake_run)

    output_path = tmp_path / "output.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"contenido viejo")

    result = deduplicate_pdf(str(dummy_input), str(output_path))

    assert result == output_path
    assert output_path.exists()
    assert output_path.read_bytes() != b"contenido viejo"


def test_deduplicate_pdf_propagates_qpdf_errors(dummy_input, tmp_path, monkeypatch):
    """Si qpdf falla, debe propagarse como error."""
    monkeypatch.setattr(optimizer.shutil, "which", lambda cmd: "/usr/bin/qpdf" if cmd == "qpdf" else None)

    def fake_run(cmd, check, capture_output, text):
        raise subprocess.CalledProcessError(1, cmd, stderr="error al ejecutar qpdf")

    monkeypatch.setattr(optimizer.subprocess, "run", fake_run)
    output_path = tmp_path / "output.pdf"

    with pytest.raises(RuntimeError):
        deduplicate_pdf(str(dummy_input), str(output_path))


def test_is_qpdf_available_parametrized():
    optimizer.shutil.which = lambda cmd: None
    assert is_qpdf_available() is False

    optimizer.shutil.which = lambda cmd: "/usr/bin/qpdf" if cmd == "qpdf" else None
    assert is_qpdf_available() is True
