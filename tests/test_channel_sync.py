"""Tests for scripts/channel_sync.py (pure core only, no network)."""

import datetime as dt

import pytest
from channel_sync import (
    TAG,
    gcal_range,
    ical_range,
    looks_wiped,
    mirror_ics,
    plan,
    reservations,
)
from sanitize_ical import parse_events

TODAY = dt.date(2026, 11, 7)
D = dt.date.fromisoformat


def feed(*events):
    body = "".join(
        f"BEGIN:VEVENT\r\nUID:{i}@x\r\nDTSTART;VALUE=DATE:{s}\r\nDTEND;VALUE=DATE:{e}\r\n"
        f"SUMMARY:{summary}\r\nEND:VEVENT\r\n"
        for i, (s, e, summary) in enumerate(events)
    )
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n{body}END:VCALENDAR\r\n"


def parse_ranges(text):
    return [ical_range(ev) for ev in parse_events(text).values()]


def gev(ev_id, start, end_exclusive, listing=None):
    ev = {"id": ev_id, "start": {"date": start}, "end": {"date": end_exclusive}}
    if listing:
        ev["extendedProperties"] = {"private": {"source": TAG, "listing": listing}}
    return ev


def test_airbnb_keeps_only_reserved_and_future():
    text = feed(
        ("20261120", "20261125", "Reserved"),
        ("20261201", "20261203", "Airbnb (Not available)"),
        ("20261001", "20261005", "Reserved"),  # past
    )
    assert reservations("airbnb-cliffs", text, TODAY) == {(D("2026-11-20"), D("2026-11-25"))}


def test_booking_stay_copied_by_hand_is_still_synced():
    # Mama's hand copy is in the Booking mirror; the real Booking stay on the same nights
    # must still reach Google, or the nights open once the hand copy is cleaned up.
    existing = {"cliffs": [gev("hand", "2026-11-20", "2026-11-26")], "gardens": []}
    feeds = {"booking-cliffs": feed(("20261120", "20261125", "CLOSED - Not available"))}
    inserts, _, mirrors, _ = plan(feeds, existing, TODAY)
    assert [gcal_range(b) for _, b in inserts] == [(D("2026-11-20"), D("2026-11-25"))]
    assert parse_ranges(mirrors["booking-cliffs"]) == [(D("2026-11-20"), D("2026-11-25"))]


def test_booking_echo_of_airbnb_block_heals_after_cancellation():
    # Only if the Booking export setting is switched away from reservations-only: Booking
    # re-exports our Airbnb block; once Airbnb cancels, the echo is not served back to
    # Booking, so Booking stops exporting it and the next run deletes it.
    existing = {
        "cliffs": [gev("echo", "2026-11-20", "2026-11-26", "booking-cliffs")],
        "gardens": [],
    }
    _, _, mirrors, _ = plan({"airbnb-cliffs": feed()}, existing, TODAY)
    assert parse_ranges(mirrors["booking-cliffs"]) == []
    assert parse_ranges(mirrors["airbnb-cliffs"]) == [(D("2026-11-20"), D("2026-11-25"))]
    _, deletes, _, _ = plan({"booking-cliffs": feed()}, existing, TODAY)
    assert deletes == [("cliffs", "echo")]


@pytest.mark.parametrize(
    "text", ["<html>login</html>", "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nEND:VEVENT\r\n"]
)
def test_bad_feed_raises(text):
    with pytest.raises(ValueError):
        reservations("airbnb-cliffs", text, TODAY)


def test_checkout_convention_round_trip():
    # Platform checkout 25th -> Google all-day end 26th (hand-entry convention) -> back to 25th.
    inserts, _, _, _ = plan(
        {"airbnb-cliffs": feed(("20261120", "20261125", "Reserved"))},
        {"cliffs": [], "gardens": []},
        TODAY,
    )
    ((apt, body),) = inserts
    assert apt == "cliffs" and body["end"] == {"date": "2026-11-26"}
    assert gcal_range(body) == (D("2026-11-20"), D("2026-11-25"))


def test_villa_listing_writes_both_and_blocks_apartment_listings():
    inserts, _, mirrors, status = plan(
        {"airbnb-villa": feed(("20261120", "20261125", "Reserved"))},
        {"cliffs": [], "gardens": []},
        TODAY,
    )
    assert sorted(a for a, _ in inserts) == ["cliffs", "gardens"]
    assert status == {"airbnb-villa": "ok"}
    assert parse_ranges(mirrors["booking-gardens"]) == [(D("2026-11-20"), D("2026-11-25"))]
    assert "airbnb-villa" not in mirrors  # importing it spreads blocks to both apartments


def test_booking_stay_blocks_airbnb_apartment_not_its_own_room():
    existing = {
        "cliffs": [gev("m1", "2026-11-10", "2026-11-16")],  # manual, checkout 15th
        "gardens": [gev("s1", "2026-11-15", "2026-11-19", "booking-gardens")],
    }
    feeds = {"booking-gardens": feed(("20261115", "20261118", "CLOSED - Not available"))}
    inserts, deletes, mirrors, _ = plan(feeds, existing, TODAY)
    assert inserts == [] and deletes == []
    assert parse_ranges(mirrors["airbnb-gardens"]) == [(D("2026-11-15"), D("2026-11-18"))]
    assert parse_ranges(mirrors["airbnb-cliffs"]) == [(D("2026-11-10"), D("2026-11-15"))]
    assert parse_ranges(mirrors["booking-gardens"]) == []


@pytest.mark.parametrize("summary", ["Reserved - Jan K.", "Pending", ""])
def test_unknown_airbnb_label_fails_instead_of_dropping_the_stay(summary):
    with pytest.raises(ValueError):
        reservations("airbnb-cliffs", feed(("20261120", "20261125", summary)), TODAY)


def test_truncated_feed_raises():
    text = feed(("20261120", "20261125", "Reserved")).replace("END:VCALENDAR\r\n", "")
    with pytest.raises(ValueError):
        reservations("airbnb-cliffs", text, TODAY)


def test_wiped_calendar_changes_nothing_and_keeps_its_mirrors():
    existing = {"cliffs": [], "gardens": [gev("g", "2026-12-01", "2026-12-04", "booking-gardens")]}
    feeds = {
        "booking-cliffs": feed(("20261120", "20261125", "CLOSED - Not available")),
        "booking-gardens": feed(("20261201", "20261203", "CLOSED - Not available")),
    }
    inserts, deletes, mirrors, status = plan(feeds, existing, TODAY, frozenset({"cliffs"}))
    assert inserts == [] and deletes == []
    assert status["booking-cliffs"] != "ok" and status["booking-gardens"] == "ok"
    assert "booking-cliffs" not in mirrors and "airbnb-cliffs" not in mirrors  # old files stay
    assert "booking-gardens" in mirrors


def test_looks_wiped_only_when_future_stays_vanish():
    site = feed(("20261120", "20261125", "Booked"), ("20261201", "20261203", "Booked"))
    past_only = feed(("20260301", "20260305", "Booked"), ("20260601", "20260605", "Booked"))
    assert looks_wiped(site, [], TODAY)
    assert not looks_wiped(site, [dict(gev("x", "2026-11-20", "2026-11-26"), iCalUID="0@x")], TODAY)
    assert not looks_wiped(past_only, [], TODAY)  # quiet season: first booking still syncs
    assert not looks_wiped(feed(), [], TODAY)  # confirmed wipe emptied the site feed
    timed = (
        "BEGIN:VCALENDAR\r\n"
        + "".join(
            f"BEGIN:VEVENT\r\nUID:t{i}\r\nDTSTART:{d}T150000Z\r\nDTEND:{d}T180000Z\r\nEND:VEVENT\r\n"
            for i, d in enumerate(("20260301", "20260601"))
        )
        + "END:VCALENDAR\r\n"
    )
    assert not looks_wiped(timed, [], TODAY)  # past timed entries are not future stays
    leftovers = [gev("out", "2026-11-03", "2026-11-08"), gev("note", "2026-11-20", "2026-11-21")]
    assert looks_wiped(site, leftovers, TODAY)  # checkout today + one-day note hide nothing
    assert looks_wiped(site, [dict(gev("new", "2027-01-10", "2027-01-16"), iCalUID="n@x")], TODAY)
    notes = (
        "BEGIN:VCALENDAR\r\n"
        + "".join(
            f"BEGIN:VEVENT\r\nUID:n{i}\r\nDTSTART:{d}T090000Z\r\nDTEND:{d}T110000Z\r\nEND:VEVENT\r\n"
            for i, d in enumerate(("20261120", "20261203"))
        )
        + "END:VCALENDAR\r\n"
    )
    assert not looks_wiped(notes, [], TODAY)  # same-day timed notes are not stays


def test_wiped_calendar_still_syncs_villa_into_the_healthy_one():
    existing = {"cliffs": [], "gardens": []}
    feeds = {"airbnb-villa": feed(("20261120", "20261125", "Reserved"))}
    inserts, deletes, mirrors, status = plan(feeds, existing, TODAY, frozenset({"cliffs"}))
    assert [apt for apt, _ in inserts] == ["gardens"] and deletes == []
    assert status["airbnb-villa"] != "ok"  # run still goes red
    assert "20261120" in mirrors["booking-gardens"] and "booking-cliffs" not in mirrors


def test_synced_event_moved_to_other_calendar_is_replaced():
    existing = {
        "cliffs": [],
        "gardens": [gev("moved", "2026-11-20", "2026-11-26", "airbnb-cliffs")],
    }
    existing["cliffs"].append(gev("hand", "2026-12-10", "2026-12-12"))
    inserts, deletes, _, _ = plan(
        {"airbnb-cliffs": feed(("20261120", "20261125", "Reserved"))}, existing, TODAY
    )
    assert deletes == [("gardens", "moved")]
    assert [a for a, _ in inserts] == ["cliffs"]


def test_cancel_deletes_only_synced_events_and_duplicates():
    existing = {
        "cliffs": [
            gev("keep", "2026-11-20", "2026-11-26", "airbnb-cliffs"),
            gev("dup", "2026-11-20", "2026-11-26", "airbnb-cliffs"),
            gev("gone", "2026-12-01", "2026-12-04", "airbnb-cliffs"),
            gev("manual", "2026-12-01", "2026-12-04"),
        ],
        "gardens": [],
    }
    feeds = {"airbnb-cliffs": feed(("20261120", "20261125", "Reserved"))}
    _, deletes, _, _ = plan(feeds, existing, TODAY)
    assert sorted(i for _, i in deletes) == ["dup", "gone"]


@pytest.mark.parametrize("bad", [OSError("timeout"), "<html>", feed()])
def test_failed_or_wiped_feed_keeps_events_and_blocks(bad):
    existing = {
        "cliffs": [
            gev("a", "2026-11-20", "2026-11-26", "airbnb-cliffs"),
            gev("b", "2026-12-01", "2026-12-04", "airbnb-cliffs"),
        ],
        "gardens": [],
    }
    inserts, deletes, mirrors, status = plan({"airbnb-cliffs": bad}, existing, TODAY)
    assert inserts == [] and deletes == []
    assert status["airbnb-cliffs"] != "ok"
    assert len(parse_ranges(mirrors["booking-cliffs"])) == 2


def test_single_checkout_is_not_a_wipe():
    existing = {"cliffs": [gev("a", "2026-11-20", "2026-11-26", "airbnb-cliffs")], "gardens": []}
    _, deletes, _, status = plan({"airbnb-cliffs": feed()}, existing, TODAY)
    assert deletes == [("cliffs", "a")] and status == {"airbnb-cliffs": "ok"}


def test_mirror_is_valid_and_deterministic():
    ics = mirror_ics([(D("2026-11-20"), D("2026-11-25")), (D("2026-11-25"), D("2026-11-27"))])
    assert ics == mirror_ics(
        [(D("2026-11-25"), D("2026-11-27")), (D("2026-11-20"), D("2026-11-25"))]
    )
    assert (
        ics.count("BEGIN:VEVENT") == 1 and "DTSTAMP:" in ics and "DTEND;VALUE=DATE:20261127" in ics
    )


def test_checkout_day_keeps_event_and_does_not_count_for_wipe():
    # Google still lists an event on its checkout day; the feed no longer has it.
    today = D("2026-11-25")
    existing = {
        "cliffs": [
            gev("left", "2026-11-20", "2026-11-26", "airbnb-cliffs"),  # checkout today
            gev("cancelled", "2026-12-01", "2026-12-04", "airbnb-cliffs"),
        ],
        "gardens": [],
    }
    _, deletes, _, status = plan({"airbnb-cliffs": feed()}, existing, today)
    assert deletes == [("cliffs", "cancelled")] and status == {"airbnb-cliffs": "ok"}
