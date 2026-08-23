import sqlite3
from typing import List, Optional, Dict, Any
from config import DB_PATH


def init_db() -> None:
    """Crea las tablas si no existen."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS job_queue (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            title          TEXT    NOT NULL,
            company        TEXT,
            location       TEXT,
            platform       TEXT,
            url            TEXT    UNIQUE,
            description    TEXT,
            salary         TEXT,
            found_date     TEXT    DEFAULT (date('now')),
            match_score    INTEGER,
            analyzed       INTEGER DEFAULT 0,
            application_id INTEGER,
            FOREIGN KEY (application_id) REFERENCES applications(id)
        );

        CREATE TABLE IF NOT EXISTS applications (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            company          TEXT    NOT NULL,
            position         TEXT    NOT NULL,
            platform         TEXT    DEFAULT 'LinkedIn',
            url              TEXT,
            applied_date     TEXT    DEFAULT (date('now')),
            status           TEXT    DEFAULT 'aplicado',
            cv_filename      TEXT,
            cover_letter     INTEGER DEFAULT 0,
            salary_expected  TEXT,
            location         TEXT,
            notes            TEXT,
            match_score      INTEGER,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS job_analyses (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id   INTEGER,
            offer_text       TEXT,
            analysis_json    TEXT,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (application_id) REFERENCES applications(id)
        );
    """)

    conn.commit()
    conn.close()


VALID_STATUSES = [
    "aplicado", "vista", "entrevista_rh", "entrevista_tecnica",
    "oferta", "rechazado", "retirado",
]


def add_application(
    company: str,
    position: str,
    platform: str = "LinkedIn",
    url: Optional[str] = None,
    cv_filename: Optional[str] = None,
    cover_letter: bool = False,
    salary_expected: Optional[str] = None,
    location: Optional[str] = None,
    notes: Optional[str] = None,
    match_score: Optional[int] = None,
) -> int:
    """Registra una nueva aplicación. Devuelve el ID creado."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO applications
           (company, position, platform, url, cv_filename, cover_letter,
            salary_expected, location, notes, match_score)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (company, position, platform, url, cv_filename,
         int(cover_letter), salary_expected, location, notes, match_score),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_status(app_id: int, status: str, notes: Optional[str] = None) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"Estado inválido. Opciones: {', '.join(VALID_STATUSES)}")
    conn = sqlite3.connect(DB_PATH)
    if notes:
        conn.execute(
            "UPDATE applications SET status=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, notes, app_id),
        )
    else:
        conn.execute(
            "UPDATE applications SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, app_id),
        )
    conn.commit()
    conn.close()


def set_cv_filename(app_id: int, filename: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE applications SET cv_filename=? WHERE id=?", (filename, app_id))
    conn.commit()
    conn.close()


def set_cover_letter(app_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE applications SET cover_letter=1 WHERE id=?", (app_id,))
    conn.commit()
    conn.close()


def get_applications(status: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if status:
        rows = conn.execute(
            "SELECT * FROM applications WHERE status=? ORDER BY applied_date DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM applications ORDER BY applied_date DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats() -> Dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    total        = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    by_status    = dict(conn.execute("SELECT status, COUNT(*) FROM applications GROUP BY status").fetchall())
    by_platform  = dict(conn.execute("SELECT platform, COUNT(*) FROM applications GROUP BY platform").fetchall())
    avg_match    = conn.execute("SELECT AVG(match_score) FROM applications WHERE match_score IS NOT NULL").fetchone()[0]
    conn.close()
    return {
        "total":          total,
        "by_status":      by_status,
        "by_platform":    by_platform,
        "avg_match_score": round(avg_match, 1) if avg_match else None,
    }


def save_analysis(application_id: int, offer_text: str, analysis_json: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO job_analyses (application_id, offer_text, analysis_json) VALUES (?,?,?)",
        (application_id, offer_text, analysis_json),
    )
    conn.commit()
    conn.close()


# ── Cola de ofertas ───────────────────────────────────────────────────────────

def save_job_to_queue(job, match_score: Optional[int] = None) -> int:
    """Guarda una oferta en la cola. Retorna ID o -1 si es duplicado."""
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute("""
            INSERT OR IGNORE INTO job_queue
            (title, company, location, platform, url, description, salary, match_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (job.title, job.company, job.location, job.platform,
              job.url, job.description, job.salary, match_score))
        new_id = cur.lastrowid if cur.rowcount > 0 else -1
        conn.commit()
        return new_id
    except Exception:
        return -1
    finally:
        conn.close()


def get_job_queue(analyzed: bool = False) -> List[Dict[str, Any]]:
    """Retorna ofertas de la cola filtradas por estado de análisis."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM job_queue WHERE analyzed = ? ORDER BY found_date DESC, match_score DESC",
        (1 if analyzed else 0,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_job_analyzed(job_id: int, application_id: Optional[int] = None) -> None:
    conn = sqlite3.connect(DB_PATH)
    if application_id:
        conn.execute(
            "UPDATE job_queue SET analyzed=1, application_id=? WHERE id=?",
            (application_id, job_id)
        )
    else:
        conn.execute("UPDATE job_queue SET analyzed=1 WHERE id=?", (job_id,))
    conn.commit()
    conn.close()


def get_queue_stats() -> Dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    total   = conn.execute("SELECT COUNT(*) FROM job_queue").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM job_queue WHERE analyzed=0").fetchone()[0]
    by_plt  = dict(conn.execute("SELECT platform, COUNT(*) FROM job_queue GROUP BY platform").fetchall())
    conn.close()
    return {"total": total, "pending": pending, "by_platform": by_plt}
