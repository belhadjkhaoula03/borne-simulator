import threading
from typing import Callable, TypeVar

from domaine.entites import Borne

T = TypeVar("T")


class AccesBorne:
    def __init__(self, borne: Borne):
        self._borne = borne
        self._verrou = threading.Lock()

    def executer(self, action: Callable[[Borne], T]) -> T:
        with self._verrou:
            return action(self._borne)
