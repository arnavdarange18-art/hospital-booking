"""Sample data so a fresh install has something to look at (used by ``flask seed-demo``)."""

from datetime import datetime, time, timedelta

from . import services
from .extensions import db
from .models import ROLE_ADMIN, ROLE_DOCTOR, ROLE_PATIENT, Availability, Doctor, User

WEEKDAYS_MON_FRI = range(0, 5)
WEEKDAYS_MON_SAT = range(0, 6)

# name, email, specialization, department, [(weekdays, from, to, minutes per visit)]
DOCTORS = [
    (
        "Meera Iyer",
        "meera.iyer@example.com",
        "Cardiology",
        "Heart Care",
        [(WEEKDAYS_MON_FRI, time(9), time(13), 30), ((0, 2), time(15), time(17), 30)],
    ),
    (
        "Arjun Rao",
        "arjun.rao@example.com",
        "Pediatrics",
        "Child Health",
        [(WEEKDAYS_MON_SAT, time(10), time(14), 20)],
    ),
    (
        "Sana Khan",
        "sana.khan@example.com",
        "Dermatology",
        "Skin Clinic",
        [((1, 3, 5), time(9, 30), time(13, 30), 30), ((1, 3), time(16), time(19), 30)],
    ),
    (
        "Vikram Shah",
        "vikram.shah@example.com",
        "Orthopedics",
        "Bone and Joint",
        [(WEEKDAYS_MON_FRI, time(11), time(15), 30)],
    ),
    (
        "Leena D'Souza",
        "leena.dsouza@example.com",
        "General Medicine",
        "Primary Care",
        [
            (WEEKDAYS_MON_SAT, time(8, 30), time(12, 30), 15),
            ((0, 1, 2, 3, 4), time(17), time(20), 15),
        ],
    ),
]

OTHER_PATIENTS = [
    ("Asha Nair", "asha.nair@example.com"),
    ("Rohan Mehta", "rohan.mehta@example.com"),
]
DEMO_PATIENT = ("Demo Patient", "demo.patient@example.com")
DEMO_ADMIN = ("Demo Admin", "demo.admin@example.com")


class DemoDataExistsError(Exception):
    """Some of the demo accounts are already in the database."""


def _make_user(name, email, role, password):
    user = User(name=name, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    return user


def demo_emails():
    return (
        [DEMO_ADMIN[1]]
        + [row[1] for row in DOCTORS]
        + [DEMO_PATIENT[1]]
        + [email for _, email in OTHER_PATIENTS]
    )


def seed_demo(password, now=None):
    """Create demo doctors, patients, working hours and bookings.

    Returns ``[(role, name, email), ...]`` for the accounts that were created.
    """
    now = now or datetime.now()
    if db.session.query(User).filter(User.email.in_(demo_emails())).first() is not None:
        raise DemoDataExistsError("Demo accounts already exist in this database.")

    accounts = [("admin", *DEMO_ADMIN)]
    _make_user(*DEMO_ADMIN, ROLE_ADMIN, password)

    doctors = []
    for name, email, specialization, department, windows in DOCTORS:
        user = _make_user(name, email, ROLE_DOCTOR, password)
        doctor = Doctor(user=user, specialization=specialization, department=department)
        for weekdays, start, end, minutes in windows:
            for weekday in weekdays:
                doctor.availability.append(
                    Availability(
                        weekday=weekday, start_time=start, end_time=end, slot_minutes=minutes
                    )
                )
        db.session.add(doctor)
        doctors.append(doctor)
        accounts.append(("doctor", name, email))

    fillers = [_make_user(name, email, ROLE_PATIENT, password) for name, email in OTHER_PATIENTS]
    patient = _make_user(*DEMO_PATIENT, ROLE_PATIENT, password)
    accounts += [("patient", name, email) for name, email in OTHER_PATIENTS]
    accounts.append(("patient", *DEMO_PATIENT))
    db.session.commit()

    # Make some slots busy so the date strip shows a realistic mix of open and full days.
    for index, doctor in enumerate(doctors[:4]):
        for offset in range(4):
            day = now.date() + timedelta(days=offset)
            for n, (start, _) in enumerate(services.available_slots(doctor, day, now)):
                if (n + index + offset) % 3 == 0:
                    services.book_appointment(fillers[(n + offset) % 2], doctor, start, now=now)

    # The demo patient: two upcoming visits, one completed visit and one cancelled visit.
    for doctor in (doctors[0], doctors[1]):
        start = services.next_available(doctor, now)
        if start:
            services.book_appointment(patient, doctor, start, now=now)

    general = doctors[4]
    for back in range(1, 8):
        past_day = (now - timedelta(days=back)).date()
        grid = services.slot_grid(general, past_day)
        if grid:
            start = grid[0][0]
            visit = services.book_appointment(
                patient, general, start, now=start - timedelta(days=2)
            )
            services.complete_appointment(general.user, visit, now=start + timedelta(minutes=30))
            break

    start = services.next_available(doctors[3], now)
    if start:
        cancelled = services.book_appointment(patient, doctors[3], start, now=now)
        services.cancel_appointment(patient, cancelled)

    return accounts
