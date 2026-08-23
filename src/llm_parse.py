"""Utilidad compartida para convertir la respuesta de la IA en un objeto validado.

Antes, analyzer.py y cover_letter/cv_adapter.py repetían el mismo bloque de
limpieza de backticks y llamaban a json.loads() sin protección: si el modelo
devolvía algo que no fuera JSON perfecto, el programa reventaba con un error
crudo y se perdía toda la corrida. Esto lo centraliza y falla de forma clara.
"""

import json
from typing import Type, TypeVar
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class RespuestaIAInvalida(Exception):
    """La IA no devolvió un JSON válido o no cumplió el esquema esperado."""


def _limpiar_cercos(texto: str) -> str:
    """Quita los ```json ... ``` que el modelo a veces agrega de todas formas."""
    t = texto.strip()
    if t.startswith("```"):
        partes = t.split("```")
        if len(partes) >= 2:
            t = partes[1]
        if t.startswith("json"):
            t = t[4:]
        t = t.strip("` \n")
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
