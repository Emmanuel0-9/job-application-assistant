"""Pruebas de seguridad del saneador de nombres de archivo.

El nombre del .docx se arma con el nombre de la empresa, que viene de una oferta
scrapeada y pasa por la IA: es dato externo. Sin saneo, una empresa llamada
"../../.." haría que el archivo se escribiera fuera de output/.

Estas pruebas son adversariales a propósito: intentan escapar de la carpeta.

Correr:  python -m pytest tests/test_seguridad_nombres.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from config import OUTPUT_DIR
from src.cv_generator import _nombre_archivo_seguro

# Nombres reservados de Windows: escribir en ellos habla con un dispositivo,
# no crea un archivo. Es un riesgo propio de esta plataforma.
RESERVADOS_WINDOWS = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

ATAQUES = [
    ("../../../etc/passwd",                   "escape estilo unix"),
    ("..\\..\\..\\Windows\\System32\\x",      "escape estilo windows"),
    ("/etc/passwd",                            "ruta absoluta unix"),
    ("C:\\Windows\\evil.docx",                "ruta absoluta windows"),
    ("....//....//x.docx",                    "puntos y barras anidados"),
    ("...",                                    "solo puntos"),
    ("",                                       "cadena vacia"),
    (".env",                                   "archivo oculto"),
    ("cv\x00.docx",                           "byte nulo"),
    ("a" * 300 + ".docx",                     "nombre larguisimo"),
    ("Empresa S.A.S. - CV.docx",              "nombre legitimo con puntos"),
]


@pytest.mark.parametrize("entrada, caso", ATAQUES)
def test_ningun_nombre_escapa_de_output_dir(entrada, caso):
    """Pase lo que pase, el archivo debe quedar DENTRO de output/."""
    saneado = _nombre_archivo_seguro(entrada)
    destino = (OUTPUT_DIR / saneado).resolve()
    assert OUTPUT_DIR.resolve() in destino.parents, (
        f"'{caso}': el nombre {entrada!r} se saneó a {saneado!r} y escapó a {destino}"
    )


@pytest.mark.parametrize("entrada, caso", ATAQUES)
def test_el_nombre_saneado_no_tiene_separadores(entrada, caso):
    saneado = _nombre_archivo_seguro(entrada)
    assert "/" not in saneado and "\\" not in saneado, f"'{caso}': quedó un separador"
    assert ".." not in saneado.strip("."), f"'{caso}': quedaron dos puntos seguidos"


def test_nunca_devuelve_vacio():
    """Un nombre vacío rompería doc.save(); debe caer a un valor por defecto."""
    for entrada in ["", "...", "///", "\\\\", "..."]:
        assert _nombre_archivo_seguro(entrada), f"{entrada!r} produjo un nombre vacío"


def test_no_produce_nombres_reservados_de_windows():
    """CON, NUL, COM1... son dispositivos de Windows, no archivos.

    Medido en Windows 11 + Python 3.13: CON/PRN/COM1/AUX ya se escriben sin
    problema, pero "NUL" a secas se acepta y deja el archivo en 0 bytes — el CV
    se perdería sin que nadie se entere. Como la defensa cuesta dos líneas, se
    neutralizan todos y no solo NUL.
    """
    fallos = []
    for reservado in ["CON", "NUL", "COM1", "PRN", "AUX", "LPT1"]:
        for entrada in (reservado, f"{reservado}.docx"):
            saneado = _nombre_archivo_seguro(entrada)
            raiz = saneado.split(".")[0].upper()
            if raiz in RESERVADOS_WINDOWS:
                fallos.append(f"{entrada!r} -> {saneado!r}")
    assert not fallos, (
        "Nombres reservados de Windows sin neutralizar: " + ", ".join(fallos)
    )


def test_conserva_nombres_legitimos_legibles():
    """El saneo no debe destruir un nombre normal."""
    saneado = _nombre_archivo_seguro("CV_Emmanuel_Acme_Corp.docx")
    assert saneado == "CV_Emmanuel_Acme_Corp.docx"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
