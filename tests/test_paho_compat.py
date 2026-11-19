from types import SimpleNamespace

from infrastructure import paho_compat


def test_creer_client_avec_paho_2(monkeypatch):
    appels = {}

    class Client:
        def __init__(self, *, callback_api_version, client_id):
            appels.update(
                callback_api_version=callback_api_version,
                client_id=client_id,
            )

    version = object()
    monkeypatch.setattr(
        paho_compat.mqtt,
        "CallbackAPIVersion",
        SimpleNamespace(VERSION2=version),
        raising=False,
    )
    monkeypatch.setattr(paho_compat.mqtt, "Client", Client)

    client = paho_compat.creer_client("borne_A")

    assert isinstance(client, Client)
    assert appels == {
        "callback_api_version": version,
        "client_id": "borne_A",
    }


def test_creer_client_avec_paho_1(monkeypatch):
    class Client:
        def __init__(self, client_id):
            self.client_id = client_id

    monkeypatch.delattr(paho_compat.mqtt, "CallbackAPIVersion", raising=False)
    monkeypatch.setattr(paho_compat.mqtt, "Client", Client)

    client = paho_compat.creer_client("borne_A")

    assert isinstance(client, Client)
    assert client.client_id == "borne_A"
