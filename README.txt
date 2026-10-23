MINI CLIP MAKER - VOCES POR PERSONAJE (COPIAR / PEGAR)

1. Realiza un respaldo o commit antes de reemplazar archivos.
2. Copia los 3 archivos .py de este ZIP en la RAIZ de mini-clip-maker. Reemplaza generar_audio_qwen.py. NO hace falta tocar main.py.
3. En stick_engine/assets/characters/humanoids/tomy_teenager coloca referencia.wav y referencia.txt (transcripcion literal).
4. En CMD desde la raiz ejecuta:
   .venv-qwen\Scripts\python.exe crear_voz_personaje.py humanoids/tomy_teenager
5. El script crea voice.pt y voice.json junto al personaje.
6. En tus guiones, define TOMY = humanoids/tomy_teenager en [CAST] y omite VOZ en sus dialogos.
   Un VOZ=Ryan o VOZ=Eric explicito tendra prioridad sobre voice.json.

La asignacion usa config.json y guion_adaptado.txt que main.py ya genera ANTES de invocar al worker.
Se conserva la sincronizacion original audio.timeline.json.

ATENCION: no se ha probado un render CUDA completo en tu PC; se verifico sintaxis y pruebas unitarias locales sin GPU.
El worker carga alternadamente 0.6B-Base y 0.6B-CustomVoice si cambia el tipo de voz.

IMPORTANTE: usa solo voces con autorizacion para clonarlas.
