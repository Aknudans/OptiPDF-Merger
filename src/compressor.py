"""
compressor.py

Se encarga de comprimir un PDF para que no supere un tamaño máximo (por
defecto 20MB). Usa Ghostscript como motor de compresión, ya que ofrece
el mejor resultado reduciendo la resolución/calidad de imágenes incrustadas,
algo que las librerías puras de Python (pypdf, pikepdf) no hacen bien por sí solas.
"""

import shutil
import subprocess
from pathlib import Path

# Niveles de compresión de Ghostscript, de MENOS a MÁS agresivo.
# Se recorren en orden inverso (más agresivo primero) solo si el PDF
# original ya supera el límite.
GS_QUALITY_LEVELS = [
    "/prepress",  # Mayor calidad, menor compresión (~300dpi)
    "/printer",   # Buena calidad (~300dpi)
    "/ebook",     # Calidad media (~150dpi) — buen balance para documentos
    "/screen",    # Máxima compresión (~72dpi) — última opción
]

MB_IN_BYTES = 1024 * 1024


class GhostscriptNotFoundError(RuntimeError):
    """Se lanza cuando el binario de Ghostscript no está instalado."""
    pass


def _check_gs_installed() -> str:
    """
    Verifica que Ghostscript esté disponible en el sistema.

    Returns:
        Nombre del comando de Ghostscript detectado ('gs' o 'gswin64c').

    Raises:
        GhostscriptNotFoundError: si no se encuentra el binario.
    """
    for cmd in ("gs", "gswin64c", "gswin32c"):
        if shutil.which(cmd):
            return cmd

    raise GhostscriptNotFoundError(
        "Ghostscript no está instalado o no está en el PATH. "
        "Instálalo con 'sudo apt install ghostscript' (Linux), "
        "'brew install ghostscript' (Mac) o descárgalo desde "
        "https://ghostscript.com/releases/ (Windows)."
    )


def get_file_size_mb(path: str) -> float:
    """Devuelve el tamaño de un archivo en megabytes."""
    return Path(path).stat().st_size / MB_IN_BYTES


def _run_ghostscript(input_path: str, output_path: str, quality: str) -> None:
    """
    Ejecuta Ghostscript con un nivel de calidad/compresión determinado.

    Args:
        input_path: PDF de entrada.
        output_path: ruta donde se guardará el PDF comprimido.
        quality: uno de los valores de GS_QUALITY_LEVELS (ej. '/ebook').

    Raises:
        subprocess.CalledProcessError: si Ghostscript falla al ejecutarse.
    """
    gs_cmd = _check_gs_installed()

    command = [
        gs_cmd,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        f"-dPDFSETTINGS={quality}",
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        f"-sOutputFile={output_path}",
        input_path,
    ]

    subprocess.run(command, check=True, capture_output=True)


def compress_pdf(
    input_path: str,
    output_path: str,
    max_size_mb: float = 20.0,
) -> Path:
    """
    Comprime un PDF probando niveles de calidad decrecientes hasta que
    el resultado esté por debajo de max_size_mb, o hasta agotar los niveles.

    Args:
        input_path: ruta del PDF a comprimir (normalmente el PDF ya fusionado).
        output_path: ruta donde se guardará el PDF comprimido final.
        max_size_mb: límite de tamaño deseado, en megabytes.

    Returns:
        Path del PDF final. Si ningún nivel logra bajar del límite,
        devuelve el resultado del nivel más agresivo (/screen) junto con
        una advertencia impresa en consola.

    Raises:
        FileNotFoundError: si input_path no existe.
        GhostscriptNotFoundError: si Ghostscript no está instalado.
    """
    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(f"El archivo '{input_path}' no existe.")

    current_size = get_file_size_mb(input_path)
    print(f"Tamaño original: {current_size:.2f}MB (límite: {max_size_mb}MB)")

    if current_size <= max_size_mb:
        print("El PDF ya está dentro del límite. No se requiere compresión.")
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(input_path, output_path)
        return output

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    # Empezamos desde el nivel MENOS agresivo (mejor calidad) y vamos
    # subiendo la agresividad solo si es necesario.
    for quality in GS_QUALITY_LEVELS:
        print(f"Probando compresión con nivel {quality}...")
        _run_ghostscript(str(input_file), str(output), quality)

        new_size = get_file_size_mb(str(output))
        print(f"  Resultado: {new_size:.2f}MB")

        if new_size <= max_size_mb:
            print(f"Objetivo alcanzado con nivel {quality}.")
            return output

    print(
        f"Advertencia: no fue posible bajar de {max_size_mb}MB ni siquiera "
        f"con el nivel más agresivo ({GS_QUALITY_LEVELS[-1]}). "
        f"Tamaño final: {get_file_size_mb(str(output)):.2f}MB"
    )
    return output


if __name__ == "__main__":
    # Prueba manual rápida del módulo
    compress_pdf(
        input_path="output/merged.pdf",
        output_path="output/merged_compressed.pdf",
        max_size_mb=20,
    )