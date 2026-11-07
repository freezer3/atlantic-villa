"""Villa Atlantic channel sync: Airbnb / Booking.com <-> Google Calendar.

Google Calendar (the Cliffs and Gardens calendars) is the single place where
every booking lives. Each run:

1. **Platforms -> Google.** Fetches each listing's iCal *export* and makes the
   matching Google calendar(s) hold exactly one event per reservation
   ("Airbnb · Cliffs", ...). Events it creates carry the private extended
   property ``source=channel-sync`` + ``listing=<name>``; it never touches any
   other event. A whole-villa listing writes into both calendars.
2. **Google -> platforms.** Writes ``ical/mirror/<listing>.ics``: every busy
   night of that listing's apartment(s) *except* the listing's own
   reservations. Airbnb / Booking import these files (served by GitHub Pages at
   https://atlanticvilla.net/ical/mirror/<listing>.ics) and close those dates.

Safety rules (tests in tests/test_channel_sync.py):

- A feed that fails to download, is not iCal, or suddenly goes from >= 2 synced
  reservations to 0 is skipped: its existing events stay in Google and stay
  blocked in every mirror. The script still finishes every healthy listing,
  then exits 1, so the run goes red and alert-router.yml opens one issue per
  outage (assigned to the owner = an email) and closes it on recovery.
- Airbnb: only ``SUMMARY:Reserved`` events are reservations. "Airbnb (Not
  available)" covers prep time, advance notice and dates Airbnb closed because
  of an imported calendar; syncing those back would loop.
- Booking.com exports everything as "CLOSED - Not available", reservations and
  closures alike, so every closed night is synced (block first). No echo
  filter: nights we cannot tell apart from a reservation (a hand copy of a
  Booking stay covers the same nights) must not be dropped. If Booking does
  re-export our imported blocks, the copy is harmless and heals itself: a
  listing's own events are never mirrored back to it, so once the source is
  gone the block leaves Booking's export and the event is deleted.
- Checkout day: platform DTEND is the checkout day. Google events are written
  with end = checkout + 1 to match how bookings are entered by hand
  (README: "data końcowa to dzień wymeldowania"), so sanitize_ical's one-day
  shift treats both the same and the checkout day stays bookable.

CLI (the sync workflow runs it after the website feed step):

    python3 scripts/channel_sync.py [--dry-run]

Env (both are repo secrets): GOOGLE_SERVICE_ACCOUNT_JSON (service-account key
with "Make changes to events" on both calendars) and CHANNEL_ICAL_URLS, a JSON
object {listing: export URL}. Listings without a URL still get a mirror file.
Without the key the script prints a notice and exits 0, so the workflow keeps
working before setup.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.request
from zoneinfo import ZoneInfo

from sanitize_ical import parse_events

CALENDARS = {
    "cliffs": "b2a835e6bed7c0910197c6510d83e2183cd6a0ef16dc04db27d6126d82f53f8b"
    "@group.calendar.google.com",
    "gardens": "38db9cfe40fa5b786c8dda63f375310c28e3a776d2b47db18d12b90c94131042"
    "@group.calendar.google.com",
}
# listing -> (platform, label shown in Google Calendar, apartments it occupies)
LISTINGS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "airbnb-villa": ("Airbnb", "cała willa", ("cliffs", "gardens")),
    "airbnb-cliffs": ("Airbnb", "Cliffs", ("cliffs",)),
    "airbnb-gardens": ("Airbnb", "Gardens", ("gardens",)),
    "booking-cliffs": ("Booking", "Cliffs", ("cliffs",)),
    "booking-gardens": ("Booking", "Gardens", ("gardens",)),
}
MIRROR_DIR = pathlib.Path("ical/mirror")
TAG = "channel-sync"
DAY = dt.timedelta(days=1)
API = "https://www.googleapis.com/calendar/v3/calendars"

Range = tuple[dt.date, dt.date]  # (check-in, checkout), checkout exclusive


def ical_range(ev: dict) -> Range | None:
    """(start, checkout) of a parsed all-day iCal event, None if it is timed."""
    if ev["start"] and ev["end"] and len(ev["start"]) == len(ev["end"]) == 10:
        return dt.date.fromisoformat(ev["start"]), dt.date.fromisoformat(ev["end"])
    return None


def reservations(listing: str, text: str, today: dt.date) -> set[Range]:
    """Current and future reservations in a platform export. Raises ValueError
    on anything that does not look like a sane feed, so the caller keeps the
    last-good state instead of deleting bookings."""
    platform = LISTINGS[listing][0]
    if "BEGIN:VCALENDAR" not in text:
        raise ValueError("response is not an iCal feed")
    events = parse_events(text)
    if text.count("BEGIN:VEVENT") != len(events):
        raise ValueError("feed has events without a unique UID; format changed?")
    out = set()
    for ev in events.values():
        if platform == "Airbnb" and ev.get("summary") != "Reserved":
            continue
        rng = ical_range(ev)
        if rng is None:
            raise ValueError(f"unexpected non all-day event {ev['start']} -> {ev['end']}")
        if rng[1] <= today or rng[1] <= rng[0]:
            continue
        out.add(rng)
    return out


def gcal_range(ev: dict) -> Range | None:
    """Google event -> (start, checkout). All-day events end one day after
    checkout (the hand-entry convention); timed events end on checkout day."""
    s, e = ev["start"], ev["end"]
    if "date" in s:
        rng = (dt.date.fromisoformat(s["date"]), dt.date.fromisoformat(e["date"]) - DAY)
    else:
        rng = (dt.date.fromisoformat(s["dateTime"][:10]), dt.date.fromisoformat(e["dateTime"][:10]))
    return rng if rng[1] > rng[0] else None


def source(ev: dict) -> str | None:
    props = ev.get("extendedProperties", {}).get("private", {})
    return props.get("listing") if props.get("source") == TAG else None


def event_body(listing: str, rng: Range) -> dict:
    platform, label, _ = LISTINGS[listing]
    return {
        "summary": f"{platform} · {label}",
        "description": (
            f"Dodane automatycznie z {platform} ({listing}). Tytuł i opis możesz zmieniać "
            f"(np. dopisać gościa). Dat nie zmieniaj i nie usuwaj: odwołanie lub zmiana dat "
            f"tylko w {platform}, kalendarz poprawi się sam."
        ),
        "start": {"date": rng[0].isoformat()},
        "end": {"date": (rng[1] + DAY).isoformat()},
        "transparency": "opaque",
        "extendedProperties": {"private": {"source": TAG, "listing": listing}},
    }


def merge(ranges: list[Range]) -> list[Range]:
    out: list[Range] = []
    for start, checkout in sorted(ranges):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], checkout))
        else:
            out.append((start, checkout))
    return out


def mirror_ics(ranges: list[Range]) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Villa Atlantic//channel-sync//EN"]
    lines.append("CALSCALE:GREGORIAN")
    for start, checkout in merge(ranges):
        lines += [
            "BEGIN:VEVENT",
            f"UID:{start:%Y%m%d}-{checkout:%Y%m%d}@atlanticvilla.net",
            f"DTSTAMP:{start:%Y%m%d}T000000Z",
            f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
            f"DTEND;VALUE=DATE:{checkout:%Y%m%d}",
            "SUMMARY:Not available",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def plan(
    feeds: dict[str, str | Exception],
    existing: dict[str, list[dict]],
    today: dt.date,
):
    """Pure core. feeds: listing -> export text, or the fetch exception
    (listings without a URL are absent). existing: apartment -> current and
    future Google events. Returns (inserts [(apt, body)], deletes [(apt, id)],
    mirrors {listing: ics}, status {listing: "ok" | error})."""
    status: dict[str, str] = {}
    want: dict[str, set[Range]] = {}
    for listing, text in feeds.items():
        units = LISTINGS[listing][2]
        try:
            if isinstance(text, Exception):
                raise ValueError(f"download failed: {text}")
            res = reservations(listing, text, today)
            synced = {
                rng
                for u in units
                for ev in existing[u]
                if source(ev) == listing and (rng := gcal_range(ev)) and rng[1] > today
            }
            if not res and len(synced) >= 2:
                raise ValueError(f"feed went from {len(synced)} reservations to 0; kept them")
        except ValueError as err:
            status[listing] = str(err)
            continue
        status[listing] = "ok"
        want[listing] = res

    inserts: list[tuple[str, dict]] = []
    deletes: list[tuple[str, str]] = []
    busy: dict[str, list[tuple[Range, str | None]]] = {u: [] for u in CALENDARS}
    for unit, events in existing.items():
        seen: set[tuple[str, Range]] = set()
        for ev in events:
            listing, rng = source(ev), gcal_range(ev)
            if rng and rng[1] <= today:
                continue  # checkout today: no longer in the feed, keep it as history
            if listing in want and (rng not in want[listing] or (listing, rng) in seen):
                deletes.append((unit, ev["id"]))  # cancelled, moved, or a duplicate
                continue
            seen.add((listing, rng))
            if rng:
                busy[unit].append((rng, listing))
        for listing, ranges in want.items():
            if unit in LISTINGS[listing][2]:
                for rng in sorted(ranges - {r for (src, r) in seen if src == listing}):
                    inserts.append((unit, event_body(listing, rng)))
                    busy[unit].append((rng, listing))

    mirrors = {
        listing: mirror_ics([rng for u in units for rng, src in busy[u] if src != listing])
        for listing, (_, _, units) in LISTINGS.items()
    }
    return inserts, deletes, mirrors, status


def _list_events(session, cal_id: str, today: dt.date) -> list[dict]:
    items, token = [], None
    while True:
        params = {"timeMin": f"{today}T00:00:00Z", "singleEvents": "true", "maxResults": 2500}
        if token:
            params["pageToken"] = token
        r = session.get(f"{API}/{cal_id}/events", params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        items += [ev for ev in data.get("items", []) if ev.get("status") != "cancelled"]
        token = data.get("nextPageToken")
        if not token:
            return items


def _fetch(url: str) -> str | Exception:
    try:  # Request() too: a malformed URL's error text would print the token
        req = urllib.request.Request(url, headers={"User-Agent": "villa-atlantic-sync/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", "replace")
    except Exception as err:  # reported per listing; never echo err: it can contain the token
        return OSError(
            " ".join(str(x) for x in (type(err).__name__, getattr(err, "code", "")) if x)
        )


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="print changes, write nothing")
    args = ap.parse_args(argv)
    key = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not key:
        print("GOOGLE_SERVICE_ACCOUNT_JSON not set; channel sync skipped.")
        return 0

    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_info(
        json.loads(key), scopes=["https://www.googleapis.com/auth/calendar.events"]
    )
    session = AuthorizedSession(creds)
    today = dt.datetime.now(ZoneInfo("Atlantic/Canary")).date()
    existing = {apt: _list_events(session, cal, today) for apt, cal in CALENDARS.items()}
    urls = json.loads(os.environ.get("CHANNEL_ICAL_URLS") or "{}")
    feeds = {name: _fetch(urls[name]) for name in LISTINGS if urls.get(name)}
    inserts, deletes, mirrors, status = plan(feeds, existing, today)
    for apt, body in inserts:
        print(f"+ {apt}: {body['summary']} {body['start']['date']} -> {body['end']['date']}")
    for apt, ev_id in deletes:
        print(f"- {apt}: event {ev_id}")
    for name, state in sorted(status.items()):
        print(f"{name}: {state}")
    failed = any(state != "ok" for state in status.values())
    if args.dry_run:
        return int(failed)

    for apt, body in inserts:
        session.post(f"{API}/{CALENDARS[apt]}/events", json=body, timeout=30).raise_for_status()
    for apt, ev_id in deletes:
        r = session.delete(f"{API}/{CALENDARS[apt]}/events/{ev_id}", timeout=30)
        if r.status_code != 410:  # 410 = already deleted
            r.raise_for_status()
    MIRROR_DIR.mkdir(parents=True, exist_ok=True)
    for name, ics in mirrors.items():
        (MIRROR_DIR / f"{name}.ics").write_text(ics, encoding="utf-8")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
