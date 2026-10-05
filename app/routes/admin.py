from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import (
    ROLE_ADMIN,
    ROLE_DOCTOR,
    ROLE_PATIENT,
    STATUS_CONFIRMED,
    Appointment,
    Doctor,
    User,
)
from ..security import is_valid_email, roles_required
from .auth import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/")
@roles_required(ROLE_ADMIN)
def dashboard():
    users = db.session.query(User).order_by(User.role, User.name).all()
    upcoming = (
        db.session.query(Appointment)
        .filter(Appointment.status == STATUS_CONFIRMED, Appointment.start_time > datetime.now())
        .count()
    )
    stats = {
        "patients": sum(1 for u in users if u.role == ROLE_PATIENT),
        "doctors": sum(1 for u in users if u.role == ROLE_DOCTOR),
        "upcoming": upcoming,
    }
    return render_template("admin/dashboard.html", users=users, stats=stats)


@bp.route("/doctors/new", methods=["GET", "POST"])
@roles_required(ROLE_ADMIN)
def new_doctor():
    if request.method == "GET":
        return render_template("admin/new_doctor.html", form={})

    form = request.form
    name = form.get("name", "").strip()
    email = form.get("email", "").strip().lower()
    password = form.get("password", "")
    specialization = form.get("specialization", "").strip()
    department = form.get("department", "").strip()

    errors = []
    if not name or len(name) > 100:
        errors.append("Please enter the doctor's name (up to 100 characters).")
    if not is_valid_email(email):
        errors.append("Please enter a valid email address.")
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        errors.append(
            f"Password must be {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters long."
        )
    if not specialization or len(specialization) > 100:
        errors.append("Please enter a specialization (up to 100 characters).")
    if not department or len(department) > 100:
        errors.append("Please enter a department (up to 100 characters).")
    if not errors and db.session.query(User).filter_by(email=email).first():
        errors.append("An account with that email already exists.")
    if errors:
        for message in errors:
            flash(message, "error")
        return render_template("admin/new_doctor.html", form=form), 400

    user = User(name=name, email=email, role=ROLE_DOCTOR)
    user.set_password(password)
    user.doctor_profile = Doctor(specialization=specialization, department=department)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("An account with that email already exists.", "error")
        return render_template("admin/new_doctor.html", form=form), 400

    flash(f"Doctor account created for {name}.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@roles_required(ROLE_ADMIN)
def toggle_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "error")
    else:
        user.active = not user.active
        db.session.commit()
        flash(f"{user.name} is now {'active' if user.active else 'deactivated'}.", "success")
    return redirect(url_for("admin.dashboard"))
