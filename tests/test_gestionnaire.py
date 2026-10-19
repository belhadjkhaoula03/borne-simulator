import json

from domaine.entites import Consommation


def telemetrie(mqtt):
    msgs = [json.loads(m) for t, m, _ in mqtt.envoyes if t.endswith("/telemetrie")]
    return msgs[-1]


def test_releve_persiste_et_publie_par_ressource(borne, mqtt, dao):
    borne._publier_releve()
    tel = telemetrie(mqtt)
    assert tel["borne"] == "T01" and tel["prise_active"] is True
    elec = tel["ressources"]["ELECTRICITE"]
    assert 1.0 <= elec["quantite_instantanee"] <= 2.0
    assert elec["unite"] == "kWh" and tel["ressources"]["EAU"]["unite"] == "litres"
    assert elec["cout_cumule_simule"] == round(elec["quantite_cumulee"] * 0.5, 4)
    assert set(dao.totaux("RES-T01")) == {"ELECTRICITE", "EAU"}
    assert dao.compter() == 2


def test_cumul_s_additionne(borne, mqtt):
    borne._publier_releve()
    borne._publier_releve()
    tel = telemetrie(mqtt)["ressources"]["EAU"]
    assert tel["quantite_cumulee"] >= 2 * 3.0 - 0.01


def test_prise_coupee_arrete_la_consommation(borne, mqtt, dao):
    borne._traiter_message("port/bornes/T01/commandes/couper", '{"correlation_id": "c1"}')
    avant = dao.compter()
    borne._publier_releve()
    tel = telemetrie(mqtt)
    assert tel["prise_active"] is False
    assert tel["ressources"]["EAU"]["quantite_instantanee"] == 0.0
    assert dao.compter() == avant                      # rien d'enregistré
    reponse = [json.loads(m) for t, m, _ in mqtt.envoyes if t.endswith("couper/reponse")][0]
    assert reponse == {"statut": "coupee", "correlation_id": "c1"}


def test_reactivation(borne, mqtt, dao):
    borne._traiter_message("port/bornes/T01/commandes/couper", "{}")
    borne._traiter_message("port/bornes/T01/commandes/activer", "{}")
    borne._publier_releve()
    assert telemetrie(mqtt)["prise_active"] is True and dao.compter() == 2


def test_commande_obtenir_consommation(borne, mqtt):
    borne._publier_releve()
    borne._traiter_message("port/bornes/T01/commandes/obtenir_consommation",
                           '{"correlation_id": "abc"}')
    topic, msg, _ = mqtt.envoyes[-1]
    corps = json.loads(msg)
    assert topic.endswith("obtenir_consommation/reponse") and corps["correlation_id"] == "abc"
    assert set(corps["cumul_par_ressource"]) == {"ELECTRICITE", "EAU"}


def test_obtenir_consommation_sans_donnees_repond_erreur(borne, mqtt):
    borne._traiter_message("port/bornes/T01/commandes/obtenir_consommation", "")
    assert "erreur" in json.loads(mqtt.envoyes[-1][1])


def test_payload_invalide_ne_plante_pas(borne, mqtt):
    for payload in ("pas du json", "[1, 2]", "null"):
        borne._traiter_message("port/bornes/T01/commandes/activer", payload)
    assert len([1 for t, *_ in mqtt.envoyes if t.endswith("activer/reponse")]) == 3


def test_config_souhaitee_est_acquittee_en_retained(borne, mqtt):
    borne._traiter_message("port/bornes/T01/config/souhaitee", '{"version": "2.0"}')
    topic, msg, retain = mqtt.envoyes[-1]
    assert topic.endswith("config/appliquee") and retain
    assert json.loads(msg)["version"] == "2.0"


def test_cumul_restaure_apres_redemarrage(borne, dao):
    from datetime import datetime, timezone
    t = datetime.now(timezone.utc)
    dao.save(Consommation(None, "RES-T01", t, t, 10.0, "EAU"))
    borne._restaurer_cumul()
    assert borne._cumul["EAU"] == 10.0 and borne._cumul["ELECTRICITE"] == 0.0


def test_un_releve_en_erreur_ne_tue_pas_le_thread(borne, dao):
    dao.deconnecter()                                  # le DAO lèvera RuntimeError
    borne._cycle_releve()                              # ne doit pas propager
