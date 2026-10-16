import json
import os
import urllib.error
import urllib.request


# ============================================================
# OPENAI
# ============================================================

OPENAI_BASE_URL = "https://api.openai.com/v1"

# Modelo principal para Mini Clip Maker
OPENAI_MODEL = "gpt-6-luna"

# Alias conservado para no tener que modificar storyboard.py.
# Aunque se llame OLLAMA_MODEL, ahora contiene el modelo de OpenAI.
OLLAMA_MODEL = OPENAI_MODEL

OPENAI_TIMEOUT = 600


# ============================================================
# API KEY
# ============================================================

def _obtener_api_key():
    api_key = os.environ.get(
        "OPENAI_API_KEY",
        "",
    ).strip()

    if not api_key:
        raise RuntimeError(
            "[OPENAI] No se encontró OPENAI_API_KEY. "
            "Configúrala como variable de entorno de Windows."
        )

    return api_key


# ============================================================
# HTTP
# ============================================================

def _post_json(endpoint, payload):
    url = (
        OPENAI_BASE_URL.rstrip("/")
        + endpoint
    )

    api_key = _obtener_api_key()

    body = json.dumps(
        payload,
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=OPENAI_TIMEOUT,
        ) as response:

            raw = response.read().decode(
                "utf-8",
                errors="replace",
            )

    except urllib.error.HTTPError as exc:
        try:
            detalle = exc.read().decode(
                "utf-8",
                errors="replace",
            )
        except Exception:
            detalle = str(exc)

        raise RuntimeError(
            f"[OPENAI] HTTP {exc.code}: {detalle}"
        ) from exc

    except urllib.error.URLError as exc:
        raise RuntimeError(
            "[OPENAI] No se pudo conectar con "
            f"{OPENAI_BASE_URL}. "
            f"Detalle: {exc}"
        ) from exc

    try:
        return json.loads(raw)

    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "[OPENAI] La API devolvió una "
            "respuesta HTTP que no es JSON válido."
        ) from exc


# ============================================================
# EXTRAER TEXTO DE RESPONSES API
# ============================================================

def _extraer_output_text(response):
    # Algunas respuestas incluyen output_text directamente.
    output_text = response.get(
        "output_text"
    )

    if isinstance(
        output_text,
        str,
    ) and output_text.strip():

        return output_text.strip()

    # Forma estándar Responses API.
    output = response.get(
        "output",
        [],
    )

    if not isinstance(
        output,
        list,
    ):
        output = []

    textos = []

    for item in output:
        if not isinstance(
            item,
            dict,
        ):
            continue

        if item.get("type") != "message":
            continue

        content = item.get(
            "content",
            [],
        )

        if not isinstance(
            content,
            list,
        ):
            continue

        for bloque in content:
            if not isinstance(
                bloque,
                dict,
            ):
                continue

            tipo = bloque.get(
                "type"
            )

            if tipo == "refusal":
                razon = bloque.get(
                    "refusal",
                    "La solicitud fue rechazada.",
                )

                raise RuntimeError(
                    "[OPENAI] El modelo rechazó "
                    f"la solicitud: {razon}"
                )

            if tipo == "output_text":
                texto = bloque.get(
                    "text",
                    "",
                )

                if texto:
                    textos.append(
                        str(texto)
                    )

    resultado = "\n".join(
        textos
    ).strip()

    if not resultado:
        status = response.get(
            "status"
        )

        incomplete_details = response.get(
            "incomplete_details"
        )

        raise RuntimeError(
            "[OPENAI] La respuesta no contiene texto. "
            f"status={status}, "
            f"incomplete_details={incomplete_details}"
        )

    return resultado


# ============================================================
# CHAT COMPATIBLE CON EL STORYBOARD ACTUAL
# ============================================================

def ollama_chat(
    messages,
    model=None,
    json_mode=False,
    temperature=0.2,
    num_predict=4096,
):
    """
    Adaptador compatible con el antiguo ollama_chat().

    storyboard.py puede seguir llamando:

        ollama_chat(...)

    pero internamente se usa OpenAI Responses API.
    """

    modelo = (
        str(model).strip()
        if model
        else OPENAI_MODEL
    )

    if not isinstance(
        messages,
        list,
    ):
        raise ValueError(
            "[OPENAI] messages debe ser una lista."
        )

    input_messages = []

    for message in messages:
        if not isinstance(
            message,
            dict,
        ):
            continue

        role = str(
            message.get(
                "role",
                "user",
            )
        ).strip()

        content = message.get(
            "content",
            "",
        )

        if not isinstance(
            content,
            str,
        ):
            content = str(
                content
            )

        input_messages.append({
            "role": role,
            "content": content,
        })

    if not input_messages:
        raise ValueError(
            "[OPENAI] No hay mensajes para enviar."
        )

    payload = {
        "model": modelo,

        "input": input_messages,

        # Bajo razonamiento es suficiente para storyboard
        # y mantiene bajo el costo.
        "reasoning": {
            "effort": "low"
        },

        "max_output_tokens": max(
            512,
            int(num_predict),
        ),
    }

    # JSON mode.
    #
    # OpenAI garantiza JSON sintácticamente válido con
    # text.format = json_object.
    if json_mode:
        payload["text"] = {
            "format": {
                "type": "json_object"
            },
            "verbosity": "low",
        }

    print(
        f"[OPENAI] Generando con {modelo}..."
    )

    response = _post_json(
        "/responses",
        payload,
    )

    status = response.get(
        "status"
    )

    if status == "failed":
        error = response.get(
            "error"
        )

        raise RuntimeError(
            f"[OPENAI] La generación falló: {error}"
        )

    if status == "incomplete":
        details = response.get(
            "incomplete_details",
            {},
        )

        reason = (
            details.get("reason")
            if isinstance(
                details,
                dict,
            )
            else details
        )

        raise RuntimeError(
            "[OPENAI] La respuesta quedó incompleta. "
            f"Razón: {reason}"
        )

    texto = _extraer_output_text(
        response
    )

    if json_mode:
        # Validamos antes de devolvérselo a storyboard.py.
        try:
            json.loads(
                texto
            )

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "[OPENAI] El modelo no devolvió "
                f"JSON válido: {exc}"
            ) from exc

    usage = response.get(
        "usage",
        {},
    )

    if isinstance(
        usage,
        dict,
    ):
        input_tokens = usage.get(
            "input_tokens",
            0,
        )

        output_tokens = usage.get(
            "output_tokens",
            0,
        )

        total_tokens = usage.get(
            "total_tokens",
            (
                int(input_tokens or 0)
                + int(output_tokens or 0)
            ),
        )

        print(
            "[OPENAI] Tokens: "
            f"entrada={input_tokens}, "
            f"salida={output_tokens}, "
            f"total={total_tokens}"
        )

    return texto


# ============================================================
# TEST DE CONEXIÓN
# ============================================================

def verificar_openai():
    """
    Hace una prueba real contra OpenAI.
    """

    respuesta = ollama_chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "Return valid JSON only."
                ),
            },
            {
                "role": "user",
                "content": (
                    'Return exactly this JSON '
                    'object: {"ok":true}'
                ),
            },
        ],
        model=OPENAI_MODEL,
        json_mode=True,
        temperature=0.0,
        num_predict=100,
    )

    data = json.loads(
        respuesta
    )

    return data


# ============================================================
# COMPATIBILIDAD CON CÓDIGO ANTERIOR
# ============================================================

def ollama_ping():
    """
    Se conserva únicamente por compatibilidad.

    Ya NO comprueba Ollama.
    Comprueba que exista OPENAI_API_KEY.
    """

    _obtener_api_key()

    return [
        OPENAI_MODEL
    ]


def verificar_modelo():
    """
    Compatibilidad con código anterior.
    """

    verificar_openai()

    return True


# ============================================================
# EJECUCIÓN DIRECTA
# ============================================================

if __name__ == "__main__":
    print(
        "[OPENAI] Mini Clip Maker"
    )

    print(
        "[OPENAI] Endpoint:",
        OPENAI_BASE_URL,
    )

    print(
        "[OPENAI] Modelo:",
        OPENAI_MODEL,
    )

    if os.environ.get(
        "OPENAI_API_KEY"
    ):
        print(
            "[OPENAI] API KEY: encontrada"
        )
    else:
        print(
            "[OPENAI] API KEY: NO encontrada"
        )

        raise SystemExit(1)

    try:
        resultado = (
            verificar_openai()
        )

        print(
            "[OPENAI] Conexión OK:"
        )

        print(
            json.dumps(
                resultado,
                ensure_ascii=False,
            )
        )

    except Exception as exc:
        print(
            "[OPENAI] ERROR:",
            exc,
        )

        raise