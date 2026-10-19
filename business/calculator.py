"""Classe Calculator (couche Business) — spécification exacte du diagramme.

Pure et testable : même entrée -> même sortie. Elle ne connaît que
l'interface IDAOConsommation (injection au constructeur = inversion de
contrôle).
"""
from decimal import Decimal
from typing import Dict, List

from domaine.entites import Consommation
from domaine.interfaces import IDAOConsommation


class Calculator:
    # attribut privé injecté via le constructeur (inversion de contrôle)
    _db_consommation: IDAOConsommation

    def __init__(self, c: IDAOConsommation):
        self._db_consommation = c

    def calculer_temps_reel(self, id_reservation: str) -> Decimal:
        consommations: List[Consommation] = self._db_consommation.get_all(id_reservation)
        if not consommations:
            raise ValueError(f"Aucune consommation en base pour la réservation {id_reservation}")
        # trier selon date_fin (décroissant)
        consommations.sort(key=lambda c: c.date_fin, reverse=True)
        # prendre la première = la consommation la plus récente
        derniere = consommations[0]
        # retourner la quantité (qt)
        return Decimal(str(derniere.quantite))

    def cumul_par_ressource(self, id_reservation: str) -> Dict[str, Decimal]:
        """Cumul de quantité par ressource (ELECTRICITE, EAU, GAZ) pour une réservation."""
        return {res: Decimal(str(round(qte, 3)))
                for res, qte in self._db_consommation.totaux(id_reservation).items()}
