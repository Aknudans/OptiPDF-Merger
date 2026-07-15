"""
test_optimizer.py

Pruebas unitarias para optimizer.py.
Se usa monkeypatch sobre shutil.which y subprocess.run para simular la
presencia/ausencia de mutool, sin depender de que esté instalado en el
sistema donde corren los tests.
"""

import pytest
import subprocess
from pathlib import Path

from src import optimizer
from src.optimizer import (
    is_mutool_available,
    deduplicate_pdf,
    deduplicate_if_available,
    MutoolNotFoundError,
)


@pytest.fixture
def dummy_input(tmp_path):
    input_path = tmp_path / "input.pdf"
    input_path.write_bytes(b"contenido de prueba")
    return input_path


def test_is_mutool_available_true_cuando_esta_en_el_path(monkeypatch):
    monkeypatch.setattr(optimizer.shutil, "which", lambda cmd: "C:/tools/mutool.exe")
    assert is_mutool_available() is True


def test_is_mutool_available_false_cuando_no_esta_en_el_path(monkeypatch):
    monkeypatch.setattr(optimizer.shutil, "which", lambda cmd: None)
    assert is_mutool_available() is False


def test_deduplicate_pdf_lanza_error_si_mutool_no_esta_instalado(dummy_input, tmp_path, monkeypatch):
    monkeypatch.setattr(optimizer.shutil, "which", lambda cmd: None)
    output_path = tmp_path / "output.pdf"

    with pytest.raises(MutoolNotFoundError):
        deduplicate_pdf(str(dummy_input), str(output_path))


def test_deduplicate_pdf_ejecuta_clean_ggg(dummy_input, tmp_path, monkeypatch):
    monkeypatch.setattr(optimizer.shutil, "which", lambda cmd: "mutool")

    captured_command = {}

    def fake_run(command, check):
        captured_command["command"] = command
        # Simula que mutool generó el archivo de salida.
        Path(command[-1]).write_bytes(b"contenido optimizado")

    monkeypatch.setattr(optimizer.subprocess, "run", fake_run)

    output_path = tmp_path / "output.pdf"
    result = deduplicate_pdf(str(dummy_input), str(output_path))

    assert result == output_path
    assert output_path.exists()
    command = captured_command["command"]
    assert command[0] == "mutool"
    assert command[1] == "clean"
    assert "-ggg" in command
    assert command[-2] == str(dummy_input)
    assert command[-1] == str(output_path)


def test_deduplicate_pdf_propaga_error_de_subprocess(dummy_input, tmp_path, monkeypatch):
    monkeypatch.setattr(optimizer.shutil, "which", lambda cmd: "mutool")

    def fake_run(command, check):
        raise subprocess.CalledProcessError(returncode=1, cmd=command)

    monkeypatch.setattr(optimizer.subprocess, "run", fake_run)

    output_path = tmp_path / "output.pdf"
    with pytest.raises(subprocess.CalledProcessError):
        deduplicate_pdf(str(dummy_input), str(output_path))


def test_deduplicate_if_available_omite_el_paso_si_no_hay_mutool(dummy_input, tmp_path, monkeypatch):
    monkeypatch.setattr(optimizer, "is_mutool_available", lambda: False)

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


def test_deduplicate_if_available_llama_a_deduplicate_pdf_si_hay_mutool(dummy_input, tmp_path, monkeypatch):
    monkeypatch.setattr(optimizer, "is_mutool_available", lambda: True)

    called_with = {}

    def fake_deduplicate_pdf(input_path, output_path):
        called_with["args"] = (input_path, output_path)
        return Path(output_path)

    monkeypatch.setattr(optimizer, "deduplicate_pdf", fake_deduplicate_pdf)

    output_path = tmp_path / "output.pdf"
    result = deduplicate_if_available(str(dummy_input), str(output_path))

    assert result == output_path
    assert called_with["args"] == (str(dummy_input), str(output_path))
