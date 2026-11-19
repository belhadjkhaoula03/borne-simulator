from dataclasses import dataclass
from typing import Callable, Protocol

from domaine.entites import TarifHoraire, ReservationCreneau


@dataclass(frozen=True)
class ProprietesDesirees:
    tarif: TarifHoraire | None
    reservations: tuple[ReservationCreneau, ...]
    version: int


class IRecepteurProprietesDesirees(Protocol):
    def demarrer(self, on_nouvelle_config: Callable[[ProprietesDesirees], None]) -> None: ...


class IRapporteurEtat(Protocol):
    def rapporter(self, etat: dict) -> None: ...