# OptiPDF Merger
OptiPDF Merger es una utilidad diseñada para combinar de forma inteligente multiples archivos PDF. Orquesta un pipeline de varios pasos para vusionar, optimizar y comprimir agresivamente los archivos PDF en un unico documento de tamaño controlado, lo que lo hace ideal para preparar archivos que deben cumplir con límites estrictos de almacenamiento.

## Características
*   **Fusión secuencial:** Combina todos los PDF de un directorio en un único documento procesandolos en orden alfabético para garantizar resultados predecibles.
*   **Optimizacion Estructural:** Utiliza qpdf para recomprimir streams, generar object streams y eliminar recursos (fuentes, imagenes, etc.) que ya no son referenciados tras la fusión, reduciendo así el tamaño sin pérdida de calidad antes de la compresión.
*   **Compresión multi-etapa:** Emplea GhostScript para una compresion potente y por fases. Intenta varios ajustes preestablecidos de calidad, desde alta calidad hasta alta compresión, sin bajar nunca de un piso mínimo de 100 DPI para mantener el texto y las firmas legibles.
*   **Compresión adicional sin pérdida:** si la compresión con GhostScript no logra alcanzar el tamaño objetivo sin cruzar el piso de calidad de imagen, la herramienta aplica un paso final de compresión sin pérdida con qpdf antes de darse por vencida.
*   **Configurable:** Personaliza fácilmente los directorios de entrada/salida y el tamaño máximo del archivo mediante argumentos de linea de comandos.

## Cómo funciona
La herramienta opera en un pipeline de tres etapas:
1.  **Fusión (`merger.py`):** Todos los archivos `.pdf` en el directorio de entrada especificado (por defecto: `input_pdfs/`) se fusionan en un único archivo `merged.pdf` utilizando `pypdf`.
2.  **Optimización (`optimizer.py`):** El archivo `merged.pdf` se procesa con `qpdf` para recomprimir streams, generar object streams y eliminar recursos ya no referenciados tras la fusión, sin pérdida de calidad. El resultado se guarda como `deduped.pdf`. Este paso se omite automáticamente con una advertencia si qpdf no está instalado.
3.  **Compresión (`compressor.py`):** La etapa final toma el archivo `deduped.pdf` y aplica una serie de estrategias de compresión para asegurar que el archivo de salida esté por debajo del límite de tamaño especificado (por defecto: 20 MB), sin bajar nunca de un piso de calidad de imagen de **100 DPI**. El proceso es el siguiente:
    *   **Fases estándar de GhostScript:** Primero intenta cuatro configuraciones estándar en orden: `/prepress`, `/printer`, `/ebook` y `/screen` (esta última forzando el piso de 100 DPI en vez de los ~72 DPI por defecto del preset). Si el tamaño del archivo entra dentro del límite después de cualquier fase, el proceso se detiene.
    *   **Compresión adicional sin pérdida:** Si ninguna de las fases anteriores es suficiente, en vez de seguir bajando la resolución de imagen (lo que degradaría la legibilidad por debajo del piso de 100 DPI), se aplica un paso final de compresión sin pérdida con `qpdf` sobre el resultado. Este paso se omite con una advertencia si qpdf no está instalado.
    *   El archivo comprimido final se guarda como `final.pdf` en el directorio de salida.

## Requisitos
### 1. Dependencias del sistema
*   **GhostScript:** Esta es una dependencia obligatoria para el paso de compresión. Debes instalarlo y asegurarte de que esté disponible en el PATH de tu sistema.
    *   **Linux (Debian/Ubuntu):**
        ```sh
        sudo apt update && sudo apt install ghostscript
        ```
    *   **macOS (usando Homebrew):**
        ```sh
        brew install ghostscript
        ```
    *   **Windows:** Descarga el instalador correspondiente desde el [sitio web de GhostScript](https://ghostscript.com/releases/). Asegúrate de añadir el directorio `bin` (por ejemplo, `C:\Program Files\gs\gs10.03.1\bin`) a la variable de entorno PATH de tu sistema durante o después de la instalación.
*   **qpdf (recomendado, no obligatorio):** Se usa tanto para la optimización estructural previa como para un paso adicional de compresión sin pérdida si GhostScript no basta para cumplir el tamaño objetivo sin bajar del piso de calidad de imagen. Si no está instalado, ambos pasos se omiten automáticamente con una advertencia y el resto del pipeline sigue funcionando igual.
    *   **Linux (Debian/Ubuntu):** `sudo apt install qpdf`
    *   **macOS (usando Homebrew):** `brew install qpdf`
    *   **Windows:** Descarga el instalador desde el [sitio de releases de qpdf](https://github.com/qpdf/qpdf/releases) y añade su carpeta `bin` al PATH.

### 2. Dependencias de Python
*   Python 3.x
*   Los paquetes de Python requeridos se encuentran listados en `requeriments.txt`.

## Instalación
1.  Clona el repositorio:
    ```sh
    git clone [https://github.com/aknudan/optipdf-merger.git](https://github.com/aknudan/optipdf-merger.git)
    cd optipdf-merger
    ```
2.  Crea y activa un entorno virtual (recomendado):
    ```sh
    python -m venv .venv
    # En Windows
    .venv\Scripts\activate
    # En macOS/Linux
    source .venv/bin/activate
    ```
3.  Instala los paquetes de Python requeridos:
    ```sh
    pip install -r requeriments.txt
    ```
4.  Verifica que GhostScript esté instalado y accesible desde tu terminal:
    ```sh
    gs --version
    ```

## Uso
1.  Coloca todos los archivos PDF que deseas fusionar en el directorio `input_pdfs` (o en el directorio de tu elección).
2.  Ejecuta el script desde la raíz del directorio del proyecto.

### Uso básico
Para ejecutar el pipeline con la configuración por defecto (entrada desde `input_pdfs/`, salida en `output/`, tamaño máximo de 20 MB):
```sh
python -m src.main
```

### Argumentos personalizados
```sh
python -m src.main ruta/a/mis_pdfs --output-dir salida --max-size-mb 15
```

### Interfaz web (sin usar la línea de comandos)
Si preferís no usar la terminal, la herramienta también se puede usar desde el navegador:
```sh
python -m src.webapp
```
o, en Windows, ejecutando `run_gui.bat`. Esto levanta un servidor local y abre automáticamente tu navegador predeterminado en `http://127.0.0.1:5000`, donde vas a encontrar dos opciones:

*   **Fusionar PDFs:** elegí dos o más archivos desde el selector de archivos de tu navegador; se fusionan, optimizan y comprimen igual que con `python -m src.main`.
*   **Comprimir PDF:** elegí un único PDF que ya tengas; se optimiza y comprime, sin fusión previa.

En ambos casos, el resultado final se descarga automáticamente como cualquier otro archivo de tu navegador (por defecto, a tu carpeta de Descargas, o donde tengas configurado tu navegador para guardar descargas).
