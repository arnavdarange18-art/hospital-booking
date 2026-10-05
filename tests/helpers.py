from datetime import date, datetime, time, timedelta

USER_PW = "Tr0ub4dor&3-testing"

ADMIN = "admin@example.com"
DOCTOR = "doctor@example.com"
ALICE = "alice@example.com"
BOB = "bob@example.com"


def tomorrow_at(hour, minute=0):
    """A moment tomorrow, so the slot is always in the future whatever day the tests run."""
    return datetime.combine(date.today() + timedelta(days=1), time(hour, minute))


def slot_value(moment):
    return moment.strftime("%Y-%m-%dT%H:%M")
