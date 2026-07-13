import os

os.environ["DATABASE_URL"] = "sqlite:///./test-health-os.db"
os.environ["APP_PIN"] = ""
import pytest
from fastapi.testclient import TestClient

from backend.database import Base, engine
from backend.main import app


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import Session

    from backend.services import seed

    with Session(engine) as db:
        seed(db)
    yield


@pytest.fixture
def client():
    with TestClient(app) as value:
        response = value.post(
            "/api/onboarding",
            json={
                "display_name": "John",
                "pin": "1234",
                "timezone": "America/Chicago",
                "starting_weight_kg": 99,
                "height_cm": 183,
                "water_target_ml": 2000,
            },
        )
        assert response.status_code == 201
        yield value
