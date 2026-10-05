from datetime import date, datetime

SLOT_FORMAT = "%Y-%m-%dT%H:%M"


def parse_date(value):
    """Parse YYYY-MM-DD, returning None for anything else."""
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def parse_slot_start(value):
    """Parse the slot value used in booking forms, returning None for anything else."""
    try:
        return datetime.strptime(value, SLOT_FORMAT)
    except (TypeError, ValueError):
        return None
