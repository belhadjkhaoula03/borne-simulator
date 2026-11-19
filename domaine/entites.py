from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
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
# ---------------------------------------------------------------------------
# Modèle IoT Hub (TP) : tarif heures pleines/creuses, créneaux du Twin, Borne
# ---------------------------------------------------------------------------

class EtatBorne(enum.Enum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"


@dataclass(frozen=True)
class PlageHoraire:
    """Plage horaire [debut, fin[ ; gère le passage de minuit (22:00 -> 06:00)."""
    debut: time
    fin: time

    def contient(self, h: time) -> bool:
        if self.debut <= self.fin:
            return self.debut <= h < self.fin
        return h >= self.debut or h < self.fin


@dataclass(frozen=True)
class TarifHoraire:
    """Tarif heures pleines / heures creuses reçu par le Device Twin."""
    prix_pleines: float
    prix_creuses: float
    plages_creuses: tuple = ()

    def prix_a(self, h: time) -> float:
        creuse = any(p.contient(h) for p in self.plages_creuses)
        return self.prix_creuses if creuse else self.prix_pleines


@dataclass(frozen=True)
class ReservationCreneau:
    """Réservation telle que décrite dans le Twin (debut + dureeMinutes)."""
    id: str
    client_id: str
    debut: datetime          # avec fuseau horaire
    duree_minutes: float

    @property
    def fin(self) -> datetime:
        return self.debut + timedelta(minutes=self.duree_minutes)

    def est_active(self, instant: datetime) -> bool:
        return self.debut <= instant < self.fin

# domaine/entites.py
@dataclass(frozen=True)
class QuantiteEnergie:
    kwh: float
    def __post_init__(self):
        if self.kwh < 0:
            raise ValueError("L'énergie ne peut pas être négative")
        

@dataclass
class ConsommationSession:
    type_energie: str
    energie_kwh: float
    duree_minutes: float
    debut: datetime
    fin: datetime
    tarif_applique: float
    montant: float


@dataclass
class SessionRecharge:
    id: str
    client_id: str
    reservation_id: str
    debut: datetime
    consommations: list[ConsommationSession] = field(default_factory=list)

    @property
    def montant_total(self) -> float:
        return round(sum(c.montant for c in self.consommations), 3)


class Borne:
    """État de la borne partagé entre le thread du simulateur et la
    réception du Twin (l'accès concurrent est protégé par AccesBorne)."""

    def __init__(self, id_borne: str):
        self.id = id_borne
        self.etat = EtatBorne.ACTIVE
        self.tarif: TarifHoraire | None = None
        self.reservations: list[ReservationCreneau] = []
        self.session: SessionRecharge | None = None

    def appliquer_tarif(self, tarif: TarifHoraire) -> None:
        self.tarif = tarif

    def remplacer_reservations(self, reservations) -> None:
        self.reservations = list(reservations)

    def reservation_active(self, instant: datetime):
        return next((r for r in self.reservations if r.est_active(instant)), None)

    def demarrer_session(self, reservation, instant: datetime) -> SessionRecharge:
        if self.etat != EtatBorne.ACTIVE:
            raise ValueError("Borne désactivée")
        if not reservation.est_active(instant):
            raise ValueError("Réservation non active")
        self.session = SessionRecharge(
            f"S-{uuid.uuid4().hex[:8]}",
            reservation.client_id,
            reservation.id,
            instant,
        )
        return self.session

    def terminer_session(self) -> SessionRecharge | None:
        session, self.session = self.session, None
        return session

    def activer(self) -> bool:
        if self.etat == EtatBorne.ACTIVE:
            return False
        self.etat = EtatBorne.ACTIVE
        return True

    def desactiver(self) -> bool:
        if self.etat == EtatBorne.INACTIVE:
            return False
        self.etat = EtatBorne.INACTIVE
        self.terminer_session()
        return True
