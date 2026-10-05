import os
from datetime import time

import pytest

from app import create_app
from app.extensions import db
from app.models import ROLE_ADMIN, ROLE_DOCTOR, ROLE_PATIENT, Availability, Doctor, User
from tests.helpers import ADMIN, ALICE, BOB, DOCTOR, USER_PW


def _config(csrf=False):
    return {
        "TESTING": True,
        "SECRET_KEY": "test-only-key-not-used-anywhere-else",
        "WTF_CSRF_ENABLED": csrf,
        # CI sets DATABASE_URL to a MySQL service container; locally tests use SQLite.
        "SQLALCHEMY_DATABASE_URI": os.environ.get("DATABASE_URL", "sqlite:///:memory:"),
    }


def _make_user(name, email, role):
    user = User(name=name, email=email, role=role)
    user.set_password(USER_PW)
    db.session.add(user)
    return user


def _seed():
    """An admin, one doctor working 09:00-12:00 (30 min slots) every day, two patients."""
    admin = _make_user("Admin", ADMIN, ROLE_ADMIN)
    doctor_user = _make_user("Grey", DOCTOR, ROLE_DOCTOR)
    doctor = Doctor(user=doctor_user, specialization="Cardiology", department="Heart Care")
    for weekday in range(7):
        doctor.availability.append(
            Availability(
                weekday=weekday, start_time=time(9, 0), end_time=time(12, 0), slot_minutes=30
            )
        )
    alice = _make_user("Alice", ALICE, ROLE_PATIENT)
    bob = _make_user("Bob", BOB, ROLE_PATIENT)
    db.session.add_all([doctor, admin])
    db.session.commit()
    return {
        "admin_id": admin.id,
        "doctor_id": doctor.id,
        "doctor_user_id": doctor_user.id,
        "alice_id": alice.id,
        "bob_id": bob.id,
    }


@pytest.fixture
def app():
    app = create_app(_config())
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def csrf_app():
    return create_app(_config(csrf=True))


@pytest.fixture
def data(app):
    """Ids of the seeded rows (plain values, so they are safe to use across app contexts)."""
    with app.app_context():
        return _seed()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def ctx(app, data):
    """An app context for tests that call the service layer directly."""
    with app.app_context():
        yield


@pytest.fixture
def doctor(ctx, data):
    return db.session.get(Doctor, data["doctor_id"])


@pytest.fixture
def doctor_user(ctx, data):
    return db.session.get(User, data["doctor_user_id"])


@pytest.fixture
def alice(ctx, data):
    return db.session.get(User, data["alice_id"])


@pytest.fixture
def bob(ctx, data):
    return db.session.get(User, data["bob_id"])
