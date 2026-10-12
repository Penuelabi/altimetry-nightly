# -*- coding: utf-8 -*-
"""
Gate for the weekly email digest and the social posts: the week's news must be compiled and verified first.

data/news.json carries two top-level fields written by the weekly news-compile task only after all of its
verification passes are done:
    "compiled": "YYYY-MM-DD"      date of the compile
    "verified_passes": 10          number of full verification passes completed

Rules (scheduled runs only; manual "Run workflow" runs are never blocked, they only print a warning):
  * Sunday 21:30 UTC run (the weekly email): compiled must be that Sunday's date (a run delayed past UTC midnight still counts as Sunday), with at least MIN_PASSES passes.
  * Other scheduled runs (social posts): compiled must be within SOCIAL_MAX_AGE_DAYS days, same passes rule.
Writes email_ok / social_ok (true/false) to $GITHUB_OUTPUT and a note to the run summary. It never fails the run.
"""
import datetime
import json
import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'news.json')
MIN_PASSES = 10
SOCIAL_MAX_AGE_DAYS = 7
SUNDAY_EMAIL_SCHEDULE = '30 21 * * 0'


def evaluate(event, schedule, today, doc):
    """Return (email_ok, social_ok, reason)."""
    try:
        compiled = datetime.date.fromisoformat(str((doc or {}).get('compiled')))
    except ValueError:
        compiled = None
    passes = (doc or {}).get('verified_passes')
    passes = passes if isinstance(passes, int) else 0
    if compiled is None:
        state, age = 'news.json has no compile date', None
    else:
        age = (today - compiled).days
        state = f'news compiled {compiled}, verified {passes}x (needs {MIN_PASSES}x)'
    verified = passes >= MIN_PASSES
    if event != 'schedule':
        return True, True, f'manual run, not gated. {state}'
    if schedule == SUNDAY_EMAIL_SCHEDULE:
        # GitHub often starts this run hours late, after UTC midnight, so "today" can already be Monday.
        # The run still belongs to the Sunday it was scheduled for: the most recent Sunday on or before today.
        sunday = today - datetime.timedelta(days=(today.weekday() + 1) % 7)
        ok = compiled is not None and compiled == sunday and verified
        why = 'ok' if ok else "this Sunday's news is not compiled and verified yet, so the email and social posts are skipped"
        return ok, ok, f'{why}. {state}'
    ok = compiled is not None and 0 <= age <= SOCIAL_MAX_AGE_DAYS and verified
    why = 'ok' if ok else 'news is missing, stale or unverified, so social posts are skipped'
    return True, ok, f'{why}. {state}'


def main():
    try:
        doc = json.load(open(PATH, encoding='utf-8'))
    except Exception as e:
        doc = {}
        print(f'WARNING: news.json not read ({type(e).__name__}: {e})')
    today = datetime.datetime.now(datetime.timezone.utc).date()
    email_ok, social_ok, reason = evaluate(os.environ.get('EVENT', ''), os.environ.get('SCHEDULE', ''), today, doc)
    print(f'NEWS GATE: email_ok={email_ok} social_ok={social_ok} - {reason}')
    out = os.environ.get('GITHUB_OUTPUT')
    if out:
        with open(out, 'a') as fh:
            fh.write(f"email_ok={'true' if email_ok else 'false'}\nsocial_ok={'true' if social_ok else 'false'}\n")
    summ = os.environ.get('GITHUB_STEP_SUMMARY')
    if summ:
        with open(summ, 'a') as fh:
            fh.write(f"### News gate\nemail: {'send' if email_ok else 'SKIPPED'}, social: {'post' if social_ok else 'SKIPPED'}. {reason}\n")


if __name__ == '__main__':
    main()
