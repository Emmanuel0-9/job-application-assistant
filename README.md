# Job Application Assistant

CLI que automatiza el ciclo completo de postulación a empleos: **encuentra ofertas,
las analiza contra tu CV con la API de Claude, adapta el CV a cada una, redacta la carta
de presentación y lleva el seguimiento en SQLite.**

> *A Python CLI that automates the full job-application pipeline: scrapes 11 job boards,
> analyses each posting against your CV using the Claude API, rewrites the CV to match,
> drafts the cover letter and tracks every application in SQLite. Interface in Spanish.*

## El problema

Postularse bien es caro en tiempo: hay que buscar en varios portales, leer cada oferta,
decidir si vale la pena, reescribir el CV con las palabras que busca el filtro ATS, redactar
una carta distinta cada vez, y no perder el hilo de en qué va cada postulación.

Este proyecto convierte ese ciclo en cuatro comandos.

## Flujo

```bash
python main.py buscar-usd --perfil ia     # 1. rastrea 8 plataformas, guarda en cola
python main.py cola                       # 2. revisa lo encontrado
python main.py procesar-cola 4            # 3. analiza + adapta CV + escribe carta
python main.py actualizar 4 entrevista_rh # 4. registra el avance
```

El paso 3 hace, en una sola corrida:

| | |
|---|---|
| **Analiza** | Match en %, habilidades exigidas, keywords ATS, qué destacar y dónde están las brechas |
| **Adapta** | Reescribe el CV priorizando lo que esa oferta pide |
| **Genera** | `.docx` limpio, sin tablas ni columnas, legible por filtros ATS |
| **Redacta** | Carta de presentación específica para esa vacante |
| **Registra** | Todo queda en SQLite con su estado |

## Arquitectura

```
main.py              CLI con Typer · 12 comandos
config.py            Rutas y variables de entorno
src/
  models.py          Esquemas Pydantic — la salida del LLM se valida, no se asume
  analyzer.py        Claude API → análisis estructurado de la oferta
  cv_adapter.py      Claude API → CV reescrito para el cargo
  cover_letter.py    Claude API → carta personalizada
  cv_generator.py    python-docx → documento compatible con ATS
  tracker.py         SQLite: postulaciones + cola, con deduplicación
  llm_parse.py       Convierte la respuesta del modelo en un objeto validado
  scraper.py         11 scrapers con reintentos, pausas y selectores de respaldo
templates/           CV base en JSON
tests/               116 pruebas con pytest (scrapers, parser del LLM, esquemas, BD, seguridad)
```

**Decisiones de diseño**

- **La salida del LLM se valida con Pydantic.** Un modelo que devuelve texto libre rompe
  el pipeline; con esquema, falla temprano y de forma visible.
- **Los scrapers degradan sin tumbar la corrida.** Reintentos, varios selectores CSS por
  campo y pausas aleatorias. Si un portal cambia su HTML, los otros siguen.
- **El `.docx` evita tablas y columnas** a propósito: los filtros ATS las leen mal.
- **Deduplicación por URL** en la cola, para no reprocesar la misma oferta.

## Plataformas

| Preset | Portales |
|---|---|
| USD / global | Remotive · RemoteOK · WeWorkRemotely · Himalayas |
| LATAM remoto | Torre · Get on Board |
| Colombia | Indeed CO · Computrabajo CO |
| México | OCC · Computrabajo · Indeed · Bumeran |

Perfiles de búsqueda: `requerimientos`, `ia` o `ambos`.

## Instalación

```bash
pip install -r requirements.txt
cp .env.example .env          # y pon tu ANTHROPIC_API_KEY
python main.py setup          # crea templates/cv_base.json y la base de datos
```

Después hay que editar `templates/cv_base.json` con los datos reales.
Ese archivo está en `.gitignore` porque contiene información personal.

## Pruebas

```bash
pip install pytest
python -m pytest tests/ -v
```

116 pruebas sobre las partes que más duelen si fallan. Ninguna toca la red:
se le pasa a cada scraper lo que el portal habría devuelto.

| Archivo | Qué cubre |
|---|---|
| `test_scraper.py` | Portales que devuelven un error donde iba una lista, campos en `null`, salarios como "negociable", y que el respaldo de selectores CSS respalde de verdad |
| `test_llm_parse.py` | Las formas en que un modelo se sale del formato: cercos ```` ```json ````, etiquetas en mayúsculas, preámbulos antes del bloque, cercos sin cerrar, JSON que no cumple el esquema |
| `test_models.py` | Que la validación sea real y no solo de tipos: un `match_score` de 150 tiene el tipo correcto y es imposible |
| `test_tracker.py` | SQLite: promedios, estados válidos, cola, y que un duplicado no se confunda con un error real |
| `test_seguridad_nombres.py` | Adversariales: el nombre del `.docx` viene de datos externos, así que se intenta escapar de `output/` con `../`, rutas absolutas y nombres de dispositivo de Windows |

Las pruebas de seguridad son adversariales a propósito: en vez de comprobar que el
camino feliz funciona, intentan romperlo.

## Stack

Python 3.13 · Typer · Rich · Pydantic · Anthropic SDK · BeautifulSoup · python-docx · SQLite
Pruebas con pytest

## Estado

Funcional. Probado sobre Remotive y RemoteOK: encuentra ofertas reales y las procesa
de punta a punta.

Pendiente: exportar el tracker a CSV, recordatorio de seguimiento por fecha, y una
plantilla de CV en inglés.
