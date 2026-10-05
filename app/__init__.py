"""Hospital Appointment Booking System."""

import os

from dotenv import load_dotenv
from flask import Flask, render_template
from flask_login import current_user

from .extensions import csrf, db, login_manager
from .formatting import FILTERS
from .services import WEEKDAYS


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///hospital.db"),
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
    )
    if test_config:
        app.config.update(test_config)
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("SECRET_KEY is not set. Copy .env.example to .env and set a value.")

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "error"

    from . import models  # noqa: F401  (registers the models with SQLAlchemy)
    from .cli import register_cli
    from .routes import admin, auth, doctor, main, patient

    for module in (main, auth, patient, doctor, admin):
        app.register_blueprint(module.bp)
    register_cli(app)

    app.jinja_env.globals["WEEKDAYS"] = WEEKDAYS
    app.jinja_env.filters.update(FILTERS)

    @app.context_processor
    def inject_unread_count():
        if not current_user.is_authenticated:
            return {"unread_count": 0}
        unread = db.session.query(models.Notification).filter_by(
            user_id=current_user.id, is_read=False
        )
        return {"unread_count": unread.count()}

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
        )
        return response

    messages = {
        400: "The request could not be understood.",
        403: "You do not have permission to view this page.",
        404: "That page could not be found.",
    }

    def render_error(error):
        code = error.code or 500
        return render_template("error.html", code=code, message=messages.get(code)), code

    for code in messages:
        app.register_error_handler(code, render_error)

    return app
