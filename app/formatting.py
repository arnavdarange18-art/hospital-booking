"""Display helpers used by the templates (registered as Jinja filters in the app factory)."""

from datetime import datetime, timedelta

DAY_PARTS = (
    ("Morning", 0, 12),
    ("Afternoon", 12, 17),
    ("Evening", 17, 24),
)


def clock(value):
    """9:05 AM (no leading zero, same on every operating system)."""
    return f"{value.hour % 12 or 12}:{value.minute:02d} {'AM' if value.hour < 12 else 'PM'}"


def long_datetime(value):
    """Tue 6 Oct 2026, 9:00 AM"""
    return f"{value:%a} {value.day} {value:%b %Y}, {clock(value)}"


def time_range(start, end):
    """9:00 - 9:30 AM when both ends share AM/PM, otherwise 11:30 AM - 12:00 PM."""
    if (start.hour < 12) == (end.hour < 12):
        return f"{clock(start)[:-3]} – {clock(end)}"
    return f"{clock(start)} – {clock(end)}"


def when(value, now=None):
    """Today, 4:30 PM / Tomorrow, 9:00 AM / Wed 7 Oct, 9:00 AM"""
    today = (now or datetime.now()).date()
    if value.date() == today:
        day = "Today"
    elif value.date() == today + timedelta(days=1):
        day = "Tomorrow"
    else:
        day = f"{value:%a} {value.day} {value:%b}"
    return f"{day}, {clock(value)}"


def ago(value, now=None):
    """just now / 5 min ago / 3 hours ago / yesterday / 12 Sep"""
    delta = (now or datetime.now()) - value
    seconds = delta.total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    if delta.days == 1:
        return "yesterday"
    return f"{value.day} {value:%b}"


def initials(name):
    """Initials for an avatar, ignoring a leading 'Dr.'."""
    words = [w for w in (name or "").replace(".", " ").split() if w.lower() != "dr"]
    return "".join(w[0] for w in words[:2]).upper() or "?"


def avatar_class(key):
    """A stable colour class for a person, so the same person always looks the same."""
    return f"av-{(key or 0) % 6}"


def group_by_day_part(slots):
    """[(start, end), ...] -> [("Morning", [...]), ("Afternoon", [...])], skipping empty parts."""
    groups = []
    for label, first_hour, last_hour in DAY_PARTS:
        chosen = [slot for slot in slots if first_hour <= slot[0].hour < last_hour]
        if chosen:
            groups.append((label, chosen))
    return groups


FILTERS = {
    "tm": clock,
    "dt": long_datetime,
    "trange": time_range,
    "when": when,
    "ago": ago,
    "initials": initials,
    "avatar_class": avatar_class,
}
