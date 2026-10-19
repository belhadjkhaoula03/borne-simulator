import sqlite3
from datetime import datetime, timezone

from domaine.entites import Consommation
from infrastructure.dao_sqlite import DaoSqlite


def conso(q, res="EAU", reservation="R1"):
    t = datetime.now(timezone.utc)
    return Consommation(None, reservation, t, t, q, res)


def test_schema_cree_au_premier_demarrage(tmp_path):
    d = DaoSqlite(tmp_path / "sub" / "b.db")
    d.connecter()
    assert d.compter() == 0
    d.deconnecter()


def test_save_et_get_all(dao):
    dao.save(conso(1.5))
    [c] = dao.get_all("R1")
    assert (c.quantite, c.ressource, c.id) == (1.5, "EAU", 1)
    assert dao.get_all("AUTRE") == []


def test_totaux_par_ressource(dao):
    for q in (1, 2):
        dao.save(conso(q, "EAU"))
    dao.save(conso(5, "GAZ"))
    dao.save(conso(9, "EAU", reservation="R2"))
    assert dao.totaux("R1") == {"EAU": 3.0, "GAZ": 5.0}


def test_get_recent_ordre_chronologique_et_limite(dao):
    for q in range(1, 6):
        dao.save(conso(q))
    dao.save(conso(99, "GAZ"))
    assert [c.quantite for c in dao.get_recent("R1", "EAU", 3)] == [3, 4, 5]


def test_migration_base_v01_sans_colonne_ressource(tmp_path):
    chemin = tmp_path / "ancienne.db"
    conn = sqlite3.connect(chemin)
    conn.execute("CREATE TABLE consommation (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                 " id_reservation TEXT, date_debut TEXT, date_fin TEXT, quantite REAL)")
    conn.execute("INSERT INTO consommation (id_reservation,date_debut,date_fin,quantite)"
                 " VALUES ('R1','2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00',4.2)")
    conn.commit()
    conn.close()
    d = DaoSqlite(chemin)
    d.connecter()
    assert d.get_all("R1")[0].ressource == ""       # ancien relevé conservé
    assert d.totaux("R1") == {}                     # mais exclu des totaux par ressource
    d.save(conso(1))
    assert d.compter() == 2
    d.deconnecter()
