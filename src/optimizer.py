"""
optimizer.py

Paso opcional de optimización estructural para PDFs fusionados, previo a
la compresión de imágenes. Usa mutool (MuPDF) para deduplicar objetos
repetidos entre los documentos fusionados (fuentes embebidas duplicadas,
streams redundantes, etc.), algo que GhostScript no resuelve bien porque
cada PDF de origen suele traer su propio subset de la misma fuente.

Es un paso OPCIONAL: a diferencia de GhostScript en compressor.py, si
mutool no está instalado el pipeline no debe interrumpirse. Se omite el
paso con un aviso y se sigue funcionando solo con compressor.py.
"""

import shutil
import subprocess
from pathlib import Path


class MutoolNotFoundError(RuntimeError):
    """Se lanzará cuando el binario de mutool no se encuentre instalado"""
    pass


def is_mutool_available() -> bool:
    """Indica si mutool está disponible en el sistema."""
    return shutil.which("mutool") is not None


def _check_mutool_installed() -> str:
    """
    Verificación que mutool esté disponible en el sistema.

    Returns:
        Nombre del comando de mutool detectado.

    Raises:
        MutoolNotFoundError: si no se encuentra el binario.
    """
    if shutil.which("mutool"):
        return "mutool"

    raise MutoolNotFoundError(
        "mutool no se encuentra instalado o no está en el PATH. "
        "Instalalo con 'sudo apt install mupdf-tools' (Linux), "
        "'brew install mupdf-tools' (Mac) o descargalo el ejecutable "
        "portable desde https://mupdf.com/releases (Windows)."
    )


def deduplicate_pdf(input_path: str, output_path: str) -> Path:
    """
    Ejecuta 'mutool clean -ggg' sobre input_path para deduplicar objetos
    repetidos (fuentes, imágenes, streams) y descartar objetos no
    referenciados, generando el resultado en output_path.

    Especialmente útil en PDFs fusionados desde múltiples documentos de
    puro texto, donde cada uno puede traer su propio subset embebido de
    la misma fuente sin deduplicar entre sí.

    Args:
        input_path: ruta del PDF a optimizar.
        output_path: ruta donde se guardará el PDF optimizado.

    Returns:
        Path del archivo PDF resultante.

    Raises:
        MutoolNotFoundError: si el binario de mutool no está disponible.
        subprocess.CalledProcessError: si mutool termina con error.
    """
    mutool_cmd = _check_mutool_installed()

    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [mutool_cmd, "clean", "-ggg", str(input_path), str(output_path)]

    print(f"Deduplicando objetos de '{input_path.name}' con mutool...")
    subprocess.run(command, check=True)
    print(f"PDF optimizado guardado en: {output_path}")

    return output_path


def deduplicate_if_available(input_path: str, output_path: str) -> Path:
    """
    Intenta deduplicar el PDF con mutool. Si mutool no está instalado,
    omite el paso y copia el archivo tal cual, permitiendo que el resto
    del pipeline (compress_pdf) siga funcionando sin esta optimización.

    Args:
        input_path: ruta del PDF a optimizar.
        output_path: ruta donde se guardará el resultado.

    Returns:
        Path del archivo PDF resultante (deduplicado, u original copiado
        si mutool no está disponible).
    """
    if not is_mutool_available():
        input_path = Path(input_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        print(
            "mutool no está instalado: se omite la deduplicación de objetos. "
            "Instalalo desde https://mupdf.com/releases para reducir mejor "
            "PDFs fusionados con fuentes duplicadas."
        )
        shutil.copyfile(input_path, output_path)
        return output_path

    return deduplicate_pdf(input_path, output_path)


if __name__ == "__main__":
    # Prueba manual rápida del módulo
    deduplicate_if_available(input_path="output/merged.pdf", output_path="output/deduped.pdf")
