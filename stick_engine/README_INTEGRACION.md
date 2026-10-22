# Motor de sprites de Mini Clip Maker

La guía básica está en `../ACTUALIZACION_SPRITES.md` y la extensión de tamaños variables y primeros planos en `../ANIMACIONES_HD.md`.

Se conserva `from stick_engine import generar_stick_scenes` y su firma anterior,
con `audio_timeline` opcional para tiempos exactos. `main.py` adapta el guion
con OpenAI antes de generar voz y después entrega escenas validadas al motor.
Los personajes usan tiras PNG horizontales, con 200×200 como formato básico;
también se detectan celdas cuadradas de 400, 512 y 1024 px y tamaños explícitos `@ANCHOxALTO`.
el cast se declara en el guion. GPU y CPU comparten las reglas de orientación
y desplazamiento.
