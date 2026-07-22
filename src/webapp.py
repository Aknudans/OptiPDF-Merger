"""
webapp.py

Interfaz gráfica simple en el navegador para OptiPDF Merger, para quienes
no quieren usar la línea de comandos. Levanta un servidor Flask local y
abre el navegador predeterminado del usuario. Ofrece dos flujos:

  - Fusión (`/fusion`):         el usuario elige varios PDFs desde un
                                 selector de archivos; se fusionan,
                                 optimizan (qpdf) y comprimen (pipeline
                                 completo, igual que `src.main`).
  - Compresión (`/compresion`): el usuario elige un único PDF ya
                                 existente; se optimiza y comprime, sin
                                 pasar por la fusión.

En ambos casos, tras procesar el PDF se muestra una página de resultado
con dos partes lado a lado: un botón de descarga del PDF final (el
usuario decide dónde guardarlo, según la configuración de su propio
navegador) y un panel con el registro de consola del proceso (las mismas
fases/mensajes que se ven al correr `src.main` por línea de comandos),
para poder confirmar que el resultado es el esperado antes de descargarlo.
Mientras el proceso corre, ese mismo registro también se va imprimiendo
en tiempo real en la ventana de cmd donde se ejecutó `run_gui.bat`, para
que se pueda ver que sigue avanzando (y no que quedó colgado) en procesos
largos con varios PDFs.
"""

import base64
import contextlib
import html
import io
import sys
import tempfile
import threading
import webbrowser
from pathlib import Path

from flask import Flask, request
from werkzeug.utils import secure_filename

from src.merger import merge_pdfs
from src.optimizer import deduplicate_if_available
from src.compressor import compress_pdf, GhostScriptNotFoundError
from src.config import DEFAULT_MAX_SIZE_MB

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1 GB: margen amplio para PDFs pesados


class _TeeWriter:
    """
    Escribe cada mensaje tanto en un buffer de captura (para el panel de
    registro de la página de resultado) como en el stream original de la
    consola (stdout/stderr reales del proceso), para que el avance también
    se vea en vivo en la ventana de cmd donde corre `run_gui.bat`.
    """

    def __init__(self, buffer: io.StringIO, original) -> None:
        self._buffer = buffer
        self._original = original

    def write(self, s: str) -> int:
        self._buffer.write(s)
        self._original.write(s)
        self._original.flush()
        return len(s)

    def flush(self) -> None:
        self._original.flush()


def _clean_console_log(raw: str) -> str:
    """
    Convierte una captura cruda de stdout/stderr (que puede incluir barras
    de progreso de tqdm usando retornos de carro '\\r') en texto legible,
    simulando lo que se vería en una terminal real: cada '\\r' reinicia la
    línea actual en vez de generar una línea nueva.
    """
    lines = []
    current = ""
    for ch in raw:
        if ch == "\r":
            current = ""
        elif ch == "\n":
            lines.append(current)
            current = ""
        else:
            current += ch
    if current:
        lines.append(current)
    return "\n".join(line for line in lines if line.strip())


def _layout(title: str, body: str, wide: bool = False) -> str:
    max_width = "900px" if wide else "480px"
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - OptiPDF Merger</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #f4f5f7;
    color: #1a1a1a;
  }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #1a1a1a; color: #f0f0f0; }}
  }}
  .card {{
    background: #ffffff;
    border-radius: 16px;
    box-shadow: 0 2px 16px rgba(0, 0, 0, 0.1);
    padding: 2.5rem;
    max-width: {max_width};
    width: 90%;
    text-align: center;
  }}
  @media (prefers-color-scheme: dark) {{
    .card {{ background: #262626; box-shadow: 0 2px 16px rgba(0, 0, 0, 0.4); }}
  }}
  h1 {{ font-size: 1.4rem; margin-bottom: 0.25rem; }}
  p.subtitle {{ opacity: 0.7; margin-top: 0; margin-bottom: 2rem; font-size: 0.95rem; }}
  .choices {{ display: flex; flex-direction: column; gap: 1rem; }}
  .choice-btn {{
    display: block;
    padding: 1.1rem;
    border-radius: 10px;
    border: 1px solid rgba(0, 0, 0, 0.1);
    text-decoration: none;
    color: inherit;
    font-weight: 600;
    font-size: 1.05rem;
  }}
  .choice-btn small {{ display: block; font-weight: 400; opacity: 0.65; margin-top: 0.3rem; }}
  .btn-fusion {{ background: #e8f0fe; }}
  .btn-compresion {{ background: #fef3e8; }}
  @media (prefers-color-scheme: dark) {{
    .btn-fusion {{ background: #1e3a5f; }}
    .btn-compresion {{ background: #5f4620; }}
  }}
  form {{ display: flex; flex-direction: column; gap: 1rem; align-items: stretch; }}
  input[type="file"] {{
    padding: 0.8rem;
    border: 1px dashed rgba(0, 0, 0, 0.25);
    border-radius: 10px;
    background: transparent;
    color: inherit;
  }}
  button {{
    padding: 0.9rem;
    border: none;
    border-radius: 10px;
    background: #1a73e8;
    color: white;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
  }}
  button:disabled {{ opacity: 0.6; cursor: default; }}
  .back {{ display: inline-block; margin-top: 1.25rem; font-size: 0.9rem; opacity: 0.7; color: inherit; }}
  .error {{
    background: #fdeaea;
    color: #8a1f1f;
    padding: 0.9rem;
    border-radius: 10px;
    font-size: 0.9rem;
    text-align: left;
  }}
  @media (prefers-color-scheme: dark) {{
    .error {{ background: #4a1f1f; color: #ffb3b3; }}
  }}
  #status {{ display: none; opacity: 0.7; font-size: 0.9rem; }}
  .result-layout {{
    display: flex;
    gap: 1.5rem;
    flex-wrap: wrap;
    text-align: left;
    align-items: stretch;
  }}
  .result-main {{
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    justify-content: center;
    min-width: 220px;
  }}
  .console {{
    flex: 1;
    min-width: 260px;
    background: #11141a;
    color: #d7ffd9;
    border-radius: 10px;
    padding: 1rem;
    max-height: 380px;
    overflow: auto;
    text-align: left;
  }}
  .console h2 {{
    margin: 0 0 0.5rem 0;
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #9fb5a3;
  }}
  .console pre {{
    margin: 0;
    white-space: pre-wrap;
    word-break: break-word;
    font-family: "Cascadia Code", Consolas, "Courier New", monospace;
    font-size: 0.8rem;
    line-height: 1.4;
  }}
</style>
</head>
<body>
  <div class="card">
    {body}
  </div>
</body>
</html>"""


def _home_body() -> str:
    return """
    <h1>OptiPDF Merger</h1>
    <p class="subtitle">Elija una opción a realizar con sus archivos PDFs</p>
    <div class="choices">
      <a class="choice-btn btn-fusion" href="/fusion">
        Fusionar PDFs
        <small>Combine varios PDFs en uno solo, optimizado y comprimido</small>
      </a>
      <a class="choice-btn btn-compresion" href="/compresion">
        Comprimir PDF
        <small>Reduzca el tamaño de un PDF que ya posea</small>
      </a>
    </div>
    """


def _fusion_form_body(error: str | None = None) -> str:
    error_html = f'<div class="error">{error}</div>' if error else ""
    return f"""
    <h1>Fusionar PDFs</h1>
    <p class="subtitle">
      Elija 2 o más archivos PDF. Se fusionarán en orden alfabético por
      nombre de archivo, se intentará optimizar y se comprimir a un máximo de
      {DEFAULT_MAX_SIZE_MB}MB.
    </p>
    {error_html}
    <form action="/fusion" method="post" enctype="multipart/form-data"
          onsubmit="document.getElementById('status').style.display='block'; document.getElementById('submit-btn').disabled=true;">
      <input type="file" name="pdfs" accept="application/pdf" multiple required>
      <button id="submit-btn" type="submit">Fusionar y comprimir</button>
      <span id="status">Procesando, esto puede tardar un momento...</span>
    </form>
    <a class="back" href="/">&larr; Volver</a>
    """


def _compresion_form_body(error: str | None = None) -> str:
    error_html = f'<div class="error">{error}</div>' if error else ""
    return f"""
    <h1>Comprimir PDF</h1>
    <p class="subtitle">
      Elija un PDF. Se intentará optimizar y comprimir a un máximo de
      {DEFAULT_MAX_SIZE_MB}MB, sin bajar la calidad de imagen por debajo
      de lo legible.
    </p>
    {error_html}
    <form action="/compresion" method="post" enctype="multipart/form-data"
          onsubmit="document.getElementById('status').style.display='block'; document.getElementById('submit-btn').disabled=true;">
      <input type="file" name="pdf" accept="application/pdf" required>
      <button id="submit-btn" type="submit">Comprimir</button>
      <span id="status">Procesando, esto puede tardar un momento...</span>
    </form>
    <a class="back" href="/">&larr; Volver</a>
    """


def _result_body(output_name: str, download_href: str, log_text: str) -> str:
    log_html = html.escape(log_text) if log_text else "(el proceso no generó mensajes)"
    return f"""
    <h1>Proceso terminado</h1>
    <p class="subtitle">El proceso terminó, si ocurre algun inconveniente en el archivo favor de enviar registro de procesos</p>
    <div class="result-layout">
      <div class="result-main">
        <a class="choice-btn btn-fusion" href="{download_href}" download="{output_name}">
          Descargar {output_name}
        </a>
        <a class="back" href="/">&larr; Volver al inicio</a>
      </div>
      <div class="console">
        <h2>Registro del proceso</h2>
        <pre>{log_html}</pre>
      </div>
    </div>
    """


@app.get("/")
def home():
    return _layout("Inicio", _home_body())


@app.get("/fusion")
def fusion_form():
    return _layout("Fusionar", _fusion_form_body())


@app.post("/fusion")
def fusion_submit():
    uploaded = [f for f in request.files.getlist("pdfs") if f.filename]
    if len(uploaded) < 2:
        return _layout("Fusionar", _fusion_form_body("Elija al menos 2 documentos .pdf para fusionarlos"))

    log_buffer = io.StringIO()
    try:
        with tempfile.TemporaryDirectory(prefix="optipdf_") as workdir:
            workdir = Path(workdir)
            input_dir = workdir / "input"
            input_dir.mkdir()

            for uploaded_file in uploaded:
                filename = secure_filename(uploaded_file.filename)
                if filename.lower().endswith(".pdf"):
                    uploaded_file.save(input_dir / filename)

            with contextlib.redirect_stdout(_TeeWriter(log_buffer, sys.stdout)), \
                 contextlib.redirect_stderr(_TeeWriter(log_buffer, sys.stderr)):
                merged_path = merge_pdfs(str(input_dir), str(workdir / "merged.pdf"))
                deduped_path = deduplicate_if_available(str(merged_path), str(workdir / "deduped.pdf"))
                final_path = compress_pdf(
                    str(deduped_path), str(workdir / "final.pdf"), max_size_mb=DEFAULT_MAX_SIZE_MB
                )
            data = final_path.read_bytes()
    except (FileNotFoundError, ValueError) as exc:
        return _layout("Fusionar", _fusion_form_body(str(exc)))
    except GhostScriptNotFoundError as exc:
        return _layout("Fusionar", _fusion_form_body(str(exc)))

    log_text = _clean_console_log(log_buffer.getvalue())
    download_href = f"data:application/pdf;base64,{base64.b64encode(data).decode('ascii')}"
    return _layout(
        "Resultado",
        _result_body("fusionado_comprimido.pdf", download_href, log_text),
        wide=True,
    )


@app.get("/compresion")
def compresion_form():
    return _layout("Comprimir", _compresion_form_body())


@app.post("/compresion")
def compresion_submit():
    uploaded_file = request.files.get("pdf")
    if not uploaded_file or not uploaded_file.filename:
        return _layout("Comprimir", _compresion_form_body("Elija un documento .pdf para comprimirlo"))

    filename = secure_filename(uploaded_file.filename)
    if not filename.lower().endswith(".pdf"):
        return _layout("Comprimir", _compresion_form_body("Archivo no admitido, debe ser un .pdf"))

    log_buffer = io.StringIO()
    try:
        with tempfile.TemporaryDirectory(prefix="optipdf_") as workdir:
            workdir = Path(workdir)
            input_path = workdir / filename
            uploaded_file.save(input_path)

            with contextlib.redirect_stdout(_TeeWriter(log_buffer, sys.stdout)), \
                 contextlib.redirect_stderr(_TeeWriter(log_buffer, sys.stderr)):
                deduped_path = deduplicate_if_available(str(input_path), str(workdir / "deduped.pdf"))
                final_path = compress_pdf(
                    str(deduped_path), str(workdir / "final.pdf"), max_size_mb=DEFAULT_MAX_SIZE_MB
                )
            data = final_path.read_bytes()
    except GhostScriptNotFoundError as exc:
        return _layout("Comprimir", _compresion_form_body(str(exc)))

    output_name = f"{Path(filename).stem}_comprimido.pdf"
    log_text = _clean_console_log(log_buffer.getvalue())
    download_href = f"data:application/pdf;base64,{base64.b64encode(data).decode('ascii')}"
    return _layout(
        "Resultado",
        _result_body(output_name, download_href, log_text),
        wide=True,
    )


def run(host: str = "127.0.0.1", port: int = 5000, open_browser: bool = True) -> None:
    """Levanta el servidor local y abre el navegador predeterminado del usuario."""
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run()
