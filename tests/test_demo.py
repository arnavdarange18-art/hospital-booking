"""The demo-data command used to preview the app."""

from datetime import datetime

import pytest

from app import services
from app.demo import DemoDataExistsError, demo_emails, seed_demo
from app.extensions import db
from app.models import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_CONFIRMED,
    Appointment,
    Doctor,
    User,
)

PASSWORD = "demo-pass-12345"  # test-only value, not a real credential


def test_seed_demo_creates_every_role_hours_and_bookings(app):
    with app.app_context():
        db.create_all()
        accounts = seed_demo(PASSWORD)

        assert {role for role, _, _ in accounts} == {"admin", "doctor", "patient"}
        assert {email for _, _, email in accounts} == set(demo_emails())
        assert db.session.query(Doctor).count() == 5
        assert all(doctor.availability for doctor in db.session.query(Doctor))

        patient = db.session.query(User).filter_by(email="demo.patient@example.com").one()
        statuses = {
            a.status for a in db.session.query(Appointment).filter_by(patient_id=patient.id)
        }
        assert statuses == {STATUS_CONFIRMED, STATUS_COMPLETED, STATUS_CANCELLED}
        assert patient.check_password(PASSWORD)


def test_seeded_doctors_have_a_mix_of_open_and_busy_days(app):
    with app.app_context():
        db.create_all()
        seed_demo(PASSWORD)
        doctor = db.session.query(Doctor).first()
        today = datetime.now().date()
        counts = [len(s) for s in services.free_slots_by_day(doctor, today, 5).values()]
        assert max(counts) > 0
        assert services.next_available(doctor) is not None


def test_seeding_twice_is_refused_instead_of_duplicating(app):
    with app.app_context():
        db.create_all()
        seed_demo(PASSWORD)
        with pytest.raises(DemoDataExistsError):
            seed_demo(PASSWORD)


def test_seed_demo_command(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["seed-demo", "--password", PASSWORD])
    assert result.exit_code == 0, result.output
    assert "demo.patient@example.com" in result.output
    assert "Do not run seed-demo on a real or public deployment." in result.output

    again = runner.invoke(args=["seed-demo", "--password", PASSWORD])
    assert again.exit_code != 0
    assert "already exist" in again.output

    short = runner.invoke(args=["seed-demo", "--password", "short"])
    assert short.exit_code != 0
