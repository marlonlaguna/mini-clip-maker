# Motor de sprites de Mini Clip Maker

La guía completa y los ejemplos están en `../ACTUALIZACION_SPRITES.md` (desde la raíz del proyecto).

Se conserva `from stick_engine import generar_stick_scenes` y su firma anterior,
con `audio_timeline` opcional para tiempos exactos. `main.py` adapta el guion
con OpenAI antes de generar voz y después entrega escenas validadas al motor.
Los personajes usan únicamente tiras PNG horizontales de celdas de 200×200;
el cast se declara en el guion. GPU y CPU comparten las reglas de orientación
y desplazamiento.
