"""
merger.py
Se encarga únicamente de fusionar múltiples archivos PDF de una carpeta
en un solo documento PDF.
"""

from pathlib import Path
from pypdf import PdfWriter
from tqdm import tqdm

def get_pdf_files(input_dir: str) -> list[Path]:
    """
    Devuelve la lista de archivos PDF encontrados en input_dir,
    ordenados alfabéticamente para garantizar un orden predecible.

    Args:
        input_dir: ruta a la carpeta que contiene los PDFs.

    Returns:
        Lista de objetos Path apuntando a cada PDF.

    Raises:
        FileNotFoundError: si la carpeta no existe.
        ValueError: si no se encuentra ningún PDF dentro de la carpeta.
    """

    folder = Path(input_dir)

    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"La carpeta '{input_dir}' no existe.")

    pdf_files = sorted(folder.glob("*.pdf"))

    if not pdf_files:
        raise ValueError(f"No se encontraron archivos PDF en '{input_dir}'.")

    return pdf_files


def merge_pdfs(input_dir: str, output_path: str) -> Path:
    """
    Fusiona todos los PDFs encontrados en input_dir en un único archivo.

    Args:
        input_dir: carpeta donde están los PDFs a fusionar.
        output_path: ruta completa (incluyendo nombre de archivo) donde
                     se guardará el PDF resultante.

    Returns:
        Path del archivo PDF fusionado generado.
    """
    
    pdf_files = get_pdf_files(input_dir)
    writer = PdfWriter()

    for pdf_file in tqdm(pdf_files, desc="Fusionando", unit="pdf"):
        tqdm.write(f"Agregando: {pdf_file.name}")
        writer.append(str(pdf_file))

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, "wb") as f:
        writer.write(f)

    writer.close()

    print(f"\nPDF fusionado guardado en: {output}")
    return output


if __name__ == "__main__":
    # Prueba manual rápida del módulo
    merge_pdfs(input_dir="input_pdfs", output_path="output/merged.pdf")