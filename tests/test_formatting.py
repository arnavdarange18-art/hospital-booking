"""The small display helpers behind the templates."""

from datetime import datetime

import pytest

from app import formatting

NOW = datetime(2026, 10, 5, 12, 0)


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2026, 10, 6, 0, 5), "12:05 AM"),
        (datetime(2026, 10, 6, 9, 0), "9:00 AM"),
        (datetime(2026, 10, 6, 12, 0), "12:00 PM"),
        (datetime(2026, 10, 6, 17, 30), "5:30 PM"),
    ],
)
def test_clock_has_no_leading_zero(moment, expected):
    assert formatting.clock(moment) == expected


def test_long_datetime():
    assert formatting.long_datetime(datetime(2026, 10, 6, 9, 0)) == "Tue 6 Oct 2026, 9:00 AM"


def test_time_range_collapses_a_shared_meridiem():
    assert formatting.time_range(datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 9, 30)) == (
        "9:00 – 9:30 AM"
    )
    assert formatting.time_range(datetime(2026, 1, 1, 11, 30), datetime(2026, 1, 1, 12)) == (
        "11:30 AM – 12:00 PM"
    )


def test_when_uses_today_and_tomorrow():
    assert formatting.when(datetime(2026, 10, 5, 16, 30), NOW) == "Today, 4:30 PM"
    assert formatting.when(datetime(2026, 10, 6, 9, 0), NOW) == "Tomorrow, 9:00 AM"
    assert formatting.when(datetime(2026, 10, 9, 9, 0), NOW) == "Fri 9 Oct, 9:00 AM"


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2026, 10, 5, 11, 59, 30), "just now"),
        (datetime(2026, 10, 5, 11, 55), "5 min ago"),
        (datetime(2026, 10, 5, 11, 0), "1 hour ago"),
        (datetime(2026, 10, 5, 9, 0), "3 hours ago"),
        (datetime(2026, 10, 4, 9, 0), "yesterday"),
        (datetime(2026, 9, 12, 9, 0), "12 Sep"),
    ],
)
def test_ago(moment, expected):
    assert formatting.ago(moment, NOW) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Meera Iyer", "MI"),
        ("Dr. Arjun Rao", "AR"),
        ("Leena D'Souza", "LD"),
        ("Cher", "C"),
        ("", "?"),
    ],
)
def test_initials(name, expected):
    assert formatting.initials(name) == expected


def test_avatar_class_is_stable_and_bounded():
    assert formatting.avatar_class(7) == formatting.avatar_class(7)
    assert {formatting.avatar_class(n) for n in range(30)} == {f"av-{n}" for n in range(6)}


def test_slots_are_grouped_by_part_of_day_and_empty_parts_are_skipped():
    def slot(hour):
        return datetime(2026, 10, 6, hour), datetime(2026, 10, 6, hour, 30)

    groups = formatting.group_by_day_part([slot(9), slot(11), slot(17), slot(19)])
    assert [(label, len(slots)) for label, slots in groups] == [("Morning", 2), ("Evening", 2)]
    assert formatting.group_by_day_part([]) == []
