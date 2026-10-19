"""Entités du domaine du simulateur de bornes énergétiques.

Ces dataclasses ne dépendent de RIEN (ni paho-mqtt, ni sqlite3) : c'est le
centre de l'architecture en oignons. Elles sont issues du diagramme de
classes manuscrit du projet.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import List


class Energie(enum.Enum):
    """Ressources distribuées par une borne. Énumération extensible :
    ajouter une ressource ne casse rien (principe ouvert/fermé)."""
    ELECTRICITE = "ELECTRICITE"
    EAU = "EAU"
    GAZ = "GAZ"


# Unité d'affichage par ressource (partagée par le simulateur et le portail web).
UNITES = {"ELECTRICITE": "kWh", "EAU": "litres", "GAZ": "m3"}


@dataclass
class Tranche:
    """Intervalle [tranche_min, tranche_max[ d'une grille tarifaire."""
    id_tranche: str
    tranche_min: float
    tranche_max: float
    prix_unitaire: float


@dataclass
class Tarif:
    """Grille tarifaire par ressource = liste ORDONNÉE de tranches.
    Modélisée dès maintenant (stockée en config) pour préparer l'UC-02."""
    id_tarif: str
    tranches: List[Tranche] = field(default_factory=list)


@dataclass
class Reservation:
    """Réservation locale simulée."""
    id: str
    tarif: Tarif
    id_plaisancier: str
    date_debut: datetime
    date_fin: datetime


@dataclass
class Consommation:
    """Objet persistant : c'est la seule entité réellement stockée en
    base (table consommation). C'est elle que Calculator interroge."""
    id: int | None
    id_reservation: str
    date_debut: datetime
    date_fin: datetime
    quantite: float
    ressource: str = ""


@dataclass
class Seuil:
    """Prépare l'UC-04 (alerte/coupure). Stocké en config pour l'instant."""
    seuil_quantite: float
    seuil_cout: float


@dataclass
class Config:
    """Identité et paramètres d'une borne (miroir du fichier JSON)."""
    id_borne: str
    hote: str
    port: int
    identifiants: dict = field(default_factory=dict)
    ressources: List[str] = field(default_factory=list)
    intervalle_releve: int = 10
