import json
from anthropic import Anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from src.models import CV, JobAnalysis

client = Anthropic(api_key=ANTHROPIC_API_KEY)

_PROMPT = """Analiza la siguiente oferta de trabajo y extrae información estructurada.
Responde ÚNICAMENTE con JSON válido (sin backticks ni texto adicional), con esta estructura exacta:

{{
  "title": "Título del cargo",
  "company": "Nombre de la empresa",
  "required_skills": ["skill1", "skill2"],
  "preferred_skills": ["skill opcional 1"],
  "soft_skills": ["comunicación", "trabajo en equipo"],
  "ats_keywords": ["palabras clave para ATS"],
  "experience_level": "Junior",
  "key_responsibilities": ["responsabilidad 1"],
  "company_culture": "descripción breve",
  "match_score": 75,
  "gaps": ["tecnologías faltantes vs el CV"],
  "highlights": ["habilidades del CV a enfatizar"]
}}

Calcula match_score (0-100) comparando habilidades del CV con los requerimientos.
Lista en gaps las habilidades requeridas que NO aparecen en el CV.
Lista en highlights las habilidades del CV que más encajan con la oferta.

OFERTA DE TRABAJO:
{offer}

CV DEL CANDIDATO (resumen):
{cv_summary}
"""


def analyze_job_offer(offer_text: str, cv: CV) -> JobAnalysis:
    """Analiza una oferta y devuelve el análisis estructurado."""
    cv_summary = (
        f"Habilidades técnicas: {', '.join(cv.skills.technical)}\n"
        f"Herramientas: {', '.join(cv.skills.tools)}\n"
        f"Experiencia: {len(cv.experience)} posición(es)\n"
        f"Proyectos: {', '.join(p.name for p in cv.projects)}\n"
        f"Tecnologías en proyectos: {', '.join(t for p in cv.projects for t in p.technologies)}"
    )

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": _PROMPT.format(offer=offer_text, cv_summary=cv_summary)
        }]
    )

    raw = response.content[0].text.strip()
    # Limpia backticks si el modelo los incluye de todas formas
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip("` \n")

    data = json.loads(raw)
    return JobAnalysis(**data)
