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
