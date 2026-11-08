"""Tests for scripts/sync_guard.py — the accidental-wipe guard.

The guard must trip on exactly one pattern: a feed that held >= 2 bookings
suddenly returning 0 (all events, or all future stays). Everything else publishes normally.
"""

import datetime as dt

import pytest
from sanitize_ical import parse_events
from sync_guard import future, is_wipe

TODAY = dt.date(2025, 12, 1)  # every _feed event is in the future


def _feed(n: int) -> str:
    """An iCal feed carrying n distinct all-day events."""
    events = "".join(
        f"BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:2026010{i}\r\n"
        f"DTEND;VALUE=DATE:2026010{i + 1}\r\nUID:e{i}@google.com\r\nEND:VEVENT\r\n"
        for i in range(1, n + 1)
    )
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n{events}END:VCALENDAR\r\n"


@pytest.mark.parametrize(
    "before_n,after_n,expected",
    [
        (2, 0, True),  # full wipe of a busy calendar — the dangerous case
        (3, 0, True),
        (1, 0, False),  # a lone booking checking out is normal
        (2, 1, False),  # partial change is normal
        (0, 0, False),  # already empty stays empty
        (0, 2, False),  # fresh bookings appearing is normal
        (5, 5, False),  # unchanged
    ],
)
def test_is_wipe(before_n, after_n, expected):
    assert is_wipe(_feed(before_n), _feed(after_n), TODAY) is expected


def test_missing_before_is_not_a_wipe():
    """Empty/absent before state must never be read as a wipe."""
    assert is_wipe("", _feed(0), TODAY) is False
    assert is_wipe("", _feed(3), TODAY) is False


def test_future_stays_deleted_while_history_remains_is_a_wipe():
    later = dt.date(2026, 1, 4)  # e1..e3 are past, e4..e5 still ahead
    assert is_wipe(_feed(5), _feed(3), later) is True
    assert is_wipe(_feed(5), _feed(4), later) is False  # one of two cancelled
    assert is_wipe(_feed(5), _feed(5), dt.date(2026, 2, 1)) is False  # time passing


def test_past_timed_entries_are_not_future():
    timed = (
        "BEGIN:VCALENDAR\r\n"
        + "".join(
            f"BEGIN:VEVENT\r\nUID:t{i}\r\nDTSTART:{d}T150000Z\r\nDTEND:{d}T180000Z\r\nEND:VEVENT\r\n"
            for i, d in enumerate(("20260301", "20260601"))
        )
        + "END:VCALENDAR\r\n"
    )
    assert future(parse_events(timed), dt.date(2026, 11, 7)) == {}
    assert len(future(parse_events(timed), dt.date(2026, 5, 1))) == 1
