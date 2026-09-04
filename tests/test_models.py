"""Pruebas de src/models.py — los esquemas que validan lo que devuelve el modelo.

El README promete que "la salida del LLM se valida, no se asume". Estas pruebas
comprueban que eso sea cierto de verdad, y no solo a nivel de tipos: un
match_score de 150 tiene el tipo correcto y aun así es imposible.

Correr:  python -m pytest tests/test_models.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pydantic import ValidationError

from src.models import JobAnalysis


def analisis(**cambios):
    """Un JobAnalysis válido, con los campos que se quieran cambiar."""
    base = dict(
        title="Dev Python",
        company="ACME",
        required_skills=["Python"],
        preferred_skills=[],
        soft_skills=[],
        ats_keywords=[],
        experience_level="Mid",
        key_responsibilities=[],
        match_score=75,
        gaps=[],
        highlights=[],
    )
    base.update(cambios)
    return JobAnalysis(**base)


# ── match_score: entra en comparaciones y promedios, así que el rango importa ──

@pytest.mark.parametrize("score", [0, 1, 50, 99, 100])
def test_acepta_puntajes_dentro_del_rango(score):
    assert analisis(match_score=score).match_score == score


@pytest.mark.parametrize("score", [-1, -20, 101, 150, 99999])
def test_rechaza_puntajes_imposibles(score):
    """Regresión: antes pasaba cualquier entero y contaminaba las estadísticas."""
    with pytest.raises(ValidationError):
        analisis(match_score=score)


def test_el_cero_es_un_puntaje_valido():
    """Compatibilidad nula es un resultado real, no un error."""
    assert analisis(match_score=0).match_score == 0


def test_match_score_es_obligatorio():
    with pytest.raises(ValidationError):
        JobAnalysis(
            title="T", company="C", required_skills=[], preferred_skills=[],
            soft_skills=[], ats_keywords=[], experience_level="Mid",
            key_responsibilities=[], gaps=[], highlights=[],
        )


# ── experience_level: libre a propósito ───────────────────────────────────────

@pytest.mark.parametrize("nivel", ["Junior", "Mid", "Senior", "Mid-level", "Semi-Senior"])
def test_acepta_variantes_de_nivel(nivel):
    """Solo se muestra; restringirlo tumbaría análisis correctos por redacción."""
    assert analisis(experience_level=nivel).experience_level == nivel


# ── Estructura ────────────────────────────────────────────────────────────────

def test_faltan_campos_obligatorios():
    with pytest.raises(ValidationError):
        JobAnalysis(title="Solo el titulo")


def test_company_culture_es_opcional():
    assert analisis().company_culture is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
