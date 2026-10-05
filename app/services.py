"""Booking rules.

Everything that decides whether an appointment is allowed lives in this module, so the
routes stay thin and the rules can be tested without a browser.
"""

from datetime import datetime, time, timedelta

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import (
    ROLE_ADMIN,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_CONFIRMED,
    Appointment,
    Availability,
    Doctor,
    Notification,
    User,
)

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MAX_ADVANCE_DAYS = 90
MIN_SLOT_MINUTES = 5
MAX_SLOT_MINUTES = 240


class BookingError(Exception):
    """A rule was broken. The message is safe to show to the user."""


class InvalidSlotError(BookingError):
    """The requested time is not a bookable slot."""


class SlotUnavailableError(BookingError):
    """The slot exists but someone else already holds it."""


class PermissionDeniedError(Exception):
    """The actor may not touch this appointment. Routes answer this with a 403."""


def _label(moment):
    return moment.strftime("%d %b %Y, %I:%M %p")


def _notify(user, message):
    db.session.add(Notification(user_id=user.id, message=message[:255]))


def _is_doctor_of(actor, appointment):
    profile = actor.doctor_profile
    return profile is not None and profile.id == appointment.doctor_id


def _can_manage(actor, appointment):
    return (
        actor.role == ROLE_ADMIN
        or actor.id == appointment.patient_id
        or _is_doctor_of(actor, appointment)
    )


def _commit_or_conflict():
    """Commit, turning a unique-constraint clash into a friendly 'slot taken' error."""
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise SlotUnavailableError(
            "Sorry, that slot was just taken. Please pick another."
        ) from None


# --- searching and slots -------------------------------------------------------------


def search_doctors(query=""):
    """Active doctors whose name, specialization or department contains the query."""
    stmt = (
        db.session.query(Doctor).join(User, Doctor.user_id == User.id).filter(User.active.is_(True))
    )
    query = (query or "").strip()
    if query:
        stmt = stmt.filter(
            or_(
                User.name.icontains(query, autoescape=True),
                Doctor.specialization.icontains(query, autoescape=True),
                Doctor.department.icontains(query, autoescape=True),
            )
        )
    return stmt.order_by(User.name).all()


def slot_grid(doctor, day):
    """Every (start, end) the doctor offers on ``day``, ignoring existing bookings."""
    slots = []
    for window in doctor.availability:
        if window.weekday != day.weekday():
            continue
        step = timedelta(minutes=window.slot_minutes)
        cursor = datetime.combine(day, window.start_time)
        limit = datetime.combine(day, window.end_time)
        while cursor + step <= limit:
            slots.append((cursor, cursor + step))
            cursor += step
    return sorted(slots)


def _overlapping(doctor_id, start, end, exclude_id=None):
    """Live (not cancelled) appointments of the doctor that overlap [start, end)."""
    query = db.session.query(Appointment).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.status != STATUS_CANCELLED,
        Appointment.start_time < end,
        Appointment.end_time > start,
    )
    if exclude_id is not None:
        query = query.filter(Appointment.id != exclude_id)
    return query


def free_slots_by_day(doctor, first_day, days, now=None):
    """Future, unbooked slots for ``days`` days from ``first_day`` as ``{date: [(start, end)]}``.

    Uses one query for the whole range, so it is cheap enough for a date strip.
    """
    now = now or datetime.now()
    range_start = datetime.combine(first_day, time.min)
    booked = _overlapping(doctor.id, range_start, range_start + timedelta(days=days)).all()
    result = {}
    for offset in range(days):
        day = first_day + timedelta(days=offset)
        result[day] = [
            (start, end)
            for start, end in slot_grid(doctor, day)
            if start > now and not any(b.start_time < end and b.end_time > start for b in booked)
        ]
    return result


def available_slots(doctor, day, now=None):
    """Future, unbooked slots for the doctor on ``day``."""
    return free_slots_by_day(doctor, day, 1, now)[day]


def next_available(doctor, now=None, horizon_days=14):
    """Start of the doctor's first free slot within ``horizon_days``, or None."""
    now = now or datetime.now()
    for slots in free_slots_by_day(doctor, now.date(), horizon_days, now).values():
        if slots:
            return slots[0][0]
    return None


def specializations():
    """Sorted, distinct specializations of active doctors (for the quick filters)."""
    rows = (
        db.session.query(Doctor.specialization)
        .join(User, Doctor.user_id == User.id)
        .filter(User.active.is_(True))
        .distinct()
        .all()
    )
    return sorted(name for (name,) in rows)


def _validate_slot(doctor, start, now):
    """Return the slot's end time, or raise if ``start`` is not a bookable slot."""
    if start <= now:
        raise InvalidSlotError("That time has already passed.")
    if start > now + timedelta(days=MAX_ADVANCE_DAYS):
        raise InvalidSlotError(f"Appointments can only be booked {MAX_ADVANCE_DAYS} days ahead.")
    for slot_start, slot_end in slot_grid(doctor, start.date()):
        if slot_start == start:
            return slot_end
    raise InvalidSlotError("That time is outside the doctor's working hours.")


def appointments_for_day(doctor, day):
    day_start = datetime.combine(day, time.min)
    return (
        db.session.query(Appointment)
        .filter(
            Appointment.doctor_id == doctor.id,
            Appointment.start_time >= day_start,
            Appointment.start_time < day_start + timedelta(days=1),
        )
        .order_by(Appointment.start_time)
        .all()
    )


def day_timeline(doctor, day):
    """A doctor's day as ``(rows, cancelled)``.

    Each row is ``{"start", "end", "appointment"}`` for one slot, with ``appointment`` set to the
    live booking or None when the slot is open. Bookings that no longer match the slot grid (the
    doctor changed their hours afterwards) still appear, so nothing on the day is hidden.
    """
    appointments = appointments_for_day(doctor, day)
    live = {a.start_time: a for a in appointments if a.status != STATUS_CANCELLED}
    rows, placed = [], set()
    for start, end in slot_grid(doctor, day):
        appointment = live.get(start)
        if appointment is not None:
            placed.add(appointment.id)
        rows.append({"start": start, "end": end, "appointment": appointment})
    for appointment in live.values():
        if appointment.id not in placed:
            rows.append(
                {
                    "start": appointment.start_time,
                    "end": appointment.end_time,
                    "appointment": appointment,
                }
            )
    rows.sort(key=lambda row: row["start"])
    cancelled = [a for a in appointments if a.status == STATUS_CANCELLED]
    return rows, cancelled


# --- appointment lifecycle -----------------------------------------------------------


def book_appointment(patient, doctor, start, now=None):
    now = now or datetime.now()
    end = _validate_slot(doctor, start, now)
    if _overlapping(doctor.id, start, end).first() is not None:
        raise SlotUnavailableError("That time slot is already booked.")

    appointment = Appointment(
        patient_id=patient.id,
        doctor_id=doctor.id,
        start_time=start,
        end_time=end,
        status=STATUS_CONFIRMED,
        slot_start=start,
    )
    db.session.add(appointment)
    when = _label(start)
    _notify(patient, f"Your appointment with Dr. {doctor.user.name} on {when} is confirmed.")
    _notify(doctor.user, f"{patient.name} booked an appointment on {when}.")
    _commit_or_conflict()
    return appointment


def cancel_appointment(actor, appointment):
    if not _can_manage(actor, appointment):
        raise PermissionDeniedError("You cannot cancel this appointment.")
    if appointment.status != STATUS_CONFIRMED:
        raise BookingError("Only confirmed appointments can be cancelled.")

    appointment.status = STATUS_CANCELLED
    appointment.slot_start = None  # frees the slot for someone else
    message = f"The appointment on {_label(appointment.start_time)} was cancelled."
    _notify(appointment.patient, message)
    _notify(appointment.doctor.user, message)
    db.session.commit()


def reschedule_appointment(actor, appointment, new_start, now=None):
    if actor.role != ROLE_ADMIN and actor.id != appointment.patient_id:
        raise PermissionDeniedError("You cannot reschedule this appointment.")
    if appointment.status != STATUS_CONFIRMED:
        raise BookingError("Only confirmed appointments can be rescheduled.")

    now = now or datetime.now()
    new_end = _validate_slot(appointment.doctor, new_start, now)
    if _overlapping(appointment.doctor_id, new_start, new_end, exclude_id=appointment.id).first():
        raise SlotUnavailableError("That time slot is already booked.")

    appointment.start_time = new_start
    appointment.end_time = new_end
    appointment.slot_start = new_start
    message = f"The appointment was rescheduled to {_label(new_start)}."
    _notify(appointment.patient, message)
    _notify(appointment.doctor.user, message)
    _commit_or_conflict()


def complete_appointment(actor, appointment, now=None):
    if actor.role != ROLE_ADMIN and not _is_doctor_of(actor, appointment):
        raise PermissionDeniedError("Only the treating doctor can complete this appointment.")
    if appointment.status != STATUS_CONFIRMED:
        raise BookingError("Only confirmed appointments can be completed.")
    if appointment.start_time > (now or datetime.now()):
        raise BookingError("This appointment has not started yet.")

    appointment.status = STATUS_COMPLETED  # keeps slot_start, so the slot stays reserved
    _notify(
        appointment.patient,
        f"Your appointment on {_label(appointment.start_time)} was marked as completed.",
    )
    db.session.commit()


# --- doctor working hours ------------------------------------------------------------


def _minutes(value):
    return value.hour * 60 + value.minute


def add_availability(doctor, weekday, start, end, slot_minutes):
    if not 0 <= weekday <= 6:
        raise BookingError("Choose a valid weekday.")
    if not MIN_SLOT_MINUTES <= slot_minutes <= MAX_SLOT_MINUTES:
        raise BookingError(
            f"Slot length must be between {MIN_SLOT_MINUTES} and {MAX_SLOT_MINUTES} minutes."
        )
    if start >= end:
        raise BookingError("End time must be after start time.")
    if _minutes(end) - _minutes(start) < slot_minutes:
        raise BookingError("The working period is shorter than one slot.")
    for existing in doctor.availability:
        if existing.weekday == weekday and start < existing.end_time and end > existing.start_time:
            raise BookingError("That overlaps another working period on the same day.")

    window = Availability(
        doctor_id=doctor.id,
        weekday=weekday,
        start_time=start,
        end_time=end,
        slot_minutes=slot_minutes,
    )
    db.session.add(window)
    db.session.commit()
    return window
