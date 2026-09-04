"""Pruebas de src/tracker.py — la capa de base de datos.

Cada prueba usa una base temporal, así que no toca la real del usuario.

Correr:  python -m pytest tests/test_tracker.py -v
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import config
import src.tracker as tracker


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Base de datos temporal y vacía para cada prueba."""
    ruta = str(tmp_path / "test.db")
    monkeypatch.setattr(config, "DB_PATH", ruta)
    monkeypatch.setattr(tracker, "DB_PATH", ruta)
    tracker.init_db()
    return ruta


class Oferta:
    """Oferta mínima con los campos que lee save_job_to_queue."""
    def __init__(self, url="http://ejemplo.com/1"):
        self.title = "Dev Python"
        self.company = "ACME"
        self.location = "Remoto"
        self.platform = "test"
        self.url = url
        self.description = "descripción"
        self.salary = "USD 3000"


class OfertaRota:
    """Su salario revienta al leerse: simula un error REAL, no un duplicado."""
    def __init__(self, url="http://ejemplo.com/rota"):
        self.title = "T"; self.company = "C"; self.location = "L"
        self.platform = "P"; self.url = url; self.description = "D"

    @property
    def salary(self):
        raise ValueError("fallo real al leer el salario")


# ── get_stats: un promedio de 0 es un dato, no un "sin datos" ─────────────────

def test_promedio_cero_no_se_confunde_con_sin_datos(db):
    """Regresión: `if avg_match` descartaba el 0.0 y reportaba None."""
    tracker.add_application("E1", "Cargo", match_score=0)
    tracker.add_application("E2", "Cargo", match_score=0)
    assert tracker.get_stats()["avg_match_score"] == 0.0


def test_sin_aplicaciones_el_promedio_es_none(db):
    assert tracker.get_stats()["avg_match_score"] is None


def test_promedio_normal(db):
    tracker.add_application("E1", "Cargo", match_score=80)
    tracker.add_application("E2", "Cargo", match_score=60)
    assert tracker.get_stats()["avg_match_score"] == 70.0


def test_stats_cuenta_el_total(db):
    for i in range(3):
        tracker.add_application(f"E{i}", "Cargo")
    assert tracker.get_stats()["total"] == 3


# ── save_job_to_queue: un duplicado NO es lo mismo que un error ───────────────

def test_oferta_nueva_devuelve_id_positivo(db):
    assert tracker.save_job_to_queue(Oferta()) > 0


def test_oferta_duplicada_devuelve_menos_uno(db):
    tracker.save_job_to_queue(Oferta("http://x.com/1"))
    assert tracker.save_job_to_queue(Oferta("http://x.com/1")) == -1


def test_error_real_se_distingue_del_duplicado(db, capsys):
    """Regresión: antes ambos devolvían -1 y un fallo real pasaba inadvertido."""
    resultado = tracker.save_job_to_queue(OfertaRota())
    assert resultado == -2, "un error real debe devolver -2, no -1"
    assert "no se pudo guardar" in capsys.readouterr().err


def test_los_llamadores_pueden_seguir_contando_con_mayor_que_cero(db):
    """main.py cuenta las guardadas con `> 0`; ni -1 ni -2 deben colarse."""
    ofertas = [Oferta("http://a.com/1"), Oferta("http://a.com/1"), OfertaRota()]
    guardadas = sum(1 for o in ofertas if tracker.save_job_to_queue(o) > 0)
    assert guardadas == 1


# ── Estados y cola ────────────────────────────────────────────────────────────

def test_estado_invalido_se_rechaza(db):
    app_id = tracker.add_application("E", "Cargo")
    with pytest.raises(ValueError):
        tracker.update_status(app_id, "estado_inventado")


def test_estado_valido_se_guarda(db):
    app_id = tracker.add_application("E", "Cargo")
    tracker.update_status(app_id, "entrevista_tecnica")
    assert tracker.get_applications()[0]["status"] == "entrevista_tecnica"


def test_la_cola_separa_analizadas_de_pendientes(db):
    job_id = tracker.save_job_to_queue(Oferta("http://x.com/9"))
    assert len(tracker.get_job_queue(analyzed=False)) == 1
    tracker.mark_job_analyzed(job_id)
    assert len(tracker.get_job_queue(analyzed=False)) == 0
    assert len(tracker.get_job_queue(analyzed=True)) == 1


def test_init_db_se_puede_llamar_dos_veces(db):
    """Todos los comandos del CLI la llaman al arrancar."""
    tracker.init_db()
    tracker.init_db()
    assert tracker.get_stats()["total"] == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
