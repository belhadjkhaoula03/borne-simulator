import threading


class RapporterEtat:
    def __init__(self, acces, rapporteur):
        self._acces, self._rapporteur = acces, rapporteur
        self._version = 0
        self._verrou_version = threading.Lock()

    def executer(self, version_desiree_traitee=None):
        with self._verrou_version:
            if version_desiree_traitee is not None:
                self._version = version_desiree_traitee
            version = self._version
        etat = self._acces.executer(
            lambda borne: {
                "etat": borne.etat.value,
                "versionDesireeTraitee": version,
            })
        self._rapporteur.rapporter(etat)
