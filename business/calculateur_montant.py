"""Calcul du montant d'une consommation selon le tarif horaire (TP IoT Hub)."""
from decimal import Decimal, ROUND_HALF_UP


class CalculateurMontant:
    def calculer(self, quantite, tarif, instant) -> float:
        """montant = énergie x prix applicable à l'heure de la mesure,
        arrondi à 3 décimales (arrondi commercial)."""
        prix = tarif.prix_a(instant.time())          # .time() = heure sans fuseau
        brut = Decimal(str(quantite.kwh)) * Decimal(str(prix))
        return float(brut.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))