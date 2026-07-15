"""
test_compressor.py

Pruebas unitarias para compressor.py.
Se usa monkeypatch sobre _run_ghostscript para simular tamaños de salida
controlados, sin depender de GhostScript real instalado en el sistema.
"""

import pytest
from pathlib import Path

from src import compressor
from src.compressor import compress_pdf, MB_IN_BYTES, EXTENDED_DPI_START, EXTENDED_DPI_STEP, EXTENDED_DPI_FLOOR


def write_mb(path, size_mb: float) -> None:
    """Escribe un archivo dummy del tamaño (en MB) indicado."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"0" * int(size_mb * MB_IN_BYTES))


@pytest.fixture
def big_input(tmp_path):
    """PDF de entrada 'pesado', por encima de cualquier límite usado en los tests."""
    input_path = tmp_path / "input.pdf"
    write_mb(input_path, 30)
    return input_path


def fake_run_ghostscript_factory(sizes_by_call):
    """
    Crea un reemplazo de _run_ghostscript que, en cada llamada sucesiva,
    escribe en output_path un archivo del tamaño (en MB) indicado en
    sizes_by_call, en orden. gs_setting/extra_args se ignoran.
    """
    calls = {"count": 0}

    def fake_run(input_path, output_path, gs_setting, extra_args=None):
        size_mb = sizes_by_call[calls["count"]]
        calls["count"] += 1
        write_mb(output_path, size_mb)

    fake_run.calls = calls
    return fake_run


def test_ya_cumple_el_limite_no_comprime(tmp_path, monkeypatch):
    input_path = tmp_path / "input.pdf"
    write_mb(input_path, 5)
    output_path = tmp_path / "output.pdf"

    called = False

    def fake_run(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(compressor, "_run_ghostscript", fake_run)

    result = compress_pdf(str(input_path), str(output_path), max_size_mb=20)

    assert result == output_path
    assert output_path.exists()
    assert not called


def test_se_detiene_en_la_primera_fase_que_cumple(tmp_path, monkeypatch, big_input):
    output_path = tmp_path / "output.pdf"

    # Fase 1 y 2 no cumplen, Fase 3 cumple -> no debe llegar a Fase 4 ni a extendidas.
    fake_run = fake_run_ghostscript_factory([25, 22, 15])
    monkeypatch.setattr(compressor, "_run_ghostscript", fake_run)

    result = compress_pdf(str(big_input), str(output_path), max_size_mb=20)

    assert result == output_path
    assert fake_run.calls["count"] == 3
    assert compressor.get_file_size_mb(output_path) == 15


def test_fase_extendida_se_dispara_solo_si_las_4_fijas_no_alcanzan(tmp_path, monkeypatch, big_input):
    output_path = tmp_path / "output.pdf"

    # Las 4 fases fijas no cumplen; el primer paso extendido (60 DPI) sí cumple.
    fake_run = fake_run_ghostscript_factory([25, 24, 23, 22, 15])
    monkeypatch.setattr(compressor, "_run_ghostscript", fake_run)

    used_settings = []
    used_extra_args = []
    real_build = compressor._build_downsample_args

    def spy_run(input_path, output_path, gs_setting, extra_args=None):
        used_settings.append(gs_setting)
        used_extra_args.append(extra_args)
        fake_run(input_path, output_path, gs_setting, extra_args)

    monkeypatch.setattr(compressor, "_run_ghostscript", spy_run)

    result = compress_pdf(str(big_input), str(output_path), max_size_mb=20)

    assert result == output_path
    assert fake_run.calls["count"] == 5
    # El 5to intento (índice 4) es el primer paso extendido: debe usar /screen + downsampling a 60 DPI.
    assert used_settings[4] == "/screen"
    assert used_extra_args[4] == real_build(EXTENDED_DPI_START)
    assert compressor.get_file_size_mb(output_path) == 15


def test_pasos_extendidos_se_ejecutan_en_orden_sin_saltarse_ninguno(tmp_path, monkeypatch, big_input):
    output_path = tmp_path / "output.pdf"

    # 4 fases fijas fallan; extendidas: 60,50,40 no mejoran casi nada (simulando "estancamiento"),
    # 30 DPI recién cumple. Deben ejecutarse igual todos los pasos intermedios, sin saltar ninguno.
    sizes = [25, 24.9, 24.8, 24.7, 24.6, 24.5, 24.4, 15]
    dpis_usados = []

    def fake_run(input_path, output_path, gs_setting, extra_args=None):
        idx = fake_run.count
        fake_run.count += 1
        write_mb(output_path, sizes[idx])
        if extra_args:
            # DPI está en el 7mo elemento de _build_downsample_args (-dColorImageResolution={dpi})
            dpi_arg = [a for a in extra_args if a.startswith("-dColorImageResolution=")][0]
            dpis_usados.append(int(dpi_arg.split("=")[1]))

    fake_run.count = 0
    monkeypatch.setattr(compressor, "_run_ghostscript", fake_run)

    result = compress_pdf(str(big_input), str(output_path), max_size_mb=20)

    assert result == output_path
    assert dpis_usados == [60, 50, 40, 30]
    assert fake_run.count == 8


def test_llega_al_piso_de_dpi_sin_exito(tmp_path, monkeypatch, big_input):
    output_path = tmp_path / "output.pdf"

    num_extended_steps = (EXTENDED_DPI_START - EXTENDED_DPI_FLOOR) // EXTENDED_DPI_STEP + 1
    total_calls = 4 + num_extended_steps
    # Ninguna llamada cumple el límite de 20MB.
    fake_run = fake_run_ghostscript_factory([25 - 0.1 * i for i in range(total_calls)])
    monkeypatch.setattr(compressor, "_run_ghostscript", fake_run)

    result = compress_pdf(str(big_input), str(output_path), max_size_mb=20)

    assert result == output_path
    assert fake_run.calls["count"] == total_calls
    # El archivo final es el del último intento (10 DPI), el más comprimido de toda la escalada.
    assert output_path.exists()
