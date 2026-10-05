import re
from functools import wraps
from urllib.parse import urlparse

from flask import abort, current_app
from flask_login import current_user

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(value):
    return bool(value) and len(value) <= 255 and EMAIL_RE.match(value) is not None


def safe_next_url(target):
    """Return ``target`` only if it is a local path, otherwise None (blocks open redirects)."""
    if not target or "\\" in target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


def roles_required(*roles):
    """Allow the view only for logged-in users with one of the given roles."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return current_app.login_manager.unauthorized()
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
