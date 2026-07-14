from datetime import date, datetime
from zoneinfo import ZoneInfo

from backend.services import completion_score, mode_for


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_docs_are_self_hosted(client):
    response = client.get("/docs")
    assert response.status_code == 200
    assert "/docs-assets/swagger-ui-bundle.js" in response.text
    assert "/docs-assets/swagger-init.js" in response.text
    assert "cdn.jsdelivr.net" not in response.text
    assert "<script>" not in response.text


def test_task_checkin_and_undo(client):
    task = client.get("/api/today").json()["tasks"][0]
    assert client.post(f"/api/tasks/{task['id']}/complete", json={}).json()["state"] == "completed"
    assert (
        next(x for x in client.get("/api/today").json()["tasks"] if x["id"] == task["id"])["state"]
        == "completed"
    )
    assert client.delete(f"/api/tasks/{task['id']}/completion").status_code == 200


def test_task_skip_and_restore(client):
    task = client.get("/api/today").json()["tasks"][0]
    assert client.post(f"/api/tasks/{task['id']}/skip").status_code == 200
    skipped = next(
        item for item in client.get("/api/today").json()["tasks"] if item["id"] == task["id"]
    )
    assert skipped["state"] == "skipped"

    assert client.delete(f"/api/tasks/{task['id']}/completion").status_code == 200
    restored = next(
        item for item in client.get("/api/today").json()["tasks"] if item["id"] == task["id"]
    )
    assert restored["state"] in ("available", "upcoming")


def test_completion_idempotent(client):
    task = client.get("/api/today").json()["tasks"][0]
    assert client.post(f"/api/tasks/{task['id']}/complete", json={}).status_code == 200
    assert client.post(f"/api/tasks/{task['id']}/complete", json={}).status_code == 200


def test_relaxed_modes():
    assert mode_for(date(2026, 7, 17))["name"] == "Relaxed Friday"
    assert mode_for(date(2026, 7, 18))["flexible"] is True
    assert mode_for(date(2026, 7, 19))["name"] == "Sunday Reset"


def test_optional_tasks_neutral():
    assert (
        completion_score(
            [{"required": True, "state": "completed"}, {"required": False, "state": "available"}]
        )
        == 100
    )


def test_week_schedule(client):
    data = client.get("/api/week?anchor=2026-07-13").json()
    assert len(data["days"]) == 7 and data["days"][4]["mode"]["flexible"]


def test_plan_entries_can_be_created_edited_and_archived(client):
    created = client.post(
        "/api/plan",
        json={
            "name": "Evening stretch",
            "description": "A short reset after work.",
            "category": "movement",
            "suggested_time": "18:30",
            "required": False,
            "minimum_label": "Stretch for two minutes",
            "days": [0, 2, 4],
        },
    )
    assert created.status_code == 201
    habit_id = created.json()["id"]
    habit = next(item for item in client.get("/api/plan").json() if item["id"] == habit_id)
    assert habit["name"] == "Evening stretch"
    assert habit["days"] == [0, 2, 4]

    updated = client.put(
        f"/api/plan/{habit_id}",
        json={"name": "Evening mobility", "days": [1, 3], "required": True},
    )
    assert updated.status_code == 200
    habit = next(item for item in client.get("/api/plan").json() if item["id"] == habit_id)
    assert habit["name"] == "Evening mobility"
    assert habit["days"] == [1, 3]
    assert habit["required"] is True

    assert client.delete(f"/api/plan/{habit_id}").status_code == 200
    assert all(item["id"] != habit_id for item in client.get("/api/plan").json())


def test_plan_entry_validation(client):
    response = client.post(
        "/api/plan",
        json={"name": "   ", "category": "movement", "days": [7]},
    )
    assert response.status_code == 422


def test_weight_trend(client):
    for day, weight in [("2026-07-01", 99), ("2026-07-08", 98.5), ("2026-07-12", 98)]:
        assert (
            client.post("/api/weight", json={"entry_date": day, "weight_kg": weight}).status_code
            == 200
        )
    result = client.get("/api/progress?range=all").json()["weight"]
    assert result[-1]["average"] < result[0]["average"]

    goal = client.get("/api/progress?range=all").json()["weight_goal"]
    assert goal["start"] == 99
    assert goal["current"] == 98
    assert goal["goal"] == 85
    assert goal["change"] == 1
    assert goal["remaining"] == 13
    assert goal["progress"] == 7


def test_weight_entries_can_be_edited_and_deleted(client):
    created = client.post(
        "/api/weight",
        json={"entry_date": "2026-07-10", "weight_kg": 98.5, "notes": "Morning"},
    ).json()
    updated = client.put(
        f"/api/weight/{created['id']}",
        json={
            "entry_date": "2026-07-11",
            "weight_kg": 98.2,
            "waist_cm": 101,
            "notes": "Corrected",
        },
    )
    assert updated.status_code == 200
    entry = client.get("/api/progress?range=all").json()["weight"][0]
    assert entry["id"] == created["id"]
    assert entry["date"] == "2026-07-11"
    assert entry["weight"] == 98.2
    assert entry["waist_cm"] == 101
    assert entry["notes"] == "Corrected"

    assert client.delete(f"/api/weight/{created['id']}").status_code == 200
    assert client.get("/api/progress?range=all").json()["weight"] == []


def test_dst_timezone():
    before = datetime(2026, 3, 8, 1, 30, tzinfo=ZoneInfo("America/Chicago"))
    after = datetime(2026, 3, 8, 3, 30, tzinfo=ZoneInfo("America/Chicago"))
    assert before.utcoffset() != after.utcoffset()


def test_integration_token_not_exposed(client):
    text = client.get("/api/settings").text
    assert "integration_token" not in text.lower() and "Bearer" not in text


def test_json_export_downloads_as_attachment(client):
    response = client.get("/api/export/json")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["content-disposition"] == ('attachment; filename="health-os-data.json"')
    assert "weight_entries" in response.json()


def test_alcohol_driving_safety(client):
    body = {
        "entry_date": date.today().isoformat(),
        "drink_type": "beer",
        "drinks": 2,
        "plans_to_drive": True,
    }
    assert "sober ride" in client.post("/api/alcohol", json=body).json()["safety"].lower()


def app_settings(**overrides):
    values = {
        "display_name": "John",
        "starting_weight_kg": 97.5,
        "timezone": "America/New_York",
        "caffeine_cutoff": "13:30",
        "water_target_ml": 2400,
        "weight_milestones": [94, 90, 87],
    }
    values.update(overrides)
    return values


def test_settings_are_user_scoped_and_timezone_is_confirmed(client):
    response = client.put("/api/settings", json=app_settings())
    assert response.status_code == 200
    saved = client.get("/api/settings").json()
    assert saved["timezone"] == "America/New_York"
    assert saved["starting_weight_kg"] == 97.5
    assert saved["caffeine_cutoff"] == "13:30"
    assert saved["water_target_ml"] == 2400
    assert saved["timezone_confirmed"] is True
    assert "is_admin" not in saved


def test_invalid_timezone_is_rejected(client):
    response = client.put("/api/settings", json=app_settings(timezone="GMT-6"))
    assert response.status_code == 422


def test_pin_can_be_set_and_changed_through_api(client):
    response = client.put(
        "/api/auth/pin", json={"current_pin": "1234", "new_pin": "2468"}
    )
    assert response.status_code == 200
    assert client.get("/api/auth/status").json()["pin_required"] is True
    assert client.post("/api/auth/login", json={"pin": "0000"}).status_code == 401
    assert client.post("/api/auth/login", json={"pin": "2468"}).status_code == 200


def test_water_progress_is_easy_to_add_and_undo(client):
    assert client.post("/api/hydration", json={"amount_ml": 350}).status_code == 200
    second = client.post("/api/hydration", json={"amount_ml": 500}).json()
    water = client.get("/api/today").json()["water"]
    assert water["current_ml"] == 850
    assert water["target_ml"] == 2000
    assert water["latest_entry_id"] == second["id"]

    assert client.delete(f"/api/hydration/{second['id']}").status_code == 200
    assert client.get("/api/today").json()["water"]["current_ml"] == 350


def test_standalone_accounts_are_independent_and_have_no_admin_routes(client):
    first_id = client.get("/api/auth/status").json()["profile"]["id"]
    member = {
        "display_name": "Taylor",
        "pin": "5678",
        "timezone": "America/Denver",
        "starting_weight_kg": 72,
        "height_cm": 168,
        "water_target_ml": 1800,
    }
    created = client.post("/api/accounts", json=member)
    assert created.status_code == 201
    client.headers["X-CSRF-Token"] = created.json()["csrf_token"]
    second_id = client.get("/api/auth/status").json()["profile"]["id"]
    assert second_id != first_id
    duplicate = client.post("/api/accounts", json={**member, "display_name": "Other"})
    assert duplicate.status_code == 409
    assert client.get("/api/settings").json()["timezone"] == "America/Denver"
    assert client.get("/api/settings").json()["water_target_ml"] == 1800
    assert client.get("/api/household").status_code == 404
    assert client.get("/api/plan").json()[0]["suggested_time"] == "07:00"
    assert client.post(
        "/api/weight", json={"entry_date": "2026-07-13", "weight_kg": 71.5}
    ).status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    first_login = client.post("/api/auth/login", json={"pin": "1234"})
    assert first_login.status_code == 200
    client.headers["X-CSRF-Token"] = first_login.json()["csrf_token"]
    assert client.get("/api/progress?range=all").json()["weight"] == []
