from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend import models
from backend.database import engine
from backend.main import app, cfg


@contextmanager
def home_assistant_mode():
    previous = (cfg.deployment_mode, cfg.auth_mode, cfg.ha_trusted_proxies)
    cfg.deployment_mode = "home_assistant"
    cfg.auth_mode = "home_assistant"
    cfg.ha_trusted_proxies = "testclient"
    try:
        yield
    finally:
        cfg.deployment_mode, cfg.auth_mode, cfg.ha_trusted_proxies = previous


def ha_headers(subject: str, display_name: str = "Sajeel") -> dict[str, str]:
    return {
        "X-Remote-User-Id": subject,
        "X-Remote-User-Name": display_name.lower(),
        "X-Remote-User-Display-Name": display_name,
    }


def finish_ha_onboarding(client: TestClient, headers: dict[str, str], timezone: str):
    response = client.post(
        "/api/onboarding/home-assistant",
        headers=headers,
        json={
            "display_name": headers["X-Remote-User-Display-Name"],
            "timezone": timezone,
            "starting_weight_kg": 80,
            "height_cm": 175,
            "water_target_ml": 2000,
        },
    )
    assert response.status_code == 200


def test_home_assistant_users_are_provisioned_without_admin_privileges():
    with home_assistant_mode(), TestClient(app) as client:
        first = client.get("/api/auth/status", headers=ha_headers("ha-user-1")).json()
        assert first["authenticated"] is True
        assert first["auth_provider"] == "home_assistant"
        assert first["onboarding_required"] is True
        first_id = first["profile"]["id"]
        finish_ha_onboarding(client, ha_headers("ha-user-1"), "America/Chicago")

        second = client.get(
            "/api/auth/status", headers=ha_headers("ha-user-2", "Sameena")
        ).json()
        second_id = second["profile"]["id"]
        assert second_id != first_id
        finish_ha_onboarding(
            client, ha_headers("ha-user-2", "Sameena"), "America/Denver"
        )

        with Session(engine) as db:
            profiles = list(db.scalars(select(models.Profile).order_by(models.Profile.id)))
            assert len(profiles) == 2
            assert all(profile.is_admin is False for profile in profiles)


def test_returning_ha_identity_and_display_name_change_do_not_duplicate_account():
    with home_assistant_mode(), TestClient(app) as client:
        original = client.get(
            "/api/auth/status", headers=ha_headers("stable-id", "Original Name")
        ).json()["profile"]["id"]
        returning = client.get(
            "/api/auth/status", headers=ha_headers("stable-id", "Changed Name")
        ).json()["profile"]["id"]
        assert returning == original
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(models.Profile)) == 1
            identity = db.scalar(select(models.UserIdentity))
            assert identity.provider_display_name == "Changed Name"


def test_ha_users_cannot_read_each_others_health_data():
    with home_assistant_mode(), TestClient(app) as client:
        first_headers = ha_headers("private-a", "User A")
        second_headers = ha_headers("private-b", "User B")
        client.get("/api/auth/status", headers=first_headers)
        finish_ha_onboarding(client, first_headers, "America/Chicago")
        assert client.post(
            "/api/weight",
            headers=first_headers,
            json={"entry_date": "2026-07-13", "weight_kg": 79.5},
        ).status_code == 200

        client.get("/api/auth/status", headers=second_headers)
        finish_ha_onboarding(client, second_headers, "America/Denver")
        assert client.get("/api/progress?range=all", headers=second_headers).json()[
            "weight"
        ] == []
        assert client.get("/api/household", headers=second_headers).status_code == 404


def test_spoofed_home_assistant_headers_are_ignored_in_standalone_mode():
    with TestClient(app) as client:
        response = client.get("/api/auth/status", headers=ha_headers("spoofed")).json()
        assert response["authenticated"] is False
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(models.Profile)) == 0


def test_ha_user_can_enable_pin_for_the_same_local_account():
    with home_assistant_mode(), TestClient(app) as client:
        headers = ha_headers("dual-access", "Dual Access")
        profile_id = client.get("/api/auth/status", headers=headers).json()["profile"]["id"]
        finish_ha_onboarding(client, headers, "America/Phoenix")
        response = client.put(
            "/api/auth/pin",
            headers=headers,
            json={"current_pin": None, "new_pin": "8642"},
        )
        assert response.status_code == 200

        cfg.deployment_mode = "standalone"
        cfg.auth_mode = "pin"
        client.cookies.clear()
        login = client.post("/api/auth/login", json={"pin": "8642"})
        assert login.status_code == 200
        assert login.json()["profile"]["id"] == profile_id
