"""
optimizer.py

Paso opcional de optimización estructural para PDFs fusionados, previo a
la compresión de imágenes. Usa PyMuPDF (biblioteca Python sobre MuPDF)
para deduplicar objetos repetidos entre los documentos fusionados
(fuentes embebidas duplicadas, streams redundantes, etc.), algo que
GhostScript no resuelve bien porque cada PDF de origen suele traer su
propio subset de la misma fuente.

Es un paso OPCIONAL: si PyMuPDF no está instalado ('pip install pymupdf'),
el pipeline no debe interrumpirse. Se omite el paso con un aviso y se
sigue funcionando solo con compressor.py.
"""

import shutil
from pathlib import Path

try:
    import pymupdf
except ImportError:
    pymupdf = None


def is_pymupdf_available() -> bool:
    """Indica si la librería PyMuPDF está instalada."""
    return pymupdf is not None


def deduplicate_pdf(input_path: str, output_path: str) -> Path:
    """
    Abre input_path con PyMuPDF y lo guarda en output_path con
    garbage=4 (deduplica objetos repetidos: fuentes, imágenes y streams,
    y descarta los no referenciados) y deflate=True (recomprime streams).

    Especialmente útil en PDFs fusionados desde múltiples documentos de
    puro texto, donde cada uno puede traer su propio subset embebido de
    la misma fuente sin deduplicar entre sí.

    Args:
        input_path: ruta del PDF a optimizar.
        output_path: ruta donde se guardará el PDF optimizado.

    Returns:
        Path del archivo PDF resultante.

    Raises:
        ImportError: si PyMuPDF no está instalado.
    """
    if pymupdf is None:
        raise ImportError(
            "PyMuPDF no está instalado. Instalalo con 'pip install pymupdf'."
        )

    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Deduplicando objetos de '{input_path.name}' con PyMuPDF...")

    doc = pymupdf.open(str(input_path))
    doc.save(str(output_path), garbage=4, deflate=True)
    doc.close()

    print(f"PDF optimizado guardado en: {output_path}")
    return output_path


def deduplicate_if_available(input_path: str, output_path: str) -> Path:
    """
    Intenta deduplicar el PDF con PyMuPDF. Si la librería no está
    instalada, omite el paso y copia el archivo tal cual, permitiendo
    que el resto del pipeline (compress_pdf) siga funcionando sin esta
    optimización.

    Args:
        input_path: ruta del PDF a optimizar.
        output_path: ruta donde se guardará el resultado.

    Returns:
        Path del archivo PDF resultante (deduplicado, u original copiado
        si PyMuPDF no está disponible).
    """
    if not is_pymupdf_available():
        input_path = Path(input_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        print(
            "PyMuPDF no está instalado: se omite la deduplicación de objetos. "
            "Instalalo con 'pip install pymupdf' para reducir mejor PDFs "
            "fusionados con fuentes duplicadas."
        )
        shutil.copyfile(input_path, output_path)
        return output_path

    return deduplicate_pdf(input_path, output_path)


if __name__ == "__main__":
    # Prueba manual rápida del módulo
    deduplicate_if_available(input_path="output/merged.pdf", output_path="output/deduped.pdf")
