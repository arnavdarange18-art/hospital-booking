from datetime import date, timedelta

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import ROLE_ADMIN, ROLE_DOCTOR, Notification

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    if not current_user.is_authenticated:
        # The landing page shows a sample booking, dated relative to today so it never looks stale.
        sample_days = [date.today() + timedelta(days=offset) for offset in range(1, 6)]
        return render_template("index.html", sample_days=sample_days)
    if current_user.role == ROLE_ADMIN:
        return redirect(url_for("admin.dashboard"))
    if current_user.role == ROLE_DOCTOR:
        return redirect(url_for("doctor.schedule"))
    return redirect(url_for("patient.doctors"))


@bp.route("/notifications")
@login_required
def notifications():
    items = (
        db.session.query(Notification)
        .filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(50)
        .all()
    )
    return render_template("notifications.html", items=items)


@bp.route("/notifications/read", methods=["POST"])
@login_required
def mark_read():
    db.session.query(Notification).filter_by(user_id=current_user.id, is_read=False).update(
        {"is_read": True}
    )
    db.session.commit()
    return redirect(url_for("main.notifications"))
