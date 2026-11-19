from datetime import datetime, time, timezone

import pytest

from business.calculateur_montant import CalculateurMontant
from domaine.entites import PlageHoraire, QuantiteEnergie, TarifHoraire

# 0,30 €/kWh en heures pleines, 0,20 €/kWh en heures creuses (22h -> 6h)
TARIF = TarifHoraire(0.30, 0.20, (PlageHoraire(time(22, 0), time(6, 0)),))
CALC = CalculateurMontant()


def a(h, m=0):
    return datetime(2026, 10, 7, h, m, tzinfo=timezone.utc)


def test_heure_pleine():
    assert CALC.calculer(QuantiteEnergie(1.0), TARIF, a(14)) == 0.300


def test_heure_creuse():
    assert CALC.calculer(QuantiteEnergie(1.0), TARIF, a(23)) == 0.200


def test_limite_debut_creuse_incluse():       # 22:00 pile = creuse
    assert CALC.calculer(QuantiteEnergie(1.0), TARIF, a(22, 0)) == 0.200


def test_limite_fin_creuse_exclue():          # 06:00 pile = pleine
    assert CALC.calculer(QuantiteEnergie(1.0), TARIF, a(6, 0)) == 0.300


def test_plage_qui_passe_minuit():
    assert CALC.calculer(QuantiteEnergie(1.0), TARIF, a(0, 30)) == 0.200
    assert CALC.calculer(QuantiteEnergie(1.0), TARIF, a(3, 0)) == 0.200


def test_arrondi_3_decimales():               # 0,412 x 0,30 = 0,1236 -> 0,124
    assert CALC.calculer(QuantiteEnergie(0.412), TARIF, a(14)) == 0.124


def test_energie_nulle():
    assert CALC.calculer(QuantiteEnergie(0.0), TARIF, a(14)) == 0.0


def test_energie_negative_refusee():
    with pytest.raises(ValueError):
        QuantiteEnergie(-0.1)
