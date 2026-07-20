# OptiPDF Merger
OptiPDF Merger es una utilidad diseñada para combinar de forma inteligente multiples archivos PDF. Orquesta un pipeline de varios pasos para vusionar, optimizar y comprimir agresivamente los archivos PDF en un unico documento de tamaño controlado, lo que lo hace ideal para preparar archivos que deben cumplir con límites estrictos de almacenamiento.

## Características
*   **Fusión secuencial:** Combina todos los PDF de un directorio en un único documento procesandolos en orden alfabético para garantizar resultados predecibles.
*   **Optimizacion Estructural:** Utiliza PyMuPDF para deduplicar objetos redundantes tales como fuentes e imagenes incrustadas a lo largo de los archivos fusionados, reduciendo así significativamente su tamaño antes de la compresión.
*   **Compresión multi-etapa:** EmpleaGhostScript para una compresion potente y por fases. intenta varios ajustes preestablecidos de calidad, desde alta calidad hasta alta comrpesion.
*   **Remuestreo progresivo:** si la comrpesion estándar no logra alcanzar el tamaño objetivo, la herramienta inicia una rutina avanzada que reduce progresivamente la resolución de las imagenes hasta lograr el tamaño de archivo deseado.
*   **Configurable:** Personaliza fácilmente los directorios de entrada/salida y el tamaño máximo del archivo mediante argumentos de linea de comandos.

## Cómo funciona
La herramienta opera en un pipeline de tres etapas:
1.  **Fusión (`merger.py`):** Todos los archivos `.pdf` en el directorio de entrada especificado (por defecto: `input_pdfs/`) se fusionan en un único archivo `merged.pdf` utilizando `pypdf`.
2.  **Optimización (`optimizer.py`):** El archivo `merged.pdf` se procesa para deduplicar objetos internos. Este paso utiliza `PyMuPDF` para buscar y eliminar datos redundantes, como fuentes idénticas o imágenes incrustadas en diferentes PDF de origen. El resultado se guarda como `deduped.pdf`. Este paso se omite automáticamente con una advertencia si PyMuPDF no está instalado.
3.  **Compresión (`compressor.py`):** La etapa final toma el archivo `deduped.pdf` y aplica una serie de estrategias de compresión utilizando GhostScript para asegurar que el archivo de salida esté por debajo del límite de tamaño especificado (por defecto: 20 MB). El proceso es el siguiente:
    *   **Fases estándar:** Primero intenta cuatro configuraciones estándar de GhostScript en orden: `/prepress`, `/printer`, `/ebook` y `/screen`. Si el tamaño del archivo entra dentro del límite después de cualquier fase, el proceso se detiene.
    *   **Fases extendidas:** Si el archivo sigue siendo demasiado grande, inicia un remuestreo progresivo de las imágenes, comenzando en 60 DPI y reduciéndose en pasos hasta un límite mínimo de 10 DPI.
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
