"""Utilidad compartida para convertir la respuesta de la IA en un objeto validado.

Antes, analyzer.py y cover_letter/cv_adapter.py repetían el mismo bloque de
limpieza de backticks y llamaban a json.loads() sin protección: si el modelo
devolvía algo que no fuera JSON perfecto, el programa reventaba con un error
crudo y se perdía toda la corrida. Esto lo centraliza y falla de forma clara.
"""

import json
import re
from typing import Type, TypeVar
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class RespuestaIAInvalida(Exception):
    """La IA no devolvió un JSON válido o no cumplió el esquema esperado."""


class FaltaApiKey(RuntimeError):
    """No hay ANTHROPIC_API_KEY configurada."""

    def __init__(self):
        super().__init__(
            "Falta ANTHROPIC_API_KEY.\n"
            "  1. Copia el ejemplo:  cp .env.example .env\n"
            "  2. Abre .env y pon tu clave de https://console.anthropic.com"
        )


def crear_cliente():
    """Crea el cliente de Anthropic, avisando claro si falta la clave.

    Antes cada módulo lo creaba al importarse: quien clonara el repo sin
    configurar el .env se encontraba con un error del SDK en vez de saber qué
    le faltaba. Se crea al usarlo, no al importar.
    """
    from anthropic import Anthropic  # import perezoso: importar el módulo no debe costar
    from config import ANTHROPIC_API_KEY

    if not ANTHROPIC_API_KEY:
        raise FaltaApiKey()
    return Anthropic(api_key=ANTHROPIC_API_KEY)


def texto_de_respuesta(response) -> str:
    """Extrae el texto de una respuesta de la API sin asumir su forma.

    `response.content[0].text` revienta si la respuesta viene sin bloques
    (IndexError) o si el primero no es de texto (AttributeError). Aquí se
    recorren todos y se juntan los que sí traen texto.
    """
    bloques = getattr(response, "content", None) or []
    partes = [
        b.text for b in bloques
        if getattr(b, "type", None) == "text" and getattr(b, "text", None)
    ]
    if not partes:   # por si un modelo no etiqueta el tipo
        partes = [b.text for b in bloques if getattr(b, "text", None)]
    if not partes:
        raise RespuestaIAInvalida("La API devolvió una respuesta sin texto.")
    return "\n".join(partes)


# Un bloque ```lenguaje ... ``` en cualquier parte del texto. La etiqueta del
# lenguaje es opcional y no distingue mayúsculas (```json, ```JSON, ``` a secas).
_BLOQUE_CERCADO = re.compile(r"```[ \t]*[A-Za-z0-9_+-]*[ \t]*\r?\n?(.*?)```", re.DOTALL)
_APERTURA_SUELTA = re.compile(r"^```[ \t]*[A-Za-z0-9_+-]*[ \t]*\r?\n?")


def _limpiar_cercos(texto: str) -> str:
    """Extrae el JSON de la respuesta del modelo.

    Aguanta las tres formas en que un modelo se sale del formato pedido:
      1. lo envuelve en ```json ... ``` (con la etiqueta en cualquier caja)
      2. escribe un preámbulo antes del bloque ("Aquí tienes el análisis:")
      3. abre el cerco y no lo cierra
    Si no hay cerco, devuelve el texto tal cual para que json.loads lo intente.
    """
    t = texto.strip()

    bloque = _BLOQUE_CERCADO.search(t)
    if bloque:
        return bloque.group(1).strip()

    if t.startswith("```"):
        return _APERTURA_SUELTA.sub("", t).strip("` \n")

    # Sin cerco pero con texto alrededor: nos quedamos con el objeto JSON.
    if not t.startswith("{"):
        inicio, fin = t.find("{"), t.rfind("}")
        if inicio != -1 and fin > inicio:
            return t[inicio:fin + 1]

    return t


def parsear_modelo(raw: str, modelo: Type[T]) -> T:
    """Convierte el texto crudo de la IA en una instancia validada de `modelo`.

    Lanza RespuestaIAInvalida (no un crash) si el texto no es JSON o si le
    faltan campos del esquema. Así el llamador puede saltarse esa oferta y
    seguir con la siguiente en vez de perder toda la corrida.
    """
    limpio = _limpiar_cercos(raw)
    try:
        data = json.loads(limpio)
    except json.JSONDecodeError as e:
        muestra = limpio[:200].replace("\n", " ")
        raise RespuestaIAInvalida(
            f"La IA no devolvió JSON válido ({e}). Empieza con: {muestra!r}"
        ) from e
    try:
        return modelo(**data)
    except (ValidationError, TypeError) as e:
        raise RespuestaIAInvalida(
            f"El JSON de la IA no cumple el esquema {modelo.__name__}: {e}"
        ) from e
