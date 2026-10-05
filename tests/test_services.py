"""Booking rules, tested directly against the service layer."""

from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app import services
from app.extensions import db
from app.models import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_CONFIRMED,
    Appointment,
    Notification,
)
from tests.helpers import tomorrow_at


def _replace_working_hours(doctor, weekday, slot_minutes):
    for window in list(doctor.availability):
        db.session.delete(window)
    db.session.commit()
    services.add_availability(doctor, weekday, time(9, 0), time(12, 0), slot_minutes)


# --- booking -------------------------------------------------------------------------


def test_booking_a_free_slot_succeeds_and_notifies_both_sides(alice, doctor):
    start = tomorrow_at(9)
    appointment = services.book_appointment(alice, doctor, start)

    assert appointment.status == STATUS_CONFIRMED
    assert appointment.end_time == start + timedelta(minutes=30)
    assert db.session.query(Notification).filter_by(user_id=alice.id).count() == 1
    assert db.session.query(Notification).filter_by(user_id=doctor.user_id).count() == 1


def test_booking_an_already_taken_slot_is_rejected(alice, bob, doctor):
    start = tomorrow_at(9)
    services.book_appointment(alice, doctor, start)

    with pytest.raises(services.SlotUnavailableError):
        services.book_appointment(bob, doctor, start)
    assert db.session.query(Appointment).count() == 1


@pytest.mark.parametrize(
    ("hour", "minute"),
    [(8, 30), (12, 0), (9, 10), (23, 0)],
    ids=["before opening", "at closing time", "between slots", "late evening"],
)
def test_booking_outside_working_hours_is_rejected(alice, doctor, hour, minute):
    with pytest.raises(services.InvalidSlotError):
        services.book_appointment(alice, doctor, tomorrow_at(hour, minute))


def test_the_last_slot_of_the_day_can_be_booked(alice, doctor):
    appointment = services.book_appointment(alice, doctor, tomorrow_at(11, 30))
    assert appointment.end_time == tomorrow_at(12, 0)


def test_booking_a_time_in_the_past_is_rejected(alice, doctor):
    start = tomorrow_at(9)
    with pytest.raises(services.InvalidSlotError):
        services.book_appointment(alice, doctor, start, now=start)


def test_booking_too_far_ahead_is_rejected(alice, doctor):
    far = datetime.combine(date.today() + timedelta(days=100), time(9, 0))
    with pytest.raises(services.InvalidSlotError):
        services.book_appointment(alice, doctor, far)


def test_overlap_is_rejected_when_the_slot_length_changes(alice, bob, doctor):
    day = tomorrow_at(9)
    _replace_working_hours(doctor, day.weekday(), 60)
    first = services.book_appointment(alice, doctor, day)
    assert first.end_time == day + timedelta(hours=1)

    # The doctor now works in 30 minute slots, so 09:30 exists but overlaps Alice's hour.
    _replace_working_hours(doctor, day.weekday(), 30)
    with pytest.raises(services.SlotUnavailableError):
        services.book_appointment(bob, doctor, tomorrow_at(9, 30))
    services.book_appointment(bob, doctor, tomorrow_at(10, 0))


# --- database-level guarantee ---------------------------------------------------------


def _raw_appointment(patient, doctor, start, status, slot_start):
    return Appointment(
        patient_id=patient.id,
        doctor_id=doctor.id,
        start_time=start,
        end_time=start + timedelta(minutes=30),
        status=status,
        slot_start=slot_start,
    )


def test_database_rejects_a_duplicate_slot_even_if_the_app_check_is_bypassed(alice, bob, doctor):
    start = tomorrow_at(9)
    db.session.add(_raw_appointment(alice, doctor, start, STATUS_CONFIRMED, start))
    db.session.add(_raw_appointment(bob, doctor, start, STATUS_CONFIRMED, start))

    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_cancelled_rows_never_collide_with_each_other_or_with_live_ones(alice, bob, doctor):
    start = tomorrow_at(9)
    db.session.add(_raw_appointment(alice, doctor, start, STATUS_CANCELLED, None))
    db.session.add(_raw_appointment(bob, doctor, start, STATUS_CANCELLED, None))
    db.session.add(_raw_appointment(alice, doctor, start, STATUS_CONFIRMED, start))
    db.session.commit()
    assert db.session.query(Appointment).count() == 3


# --- cancelling, rescheduling, completing ---------------------------------------------


def test_cancelling_frees_the_slot_for_someone_else(alice, bob, doctor):
    start = tomorrow_at(9)
    appointment = services.book_appointment(alice, doctor, start)

    services.cancel_appointment(alice, appointment)
    assert appointment.status == STATUS_CANCELLED
    assert appointment.slot_start is None
    assert start in [slot for slot, _ in services.available_slots(doctor, start.date())]

    rebooked = services.book_appointment(bob, doctor, start)
    assert rebooked.id != appointment.id
    assert rebooked.status == STATUS_CONFIRMED


def test_rescheduling_moves_the_appointment_and_frees_the_old_slot(alice, bob, doctor):
    old, new = tomorrow_at(9), tomorrow_at(10)
    appointment = services.book_appointment(alice, doctor, old)

    services.reschedule_appointment(alice, appointment, new)
    assert (appointment.start_time, appointment.slot_start) == (new, new)
    services.book_appointment(bob, doctor, old)  # the old slot is free again


def test_rescheduling_into_a_taken_slot_is_rejected_and_changes_nothing(alice, bob, doctor):
    mine = services.book_appointment(alice, doctor, tomorrow_at(9))
    services.book_appointment(bob, doctor, tomorrow_at(10))

    with pytest.raises(services.SlotUnavailableError):
        services.reschedule_appointment(alice, mine, tomorrow_at(10))
    assert mine.start_time == tomorrow_at(9)


def test_another_patient_cannot_cancel_or_reschedule(alice, bob, doctor):
    appointment = services.book_appointment(alice, doctor, tomorrow_at(9))

    with pytest.raises(services.PermissionDeniedError):
        services.cancel_appointment(bob, appointment)
    with pytest.raises(services.PermissionDeniedError):
        services.reschedule_appointment(bob, appointment, tomorrow_at(10))
    assert appointment.status == STATUS_CONFIRMED
    assert appointment.start_time == tomorrow_at(9)


def test_only_the_treating_doctor_can_complete_and_only_once_it_has_started(
    alice, bob, doctor, doctor_user
):
    appointment = services.book_appointment(alice, doctor, tomorrow_at(9))

    with pytest.raises(services.PermissionDeniedError):
        services.complete_appointment(alice, appointment, now=appointment.end_time)
    with pytest.raises(services.BookingError, match="not started"):
        services.complete_appointment(
            doctor_user, appointment, now=appointment.start_time - timedelta(minutes=1)
        )

    services.complete_appointment(doctor_user, appointment, now=appointment.start_time)
    assert appointment.status == STATUS_COMPLETED
    # A completed visit keeps its slot reserved and can no longer be cancelled.
    with pytest.raises(services.SlotUnavailableError):
        services.book_appointment(bob, doctor, tomorrow_at(9))
    with pytest.raises(services.BookingError):
        services.cancel_appointment(alice, appointment)


# --- slots and working hours ----------------------------------------------------------


def test_available_slots_hide_booked_and_past_times(alice, doctor):
    day = tomorrow_at(9)
    assert len(services.available_slots(doctor, day.date())) == 6

    services.book_appointment(alice, doctor, day)
    remaining = [start for start, _ in services.available_slots(doctor, day.date())]
    assert day not in remaining
    assert len(remaining) == 5

    later = services.available_slots(doctor, day.date(), now=tomorrow_at(10, 15))
    assert [start.time() for start, _ in later] == [time(10, 30), time(11, 0), time(11, 30)]


def test_search_matches_name_specialization_and_department(doctor):
    assert services.search_doctors("grey") == [doctor]
    assert services.search_doctors("CARDIO") == [doctor]
    assert services.search_doctors("heart") == [doctor]
    assert services.search_doctors("dermatology") == []
    assert services.search_doctors("%") == []  # wildcards are matched literally


@pytest.mark.parametrize(
    ("weekday", "start", "end", "minutes"),
    [
        (7, time(9), time(10), 30),
        (0, time(10), time(9), 30),
        (0, time(14), time(14, 20), 30),
        (0, time(14), time(16), 2),
        (0, time(11), time(13), 30),
    ],
    ids=["bad weekday", "end before start", "shorter than a slot", "slot too short", "overlap"],
)
def test_invalid_working_hours_are_rejected(doctor, weekday, start, end, minutes):
    with pytest.raises(services.BookingError):
        services.add_availability(doctor, weekday, start, end, minutes)


def test_valid_working_hours_are_added(doctor):
    services.add_availability(doctor, 0, time(14), time(16), 20)
    assert len(doctor.availability) == 8


# --- date strip, next free slot, doctor timeline --------------------------------------


def test_free_slots_by_day_counts_each_day_separately(alice, doctor):
    first = tomorrow_at(9)
    services.book_appointment(alice, doctor, first)
    services.book_appointment(alice, doctor, tomorrow_at(10))

    by_day = services.free_slots_by_day(doctor, first.date(), 3)
    assert list(by_day) == [first.date() + timedelta(days=n) for n in range(3)]
    assert [len(slots) for slots in by_day.values()] == [4, 6, 6]


def test_next_available_skips_booked_and_past_slots(alice, doctor):
    day = tomorrow_at(9)
    assert services.next_available(doctor, now=day - timedelta(hours=1)) == day

    services.book_appointment(alice, doctor, day)
    assert services.next_available(doctor, now=day - timedelta(hours=1)) == tomorrow_at(9, 30)
    assert services.next_available(doctor, now=tomorrow_at(11, 45)) == tomorrow_at(9) + timedelta(
        days=1
    )


def test_next_available_is_none_without_working_hours(alice, doctor):
    _replace_working_hours(doctor, weekday=0, slot_minutes=30)
    today = date.today()
    sunday_start = datetime.combine(today + timedelta(days=(6 - today.weekday()) % 7), time(8, 0))
    # With hours on Mondays only, one day of lookahead from a Sunday finds nothing.
    assert services.next_available(doctor, now=sunday_start, horizon_days=1) is None


def test_specializations_lists_active_doctors_only(doctor, doctor_user):
    assert services.specializations() == ["Cardiology"]
    doctor_user.active = False
    db.session.commit()
    assert services.specializations() == []


def test_day_timeline_marks_open_booked_and_cancelled(alice, bob, doctor):
    day = tomorrow_at(9).date()
    kept = services.book_appointment(alice, doctor, tomorrow_at(9))
    dropped = services.book_appointment(bob, doctor, tomorrow_at(10))
    services.cancel_appointment(bob, dropped)

    rows, cancelled = services.day_timeline(doctor, day)
    assert [row["start"].time() for row in rows] == [
        time(9),
        time(9, 30),
        time(10),
        time(10, 30),
        time(11),
        time(11, 30),
    ]
    assert [row["appointment"] for row in rows] == [kept, None, None, None, None, None]
    assert cancelled == [dropped]


def test_day_timeline_still_shows_bookings_that_no_longer_match_the_hours(alice, doctor):
    start = tomorrow_at(9)
    appointment = services.book_appointment(alice, doctor, start)
    _replace_working_hours(doctor, start.weekday(), 20)  # 09:00 still fits, but ends at 09:20

    rows, _ = services.day_timeline(doctor, start.date())
    assert any(row["appointment"] is appointment for row in rows)
    assert [row["start"] for row in rows] == sorted(row["start"] for row in rows)
