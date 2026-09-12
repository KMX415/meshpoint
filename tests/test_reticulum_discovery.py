"""Interface contacts must remain opt-in and distinct from automatic peering."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.reticulum.backend import routes, state
from apps.reticulum.backend.config_routes import ReticulumUpdate
from apps.reticulum.backend.discovery import contact_address, public_interfaces
from apps.reticulum.backend.rns_config import render_config
from src.api.auth import dependencies
from src.api.auth.jwt_session import JwtSessionService

ADDRESS = "ab" * 16


@pytest.mark.parametrize("address", ["a" * 31, "a" * 33, "z" * 32, "<" + ADDRESS + ">", ADDRESS + "\ndiscoverable=Yes"])
def test_reject_invalid_contact(address):
    with pytest.raises(ValueError):
        contact_address(address)
    with pytest.raises(ValueError):
        ReticulumUpdate(rnode_discovery_lxmf_address=address)


def test_default_and_saved_contact_do_not_publish():
    for config in ({}, {"rnode_discovery_lxmf_address": ADDRESS}):
        text = render_config(config)
        assert "discover_interfaces = No" in text
        assert "autoconnect_discovered_interfaces = 0" in text
        assert "discoverable = Yes" not in text
        assert ADDRESS not in text


def test_listening_does_not_publish_or_enable_transport():
    text = render_config({"discover_interfaces": True})
    assert "discover_interfaces = Yes" in text
    assert "enable_transport = False" in text
    assert "discoverable = Yes" not in text
    assert "enabled = No" in text


def test_publication_requires_both_radio_and_contact():
    for fields in ({}, {"rnode_discovery_lxmf_address": ADDRESS}, {"rnode_enabled": True, "rnode_frequency_hz": 915000000}):
        with pytest.raises(ValueError):
            ReticulumUpdate(rnode_discovery_enabled=True, **fields)


def test_publication_is_scoped_to_rnode_and_can_be_revoked():
    cfg = dict(rnode_enabled=True, rnode_serial_port="/dev/ttyTEST",
               rnode_frequency_hz=915000000, rnode_discovery_enabled=True,
               rnode_discovery_lxmf_address=ADDRESS.upper(), backbone_enabled=True,
               backbone_host="example.test")
    model = ReticulumUpdate(**cfg)
    text = render_config(model.model_dump())
    radio, backbone = text.split("[[ReticulumNet Internet]]")
    assert f"discovery_lxmf_address = {ADDRESS}" in radio
    assert "mode = access_point" in radio
    assert "announce_interval = 360" in radio
    assert "publish_ifac = No" in radio
    assert "discovery_lxmf_address" not in backbone
    assert "enable_transport = False" in text
    assert "latitude" not in text
    model.rnode_discovery_enabled = False
    revoked = render_config(model.model_dump())
    assert "discoverable = Yes" not in revoked
    assert "mode = access_point" not in revoked
    assert ADDRESS not in revoked


def test_discovered_metadata_omits_credentials_and_invalid_contacts():
    rows = public_interfaces([
        {"name": "Example", "operator_lxmf_address": ADDRESS, "ifac_passphrase": "fixture-only", "config": "private", "reachable_on": "example.test"},
        {"operator_lxmf_address": "bad"}, None,
    ])
    assert len(rows) == 2
    assert rows[0]["operator_lxmf_address"] == ADDRESS
    assert rows[1]["operator_lxmf_address"] == ""
    assert set(rows[0]) == {"name", "type", "status", "operator_lxmf_address"}


def test_interface_api_is_admin_only_and_disabled_without_library_access(monkeypatch):
    jwt = JwtSessionService("discovery-test-" + "x" * 32, 60, 1)
    dependencies.init_auth(jwt)
    lookup = Mock(return_value=[{"name": "Example", "operator_lxmf_address": ADDRESS}])
    monkeypatch.setattr(routes, "_service", SimpleNamespace(own_address=ADDRESS, discovered_interfaces=lookup))
    config = {"discover_interfaces": False}
    monkeypatch.setattr(state, "to_dict", lambda: config)
    app = FastAPI()
    app.include_router(routes.router)
    try:
        with TestClient(app) as client:
            assert client.get("/api/reticulum/interfaces").status_code == 401
            client.headers["Authorization"] = "Bearer " + jwt.issue("viewer", "viewer")
            assert client.get("/api/reticulum/interfaces").status_code == 403
            client.headers["Authorization"] = "Bearer " + jwt.issue("admin", "admin")
            assert client.get("/api/reticulum/interfaces").json() == {"enabled": False, "interfaces": []}
            lookup.assert_not_called()
            config["discover_interfaces"] = True
            assert client.get("/api/reticulum/interfaces").json()["interfaces"][0]["operator_lxmf_address"] == ADDRESS
            lookup.side_effect = RuntimeError("private diagnostic")
            response = client.get("/api/reticulum/interfaces")
            assert response.status_code == 503
            assert "private diagnostic" not in response.text
    finally:
        dependencies.reset_auth()
