"""
compressor.py

Es el modulo que se encargara de comprimir los PDF's para que estos no superen un 
tamaño maximo (20mb por el momento, se ajustará a futuro para que lo elija el usuario).
Usa GhostScript como motor para la compresión, ya que este ofrece el mejor resultado
reduciendo la resolución/calidad de imagenes incrustadas, algo que las librerias
de python en general no hacen ni logran por si solas

Flujo:
  Archivo recibido
    -> ¿pesa más de 20MB? -> Fase 1: /prepress
    -> ¿pesa más de 20MB? -> Fase 2: /printer
    -> ¿pesa más de 20MB? -> Fase 3: /ebook
    -> ¿pesa más de 20MB? -> Fase 4: /screen
    -> ¿pesa más de 20MB? -> Fases extendidas: downsampling progresivo de
       imágenes (60 -> 50 -> 40 -> 30 -> 20 -> 10 DPI), deteniéndose en el
       primer paso que cumpla el objetivo o al llegar al piso de 10 DPI
"""

import shutil
import subprocess
from pathlib import Path

COMPRESSION_PHASES = [
    {"name": "Fase 1", "gs_setting": "/prepress"},  #Mayor calidad
    {"name": "Fase 2", "gs_setting": "/printer"},   #Buena Calidad
    {"name": "Fase 3", "gs_setting": "/ebook"},     #Calidad Media
    {"name": "Fase 4", "gs_setting": "/screen"},    #Maxima Compresion
]

MB_IN_BYTES = 1024 * 1024

EXTENDED_DPI_START = 60   # primer paso extendido, justo por debajo de /screen (~72 DPI)
EXTENDED_DPI_STEP = 10    # decremento de DPI en cada paso
EXTENDED_DPI_FLOOR = 10   # piso de seguridad: no se baja de este DPI

class GhostScriptNotFoundError(RuntimeError):
    """Se lanzará cuando el binario de GhostScript no se encuentre instalado"""
    pass

def _check_gs_installed() -> str:
    """
    Verificación que GhostScript esté disponible en el sistema
    
    Returns:
        Nombre del comando de GhostScript detectado (puede ser 'gs' o 'gswin64c)
        
    Raises:
        GhostScriptNotFoundError: si no se encuentra el binario
    """

    for cmd in ("gs", "gswin64c", "gswin32c"):
        if shutil.which(cmd):
            return cmd
    
    raise GhostScriptNotFoundError(
        "GhostScript no se encuentra instalado o no está instalado en el PATH." \
        "Instalalo con 'sudo apt install ghostsript' (Linux)" \
        "'brew install ghostscript' (Mac) o descargalo desde " \
        "https://ghostscript.com/releases/ (Windows)."
    )

def get_file_size_mb(path: str) -> float:
    """Devuelve el tamaño de un archivo en Megabytes"""
    return Path(path).stat().st_size / MB_IN_BYTES

def _exceeds_limit(path: str, max_size_mb: float) -> bool:
    """Comprueba si el archivo en 'Path' pesa más que max_size_mb"""
    return get_file_size_mb(path) > max_size_mb

def _run_ghostscript(
    input_path: str,
    output_path: str,
    gs_setting: str,
    extra_args: list[str] | None = None,
) -> None:
    """
    Ejecuta GhostScript sobre input_path aplicando el nivel de calidad
    indicado en gs_setting, generando el resultado en output_path.
    extra_args permite agregar parámetros adicionales (por ejemplo,
    downsampling custom de resolución para las fases extendidas).

    Raises:
        GhostScriptNotFoundError: si el binario de GhostScript no está disponible.
        subprocess.CalledProcessError: si GhostScript termina con error.
    """
    gs_cmd = _check_gs_installed()

    command = [
        gs_cmd,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        f"-dPDFSETTINGS={gs_setting}",
        "-dNOPAUSE",
        "-dBATCH",
        "-dQUIET",
    ]

    if extra_args:
        command.extend(extra_args)

    command.extend([f"-sOutputFile={output_path}", str(input_path)])

    subprocess.run(command, check=True)


def _build_downsample_args(dpi: int) -> list[str]:
    """
    Construye los parámetros de GhostScript para forzar el downsampling
    de imágenes incrustadas (color, gris y monocromo) a una resolución
    específica, usada en las fases extendidas de compresión.
    """
    return [
        "-dDownsampleColorImages=true",
        "-dDownsampleGrayImages=true",
        "-dDownsampleMonoImages=true",
        "-dColorImageDownsampleType=/Average",
        "-dGrayImageDownsampleType=/Average",
        "-dMonoImageDownsampleType=/Subsample",
        f"-dColorImageResolution={dpi}",
        f"-dGrayImageResolution={dpi}",
        f"-dMonoImageResolution={dpi}",
    ]


def _attempt_compression(
    label: str,
    input_path: str,
    output_path: str,
    gs_setting: str,
    extra_args: list[str] | None = None,
) -> float:
    """
    Ejecuta un intento de compresión y devuelve el tamaño resultante en MB,
    imprimiendo el progreso por consola.
    """
    print(f"{label}: comprimiendo con calidad {gs_setting}...")
    _run_ghostscript(input_path, output_path, gs_setting, extra_args)

    current_size = get_file_size_mb(output_path)
    print(f"Tamaño resultante: {current_size:.2f}MB")
    return current_size


def compress_pdf(input_path: str, output_path: str, max_size_mb: float = 20) -> Path:
    """
    Comprime un PDF aplicando fases sucesivas de calidad decreciente hasta
    que el resultado pese menos que max_size_mb. Si las 4 fases estándar
    de GhostScript no alcanzan, continúa con fases extendidas de
    downsampling progresivo de imágenes hasta cumplir el objetivo o hasta
    llegar al piso de seguridad de EXTENDED_DPI_FLOOR.

    Args:
        input_path: ruta del PDF a comprimir.
        output_path: ruta donde se guardará el PDF comprimido.
        max_size_mb: tamaño máximo permitido, en Megabytes.

    Returns:
        Path del archivo PDF resultante (comprimido, o el mejor logrado
        tras agotar todas las fases).
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not _exceeds_limit(input_path, max_size_mb):
        shutil.copyfile(input_path, output_path)
        print(f"'{input_path.name}' ya cumple el límite de {max_size_mb}MB. No requiere compresión.")
        return output_path

    for phase in COMPRESSION_PHASES:
        current_size = _attempt_compression(
            phase["name"], input_path, output_path, phase["gs_setting"]
        )

        if current_size <= max_size_mb:
            print(f"\nPDF comprimido guardado en: {output_path}")
            return output_path

    print(
        "\nLas fases estándar no fueron suficientes. "
        "Iniciando compresión extendida con downsampling progresivo de imágenes..."
    )

    dpi = EXTENDED_DPI_START
    fase_num = len(COMPRESSION_PHASES)

    while dpi >= EXTENDED_DPI_FLOOR:
        fase_num += 1
        current_size = _attempt_compression(
            f"Fase {fase_num}",
            input_path,
            output_path,
            "/screen",
            extra_args=_build_downsample_args(dpi),
        )

        if current_size <= max_size_mb:
            print(f"\nPDF comprimido guardado en: {output_path}")
            return output_path

        dpi -= EXTENDED_DPI_STEP

    print(
        f"\nNo fue posible reducir '{input_path.name}' por debajo de {max_size_mb}MB "
        f"tras aplicar todas las fases de compresión, incluida la compresión extendida "
        f"hasta {EXTENDED_DPI_FLOOR} DPI. Se recomienda reintentar "
        "o revisar el contenido del PDF (imágenes muy pesadas, etc.)."
    )
    return output_path


if __name__ == "__main__":
    # Prueba manual rápida del módulo
    compress_pdf(input_path="output/merged.pdf", output_path="output/compressed.pdf")
