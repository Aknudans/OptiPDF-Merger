"""
test_compressor.py

Pruebas unitarias para compressor.py.
Se usa monkeypatch sobre _run_ghostscript para simular tamaños de salida
controlados, sin depender de GhostScript real instalado en el sistema, y
sobre is_qpdf_available/deduplicate_pdf para simular la disponibilidad y
el resultado del paso final de compresión sin pérdida con qpdf (Fase 5),
sin depender de qpdf real instalado en el sistema.
"""

import pytest
from pathlib import Path

from src import compressor
from src.compressor import compress_pdf, MB_IN_BYTES, MIN_DPI_FLOOR


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


def fake_deduplicate_pdf_factory(size_mb):
    """
    Crea un reemplazo de deduplicate_pdf (el qpdf real) que escribe en
    output_path un archivo del tamaño (en MB) indicado, simulando el
    resultado de la Fase 5 sin invocar qpdf de verdad.
    """
    calls = {"count": 0}

    def fake_deduplicate(input_path, output_path):
        calls["count"] += 1
        write_mb(output_path, size_mb)
        return Path(output_path)

    fake_deduplicate.calls = calls
    return fake_deduplicate


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

    # Fase 1 y 2 no cumplen, Fase 3 cumple -> no debe llegar a Fase 4 ni a qpdf.
    fake_run = fake_run_ghostscript_factory([25, 22, 15])
    monkeypatch.setattr(compressor, "_run_ghostscript", fake_run)
    monkeypatch.setattr(compressor, "is_qpdf_available", lambda: False)

    result = compress_pdf(str(big_input), str(output_path), max_size_mb=20)

    assert result == output_path
    assert fake_run.calls["count"] == 3
    assert compressor.get_file_size_mb(output_path) == 15


def test_fase_4_fuerza_el_piso_de_dpi_en_vez_del_default_de_screen(tmp_path, monkeypatch, big_input):
    output_path = tmp_path / "output.pdf"

    # Fases 1-3 no cumplen, Fase 4 (/screen) sí cumple.
    fake_run = fake_run_ghostscript_factory([25, 24, 23, 15])
    monkeypatch.setattr(compressor, "is_qpdf_available", lambda: False)

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
    assert fake_run.calls["count"] == 4
    # La Fase 4 (índice 3) debe usar /screen forzando MIN_DPI_FLOOR, no el
    # ~72 DPI por defecto del preset.
    assert used_settings[3] == "/screen"
    assert used_extra_args[3] == real_build(MIN_DPI_FLOOR)
    assert compressor.get_file_size_mb(output_path) == 15


def test_fase_5_qpdf_se_ejecuta_si_las_4_fases_gs_no_alcanzan(tmp_path, monkeypatch, big_input):
    output_path = tmp_path / "output.pdf"

    # Las 4 fases fijas de GhostScript no cumplen.
    fake_run = fake_run_ghostscript_factory([25, 24, 23, 22])
    monkeypatch.setattr(compressor, "_run_ghostscript", fake_run)
    monkeypatch.setattr(compressor, "is_qpdf_available", lambda: True)

    # qpdf sí logra bajar del límite.
    fake_dedup = fake_deduplicate_pdf_factory(15)
    monkeypatch.setattr(compressor, "deduplicate_pdf", fake_dedup)

    result = compress_pdf(str(big_input), str(output_path), max_size_mb=20)

    assert result == output_path
    assert fake_run.calls["count"] == 4
    assert fake_dedup.calls["count"] == 1
    assert compressor.get_file_size_mb(output_path) == 15
    # El archivo temporal usado para la recompresión no debe quedar en disco.
    assert not output_path.with_name(output_path.name + ".qpdf.tmp").exists()


def test_fase_5_se_omite_con_aviso_si_qpdf_no_esta_instalado(tmp_path, monkeypatch, big_input):
    output_path = tmp_path / "output.pdf"

    # Las 4 fases fijas de GhostScript no cumplen y qpdf no está disponible.
    fake_run = fake_run_ghostscript_factory([25, 24, 23, 22])
    monkeypatch.setattr(compressor, "_run_ghostscript", fake_run)
    monkeypatch.setattr(compressor, "is_qpdf_available", lambda: False)

    called = False

    def fake_dedup(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(compressor, "deduplicate_pdf", fake_dedup)

    result = compress_pdf(str(big_input), str(output_path), max_size_mb=20)

    assert result == output_path
    assert fake_run.calls["count"] == 4
    assert not called
    # Se conserva el resultado de la Fase 4, el mejor logrado sin qpdf.
    assert compressor.get_file_size_mb(output_path) == 22


def test_qpdf_no_alcanza_se_conserva_el_mejor_intento_sin_fallar(tmp_path, monkeypatch, big_input):
    output_path = tmp_path / "output.pdf"

    # Ni las 4 fases de GhostScript ni qpdf logran bajar del límite.
    fake_run = fake_run_ghostscript_factory([25, 24, 23, 22])
    monkeypatch.setattr(compressor, "_run_ghostscript", fake_run)
    monkeypatch.setattr(compressor, "is_qpdf_available", lambda: True)

    fake_dedup = fake_deduplicate_pdf_factory(21)
    monkeypatch.setattr(compressor, "deduplicate_pdf", fake_dedup)

    result = compress_pdf(str(big_input), str(output_path), max_size_mb=20)

    assert result == output_path
    assert output_path.exists()
    assert fake_dedup.calls["count"] == 1
    assert compressor.get_file_size_mb(output_path) == 21


def test_exactly_at_limit_no_compress(tmp_path, monkeypatch):
    """Si el archivo pesa exactamente el límite, no debe comprimirse."""
    input_path = tmp_path / "input.pdf"
    write_mb(input_path, 20)
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


def test_zero_size_file_copies(tmp_path, monkeypatch):
    """Un archivo de 0 bytes se copia sin llamar a GhostScript."""
    input_path = tmp_path / "input.pdf"
    write_mb(input_path, 0)
    output_path = tmp_path / "output.pdf"

    called = False

    def fake_run(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(compressor, "_run_ghostscript", fake_run)

    result = compress_pdf(str(input_path), str(output_path), max_size_mb=1)

    assert result == output_path
    assert output_path.exists()
    assert not called


def test_missing_input_raises(tmp_path):
    """Si el archivo de entrada no existe, debe propagarse FileNotFoundError."""
    input_path = tmp_path / "no_existe.pdf"
    output_path = tmp_path / "output.pdf"

    with pytest.raises(FileNotFoundError):
        compress_pdf(str(input_path), str(output_path), max_size_mb=1)


def test_build_downsample_args_returns_expected_length():
    """_build_downsample_args debe devolver la lista correcta de argumentos."""
    args = compressor._build_downsample_args(50)
    # Debe contener 9 elementos (3 switches + 3 tipos + 3 resoluciones)
    assert isinstance(args, list)
    assert len(args) == 9


def test_build_downsample_args_contains_resolution_args():
    args = compressor._build_downsample_args(30)
    # Verificar que aparecen las claves de resolución con el valor correcto
    assert any(a == "-dColorImageResolution=30" for a in args)
    assert any(a == "-dGrayImageResolution=30" for a in args)
    assert any(a == "-dMonoImageResolution=30" for a in args)
