# -*- coding: utf-8 -*-
"""
GitHub schedules run on UTC. Midnight in Cairo is 21:00 UTC in summer (UTC+3)
and 22:00 UTC in winter (UTC+2), so the workflow is triggered at both times and
this check lets only the one that is really 00:00 in Cairo continue.
Manual runs ("Run workflow" button) always continue.

Reads EVENT (github.event_name) and SCHEDULE (github.event.schedule, e.g. '0 21 * * *');
writes run=true/false to $GITHUB_OUTPUT.
"""
import datetime
import os
from zoneinfo import ZoneInfo

CAIRO = ZoneInfo('Africa/Cairo')


def should_run(event, schedule, now_utc):
    if event != 'schedule':
        return True, 'manual run'
    parts = (schedule or '').split()
    if len(parts) < 2:
        return True, f'unrecognised schedule {schedule!r} - running anyway'
    minute, hour = int(parts[0]), int(parts[1])
    # The scheduled time this trigger belongs to (GitHub can start a few minutes late)
    sched = now_utc.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if sched > now_utc:
        sched -= datetime.timedelta(days=1)
    cairo = sched.astimezone(CAIRO)
    # Run on the first trigger after the Cairo date changes. Normally that is 00:00;
    # on the night summer time starts, clocks jump from 23:59 to 01:00, so it is 01:00.
    hour_before = (sched - datetime.timedelta(hours=1)).astimezone(CAIRO)
    ok = cairo.date() != hour_before.date()
    return ok, f"trigger {sched:%H:%M} UTC = {cairo:%Y-%m-%d %H:%M %Z} in Cairo"


if __name__ == '__main__':
    now = datetime.datetime.now(datetime.timezone.utc)
    run, why = should_run(os.environ.get('EVENT', ''), os.environ.get('SCHEDULE', ''), now)
    print(('RUN: ' if run else 'SKIP: ') + why)
    out = os.environ.get('GITHUB_OUTPUT')
    if out:
        with open(out, 'a') as fh:
            fh.write(f"run={'true' if run else 'false'}\n")
