"""Villa Atlantic sync guard.

Refuses to let an accidental full calendar wipe blank the live site.

A "wipe" is the one dangerous pattern observed in production: a calendar that
held real bookings suddenly returns *zero* events from Google (someone deleted
everything, or the feed broke). Publishing that empties the site and invites
double-bookings.

The guard trips on either condition, per feed:

    previous feed had >= 2 events         AND  new feed has 0 events
    previous feed had >= 2 future stays   AND  new feed has 0 future stays

The second catches every upcoming booking deleted while past ones remain
(future = ends after today on the Canary Islands, the same for both feeds, so
time passing never trips it; it also means a wipe left unconfirmed stops being
held once fewer than 2 of the held stays are still ahead). Anything else
publishes normally: a single checkout (1 -> 0), partial change (2 -> 1),
additions, reorders. The 2+ floor avoids tripping on a calendar that only ever
had one booking.

CLI (used by the sync workflow):

    python3 scripts/sync_guard.py <before.ics> <after.ics>

Exit 0 = safe to publish. Exit 3 = wipe detected, do NOT publish. Exit 2 =
usage error. On a wipe it prints a human-readable summary to stdout (consumed
into the alert email).
"""

from __future__ import annotations

import datetime as dt
import pathlib
import sys
from zoneinfo import ZoneInfo

from sanitize_ical import parse_events

WIPE_EXIT = 3


def future(events: dict[str, dict], today: dt.date) -> dict[str, dict]:
    """Events ending after today. Timed values stay raw (20261103T070000Z) and
    date-only ones are YYYY-MM-DD, so compare digits only."""
    cutoff = f"{today:%Y%m%d}"
    return {
        uid: ev for uid, ev in events.items() if (ev["end"] or "").replace("-", "")[:8] > cutoff
    }


def is_wipe(before_text: str, after_text: str, today: dt.date) -> bool:
    """True iff all events, or all future stays, went from >= 2 to 0."""
    before, after = parse_events(before_text), parse_events(after_text)
    if len(before) >= 2 and not after:
        return True
    return len(future(before, today)) >= 2 and not future(after, today)


def _main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} <before.ics> <after.ics>", file=sys.stderr)
        return 2
    before_path, after_path = pathlib.Path(argv[1]), pathlib.Path(argv[2])
    before_text = before_path.read_text(encoding="utf-8") if before_path.exists() else ""
    after_text = after_path.read_text(encoding="utf-8") if after_path.exists() else ""
    before = parse_events(before_text)
    after = parse_events(after_text)
    today = dt.datetime.now(ZoneInfo("Atlantic/Canary")).date()
    if is_wipe(before_text, after_text, today):
        gone = before if not after else future(before, today)
        what = "events" if not after else "future stays"
        print(f"WIPE: feed went from {len(gone)} {what} to 0.")
        for uid, ev in sorted(gone.items(), key=lambda kv: (kv[1]["start"] or "", kv[0])):
            print(f"  vanished: {ev['start']} -> {ev['end']}  (uid {uid})")
        return WIPE_EXIT
    print(f"OK: {len(before)} -> {len(after)} events.")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
