from pathlib import Path

from ollama_client import OLLAMA_MODEL, ollama_chat


def generar_guion(
    prompt_video: str,
    duracion_segundos: int,
    ruta_salida: str | Path,
) -> Path:
    """Genera un guion en español con el modelo local de Ollama."""
    print("\n========================================")
    print("[GUION] INICIANDO GENERACION CON OLLAMA")
    print("========================================")

    if not prompt_video or not prompt_video.strip():
        raise ValueError("[GUION] ERROR: prompt_video está vacío.")
    if duracion_segundos <= 0:
        raise ValueError(
            "[GUION] ERROR: duracion_segundos debe ser mayor que 0."
        )

    ruta_salida = Path(ruta_salida)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    palabras_objetivo = int((duracion_segundos / 60) * 130)

    print(f"[GUION] Modelo local: {OLLAMA_MODEL}")
    print(f"[GUION] Duración objetivo: {duracion_segundos} segundos")
    print(f"[GUION] Longitud estimada: {palabras_objetivo} palabras")
    print(f"[GUION] Archivo de salida: {ruta_salida}")

    prompt = f"""Crea un guion narrativo para un video.

Tema solicitado:
{prompt_video}

Duración objetivo: {duracion_segundos} segundos.
Longitud aproximada: {palabras_objetivo} palabras.

Reglas obligatorias:
- Devuelve únicamente el texto que debe pronunciar el narrador.
- No escribas títulos, encabezados, "Narrador", Markdown, listas ni timestamps.
- No incluyas música, efectos de sonido ni instrucciones técnicas.
- Escribe en español natural, con tildes y la letra ñ.
- Usa frases claras para texto a voz y mantén una narrativa fluida.
- Comienza con un gancho, mantén el interés y termina con una conclusión breve y fuerte.
- Si trata sobre hechos reales, no inventes datos; distingue hechos de teorías,
  no presentes rumores como hechos ni acuses personas sin evidencia.
"""

    ultimo_error = None
    guion = ""
    for intento in range(1, 4):
        try:
            print(f"[GUION] Intento {intento}/3 con {OLLAMA_MODEL}...")
            guion = ollama_chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "Eres guionista de videos narrativos en español. "
                            "Cumple las instrucciones y devuelve solo la narración."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                num_predict=max(2048, palabras_objetivo * 3),
            )
            break
        except Exception as exc:
            ultimo_error = exc
            print(f"[GUION] Error: {exc}")

    if not guion:
        raise RuntimeError(
            f"No se pudo generar el guion con Ollama. Último error: {ultimo_error}"
        )

    ruta_salida.write_text(guion.strip(), encoding="utf-8")
    print(
        f"[GUION] Generado: {ruta_salida} "
        f"({len(guion.split())} palabras, {len(guion)} caracteres)"
    )
    return ruta_salida
