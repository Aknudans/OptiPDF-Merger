"""
compressor.py

Es el modulo que se encargara de comprimir los PDF's para que estos no superen un
tamaño maximo (20mb por defecto, configurable desde config.py o pasando
max_size_mb explícitamente), sin bajar la calidad de imagen de un piso mínimo
legible (MIN_DPI_FLOOR).
Usa GhostScript como motor principal para la compresión con pérdida, ya que este
ofrece el mejor resultado reduciendo la resolución/calidad de imagenes incrustadas,
algo que las librerias de python en general no hacen ni logran por si solas. Cuando
GhostScript no basta, se recurre a qpdf (optimizer.py) para un paso adicional de
compresión sin pérdida, en vez de seguir sacrificando calidad de imagen.

Flujo:
  Archivo recibido
    -> ¿pesa más de max_size_mb? -> Fase 1: /prepress
    -> ¿pesa más de max_size_mb? -> Fase 2: /printer
    -> ¿pesa más de max_size_mb? -> Fase 3: /ebook
    -> ¿pesa más de max_size_mb? -> Fase 4: /screen, forzando el piso de
       MIN_DPI_FLOOR en vez del ~72 DPI por defecto del preset, para no
       cruzar la calidad mínima aceptable
    -> ¿pesa más de max_size_mb? -> Fase 5: compresión adicional sin
       pérdida con qpdf (recompresión de streams, object streams, poda de
       recursos no referenciados). Si qpdf no está instalado, se omite
       con un aviso y se conserva el resultado de la Fase 4.
"""

import shutil
import subprocess
from pathlib import Path

from tqdm import tqdm

from src.config import DEFAULT_MAX_SIZE_MB
from src.optimizer import deduplicate_pdf, is_qpdf_available

MIN_DPI_FLOOR = 80  # piso de calidad de imagen: nunca bajar de esta resolución

COMPRESSION_PHASES = [
    {"name": "Fase 1", "gs_setting": "/prepress"},                        #Mayor calidad
    {"name": "Fase 2", "gs_setting": "/printer"},                         #Buena Calidad
    {"name": "Fase 3", "gs_setting": "/ebook"},                           #Calidad Media
    {"name": "Fase 4", "gs_setting": "/screen", "floor_dpi": MIN_DPI_FLOOR},  #Maxima Compresion con pérdida, sin cruzar el piso
]

MB_IN_BYTES = 1024 * 1024

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
        "-dMonoImageDownsampleType=/Bicubic",
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
    imprimiendo el progreso por consola. Usa tqdm.write en vez de print
    para no corromper una barra de progreso activa.
    """
    tqdm.write(f"{label}: comprimiendo con calidad {gs_setting}...")
    _run_ghostscript(input_path, output_path, gs_setting, extra_args)

    current_size = get_file_size_mb(output_path)
    tqdm.write(f"Tamaño resultante: {current_size:.2f}MB")
    return current_size


def _attempt_qpdf_squeeze(label: str, path: Path) -> float:
    """
    Ejecuta un paso adicional de compresión sin pérdida con qpdf sobre un
    archivo ya comprimido con GhostScript, sobrescribiéndolo en su lugar.
    Devuelve el tamaño resultante en MB, imprimiendo el progreso por consola
    con tqdm.write para no corromper la barra de progreso activa.
    """
    tqdm.write(f"{label}: compresión adicional sin pérdida con qpdf...")

    tmp_path = path.with_name(path.name + ".qpdf.tmp")
    deduplicate_pdf(str(path), str(tmp_path))
    tmp_path.replace(path)

    current_size = get_file_size_mb(path)
    tqdm.write(f"Tamaño resultante: {current_size:.2f}MB")
    return current_size


def compress_pdf(input_path: str, output_path: str, max_size_mb: float = DEFAULT_MAX_SIZE_MB) -> Path:
    """
    Comprime un PDF aplicando fases sucesivas de calidad decreciente hasta
    que el resultado pese menos que max_size_mb, sin bajar nunca la
    resolución de imagen por debajo de MIN_DPI_FLOOR. Si las 4 fases
    estándar de GhostScript no alcanzan, se aplica una fase final de
    compresión sin pérdida con qpdf (Fase 5) en vez de seguir sacrificando
    calidad de imagen.

    Args:
        input_path: ruta del PDF a comprimir.
        output_path: ruta donde se guardará el PDF comprimido.
        max_size_mb: tamaño máximo permitido, en Megabytes.

    Returns:
        Path del archivo PDF resultante (comprimido, o el mejor logrado
        tras agotar todas las fases, respetando siempre MIN_DPI_FLOOR).
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not _exceeds_limit(input_path, max_size_mb):
        shutil.copyfile(input_path, output_path)
        print(f"'{input_path.name}' ya cumple el límite de {max_size_mb}MB. No requiere compresión.")
        return output_path

    qpdf_available = is_qpdf_available()
    total_steps = len(COMPRESSION_PHASES) + (1 if qpdf_available else 0)

    with tqdm(total=total_steps, desc="Comprimiendo", unit="fase") as pbar:
        for phase in COMPRESSION_PHASES:
            extra_args = _build_downsample_args(phase["floor_dpi"]) if "floor_dpi" in phase else None

            pbar.set_postfix_str(phase["name"])
            current_size = _attempt_compression(
                phase["name"], input_path, output_path, phase["gs_setting"], extra_args
            )
            pbar.update(1)

            if current_size <= max_size_mb:
                tqdm.write(f"\nPDF comprimido guardado en: {output_path}")
                return output_path

        if qpdf_available:
            tqdm.write(
                "\nLas fases de GhostScript no fueron suficientes. "
                f"Bajar más la resolución cruzaría el piso de calidad de {MIN_DPI_FLOOR} DPI, "
                "así que se intenta un paso final de compresión sin pérdida con qpdf..."
            )
            fase_num = len(COMPRESSION_PHASES) + 1
            pbar.set_postfix_str(f"Fase {fase_num} (qpdf)")
            current_size = _attempt_qpdf_squeeze(f"Fase {fase_num}", output_path)
            pbar.update(1)

            if current_size <= max_size_mb:
                tqdm.write(f"\nPDF comprimido guardado en: {output_path}")
                return output_path
        else:
            tqdm.write(
                "\nLas fases de GhostScript no fueron suficientes y qpdf no está instalado: "
                "se omite el paso final de compresión sin pérdida. Instálalo para exprimir "
                "aún más el tamaño sin bajar la calidad de imagen."
            )

    tqdm.write(
        f"\nNo fue posible reducir '{input_path.name}' por debajo de {max_size_mb}MB "
        f"sin bajar la resolución de imagen por debajo del piso de calidad de {MIN_DPI_FLOOR} DPI. "
        "Se recomienda reintentar o revisar el contenido del PDF (imágenes muy pesadas, etc.)."
    )
    return output_path


if __name__ == "__main__":
    # Prueba manual rápida del módulo
    compress_pdf(input_path="output/merged.pdf", output_path="output/compressed.pdf")
