from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import ROLE_PATIENT, User
from ..security import is_valid_email, safe_next_url

bp = Blueprint("auth", __name__)

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if request.method == "GET":
        return render_template("auth/register.html", form={})

    form = request.form
    name = form.get("name", "").strip()
    email = form.get("email", "").strip().lower()
    password = form.get("password", "")

    errors = []
    if not name or len(name) > 100:
        errors.append("Please enter your name (up to 100 characters).")
    if not is_valid_email(email):
        errors.append("Please enter a valid email address.")
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        errors.append(
            f"Password must be {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters long."
        )
    if not errors and db.session.query(User).filter_by(email=email).first():
        errors.append("An account with that email already exists.")
    if errors:
        for message in errors:
            flash(message, "error")
        return render_template("auth/register.html", form=form), 400

    user = User(name=name, email=email, role=ROLE_PATIENT)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("An account with that email already exists.", "error")
        return render_template("auth/register.html", form=form), 400

    login_user(user)
    flash("Welcome! Your account has been created.", "success")
    return redirect(url_for("main.index"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if request.method == "GET":
        return render_template("auth/login.html", form={})

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    user = db.session.query(User).filter_by(email=email).first()
    if user is None or not user.active or not user.check_password(password):
        flash("Invalid email or password.", "error")
        return render_template("auth/login.html", form=request.form), 401

    login_user(user)
    return redirect(safe_next_url(request.args.get("next")) or url_for("main.index"))


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("main.index"))
