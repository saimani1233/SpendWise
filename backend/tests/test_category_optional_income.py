from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import create_access_token
from app.database.connection import Base, get_db
from app.database.models import Category, User
from app.main import app


@pytest.fixture
def api(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'api.sqlite'}", connect_args={"check_same_thread": False})
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSession() as db:
        user = User(name="Test User", email="test@example.com", password_hash="unused-test-hash")
        db.add(user)
        db.flush()
        food = Category(user_id=user.id, name="Food", type="expense")
        db.add(food)
        db.commit()
        user_id, food_id = user.id, food.id

    def override_db():
        with TestingSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {create_access_token(str(user_id))}"})
    yield client, food_id, TestingSession
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def test_income_crud_without_category_and_search(api):
    client, _, _ = api
    income = {"description": "Salary", "amount_paise": 250000, "type": "income", "transaction_date": date.today().isoformat()}
    created = client.post("/api/transactions", json=income)
    assert created.status_code == 201, created.text
    record = created.json()
    assert record["category_id"] is None
    assert record["category_name"] == "Uncategorized"
    assert client.get("/api/transactions?type=income&search=Salary").json()["items"][0]["_id"] == record["_id"]

    changed = income | {"description": "Monthly salary", "amount_paise": 275000}
    updated = client.put(f"/api/transactions/{record['_id']}", json=changed)
    assert updated.status_code == 200, updated.text
    assert updated.json()["category_id"] is None
    assert updated.json()["category_name"] == "Uncategorized"
    assert client.delete(f"/api/transactions/{record['_id']}").status_code == 200
    assert client.get(f"/api/transactions/{record['_id']}").status_code == 404


def test_expense_crud_requires_valid_expense_category(api):
    client, food_id, _ = api
    expense = {"description": "Lunch", "amount_paise": 12500, "type": "expense", "category_id": str(food_id), "transaction_date": date.today().isoformat()}
    assert client.post("/api/transactions", json=expense | {"category_id": None}).status_code == 422
    assert client.post("/api/transactions", json=expense | {"category_id": "999999"}).status_code == 422

    created = client.post("/api/transactions", json=expense)
    assert created.status_code == 201, created.text
    record = created.json()
    assert record["category_name"] == "Food"
    assert client.get("/api/transactions?type=expense&search=Food").json()["items"][0]["_id"] == record["_id"]
    changed = expense | {"description": "Dinner", "amount_paise": 18000}
    updated = client.put(f"/api/transactions/{record['_id']}", json=changed)
    assert updated.status_code == 200, updated.text
    assert updated.json()["category_name"] == "Food"
    assert client.delete(f"/api/transactions/{record['_id']}").status_code == 200


def test_category_list_exposes_expense_categories_only(api):
    client, _, _ = api
    assert all(category["type"] == "expense" for category in client.get("/api/categories").json()["items"])
