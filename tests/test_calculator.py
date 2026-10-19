from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from business.calculator import Calculator
from domaine.entites import Consommation


def test_derniere_consommation_selon_date_fin(dao):
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i, q in enumerate((1.0, 7.5, 3.0)):       # insérées dans le désordre de dates
        dt = t0 + timedelta(minutes=[0, 10, 5][i])
        dao.save(Consommation(None, "R1", dt, dt, q, "EAU"))
    assert Calculator(dao).calculer_temps_reel("R1") == Decimal("7.5")


def test_erreur_si_aucune_consommation(dao):
    with pytest.raises(ValueError):
        Calculator(dao).calculer_temps_reel("VIDE")


def test_cumul_par_ressource(dao):
    t = datetime.now(timezone.utc)
    for q, r in ((1.25, "EAU"), (2.0, "EAU"), (4.0, "GAZ")):
        dao.save(Consommation(None, "R1", t, t, q, r))
    assert Calculator(dao).cumul_par_ressource("R1") == {"EAU": Decimal("3.25"),
                                                         "GAZ": Decimal("4.0")}
