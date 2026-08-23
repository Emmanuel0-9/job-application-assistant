from anthropic import Anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from src.llm_parse import parsear_modelo
from src.models import CV, JobAnalysis

client = Anthropic(api_key=ANTHROPIC_API_KEY)

_PROMPT = """Eres un experto en redacción de CVs y optimización ATS.
Adapta el CV JSON para maximizar el match con el cargo indicado.

CARGO: {title} en {company}
HABILIDADES REQUERIDAS: {required}
PALABRAS CLAVE ATS: {keywords}
A DESTACAR: {highlights}

CV BASE (JSON):
{cv_json}

Devuelve ÚNICAMENTE el CV adaptado en el MISMO formato JSON (sin backticks ni texto adicional).

REGLAS ESTRICTAS:
1. NO inventes experiencia, cargos ni habilidades que no estén en el CV base
2. SÍ puedes reordenar habilidades para que las más relevantes vayan primero
3. SÍ puedes reformular logros de experiencia usando keywords de la oferta (sin cambiar el hecho)
4. SÍ ajusta el resumen profesional específicamente para este cargo
5. SÍ reordena proyectos priorizando los más relevantes
6. Toda información debe ser verdadera; solo optimiza presentación y énfasis
"""


def adapt_cv(base_cv: CV, analysis: JobAnalysis) -> CV:
    """Devuelve una versión del CV optimizada para el cargo analizado."""
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": _PROMPT.format(
                title=analysis.title,
                company=analysis.company,
                required=", ".join(analysis.required_skills),
                keywords=", ".join(analysis.ats_keywords),
                highlights=", ".join(analysis.highlights),
                cv_json=base_cv.model_dump_json(indent=2),
            )
        }]
    )

    raw = response.content[0].text
    return parsear_modelo(raw, CV)
