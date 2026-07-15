"""
main.py

Punto de entrada del programa: orquesta el pipeline completo de
OptiPDF Merger sobre una carpeta de PDFs.

Flujo:
  input_dir/ (carpeta con los PDFs a fusionar)
    -> merge_pdfs               -> output_dir/merged.pdf
    -> deduplicate_if_available -> output_dir/deduped.pdf
    -> compress_pdf             -> output_dir/final.pdf
"""

import argparse
from pathlib import Path

from src.merger import merge_pdfs
from src.optimizer import deduplicate_if_available
from src.compressor import compress_pdf
from src.config import DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR, DEFAULT_MAX_SIZE_MB


def run_pipeline(
    input_dir: str = DEFAULT_INPUT_DIR,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    max_size_mb: float = DEFAULT_MAX_SIZE_MB,
) -> Path:
    """
    Ejecuta el pipeline completo sobre los PDFs de input_dir: los fusiona,
    deduplica objetos repetidos (si PyMuPDF está disponible) y comprime
    el resultado hasta cumplir max_size_mb, dejando el archivo final en
    output_dir/final.pdf.

    Args:
        input_dir: carpeta con los PDFs a fusionar.
        output_dir: carpeta donde se guardarán los archivos intermedios
                    y el resultado final.
        max_size_mb: tamaño máximo permitido para el archivo final, en Megabytes.

    Returns:
        Path del archivo PDF final.
    """
    output_dir = Path(output_dir)

    merged_path = merge_pdfs(input_dir, str(output_dir / "merged.pdf"))
    deduped_path = deduplicate_if_available(str(merged_path), str(output_dir / "deduped.pdf"))
    final_path = compress_pdf(str(deduped_path), str(output_dir / "final.pdf"), max_size_mb=max_size_mb)

    print(f"\nProceso completo. Archivo final: {final_path}")
    return final_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fusiona, optimiza y comprime los PDFs de una carpeta en un único archivo."
    )
    parser.add_argument(
        "input_dir",
        nargs="?",
        default=DEFAULT_INPUT_DIR,
        help=f"Carpeta con los PDFs a fusionar (por defecto: '{DEFAULT_INPUT_DIR}').",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Carpeta donde se guardará el resultado (por defecto: '{DEFAULT_OUTPUT_DIR}').",
    )
    parser.add_argument(
        "--max-size-mb",
        type=float,
        default=DEFAULT_MAX_SIZE_MB,
        help=f"Tamaño máximo permitido del archivo final, en MB (por defecto: {DEFAULT_MAX_SIZE_MB}).",
    )
    return parser


def main() -> Path:
    args = _build_arg_parser().parse_args()
    return run_pipeline(args.input_dir, args.output_dir, args.max_size_mb)


if __name__ == "__main__":
    main()
