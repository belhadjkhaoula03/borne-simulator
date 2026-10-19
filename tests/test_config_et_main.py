import json

import pytest

import main
from infrastructure.config_file import ConfigFileDAO, ConfigurationInvalide
from infrastructure.settings import Settings


def ecrire(chemin, contenu):
    chemin.write_text(json.dumps(contenu), encoding="utf-8")
    return chemin


GLOBALE = {"nombre_bornes": 2, "bornes": ["A", "B"], "broker": {"hote": "h", "port": 1883}}


def test_config_globale_valide(tmp_path):
    assert main.charger_config_globale(ecrire(tmp_path / "s.json", GLOBALE))["nombre_bornes"] == 2


@pytest.mark.parametrize("modif", [
    {"nombre_bornes": 0}, {"nombre_bornes": 6}, {"nombre_bornes": "3"},
    {"bornes": ["A"]}, {"broker": {}},
])
def test_config_globale_invalide(tmp_path, modif):
    with pytest.raises(ConfigurationInvalide):
        main.charger_config_globale(ecrire(tmp_path / "s.json", {**GLOBALE, **modif}))


def test_config_globale_absente_ou_mal_formee(tmp_path):
    with pytest.raises(ConfigurationInvalide):
        main.charger_config_globale(tmp_path / "absent.json")
    (tmp_path / "x.json").write_text("{pas json")
    with pytest.raises(ConfigurationInvalide):
        main.charger_config_globale(tmp_path / "x.json")


def test_config_borne_cles_manquantes(tmp_path):
    with pytest.raises(ConfigurationInvalide, match="Clés manquantes"):
        ConfigFileDAO(ecrire(tmp_path / "b.json", {"id_borne": "A"})).lire()


def test_priorite_variables_d_environnement_sur_fichiers():
    borne = {"hote": "localhost", "port": 1111, "identifiants": {"username": "u", "password": "p"}}
    sans_env = main.resoudre_broker(Settings(), GLOBALE, borne)
    assert (sans_env["hote"], sans_env["port"], sans_env["username"]) == ("localhost", 1111, "u")
    avec_env = main.resoudre_broker(
        Settings.from_env({"MQTT_HOST": "mosquitto", "MQTT_PORT": "1883",
                           "MQTT_USERNAME": "svc", "MQTT_PASSWORD": "s3"}), GLOBALE, borne)
    assert avec_env == {"hote": "mosquitto", "port": 1883, "username": "svc", "password": "s3"}


def test_settings_defauts_et_booleens():
    s = Settings.from_env({"WEB_ENABLED": "false", "WEB_PORT": "9000", "DATA_DIR": "/d"})
    assert not s.web_enabled and s.web_port == 9000 and str(s.data_dir) == "/d"
    assert Settings.from_env({}).web_enabled
