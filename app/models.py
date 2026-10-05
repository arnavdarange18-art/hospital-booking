"""Database models.

All datetimes are naive and mean the clinic's local time.
"""

from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager

ROLE_PATIENT = "patient"
ROLE_DOCTOR = "doctor"
ROLE_ADMIN = "admin"

STATUS_CONFIRMED = "confirmed"
STATUS_CANCELLED = "cancelled"
STATUS_COMPLETED = "completed"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=ROLE_PATIENT)
    active = db.Column(db.Boolean, nullable=False, default=True)

    doctor_profile = db.relationship("Doctor", back_populates="user", uselist=False)

    @property
    def is_active(self):
        return self.active

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Doctor(db.Model):
    __tablename__ = "doctors"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    specialization = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100), nullable=False)

    user = db.relationship("User", back_populates="doctor_profile")
    availability = db.relationship(
        "Availability", back_populates="doctor", cascade="all, delete-orphan"
    )
    appointments = db.relationship("Appointment", back_populates="doctor")


class Availability(db.Model):
    """A weekly working period, e.g. Mondays 09:00-12:00 in 30 minute slots."""

    __tablename__ = "availability"

    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=False)
    weekday = db.Column(db.Integer, nullable=False)  # Monday = 0 ... Sunday = 6
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    slot_minutes = db.Column(db.Integer, nullable=False, default=30)

    doctor = db.relationship("Doctor", back_populates="availability")


class Appointment(db.Model):
    """A booking.

    ``slot_start`` equals ``start_time`` while the appointment holds its slot and is NULL
    once it is cancelled. The unique constraint on (doctor_id, slot_start) therefore stops
    two live appointments sharing a slot at database level, while cancelled rows (NULL)
    never collide, so a cancelled slot can be booked again.
    """

    __tablename__ = "appointments"
    __table_args__ = (db.UniqueConstraint("doctor_id", "slot_start", name="uq_doctor_slot"),)

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=STATUS_CONFIRMED)
    slot_start = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    patient = db.relationship("User")
    doctor = db.relationship("Doctor", back_populates="appointments")


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
