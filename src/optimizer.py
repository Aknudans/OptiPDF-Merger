"""
optimizer.py

Paso de optimización estructural sin pérdida para PDFs, basado en qpdf
(recomprimir streams, generar object streams y quitar recursos ya no
referenciados). Se reutiliza en dos puntos del pipeline:

1. Como pre-paso, antes de la compresión con pérdida de GhostScript
   (llamado desde main.py sobre merged.pdf -> deduped.pdf).
2. Como paso final de "exprimido" sin pérdida dentro de compressor.py,
   cuando las fases de GhostScript no bastan para cumplir el tamaño
   objetivo sin bajar la resolución de imagen por debajo del piso de
   calidad mínimo.

Es un paso OPCIONAL en ambos casos: si qpdf no está instalado, el pipeline
no debe interrumpirse. Se omite el paso con un aviso y se sigue
funcionando solo con GhostScript (compressor.py).
"""

import shutil
import subprocess
from pathlib import Path


def is_qpdf_available() -> bool:
    """Indica si el binario qpdf está instalado y accesible en el PATH."""
    return shutil.which("qpdf") is not None


def deduplicate_pdf(input_path: str, output_path: str) -> Path:
    """
    Optimiza un PDF usando qpdf sin pérdida antes de la compresión final.

    Se ejecuta qpdf con opciones razonables para:
    - recomprimir streams
    - generar object streams
    - eliminar recursos (fuentes, imágenes, etc.) que ya no son referenciados
      por ninguna página, tras la fusión de múltiples PDFs
    - reducir el tamaño sin perder calidad visual

    Args:
        input_path: ruta del PDF a optimizar.
        output_path: ruta donde se guardará el PDF optimizado.

    Returns:
        Path del archivo PDF resultante.

    Raises:
        ImportError: si qpdf no está instalado.
        RuntimeError: si qpdf falla al ejecutar.
    """
    if not is_qpdf_available():
        raise ImportError(
            "qpdf no está instalado. Instálalo y asegúrate de que esté en el PATH."
        )

    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Optimizando sin pérdida '{input_path.name}' con qpdf...")

    try:
        subprocess.run(
            [
                "qpdf",
                "--stream-data=compress",
                "--object-streams=generate",
                "--remove-unreferenced-resources=yes",
                str(input_path),
                str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"qpdf falló al optimizar el PDF: {exc.stderr.strip()}") from exc

    print(f"PDF optimizado guardado en: {output_path}")
    return output_path


def deduplicate_if_available(input_path: str, output_path: str) -> Path:
    """
    Intenta optimizar el PDF con qpdf. Si no está disponible, omite el paso
    y copia el archivo tal cual, permitiendo que el resto del pipeline
    (compress_pdf) siga funcionando.

    Args:
        input_path: ruta del PDF a optimizar.
        output_path: ruta donde se guardará el resultado.

    Returns:
        Path del archivo PDF resultante (optimizado, u original copiado
        si qpdf no está disponible).
    """
    if not is_qpdf_available():
        input_path = Path(input_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        print(
            "qpdf no está instalado: se omite la optimización sin pérdida. "
            "Instálalo para reducir mejor los PDFs antes de la compresión con pérdida."
        )
        shutil.copyfile(input_path, output_path)
        return output_path

    return deduplicate_pdf(input_path, output_path)


if __name__ == "__main__":
    deduplicate_if_available(input_path="output/merged.pdf", output_path="output/deduped.pdf")
