import random


class MesureurSimule:
    PUISSANCES_KW = {"Electricite16A": 3.68}

    def mesurer(self, debut, fin) -> dict:
        heures = (fin - debut).total_seconds() / 3600
        return {type_energie: round(puissance * heures * random.uniform(0.6, 1.0), 3)
                for type_energie, puissance in self.PUISSANCES_KW.items()}
