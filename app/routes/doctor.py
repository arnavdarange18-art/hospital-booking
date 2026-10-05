from datetime import date, datetime, time, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .. import services
from ..extensions import db
from ..models import ROLE_DOCTOR, Appointment, Availability
from ..security import roles_required
from ..utils import parse_date

bp = Blueprint("doctor", __name__, url_prefix="/doctor")


def _me():
    return current_user._get_current_object()


def _profile():
    profile = current_user.doctor_profile
    if profile is None:
        abort(403)
    return profile


def _redirect_to_day(appointment):
    return redirect(url_for("doctor.schedule", date=appointment.start_time.date().isoformat()))


@bp.route("/schedule")
@roles_required(ROLE_DOCTOR)
def schedule():
    doctor = _profile()
    today = date.today()
    day = parse_date(request.args.get("date")) or today
    rows, cancelled = services.day_timeline(doctor, day)
    booked = sum(1 for row in rows if row["appointment"] is not None)
    return render_template(
        "doctor/schedule.html",
        day=day,
        today=today,
        now=datetime.now(),
        rows=rows,
        cancelled=cancelled,
        booked=booked,
        open_slots=len(rows) - booked,
        prev_day=day - timedelta(days=1),
        next_day=day + timedelta(days=1),
    )


@bp.route("/appointments/<int:appointment_id>/complete", methods=["POST"])
@roles_required(ROLE_DOCTOR)
def complete(appointment_id):
    appointment = db.get_or_404(Appointment, appointment_id)
    try:
        services.complete_appointment(_me(), appointment)
    except services.PermissionDeniedError:
        abort(403)
    except services.BookingError as error:
        flash(str(error), "error")
    else:
        flash("Appointment marked as completed.", "success")
    return _redirect_to_day(appointment)


@bp.route("/appointments/<int:appointment_id>/cancel", methods=["POST"])
@roles_required(ROLE_DOCTOR)
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
    return _redirect_to_day(appointment)


@bp.route("/availability", methods=["GET", "POST"])
@roles_required(ROLE_DOCTOR)
def availability():
    doctor = _profile()
    if request.method == "POST":
        try:
            weekday = int(request.form["weekday"])
            start = time.fromisoformat(request.form["start_time"])
            end = time.fromisoformat(request.form["end_time"])
            minutes = int(request.form["slot_minutes"])
        except (KeyError, ValueError):
            flash("Please fill in every field with a valid value.", "error")
        else:
            try:
                services.add_availability(doctor, weekday, start, end, minutes)
            except services.BookingError as error:
                flash(str(error), "error")
            else:
                flash("Working period added.", "success")
        return redirect(url_for("doctor.availability"))

    windows = sorted(doctor.availability, key=lambda w: (w.weekday, w.start_time))
    return render_template("doctor/availability.html", windows=windows)


@bp.route("/availability/<int:window_id>/delete", methods=["POST"])
@roles_required(ROLE_DOCTOR)
def delete_availability(window_id):
    doctor = _profile()
    window = db.get_or_404(Availability, window_id)
    if window.doctor_id != doctor.id:
        abort(403)
    db.session.delete(window)
    db.session.commit()
    flash("Working period removed.", "success")
    return redirect(url_for("doctor.availability"))
