"""
config.py

Configuración centralizada del pipeline de OptiPDF Merger: valores por
defecto para la fusión, deduplicación y compresión de PDFs. Se mantienen
acá para que main.py y compressor.py compartan una única fuente de
verdad, en vez de tener el límite de tamaño duplicado en cada módulo.
"""

DEFAULT_INPUT_DIR = "input_pdfs"
DEFAULT_OUTPUT_DIR = "output"
DEFAULT_MAX_SIZE_MB = 20
