from anthropic import Anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from src.models import CV, JobAnalysis

client = Anthropic(api_key=ANTHROPIC_API_KEY)

_PROMPT = """Eres un experto en búsqueda de empleo. Escribe una carta de presentación profesional en español.

CARGO: {title}
EMPRESA: {company}
NOMBRE DEL CANDIDATO: {name}

ANÁLISIS DE LA OFERTA:
- Habilidades requeridas: {required}
- Responsabilidades clave: {responsibilities}
- Cultura de empresa: {culture}

PERFIL DEL CANDIDATO:
Habilidades: {skills}
Experiencia destacada:
{experience}
Educación: {education}

INSTRUCCIONES:
- Máximo 320 palabras
- Tono profesional pero humano, NO robótico ni genérico
- Primera línea: gancho poderoso que capture atención inmediata (no "Me complace...")
- Menciona 2-3 logros concretos del candidato con datos si los hay
- Conecta directamente las habilidades del candidato con las necesidades del cargo
- Cierre con call-to-action claro y confiado
- Usa párrafos directos, sin viñetas
- Muestra entusiasmo genuino, no frases de relleno
"""


def generate_cover_letter(cv: CV, analysis: JobAnalysis) -> str:
    """Genera una carta de presentación personalizada."""
    experience_lines = "\n".join(
        f"  - {e.title} en {e.company}: {'; '.join(e.achievements[:2])}"
        for e in cv.experience[:3]
    )
    education_str = f"{cv.education[0].degree} – {cv.education[0].institution}" if cv.education else ""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": _PROMPT.format(
                title=analysis.title,
                company=analysis.company,
                name=cv.personal.name,
                required=", ".join(analysis.required_skills[:6]),
                responsibilities="; ".join(analysis.key_responsibilities[:3]),
                culture=analysis.company_culture or "No especificada",
                skills=", ".join(cv.skills.technical[:8]),
                experience=experience_lines,
                education=education_str,
            )
        }]
    )

    return response.content[0].text.strip()
