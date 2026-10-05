from datetime import date, datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .. import services
from ..extensions import db
from ..formatting import group_by_day_part
from ..models import ROLE_PATIENT, STATUS_CONFIRMED, Appointment, Doctor
from ..security import roles_required
from ..utils import parse_date, parse_slot_start

bp = Blueprint("patient", __name__, url_prefix="/patient")

STRIP_DAYS = 14


def _me():
    return current_user._get_current_object()


def _bookable_doctor_or_404(doctor_id):
    doctor = db.session.get(Doctor, doctor_id) if doctor_id is not None else None
    if doctor is None or not doctor.user.active:
        abort(404)
    return doctor


def _picker(doctor, endpoint, **url_args):
    """Everything the date strip and slot buttons need for the day in ``?date=``."""
    today = date.today()
    last_day = today + timedelta(days=services.MAX_ADVANCE_DAYS)
    wanted = parse_date(request.args.get("date"))
    if wanted is None:
        # No day chosen yet: open on the first day with free times, not an empty "today".
        soonest = services.next_available(doctor)
        wanted = soonest.date() if soonest else today
    day = min(max(wanted, today), last_day)

    first = today + timedelta(days=((day - today).days // STRIP_DAYS) * STRIP_DAYS)
    count = min(STRIP_DAYS, (last_day - first).days + 1)
    free = services.free_slots_by_day(doctor, first, count)

    def link(target):
        return url_for(endpoint, date=target.isoformat(), **url_args)

    earlier = first - timedelta(days=STRIP_DAYS)
    later = first + timedelta(days=STRIP_DAYS)
    return {
        "day": day,
        "today": today,
        "strip": [{"date": d, "free": len(s), "url": link(d)} for d, s in free.items()],
        "prev_url": link(earlier) if earlier >= today else None,
        "next_url": link(later) if later <= last_day else None,
        "groups": group_by_day_part(free[day]),
        "total": len(free[day]),
    }


@bp.route("/doctors")
@roles_required(ROLE_PATIENT)
def doctors():
    query = request.args.get("q", "").strip()
    found = services.search_doctors(query)
    return render_template(
        "patient/doctors.html",
        doctors=found,
        query=query,
        specializations=services.specializations(),
        next_slots={doctor.id: services.next_available(doctor) for doctor in found},
    )


@bp.route("/doctors/<int:doctor_id>")
@roles_required(ROLE_PATIENT)
def doctor_detail(doctor_id):
    doctor = _bookable_doctor_or_404(doctor_id)
    return render_template(
        "patient/doctor_detail.html",
        doctor=doctor,
        picker=_picker(doctor, "patient.doctor_detail", doctor_id=doctor.id),
        hours=sorted(doctor.availability, key=lambda w: (w.weekday, w.start_time)),
    )


@bp.route("/book", methods=["POST"])
@roles_required(ROLE_PATIENT)
def book():
    doctor = _bookable_doctor_or_404(request.form.get("doctor_id", type=int))
    start = parse_slot_start(request.form.get("start"))
    if start is None:
        abort(400)
    try:
        services.book_appointment(_me(), doctor, start)
    except services.BookingError as error:
        flash(str(error), "error")
        return redirect(
            url_for("patient.doctor_detail", doctor_id=doctor.id, date=start.date().isoformat())
        )
    flash("Appointment confirmed.", "success")
    return redirect(url_for("patient.appointments"))


@bp.route("/appointments")
@roles_required(ROLE_PATIENT)
def appointments():
    now = datetime.now()
    mine = (
        db.session.query(Appointment)
        .filter_by(patient_id=current_user.id)
        .order_by(Appointment.start_time)
        .all()
    )
    upcoming = [a for a in mine if a.status == STATUS_CONFIRMED and a.end_time > now]
    history = [a for a in reversed(mine) if a not in upcoming]
    return render_template("patient/appointments.html", upcoming=upcoming, history=history)


@bp.route("/appointments/<int:appointment_id>/cancel", methods=["POST"])
@roles_required(ROLE_PATIENT)
def cancel(appointment_id):
    appointment = db.get_or_404(Appointment, appointment_id)
    try:
        services.cancel_appointment(_me(), appointment)
    except services.PermissionDeniedError:
        abort(403)
    except services.BookingError as error:
        flash(str(error), "error")
    else:
        flash("Appointment cancelled.", "success")
    return redirect(url_for("patient.appointments"))


@bp.route("/appointments/<int:appointment_id>/reschedule", methods=["GET", "POST"])
@roles_required(ROLE_PATIENT)
def reschedule(appointment_id):
    appointment = db.get_or_404(Appointment, appointment_id)
    if appointment.patient_id != current_user.id:
        abort(403)

    if request.method == "POST":
        start = parse_slot_start(request.form.get("start"))
        if start is None:
            abort(400)
        try:
            services.reschedule_appointment(_me(), appointment, start)
        except services.PermissionDeniedError:
            abort(403)
        except services.BookingError as error:
            flash(str(error), "error")
            return redirect(
                url_for(
                    "patient.reschedule",
                    appointment_id=appointment.id,
                    date=start.date().isoformat(),
                )
            )
        flash("Appointment rescheduled.", "success")
        return redirect(url_for("patient.appointments"))

    if appointment.status != STATUS_CONFIRMED:
        flash("Only confirmed appointments can be rescheduled.", "error")
        return redirect(url_for("patient.appointments"))
    return render_template(
        "patient/reschedule.html",
        appointment=appointment,
        picker=_picker(appointment.doctor, "patient.reschedule", appointment_id=appointment.id),
    )
