# Motor de voz de Mini Clip Maker: Qwen3-TTS

Mini Clip Maker genera el audio con Qwen3-TTS. Puedes elegir la voz en el
archivo de guion; si omites esta sección, se usa `Ryan`:

```text
[VOZ_QWEN]
Ryan
```

Voces disponibles en `Qwen3-TTS-12Hz-0.6B-CustomVoice`:
`Ryan`, `Aiden`, `Uncle_Fu`, `Dylan`, `Eric`, `Vivian`, `Serena`,
`Ono_Anna` y `Sohee`. Todas pueden generar español; ninguna tiene el español
como idioma nativo en este modelo.

El proyecto necesita conservar `.venv-qwen` en la raíz del repositorio, con
`qwen-tts` instalado y PyTorch CUDA. El generador carga Qwen en la RTX 2070
usando `float32`, necesario para evitar el error de muestreo observado en
GPU Turing. Si el entorno virtual está en otra ruta, define `QWEN_PYTHON` con
la ruta completa a su ejecutable de Python.

Por ejemplo, en PowerShell:

```powershell
$env:QWEN_PYTHON = "C:\ruta\a\mini-clip-maker\.venv-qwen\Scripts\python.exe"
```

`generar_audio.py` inicia el worker `generar_audio_qwen.py` en ese entorno.
El worker divide guiones largos en fragmentos y escribe el WAV en la ruta que
Mini Clip Maker usa para subtítulos y montaje.
