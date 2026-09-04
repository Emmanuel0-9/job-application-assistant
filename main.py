#!/usr/bin/env python3
"""
Job Application Assistant
Automatiza la preparación de CVs y cartas de presentación con IA.
"""

import json
import sys
from pathlib import Path

# La consola de Windows usa cp1252 y revienta con los emojis de la interfaz.
# Sin esto, el CLI ni siquiera muestra la ayuda.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from typing import Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import TEMPLATES_DIR, OUTPUT_DIR
from src import tracker
from src.analyzer import analyze_job_offer
from src.cover_letter import generate_cover_letter
from src.cv_adapter import adapt_cv
from src.cv_generator import generate_cv_docx
from src.models import CV, JobAnalysis
from src.scraper import (
    search_all, search_colombia_remote,
    PLATFORMS, COLOMBIA_REMOTE_PLATFORMS, USD_PLATFORMS,
    ALL_REMOTE_PLATFORMS, BILINGUAL_KEYWORDS,
    KEYWORDS_EN, KEYWORDS_ES, REQUERIMIENTOS_KEYWORDS, KEYWORDS_IA,
    fetch_full_description,
)

cli = typer.Typer(
    help="🎯 Job Application Assistant – Prepara CVs y cartas con IA",
    rich_markup_mode="rich",
)
console = Console()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_cv(path: Optional[Path] = None) -> CV:
    cv_path = path or (TEMPLATES_DIR / "cv_base.json")
    if not cv_path.exists():
        rprint(f"[red]❌  No se encontró {cv_path}\n   Ejecuta primero: python main.py setup[/red]")
        raise typer.Exit(1)
    return CV(**json.loads(cv_path.read_text(encoding="utf-8")))


def _load_analysis(app_id: int) -> JobAnalysis:
    path = OUTPUT_DIR / f"analysis_{app_id}.json"
    if not path.exists():
        rprint(f"[red]❌  Sin análisis para aplicación #{app_id}[/red]")
        raise typer.Exit(1)
    return JobAnalysis(**json.loads(path.read_text(encoding="utf-8")))


# ── Comandos ──────────────────────────────────────────────────────────────────

@cli.command()
def setup():
    """⚙️   Primera vez: crea la plantilla cv_base.json y la BD."""
    cv_path = TEMPLATES_DIR / "cv_base.json"
    if cv_path.exists() and not typer.confirm("cv_base.json ya existe. ¿Sobreescribir?"):
        raise typer.Exit()

    TEMPLATES_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    tracker.init_db()

    ejemplo = TEMPLATES_DIR / "cv_base.example.json"
    if not ejemplo.exists():
        rprint(f"[red]❌  Falta la plantilla de ejemplo: {ejemplo}[/red]")
        raise typer.Exit(1)

    # Una sola fuente de verdad: el ejemplo vive en un archivo, no en el código.
    # Antes estaba duplicado aquí dentro y era fácil confundirlo con el CV real.
    template = json.loads(ejemplo.read_text(encoding="utf-8"))

    cv_path.write_text(
        json.dumps(template, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    rprint(f"[green]✅  Plantilla creada:[/green] {cv_path}")
    rprint("[yellow]⚠️   Edita templates/cv_base.json con tu información real.[/yellow]")
    rprint("\n[bold]Flujo de trabajo:[/bold]")
    rprint("  1. python main.py analizar [texto o --file oferta.txt]")
    rprint("  2. python main.py adaptar <ID>")
    rprint("  3. python main.py carta <ID>")
    rprint("  4. Aplica manualmente con el .docx generado")
    rprint("  5. python main.py actualizar <ID> entrevista_rh")


@cli.command()
def analizar(
    oferta: Optional[str] = typer.Argument(None, help="Texto de la oferta"),
    archivo: Optional[Path] = typer.Option(None, "--file", "-f", help="Archivo .txt con la oferta"),
    cv_path: Optional[Path] = typer.Option(None, "--cv", help="CV base alternativo"),
):
    """🔍  Analiza una oferta y calcula compatibilidad con tu CV."""
    if archivo:
        offer_text = archivo.read_text(encoding="utf-8")
    elif oferta:
        offer_text = oferta
    else:
        rprint("[yellow]Pega la oferta y presiona Enter + Ctrl+D (Linux/Mac) o Ctrl+Z (Windows):[/yellow]")
        lines = []
        try:
            while True:
                lines.append(input())
        except EOFError:
            pass
        offer_text = "\n".join(lines)

    if not offer_text.strip():
        rprint("[red]❌  Texto vacío[/red]")
        raise typer.Exit(1)

    cv = _load_cv(cv_path)

    with console.status("[bold blue]Analizando con IA…"):
        analysis = analyze_job_offer(offer_text, cv)

    score_color = "green" if analysis.match_score >= 70 else ("yellow" if analysis.match_score >= 50 else "red")

    console.print(Panel(
        f"[bold]{analysis.title}[/bold]  @  [cyan]{analysis.company}[/cyan]\n"
        f"Nivel: {analysis.experience_level}   |   "
        f"Match: [{score_color}]{analysis.match_score}%[/{score_color}]",
        title="📋 Análisis de Oferta"
    ))

    _print_list("✅ Habilidades requeridas",   "cyan",   analysis.required_skills)
    _print_list("🎯 Keywords ATS",             "yellow", analysis.ats_keywords)
    _print_list("⭐ A destacar de tu CV",      "green",  analysis.highlights)
    _print_list("⚠️  Brechas",                 "red",    analysis.gaps)

    if not typer.confirm("\n¿Guardar análisis y registrar en tracker?"):
        return

    company  = typer.prompt("Empresa",    default=analysis.company)
    position = typer.prompt("Cargo",      default=analysis.title)
    platform = typer.prompt("Plataforma", default="LinkedIn")
    url      = typer.prompt("URL oferta (Enter omite)", default="")
    salary   = typer.prompt("Salario esperado (Enter omite)", default="")

    tracker.init_db()
    app_id = tracker.add_application(
        company=company, position=position,
        platform=platform, url=url or None,
        salary_expected=salary or None,
        match_score=analysis.match_score,
    )
    tracker.save_analysis(app_id, offer_text, analysis.model_dump_json())

    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / f"analysis_{app_id}.json").write_text(
        analysis.model_dump_json(indent=2), encoding="utf-8"
    )

    rprint(f"\n[green]✅  Aplicación [bold]#{app_id}[/bold] guardada.[/green]")
    rprint(f"   Siguiente: [bold]python main.py adaptar {app_id}[/bold]")


@cli.command()
def adaptar(
    app_id: int = typer.Argument(..., help="ID de la aplicación"),
    cv_path: Optional[Path] = typer.Option(None, "--cv", help="CV base alternativo"),
    sin_docx: bool = typer.Option(False, "--sin-docx", help="No generar .docx"),
):
    """✏️   Adapta tu CV para la oferta y genera el .docx."""
    analysis  = _load_analysis(app_id)
    base_cv   = _load_cv(cv_path)

    with console.status("[bold blue]Adaptando CV con IA…"):
        adapted = adapt_cv(base_cv, analysis)

    rprint(f"[green]✅  CV adaptado para:[/green] {analysis.title} @ {analysis.company}")

    adapted_json = OUTPUT_DIR / f"cv_adapted_{app_id}.json"
    OUTPUT_DIR.mkdir(exist_ok=True)
    adapted_json.write_text(adapted.model_dump_json(indent=2), encoding="utf-8")

    if not sin_docx:
        safe_name = f"CV_{adapted.personal.name.replace(' ','_')}_{analysis.company.replace(' ','_')}_{app_id}.docx"
        with console.status("[bold blue]Generando .docx…"):
            docx_path = generate_cv_docx(adapted, safe_name)
        tracker.set_cv_filename(app_id, safe_name)
        rprint(f"[green]📄  Archivo generado:[/green] {docx_path}")

    rprint(f"   Siguiente: [bold]python main.py carta {app_id}[/bold]")


@cli.command()
def carta(
    app_id: int = typer.Argument(..., help="ID de la aplicación"),
    cv_path: Optional[Path] = typer.Option(None, "--cv", help="CV base alternativo"),
    sin_guardar: bool = typer.Option(False, "--sin-guardar"),
):
    """📝  Genera carta de presentación personalizada."""
    analysis = _load_analysis(app_id)
    adapted  = OUTPUT_DIR / f"cv_adapted_{app_id}.json"
    cv = CV(**json.loads(adapted.read_text())) if adapted.exists() else _load_cv(cv_path)

    with console.status("[bold blue]Generando carta con IA…"):
        letter = generate_cover_letter(cv, analysis)

    console.print(Panel(letter, title=f"📝  Carta – {analysis.title} @ {analysis.company}"))

    if not sin_guardar:
        path = OUTPUT_DIR / f"carta_{app_id}_{analysis.company.replace(' ','_')}.txt"
        path.write_text(letter, encoding="utf-8")
        tracker.set_cover_letter(app_id)
        rprint(f"\n[green]✅  Carta guardada:[/green] {path}")


@cli.command("listar")
def listar(
    estado: Optional[str] = typer.Option(None, "--estado", "-s", help="Filtrar por estado"),
):
    """📊  Lista todas las aplicaciones registradas."""
    tracker.init_db()
    apps = tracker.get_applications(estado)

    if not apps:
        rprint("[yellow]Sin aplicaciones registradas aún.[/yellow]")
        return

    STATUS_COLOR = {
        "aplicado":            "blue",
        "vista":               "cyan",
        "entrevista_rh":       "yellow",
        "entrevista_tecnica":  "yellow",
        "oferta":              "green",
        "rechazado":           "red",
        "retirado":            "dim",
    }

    t = Table(title=f"📋 Aplicaciones ({len(apps)})", show_lines=True)
    t.add_column("ID",        style="dim",  width=4)
    t.add_column("Empresa",   style="bold", min_width=16)
    t.add_column("Cargo",     min_width=20)
    t.add_column("Plataforma",style="cyan", width=12)
    t.add_column("Fecha",     width=11)
    t.add_column("Estado",    width=20)
    t.add_column("Match",     width=7)
    t.add_column("CV/Carta",  width=9)

    for a in apps:
        sc  = STATUS_COLOR.get(a["status"], "white")
        mat = f"{a['match_score']}%" if a.get("match_score") else "-"
        doc = ("✓CV " if a.get("cv_filename") else "") + ("✓Carta" if a.get("cover_letter") else "")
        t.add_row(
            str(a["id"]),
            a["company"],
            a["position"],
            a["platform"] or "-",
            a["applied_date"] or "-",
            f"[{sc}]{a['status']}[/{sc}]",
            mat,
            doc or "-",
        )
    console.print(t)


@cli.command()
def stats():
    """📈  Estadísticas de tu búsqueda de empleo."""
    tracker.init_db()
    s = tracker.get_stats()

    console.print(Panel(
        f"[bold]Total aplicaciones:[/bold] {s['total']}\n"
        # Igual que en tracker.get_stats: 0 es un promedio válido, no un "sin datos".
        f"[bold]Match promedio:[/bold]    "
        f"{'N/A' if s.get('avg_match_score') is None else s['avg_match_score']}%",
        title="📊 Estadísticas"
    ))

    if s["by_status"]:
        t = Table(title="Por Estado")
        t.add_column("Estado"); t.add_column("Total", justify="right")
        for st, cnt in s["by_status"].items():
            t.add_row(st, str(cnt))
        console.print(t)

    if s["by_platform"]:
        t = Table(title="Por Plataforma")
        t.add_column("Plataforma"); t.add_column("Total", justify="right")
        for pl, cnt in s["by_platform"].items():
            t.add_row(pl, str(cnt))
        console.print(t)


@cli.command()
def actualizar(
    app_id: int = typer.Argument(..., help="ID de la aplicación"),
    estado: str  = typer.Argument(..., help="Nuevo estado"),
    notas:  Optional[str] = typer.Option(None, "--notas", "-n"),
):
    """🔄  Actualiza el estado de una aplicación."""
    tracker.init_db()
    tracker.update_status(app_id, estado, notas)
    rprint(f"[green]✅  Aplicación [bold]#{app_id}[/bold] → {estado}[/green]")


# ── Búsqueda automática ───────────────────────────────────────────────────────

@cli.command()
def buscar(
    keywords: str = typer.Argument(..., help="Palabras clave, ej: 'Python data'"),
    ubicacion: str  = typer.Option("Tijuana", "--ubicacion", "-u", help="Ciudad o región"),
    remoto: bool    = typer.Option(False, "--remoto/--no-remoto", "-r", help="Solo remotas"),
    plataformas: Optional[str] = typer.Option(
        None, "--plataformas", "-p",
        help="Separadas por coma: occ,computrabajo,indeed,bumeran (defecto: todas)"
    ),
    max_por: int = typer.Option(20, "--max", "-m", help="Máx. ofertas por plataforma"),
):
    """🌐  Busca ofertas automáticamente en OCC, Computrabajo, Indeed y Bumeran."""
    tracker.init_db()

    active = [p.strip() for p in plataformas.split(",")] if plataformas else None

    console.print(Panel(
        f"[bold]Keywords:[/bold]     {keywords}\n"
        f"[bold]Ubicación:[/bold]    {'Remoto' if remoto else ubicacion}\n"
        f"[bold]Plataformas:[/bold]  {', '.join(active) if active else 'OCC · Computrabajo · Indeed · Bumeran'}",
        title="🔍 Búsqueda automática de ofertas"
    ))

    jobs = []
    active_list = active or list(PLATFORMS.keys())
    with console.status("[bold blue]Buscando…"):
        for name in active_list:
            fn = PLATFORMS.get(name)
            if not fn:
                rprint(f"[yellow]  Plataforma desconocida: {name}[/yellow]")
                continue
            rprint(f"  Buscando en [bold]{name.upper()}[/bold]…")
            try:
                found = fn(keywords=keywords, location=ubicacion,
                           max_results=max_por, remote=remoto)
                jobs.extend(found)
                rprint(f"     → {len(found)} encontradas")
            except Exception as e:
                rprint(f"     [red]✗ Error: {e}[/red]")

    if not jobs:
        rprint("[yellow]Sin resultados. Prueba otras palabras clave.[/yellow]")
        return

    # Deduplicar y guardar en cola
    seen, saved = set(), 0
    for job in jobs:
        if job.url in seen:
            continue
        seen.add(job.url)
        if tracker.save_job_to_queue(job) > 0:
            saved += 1

    rprint(f"\n[green]✅  {saved} ofertas nuevas en la cola[/green]  ({len(jobs) - saved} duplicadas)")
    rprint(f"   Ver cola: [bold]python main.py cola[/bold]")
    rprint(f"   Procesar: [bold]python main.py procesar-cola <ID>[/bold]")


@cli.command("buscar-usd")
def buscar_usd(
    extra: Optional[str] = typer.Argument(None, help="Keyword extra (se suma a los 12 bilingues)"),
    max_por: int = typer.Option(10, "--max", "-m", help="Máx. resultados por búsqueda"),
    solo_en: bool = typer.Option(False, "--solo-en", help="Solo keywords en inglés"),
    solo_es: bool = typer.Option(False, "--solo-es", help="Solo keywords en español"),
    plataformas: Optional[str] = typer.Option(None, "--plataformas", "-p"),
    perfil: str = typer.Option("ambos", "--perfil",
                               help="requerimientos | ia | ambos"),
):
    """💵  Máxima cobertura: inglés + español · 8 plataformas · preferencia USD.\n
    Usa 12 keywords bilingues en Remotive, RemoteOK, Himalayas, WWR, Torre,
    GetOnBoard, Indeed CO y Computrabajo CO."""
    tracker.init_db()

    # Seleccionar keywords
    if solo_en:
        kw_list = list(KEYWORDS_EN)
    elif solo_es:
        kw_list = list(KEYWORDS_ES)
    else:
        kw_list = list(BILINGUAL_KEYWORDS)

    # Filtrar o ampliar segun el perfil buscado
    if perfil == "ia":
        kw_list = list(KEYWORDS_IA)
    elif perfil == "ambos":
        kw_list = kw_list + list(KEYWORDS_IA)

    if extra:
        kw_list.insert(0, extra)

    # Seleccionar plataformas
    active = [p.strip() for p in plataformas.split(",")] if plataformas else list(ALL_REMOTE_PLATFORMS)

    console.print(Panel(
        f"[bold]Keywords:[/bold]     {len(kw_list)} bilingues  "
        f"({'EN+ES' if not solo_en and not solo_es else 'EN' if solo_en else 'ES'})\n"
        f"[bold]Plataformas:[/bold]  {len(active)}  →  {', '.join(active)}\n"
        f"[bold]Salario:[/bold]      preferencia USD · resultados con salario primero\n"
        f"[bold]Total:[/bold]        ~{len(kw_list) * len(active)} búsquedas",
        title="💵 Búsqueda máxima — USD Remote",
        border_style="green",
    ))

    import requests as _req
    from src.scraper import _pause

    session   = _req.Session()
    all_jobs  = []
    seen_urls = set()
    errors    = []

    for kw in kw_list:
        rprint(f"\n  [bold cyan]🔑 \"{kw}\"[/bold cyan]")
        for name in active:
            fn = PLATFORMS.get(name)
            if not fn:
                continue
            tag = "[green]$[/green]" if name in ("remotive", "himalayas", "weworkremotely") else " "
            rprint(f"     {tag} [dim]{name}…[/dim]", end="")
            try:
                found = fn(keywords=kw, max_results=max_por, remote=True, session=session)
                new = [j for j in found if j.url not in seen_urls]
                seen_urls.update(j.url for j in new)
                all_jobs.extend(new)
                rprint(f" [green]{len(new)}[/green]" if new else " [dim]0[/dim]")
                _pause()
            except Exception as e:
                rprint(f" [red]✗[/red]")
                errors.append(f"{name}/{kw}: {e}")

    if not all_jobs:
        rprint("\n[yellow]Sin resultados. Prueba con --plataformas remotive o --solo-en.[/yellow]")
        return

    # Ordenar: con salario primero
    with_salary    = [j for j in all_jobs if j.salary]
    without_salary = [j for j in all_jobs if not j.salary]
    ordered = with_salary + without_salary

    # Guardar en cola
    saved = sum(1 for j in ordered if tracker.save_job_to_queue(j) > 0)

    rprint(f"\n[green bold]✅  {saved} ofertas nuevas guardadas[/green bold]")

    # Resumen por plataforma
    from collections import Counter
    plts = Counter(j.platform for j in all_jobs)
    sal_count = len(with_salary)

    t = Table(title="Resumen", show_header=True, box=None)
    t.add_column("Plataforma",  style="cyan")
    t.add_column("Ofertas",     justify="right")
    t.add_column("Con salario", justify="right", style="green")
    for plt, cnt in plts.most_common():
        with_sal = sum(1 for j in all_jobs if j.platform == plt and j.salary)
        t.add_row(plt, str(cnt), str(with_sal) if with_sal else "-")
    console.print(t)

    rprint(f"\n[bold]💰 Con salario visible:[/bold] {sal_count} de {len(all_jobs)} ofertas")
    if errors:
        rprint(f"[dim]Errores ({len(errors)}): {errors[0]}…[/dim]")
    rprint(f"\n[bold]Ver:[/bold]      python main.py cola")
    rprint(f"[bold]Procesar:[/bold] python main.py procesar-cola <ID>")



@cli.command("cola")
def ver_cola(
    analizado: bool = typer.Option(False, "--analizado", help="Mostrar los ya procesados"),
):
    """📋  Muestra las ofertas pendientes de la cola."""
    tracker.init_db()
    jobs = tracker.get_job_queue(analyzed=analizado)

    label = "procesadas" if analizado else "pendientes"
    if not jobs:
        rprint(f"[yellow]No hay ofertas {label}.[/yellow]")
        if not analizado:
            rprint("   Busca primero: [bold]python main.py buscar \"Python developer\"[/bold]")
        return

    t = Table(title=f"📋 Cola — {label.title()} ({len(jobs)})", show_lines=True)
    t.add_column("ID",       style="dim",  width=4)
    t.add_column("Cargo",    min_width=22)
    t.add_column("Empresa",  style="bold", min_width=16)
    t.add_column("Plataforma", style="cyan", width=14)
    t.add_column("Ubicación", width=14)
    t.add_column("Salario",  width=14)
    t.add_column("Fecha",    width=11)

    for j in jobs:
        t.add_row(
            str(j["id"]),
            j["title"],
            j["company"] or "-",
            j["platform"] or "-",
            j["location"] or "-",
            j["salary"] or "-",
            j["found_date"] or "-",
        )
    console.print(t)

    if not analizado:
        rprint(f"\n[bold]Procesar oferta:[/bold] python main.py procesar-cola <ID>")


@cli.command("buscar-colombia")
def buscar_colombia(
    keywords: Optional[str] = typer.Argument(
        None,
        help="Keywords personalizados (defecto: variantes de analista requerimientos)"
    ),
    max_por: int = typer.Option(15, "--max", "-m", help="Máx. resultados por plataforma"),
    solo_una: Optional[str] = typer.Option(
        None, "--plataforma", "-p",
        help="Buscar solo en una: torre/remoteok/getonboard/indeed_co/computrabajo_co"
    ),
):
    """🇨🇴  Búsqueda optimizada: 100% remoto · accesible desde Colombia · LATAM.\n
    Sin argumento, busca automáticamente con todas las variantes de\n
    'analista de requerimientos' (español + inglés) en 5 plataformas."""
    tracker.init_db()

    # Keywords a usar
    if keywords:
        kw_list = [keywords]
    else:
        kw_list = REQUERIMIENTOS_KEYWORDS
        rprint(
            "\n[dim]Usando keywords:[/dim] "
            + "  ·  ".join(f"[cyan]{k}[/cyan]" for k in kw_list)
        )

    plataformas_activas = [solo_una] if solo_una else COLOMBIA_REMOTE_PLATFORMS

    console.print(Panel(
        f"[bold]Perfil:[/bold]       Analista de Requerimientos / BA\n"
        f"[bold]Modalidad:[/bold]    100% remoto · LATAM / Colombia\n"
        f"[bold]Plataformas:[/bold]  {', '.join(plataformas_activas)}\n"
        f"[bold]Variantes:[/bold]    {len(kw_list)} keywords",
        title="🇨🇴 Búsqueda Colombia Remote",
        border_style="blue",
    ))

    # Correr scraper
    from src.scraper import PLATFORMS, _pause, _delay
    import requests as _req

    session    = _req.Session()
    all_jobs   = []
    seen_urls  = set()

    for kw in kw_list:
        rprint(f"\n  [bold cyan]🔑 \"{kw}\"[/bold cyan]")
        for name in plataformas_activas:
            fn = PLATFORMS.get(name)
            if not fn:
                continue
            rprint(f"     [dim]▸ {name}…[/dim]", end="")
            try:
                found = fn(keywords=kw, max_results=max_por, remote=True, session=session)
                new   = [j for j in found if j.url not in seen_urls]
                seen_urls.update(j.url for j in new)
                all_jobs.extend(new)
                rprint(f" [green]{len(new)} nuevas[/green]" if new else " [dim]0 nuevas[/dim]")
                _pause()
            except Exception as e:
                rprint(f" [red]✗ {e}[/red]")

    if not all_jobs:
        rprint("\n[yellow]Sin resultados. Intenta ajustar keywords o plataformas.[/yellow]")
        return

    # Guardar en cola
    saved = sum(1 for j in all_jobs if tracker.save_job_to_queue(j) > 0)

    rprint(f"\n[green bold]✅  {saved} ofertas nuevas guardadas[/green bold]"
           f"  [dim]({len(all_jobs) - saved} ya estaban en cola)[/dim]\n")

    # Resumen por plataforma
    from collections import Counter
    plts = Counter(j.platform for j in all_jobs)
    t = Table(title="Resumen por plataforma", show_header=True, box=None)
    t.add_column("Plataforma", style="cyan")
    t.add_column("Encontradas", justify="right")
    for plt, cnt in plts.most_common():
        t.add_row(plt, str(cnt))
    console.print(t)

    rprint(f"\n[bold]Ver cola:[/bold]     python main.py cola")
    rprint(f"[bold]Procesar #ID:[/bold] python main.py procesar-cola <ID>")



@cli.command("procesar-cola")
def procesar_cola(
    queue_id: int = typer.Argument(..., help="ID de la oferta en la cola"),
    cv_path: Optional[Path] = typer.Option(None, "--cv"),
    solo_analisis: bool = typer.Option(False, "--solo-analisis", help="Solo analizar, sin generar .docx"),
):
    """⚡  Pipeline completo para una oferta de la cola: analiza → adapta CV → genera carta."""
    tracker.init_db()
    pending = tracker.get_job_queue(analyzed=False)
    job_data = next((j for j in pending if j["id"] == queue_id), None)

    if not job_data:
        rprint(f"[red]❌  Oferta #{queue_id} no encontrada en pendientes[/red]")
        raise typer.Exit(1)

    rprint(f"\n[bold]{job_data['title']}[/bold]  @  [cyan]{job_data['company']}[/cyan]")
    rprint(f"[dim]{job_data['url']}[/dim]\n")

    # Descripción completa — descarga si la guardada es corta
    description = job_data["description"] or ""
    if len(description) < 200:
        with console.status("[dim]Descargando descripción completa…[/dim]"):
            full = fetch_full_description(job_data["url"])
            if full:
                description = full

    if not description:
        description = f"{job_data['title']} en {job_data['company']} — {job_data['location']}"

    # Analizar con Claude
    base_cv = _load_cv(cv_path)
    with console.status("[bold blue]Analizando con IA…"):
        analysis = analyze_job_offer(description, base_cv)

    sc = "green" if analysis.match_score >= 70 else ("yellow" if analysis.match_score >= 50 else "red")
    rprint(f"[{sc}]Match: {analysis.match_score}%[/{sc}]   Nivel: {analysis.experience_level}")
    _print_list("A destacar", "green",  analysis.highlights[:4])
    _print_list("Brechas",    "red",    analysis.gaps[:3])

    # Registrar en el tracker de aplicaciones
    app_id = tracker.add_application(
        company=job_data["company"], position=analysis.title,
        platform=job_data["platform"], url=job_data["url"],
        match_score=analysis.match_score,
    )
    tracker.save_analysis(app_id, description, analysis.model_dump_json())
    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / f"analysis_{app_id}.json").write_text(
        analysis.model_dump_json(indent=2), encoding="utf-8"
    )
    tracker.mark_job_analyzed(queue_id, app_id)
    rprint(f"\n[green]✅  Aplicación [bold]#{app_id}[/bold] registrada.[/green]")

    if solo_analisis:
        return

    if not typer.confirm("¿Adaptar CV y generar carta ahora?"):
        rprint(f"   Hacerlo después: python main.py adaptar {app_id}")
        return

    # CV adaptado
    with console.status("[bold blue]Adaptando CV…"):
        adapted = adapt_cv(base_cv, analysis)

    safe = f"CV_{adapted.personal.name.replace(' ','_')}_{analysis.company.replace(' ','_')}_{app_id}.docx"
    with console.status("[bold blue]Generando .docx…"):
        docx_path = generate_cv_docx(adapted, safe)

    (OUTPUT_DIR / f"cv_adapted_{app_id}.json").write_text(
        adapted.model_dump_json(indent=2), encoding="utf-8"
    )
    tracker.set_cv_filename(app_id, safe)

    # Carta
    with console.status("[bold blue]Generando carta…"):
        letter = generate_cover_letter(adapted, analysis)

    letter_path = OUTPUT_DIR / f"carta_{app_id}_{analysis.company.replace(' ','_')}.txt"
    letter_path.write_text(letter, encoding="utf-8")
    tracker.set_cover_letter(app_id)

    rprint(f"[green]📄  CV:[/green]    {docx_path}")
    rprint(f"[green]📝  Carta:[/green] {letter_path}")
    rprint(f"\n[bold cyan]➡  Aplica manualmente:[/bold cyan] {job_data['url']}")


# ── Utils privados ─────────────────────────────────────────────────────────────

def _print_list(label: str, color: str, items: list):
    if not items:
        return
    rprint(f"\n[bold {color}]{label}:[/bold {color}]")
    for item in items:
        rprint(f"  [dim]•[/dim] {item}")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
