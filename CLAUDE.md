# Job Application Assistant

Herramienta CLI en Python que usa la API de Anthropic para preparar y gestionar aplicaciones de trabajo.

## Qué hace
- Analiza texto de ofertas de trabajo y calcula match con el CV base
- Adapta el CV (JSON → DOCX) para maximizar keywords ATS por oferta
- Genera cartas de presentación personalizadas
- Registra y rastrea todas las aplicaciones en SQLite

## Estructura
```
job-assistant/
├── main.py              # CLI (Typer) – entry point
├── config.py            # Rutas y variables de entorno
├── src/
│   ├── models.py        # Pydantic: CV, JobAnalysis
│   ├── analyzer.py      # Claude API → analiza oferta
│   ├── cv_adapter.py    # Claude API → adapta CV
│   ├── cover_letter.py  # Claude API → genera carta
│   ├── tracker.py       # SQLite CRUD
│   └── cv_generator.py  # python-docx → genera .docx
├── templates/
│   └── cv_base.json     # TU CV base (editarlo a mano)
└── output/              # CVs, cartas y análisis generados
```

## Setup inicial
```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Crear .env con API key
cp .env.example .env
# Editar .env y poner: ANTHROPIC_API_KEY=sk-ant-...

# 3. Crear plantilla de CV y BD
python main.py setup

# 4. IMPORTANTE: editar templates/cv_base.json con tu información real
```

## Flujo por cada oferta
```bash
# Paso 1 – Analizar la oferta (pegar texto o usar archivo)
python main.py analizar "texto de la oferta..."
python main.py analizar --file oferta.txt

# Paso 2 – Adaptar CV para esa oferta (genera .docx en output/)
python main.py adaptar 1

# Paso 3 – Generar carta de presentación
python main.py carta 1

# Paso 4 – Aplicar manualmente con el .docx generado

# Paso 5 – Registrar resultado
python main.py actualizar 1 entrevista_rh
python main.py actualizar 1 oferta --notas "Salario: $X"
```

## Todos los comandos
```bash
python main.py setup                          # Configuración inicial
python main.py analizar [texto] [--file f]    # Analizar oferta
python main.py adaptar <ID> [--sin-docx]      # Adaptar CV
python main.py carta <ID>                     # Generar carta
python main.py listar [--estado aplicado]     # Ver tracker
python main.py stats                          # Estadísticas
python main.py actualizar <ID> <estado>       # Actualizar estado
```

## Estados válidos
`aplicado` → `vista` → `entrevista_rh` → `entrevista_tecnica` → `oferta` / `rechazado` / `retirado`

## Posibles mejoras
- Exportar tracker a Excel/CSV
- Integración con Computrabajo scraper (Crawlee)
- Template de CV en inglés para México/España
- Dashboard web con FastAPI
- Reminder automático de follow-up por fecha
