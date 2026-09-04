"""
Búsqueda de ofertas de trabajo en plataformas mexicanas y latinoamericanas.

Plataformas:
  occ         → occ.com.mx
  computrabajo → computrabajo.com.mx
  indeed       → mx.indeed.com
  bumeran      → bumeran.com.mx

Uso:
  from src.scraper import search_all, PLATFORMS
  jobs = search_all("Python developer", location="Tijuana", remote=False)
"""

import re
import time
import random
import logging
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlencode, quote_plus

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Configuración ────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}


@dataclass
class JobListing:
    title:       str
    company:     str
    location:    str
    platform:    str
    url:         str
    description: str
    salary:      Optional[str] = None

    def __str__(self) -> str:
        sal = f"  💰 {self.salary}" if self.salary else ""
        return f"[{self.platform}] {self.title} @ {self.company} — {self.location}{sal}"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    return re.sub(r'\s+', ' ', (text or "").strip())


def _fetch(url: str, session: requests.Session) -> Optional[BeautifulSoup]:
    """GET con reintentos. Retorna BeautifulSoup o None si falla."""
    for attempt in range(3):
        try:
            r = session.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            return BeautifulSoup(r.text, "lxml")
        except requests.RequestException as e:
            logger.warning(f"    intento {attempt+1}/3: {e}")
            if attempt < 2:
                time.sleep(2 + attempt)
    return None


def _pause():
    """Pausa aleatoria entre requests para no saturar los servidores."""
    time.sleep(random.uniform(1.5, 3.2))


def _entero_o_none(valor) -> Optional[int]:
    """Convierte a entero lo que devuelva una API, sin reventar por basura.

    Los portales mandan el salario como número, como texto ("80000", "80,000")
    o como palabra ("negociable"). Un int() directo tumbaba la corrida entera
    por una sola oferta mal formada.
    """
    if valor is None:
        return None
    try:
        return int(float(str(valor).replace(",", "").replace("$", "").strip()))
    except (TypeError, ValueError):
        return None


def _first(el, *selectors, attr: str = None):
    """Prueba una lista de selectores CSS y devuelve el primer valor NO VACÍO.

    Sigue con el siguiente selector cuando uno coincide pero no aporta nada: el
    elemento existe pero le falta el atributo, o su texto está en blanco. Ese es
    justamente el caso que vuelve útiles a los respaldos —un portal cambia su
    HTML y el selector viejo todavía coincide con algo vacío—, y antes se
    devolvía "" sin llegar a probarlos, perdiendo la URL o el título.
    """
    for sel in selectors:
        found = el.select_one(sel)
        if not found:
            continue
        if attr:
            valor = found.get(attr, "")
            # BeautifulSoup devuelve una lista en atributos multivaluados (class,
            # rel...); sin esto, .strip() reventaba con AttributeError.
            if isinstance(valor, (list, tuple)):
                valor = " ".join(valor)
            valor = valor.strip()
        else:
            valor = _clean(found.get_text())
        if valor:
            return valor
    return ""


# ── OCC Mundial ──────────────────────────────────────────────────────────────

def scrape_occ(
    keywords: str,
    location: str = "Tijuana",
    max_results: int = 20,
    remote: bool = False,
    session: Optional[requests.Session] = None,
) -> List[JobListing]:
    session = session or requests.Session()
    q = keywords.lower().replace(" ", "-")

    if remote:
        url = f"https://www.occ.com.mx/empleos/de-{q}/trabajo-remoto/"
    else:
        loc = location.lower().replace(" ", "-")
        url = f"https://www.occ.com.mx/empleos/de-{q}/en-{loc}/"

    logger.info(f"  OCC: {url}")
    soup = _fetch(url, session)
    if not soup:
        return []

    cards = (
        soup.select("article[data-id]") or
        soup.select("article.listing-item") or
        soup.select(".box_trabajo") or
        soup.select("div[data-testid='job-card']")
    )
    if not cards:
        logger.warning("  OCC: sin resultados (posible cambio en HTML)")
        return []

    results = []
    for card in cards[:max_results]:
        title   = _first(card, "h2", "h3", "[class*=title]", "a")
        company = _first(card, "[class*=company]", "[class*=empresa]", "span.org")
        salary  = _first(card, "[class*=salary]", "[class*=sueldo]") or None
        desc    = _first(card, "p", "[class*=desc]", "[class*=summary]")[:280]

        link = card.find("a", href=True)
        href = link["href"] if link else ""
        if href and not href.startswith("http"):
            href = "https://www.occ.com.mx" + href

        if title and href:
            results.append(JobListing(
                title=title, company=company or "Empresa no especificada",
                location="Remoto" if remote else location,
                platform="OCC Mundial", url=href,
                description=desc, salary=salary,
            ))
    return results


# ── Computrabajo MX ──────────────────────────────────────────────────────────

def scrape_computrabajo(
    keywords: str,
    location: str = "Tijuana",
    max_results: int = 20,
    remote: bool = False,
    session: Optional[requests.Session] = None,
) -> List[JobListing]:
    session = session or requests.Session()
    q = keywords.lower().replace(" ", "-")

    if remote:
        url = f"https://www.computrabajo.com.mx/trabajo-de-{q}-en-home-office"
    else:
        loc = location.lower().replace(" ", "-")
        url = f"https://www.computrabajo.com.mx/trabajo-de-{q}-en-{loc}"

    logger.info(f"  Computrabajo: {url}")
    soup = _fetch(url, session)
    if not soup:
        return []

    cards = (
        soup.select("article[id^='p']") or
        soup.select("article.box_offer") or
        soup.select("[data-component='jobCard']") or
        soup.select(".offerList article")
    )
    if not cards:
        logger.warning("  Computrabajo: sin resultados")
        return []

    results = []
    for card in cards[:max_results]:
        # Título: a veces en atributo title del <a>
        link = card.find("a", href=True)
        title = (
            (link.get("title") or "").strip() or
            _first(card, "h2", "h3", "[class*=title]")
        )
        company = _first(card, "[class*=company]", "[class*=empresa]", "a[data-company]")
        salary  = _first(card, "[class*=salary]", "[class*=salario]") or None
        desc    = _first(card, "p", "[class*=desc]")[:280]

        href = link["href"] if link else ""
        if href and not href.startswith("http"):
            href = "https://www.computrabajo.com.mx" + href

        if title and href:
            results.append(JobListing(
                title=title, company=company or "Empresa no especificada",
                location="Home Office" if remote else location,
                platform="Computrabajo", url=href,
                description=desc, salary=salary,
            ))
    return results


# ── Indeed MX ────────────────────────────────────────────────────────────────

def scrape_indeed(
    keywords: str,
    location: str = "Tijuana",
    max_results: int = 20,
    remote: bool = False,
    session: Optional[requests.Session] = None,
) -> List[JobListing]:
    session = session or requests.Session()
    params = {"q": keywords, "l": "" if remote else location, "lang": "es"}
    if remote:
        params["remotejob"] = "1"

    url = "https://mx.indeed.com/jobs?" + urlencode(params)
    logger.info(f"  Indeed: {url}")

    soup = _fetch(url, session)
    if not soup:
        return []

    cards = (
        soup.select("div.job_seen_beacon") or
        soup.select("td.resultContent") or
        soup.select("div[data-testid='job-card']") or
        soup.select("li[class*='job-']")
    )
    if not cards:
        logger.warning("  Indeed: sin resultados")
        return []

    results = []
    for card in cards[:max_results]:
        # Indeed: título en span[title] dentro de h2
        title_el = card.select_one("h2 span[title]") or card.select_one("h2 a span")
        title = (title_el.get("title") or _clean(title_el.get_text())) if title_el else ""
        if not title:
            title = _first(card, "h2", "[class*=title]")

        company  = _first(card, "[data-testid='company-name']", "span.company", "[class*=companyName]")
        job_loc  = _first(card, "[data-testid='text-location']", "[class*=location]", "div.companyLocation")
        salary   = _first(card, "[data-testid='attribute_snippet_testid']", "[class*=salary]") or None
        desc     = _first(card, "[class*=summary]", "ul.jobCardShelfContainer")[:280]

        link = card.find("a", href=True)
        href = link["href"] if link else ""
        if href and not href.startswith("http"):
            href = "https://mx.indeed.com" + href

        if title and href:
            results.append(JobListing(
                title=title, company=company or "Empresa no especificada",
                location=job_loc or ("Remoto" if remote else location),
                platform="Indeed MX", url=href,
                description=desc, salary=salary,
            ))
    return results


# ── Bumeran MX ───────────────────────────────────────────────────────────────

def scrape_bumeran(
    keywords: str,
    location: str = "Tijuana",
    max_results: int = 20,
    remote: bool = False,
    session: Optional[requests.Session] = None,
) -> List[JobListing]:
    session = session or requests.Session()
    q = keywords.lower().replace(" ", "-")

    if remote:
        url = f"https://www.bumeran.com.mx/empleos-{q}-modalidad-100-por-ciento-remoto.html"
    else:
        loc = location.lower().replace(" ", "-")
        url = f"https://www.bumeran.com.mx/empleos-{q}-en-{loc}.html"

    logger.info(f"  Bumeran: {url}")
    soup = _fetch(url, session)
    if not soup:
        return []

    cards = (
        soup.select("div[data-test='job-list-item']") or
        soup.select("article.aviso") or
        soup.select("li.aviso-list-item")
    )
    if not cards:
        logger.warning("  Bumeran: sin resultados")
        return []

    results = []
    for card in cards[:max_results]:
        title   = _first(card, "h2", "h3", "[class*=title]")
        company = _first(card, "[class*=company]", "[class*=empresa]")
        salary  = _first(card, "[class*=salary]", "[class*=salario]") or None

        link = card.find("a", href=True)
        href = link["href"] if link else ""
        if href and not href.startswith("http"):
            href = "https://www.bumeran.com.mx" + href

        if title and href:
            results.append(JobListing(
                title=title, company=company or "Empresa no especificada",
                location="Remoto" if remote else location,
                platform="Bumeran", url=href,
                description="", salary=salary,
            ))
    return results


# ── Buscar en todas las plataformas ──────────────────────────────────────────

PLATFORMS = {
    "occ":          scrape_occ,
    "computrabajo": scrape_computrabajo,
    "indeed":       scrape_indeed,
    "bumeran":      scrape_bumeran,
}


def search_all(
    keywords: str,
    location: str = "Tijuana",
    max_per_platform: int = 20,
    remote: bool = False,
    platforms: Optional[List[str]] = None,
    verbose: bool = True,
) -> List[JobListing]:
    """Busca en todas las plataformas y retorna resultados sin duplicados."""
    active  = platforms or list(PLATFORMS.keys())
    session = requests.Session()
    results = []
    seen    = set()

    for name in active:
        fn = PLATFORMS.get(name)
        if not fn:
            continue
        if verbose:
            print(f"  🔎 Buscando en {name.upper()}...")
        try:
            found = fn(keywords=keywords, location=location,
                       max_results=max_per_platform, remote=remote, session=session)
            new = [j for j in found if j.url not in seen]
            seen.update(j.url for j in new)
            results.extend(new)
            if verbose:
                print(f"     → {len(new)} ofertas nuevas")
            _pause()
        except Exception as e:
            logger.error(f"  Error en {name}: {e}")
            if verbose:
                print(f"     ✗ Error: {e}")

    return results


# ── Torre.co (API JSON — mejor plataforma LATAM remota) ──────────────────────

def scrape_torre_co(
    keywords: str,
    location: str = "",
    max_results: int = 20,
    remote: bool = True,
    session: Optional[requests.Session] = None,
) -> List[JobListing]:
    """
    Torre.co — plataforma colombiana de empleo tech remoto.
    Usa su API de búsqueda que devuelve JSON.
    """
    session = session or requests.Session()
    url = "https://torre.co/api/search/jobs"
    payload = {
        "query": keywords,
        "filters": {"remote": True, "openTo": ["employees", "contractors"]},
        "size": min(max_results, 30),
        "from": 0,
        "sort": "relevance",
    }
    try:
        r = session.post(
            url,
            json=payload,
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.warning(f"  Torre.co: {e}")
        return []

    # Si la API responde algo que no es un objeto, .get() lanzaría AttributeError
    # y se caería toda la búsqueda, no solo Torre.
    if not isinstance(data, dict):
        logger.warning(f"  Torre.co: respuesta inesperada ({type(data).__name__})")
        return []

    results = []
    for item in (data.get("results") or [])[:max_results]:
        if not isinstance(item, dict):
            continue
        opp  = item.get("opportunity") or {}
        org  = (opp.get("organizations") or [{}])[0] or {}
        comp = opp.get("compensation") or {}

        # Los montos pueden venir como texto o como palabra; int() directo reventaba.
        mn = _entero_o_none(comp.get("minAmount"))
        mx = _entero_o_none(comp.get("maxAmount"))
        salary = None
        if mn:
            cur = comp.get("currency") or "USD"
            salary = f"{cur} {mn:,}–{mx:,}/año" if mx else f"{cur} {mn:,}+/año"

        opp_id = opp.get("id") or ""
        # `details` puede venir con valor None, y entonces .get() encadenado falla.
        detalles = opp.get("details") or {}
        results.append(JobListing(
            title=_clean(opp.get("objective")) or "Sin título",
            company=_clean(org.get("name")) or "Empresa no especificada",
            location="100% Remoto · LATAM",
            platform="Torre.co",
            url=f"https://torre.co/jobs/{opp_id}",
            description=_clean(detalles.get("description") if isinstance(detalles, dict) else "")[:300],
            salary=salary,
        ))
    logger.info(f"  Torre.co: {len(results)} encontradas")
    return results


# ── RemoteOK (API JSON — empleos remotos internacionales) ────────────────────

def scrape_remoteok(
    keywords: str,
    location: str = "",
    max_results: int = 20,
    remote: bool = True,
    session: Optional[requests.Session] = None,
) -> List[JobListing]:
    """
    RemoteOK — directorio global de empleos 100% remotos.
    API pública que devuelve JSON.
    """
    session = session or requests.Session()
    tags = keywords.lower().replace(" ", "+")
    url  = f"https://remoteok.com/api?tags={tags}&location=anywhere"
    try:
        r = session.get(
            url,
            headers={**HEADERS, "Accept": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.warning(f"  RemoteOK: {e}")
        return []

    # La API devuelve una lista con metadatos en el índice 0. Cuando algo va mal
    # (límite de peticiones, mantenimiento) responde un dict, y cortarlo con
    # data[1:...] lanzaba KeyError y tumbaba la búsqueda entera, no solo RemoteOK.
    if not isinstance(data, list):
        logger.warning(f"  RemoteOK: respuesta inesperada ({type(data).__name__})")
        return []

    results = []
    for job in data[1:max_results + 1]:   # data[0] es metadatos
        if not isinstance(job, dict):
            continue
        sal_min = _entero_o_none(job.get("salary_min"))
        sal_max = _entero_o_none(job.get("salary_max"))
        salary = None
        if sal_min:
            salary = (f"USD {sal_min:,}–{sal_max:,}/año" if sal_max
                      else f"USD {sal_min:,}+/año")

        raw_desc = job.get("description") or ""
        desc_clean = _clean(BeautifulSoup(raw_desc, "lxml").get_text())[:300]
        job_url = job.get("url") or f"https://remoteok.com/jobs/{job.get('id', '')}"

        results.append(JobListing(
            # `or` y no el default de .get(): la clave puede venir con valor None,
            # y .get(k, default) solo usa el default si la clave NO existe. Un
            # title en None choca contra el NOT NULL de la tabla.
            title=_clean(job.get("position")) or "Sin título",
            company=_clean(job.get("company")) or "Empresa no especificada",
            location="100% Remoto",
            platform="RemoteOK",
            url=job_url,
            description=desc_clean,
            salary=salary,
        ))
    logger.info(f"  RemoteOK: {len(results)} encontradas")
    return results


# ── Indeed Colombia ───────────────────────────────────────────────────────────

def scrape_indeed_co(
    keywords: str,
    location: str = "",
    max_results: int = 20,
    remote: bool = True,
    session: Optional[requests.Session] = None,
) -> List[JobListing]:
    """Indeed Colombia — co.indeed.com, filtra trabajo remoto."""
    session = session or requests.Session()
    params  = {"q": keywords, "remotejob": "1", "lang": "es"}
    url     = "https://co.indeed.com/jobs?" + urlencode(params)
    logger.info(f"  Indeed CO: {url}")

    soup = _fetch(url, session)
    if not soup:
        return []

    cards = (
        soup.select("div.job_seen_beacon") or
        soup.select("td.resultContent") or
        soup.select("div[data-testid='job-card']")
    )
    if not cards:
        logger.warning("  Indeed CO: sin resultados")
        return []

    results = []
    for card in cards[:max_results]:
        title_el = card.select_one("h2 span[title]") or card.select_one("h2 a span")
        title    = (title_el.get("title") or _clean(title_el.get_text())) if title_el else _first(card, "h2")
        company  = _first(card, "[data-testid='company-name']", "span.company", "[class*=companyName]")
        salary   = _first(card, "[data-testid='attribute_snippet_testid']", "[class*=salary]") or None
        desc     = _first(card, "[class*=summary]", "ul.jobCardShelfContainer")[:280]

        link = card.find("a", href=True)
        href = link["href"] if link else ""
        if href and not href.startswith("http"):
            href = "https://co.indeed.com" + href

        if title and href:
            results.append(JobListing(
                title=title, company=company or "Empresa no especificada",
                location="Remoto · Colombia",
                platform="Indeed Colombia",
                url=href, description=desc, salary=salary,
            ))
    return results


# ── Computrabajo Colombia ─────────────────────────────────────────────────────

def scrape_computrabajo_co(
    keywords: str,
    location: str = "",
    max_results: int = 20,
    remote: bool = True,
    session: Optional[requests.Session] = None,
) -> List[JobListing]:
    """Computrabajo Colombia — trabajo en casa / remoto."""
    session = session or requests.Session()
    q   = keywords.lower().replace(" ", "-")
    url = f"https://www.computrabajo.com.co/trabajo-de-{q}-trabajo-en-casa"
    logger.info(f"  Computrabajo CO: {url}")

    soup = _fetch(url, session)
    if not soup:
        return []

    cards = (
        soup.select("article[id^='p']") or
        soup.select("article.box_offer") or
        soup.select("[data-component='jobCard']")
    )
    if not cards:
        logger.warning("  Computrabajo CO: sin resultados")
        return []

    results = []
    for card in cards[:max_results]:
        link  = card.find("a", href=True)
        title = (link.get("title") or "").strip() or _first(card, "h2", "h3")
        company = _first(card, "[class*=company]", "[class*=empresa]")
        salary  = _first(card, "[class*=salary]", "[class*=salario]") or None
        desc    = _first(card, "p", "[class*=desc]")[:280]

        href = link["href"] if link else ""
        if href and not href.startswith("http"):
            href = "https://www.computrabajo.com.co" + href

        if title and href:
            results.append(JobListing(
                title=title, company=company or "Empresa no especificada",
                location="Teletrabajo · Colombia",
                platform="Computrabajo CO",
                url=href, description=desc, salary=salary,
            ))
    return results


# ── Get on Board (empleos tech LATAM, muchos remotos) ────────────────────────

def scrape_getonboard(
    keywords: str,
    location: str = "",
    max_results: int = 20,
    remote: bool = True,
    session: Optional[requests.Session] = None,
) -> List[JobListing]:
    """Get on Board — plataforma tech LATAM, gran oferta remota."""
    session = session or requests.Session()
    params  = {"query": keywords, "remote": "1", "lang": "es"}
    url     = "https://www.getonbrd.com/jobs/search?" + urlencode(params)
    logger.info(f"  GetOnBoard: {url}")

    soup = _fetch(url, session)
    if not soup:
        return []

    cards = (
        soup.select("a[class*='gb-job']") or
        soup.select("div[class*='job-card']") or
        soup.select("article[class*='job']") or
        soup.select("[data-gb-component='job-row']")
    )
    if not cards:
        logger.warning("  GetOnBoard: sin resultados")
        return []

    results = []
    for card in cards[:max_results]:
        title   = _first(card, "h3", "h2", "[class*=title]", "[class*=name]")
        company = _first(card, "[class*=company]", "[class*=team]", "p")
        salary  = _first(card, "[class*=salary]", "[class*=comp]") or None

        href = card.get("href") or (card.find("a") or {}).get("href", "")
        if href and not href.startswith("http"):
            href = "https://www.getonbrd.com" + href

        if title and href:
            results.append(JobListing(
                title=title, company=company or "Empresa no especificada",
                location="Remoto · LATAM",
                platform="Get on Board",
                url=href, description="", salary=salary,
            ))
    return results


# ── Actualizar PLATFORMS y definir preset Colombia ────────────────────────────

PLATFORMS.update({
    "torre":             scrape_torre_co,
    "remoteok":          scrape_remoteok,
    "indeed_co":         scrape_indeed_co,
    "computrabajo_co":   scrape_computrabajo_co,
    "getonboard":        scrape_getonboard,
})

# ── Remotive (API JSON, siempre muestra salario USD) ─────────────────────────

def scrape_remotive(
    keywords: str,
    location: str = "",
    max_results: int = 20,
    remote: bool = True,
    session: Optional[requests.Session] = None,
) -> List[JobListing]:
    """Remotive — API pública JSON, muchos salarios en USD explícitos."""
    session = session or requests.Session()
    url = f"https://remotive.com/api/remote-jobs?search={quote_plus(keywords)}&limit={max_results}"
    try:
        r = session.get(url, headers={**HEADERS, "Accept": "application/json"}, timeout=15)
        r.raise_for_status()
        jobs = r.json().get("jobs", [])
    except Exception as e:
        logger.warning(f"  Remotive: {e}")
        return []

    # La clave "jobs" puede llegar como null; cortar None revienta aquí afuera
    # del try y se llevaría toda la búsqueda por delante.
    if not isinstance(jobs, list):
        logger.warning(f"  Remotive: respuesta inesperada ({type(jobs).__name__})")
        return []

    results = []
    for job in jobs[:max_results]:
        if not isinstance(job, dict):
            continue
        raw_desc = job.get("description") or ""
        desc = _clean(BeautifulSoup(raw_desc, "lxml").get_text())[:300]
        salary = (job.get("salary") or "").strip() or None
        titulo = _clean(job.get("title")) or "Sin título"
        results.append(JobListing(
            title=titulo,
            company=_clean(job.get("company_name")) or "Empresa no especificada",
            location="100% Remote",
            platform="Remotive",
            url=job.get("url") or "",
            description=desc,
            salary=salary,
        ))
    logger.info(f"  Remotive: {len(results)} encontradas")
    return results


# ── We Work Remotely (HTML, empleos bien pagados en USD) ─────────────────────

def scrape_weworkremotely(
    keywords: str,
    location: str = "",
    max_results: int = 20,
    remote: bool = True,
    session: Optional[requests.Session] = None,
) -> List[JobListing]:
    """We Work Remotely — directorio premium de empleos remotos con salarios USD."""
    session = session or requests.Session()
    url = f"https://weworkremotely.com/remote-jobs/search?term={quote_plus(keywords)}"
    logger.info(f"  WWR: {url}")
    soup = _fetch(url, session)
    if not soup:
        return []

    # WWR: <section class="jobs"> > <article>
    articles = (
        soup.select("section.jobs article") or
        soup.select("ul.jobs-container li") or
        soup.select("article[class*='job']")
    )
    if not articles:
        logger.warning("  WWR: sin resultados")
        return []

    results = []
    for art in articles[:max_results]:
        link = art.find("a", href=True)
        title = _first(art, "span.title", "h2", "h3", "span[class*=title]")
        company = _first(art, "span.company", "span[class*=company]")
        href = link["href"] if link else ""
        if href and not href.startswith("http"):
            href = "https://weworkremotely.com" + href
        if title and href:
            results.append(JobListing(
                title=title,
                company=company or "Empresa no especificada",
                location="100% Remote · USD",
                platform="We Work Remotely",
                url=href,
                description="",
                salary=None,
            ))
    logger.info(f"  WWR: {len(results)} encontradas")
    return results


# ── Himalayas.app (Next.js — extrae JSON embebido) ────────────────────────────

def scrape_himalayas(
    keywords: str,
    location: str = "",
    max_results: int = 20,
    remote: bool = True,
    session: Optional[requests.Session] = None,
) -> List[JobListing]:
    """Himalayas.app — plataforma premium con salarios USD siempre visibles."""
    import json as _json
    session = session or requests.Session()
    url = f"https://himalayas.app/jobs?q={quote_plus(keywords)}&location=anywhere"
    logger.info(f"  Himalayas: {url}")
    soup = _fetch(url, session)
    if not soup:
        return []

    results = []

    # Intentar extraer datos del script Next.js __NEXT_DATA__
    nxt = soup.find("script", {"id": "__NEXT_DATA__"})
    if nxt:
        try:
            data = _json.loads(nxt.string)
            pp = data.get("props", {}).get("pageProps", {})
            raw_jobs = (
                pp.get("jobs") or
                pp.get("jobListings") or
                pp.get("initialJobs") or []
            )
            for job in raw_jobs[:max_results]:
                comp = job.get("company") or {}
                comp_name = comp.get("name", "") if isinstance(comp, dict) else str(comp)
                sal = job.get("salary") or job.get("salaryRange") or job.get("compensation") or None
                jid = job.get("slug") or job.get("id") or ""
                results.append(JobListing(
                    title=job.get("title") or job.get("role") or "",
                    company=comp_name or "Empresa no especificada",
                    location="100% Remote · USD",
                    platform="Himalayas",
                    url=job.get("url") or f"https://himalayas.app/jobs/{jid}",
                    description=_clean(str(job.get("description", "")))[:300],
                    salary=str(sal).strip() if sal else None,
                ))
            if results:
                logger.info(f"  Himalayas (Next.js): {len(results)} encontradas")
                return results
        except Exception as e:
            logger.debug(f"  Himalayas __NEXT_DATA__ falló: {e}")

    # Fallback: HTML scraping
    cards = (
        soup.select("article[class*='job']") or
        soup.select("div[class*='job-card']") or
        soup.select("li[class*='job']")
    )
    for card in cards[:max_results]:
        title   = _first(card, "h2", "h3", "[class*=title]", "[class*=role]")
        company = _first(card, "[class*=company]", "[class*=org]")
        salary  = _first(card, "[class*=salary]", "[class*=comp]") or None
        link    = card.find("a", href=True)
        href    = link["href"] if link else ""
        if href and not href.startswith("http"):
            href = "https://himalayas.app" + href
        if title and href:
            results.append(JobListing(
                title=title, company=company or "Empresa no especificada",
                location="100% Remote · USD",
                platform="Himalayas",
                url=href, description="", salary=salary,
            ))

    logger.info(f"  Himalayas (HTML): {len(results)} encontradas")
    return results


# ── Registrar todas las plataformas ──────────────────────────────────────────

PLATFORMS.update({
    "remotive":         scrape_remotive,
    "weworkremotely":   scrape_weworkremotely,
    "himalayas":        scrape_himalayas,
})

# ── Presets de plataformas ────────────────────────────────────────────────────

# Colombianos buscando remoto LATAM
COLOMBIA_REMOTE_PLATFORMS = [
    "torre",            # Mejor para LATAM tech
    "remoteok",         # Internacional con salarios en USD
    "getonboard",       # LATAM tech con muchos remotos
    "indeed_co",        # Gran volumen Colombia
    "computrabajo_co",  # Tradicional Colombia
]

# Plataformas USD — salarios en dólares, audiencia global
USD_PLATFORMS = [
    "remotive",         # API JSON, salarios USD explícitos
    "remoteok",         # USD, tech-focused
    "weworkremotely",   # USD premium jobs
    "himalayas",        # USD, salarios visibles
    "torre",            # LATAM con muchos USD
    "getonboard",       # LATAM/global remote
]

# Cobertura máxima — todas las plataformas sin duplicar
ALL_REMOTE_PLATFORMS = list(dict.fromkeys(
    USD_PLATFORMS + COLOMBIA_REMOTE_PLATFORMS
))  # mantiene orden y elimina duplicados

# ── Presets de keywords ───────────────────────────────────────────────────────

# Español — plataformas LATAM
KEYWORDS_ES = [
    "analista requerimientos",
    "analista funcional",
    "analista sistemas",
    "analista de negocios",
    "ingeniero requerimientos",
]

# Inglés — plataformas USD/globales
KEYWORDS_EN = [
    "requirements analyst",
    "business analyst",
    "systems analyst",
    "requirements engineer",
    "functional analyst",
    "product analyst",
    "business systems analyst",
]

# Perfil IA / Python / datos — el otro lado del perfil técnico
KEYWORDS_IA_EN = [
    "python developer",
    "ai engineer",
    "prompt engineer",
    "machine learning engineer",
    "computer vision engineer",
    "automation engineer",
    "data analyst",
    "backend developer python",
]

KEYWORDS_IA_ES = [
    "desarrollador python",
    "ingeniero de datos",
    "automatizacion procesos",
    "analista de datos",
]

KEYWORDS_IA = KEYWORDS_IA_EN + KEYWORDS_IA_ES

# Bilingüe completo (sin duplicados)
BILINGUAL_KEYWORDS = KEYWORDS_EN + KEYWORDS_ES

# Backwards compat
REQUERIMIENTOS_KEYWORDS = ["analista requerimientos", "business analyst",
                            "analista funcional", "requirements analyst",
                            "analista sistemas"]




def search_colombia_remote(
    keywords: str,
    extra_keywords: Optional[List[str]] = None,
    max_per_platform: int = 15,
    verbose: bool = True,
) -> List[JobListing]:
    """
    Búsqueda optimizada para colombianos: 100% remoto, plataformas LATAM.
    Busca con múltiples variantes de keywords y deduplica resultados.
    """
    all_keywords = [keywords] + (extra_keywords or [])
    session = requests.Session()
    results = []
    seen    = set()

    for kw in all_keywords:
        if verbose:
            print(f"\n  🔑 Keywords: \"{kw}\"")
        for name in COLOMBIA_REMOTE_PLATFORMS:
            fn = PLATFORMS[name]
            if verbose:
                print(f"     🔎 {name.upper()}…", end=" ", flush=True)
            try:
                found = fn(keywords=kw, max_results=max_per_platform,
                           remote=True, session=session)
                new   = [j for j in found if j.url not in seen]
                seen.update(j.url for j in new)
                results.extend(new)
                if verbose:
                    print(f"{len(new)} nuevas")
                _pause()
            except Exception as e:
                logger.error(f"Error en {name}: {e}")
                if verbose:
                    print(f"✗ {e}")

    return results


def fetch_full_description(url: str) -> str:
    """Descarga la descripción completa de una oferta por URL."""
    try:
        session = requests.Session()
        soup = _fetch(url, session)
        if not soup:
            return ""
        # Quitar scripts, estilos, nav, footer
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        # Buscar el contenedor principal de la oferta
        container = (
            soup.select_one("section[class*=description]") or
            soup.select_one("div[class*=description]") or
            soup.select_one("div[class*=offer]") or
            soup.select_one("div[class*=vacancy]") or
            soup.select_one("main") or
            soup.body
        )
        text = _clean(container.get_text(separator="\n")) if container else ""
        return text[:3000]
    except Exception:
        return ""
