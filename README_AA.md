# Anticipatory action add-ons for the Sudd hydro-climate platform

Seven standalone Python scripts that extend the "Rainfall Outlook and Observed River Level Status" app
(repository `altimetry-nightly`) so its outputs serve the **South Sudan Roadmap on Anticipatory Action 2025-2030**,
Pillars 1, 2, 3 and 5. They read the files the app already produces and never modify the existing scripts.

## The add-ons

| File | Pillar | Actions (roadmap activities served) | Indicators logged | Main outputs |
|---|---|---|---|---|
| `aa_p1_risk_profile.py` | 1 Risk knowledge | County flood-risk profile (INFORM-style: hazard and impact history, exposure, vulnerability, lack of coping); profile by livelihood zone; risk map; HXL export for the IMS | Counties with a risk profile; livelihood zones analysed; vulnerability indicators in use; risk maps produced; risk datasets exported in HXL | `p1_county_risk_profile.csv`, `_hxl.csv`, `p1_zone_profile.csv`, `p1_risk_map.png`, method notes with a validation checklist |
| `aa_p2_trigger_scorecard.py` | 2 Triggers and EWS | Scores five kinds of river signal as flood triggers: water level, seasonal anomaly (how unusual for the time of year), rise since the dry-season low, the Sudd regional upstream index, and county signal + regional index. Only upstream or local gauges with medium/high-confidence thresholds are used. Impacts = flood displacement or listing in a flood assessment, on time where the onset month is known. Proposes a readiness and an activation rule per county, with suggested plan rules; trigger design note for SSMS / MWRI | Hazards with defined thresholds; counties with proposed and with validated triggers; skill evaluations | `aa_triggers.csv`, season skill table, county track record, `p2_trigger_design_note.md`, signal charts |
| `aa_p2_data_package.py` | 2 Triggers and EWS (also 1) | Checks every table (columns, keys, ranges, ordered thresholds, freshness, 79-county coverage) and builds a documented package for the national EW repository: CSV + HXL copies, Frictionless `datapackage.json` with checksums, README | Datasets packaged and validated; datasets failing validation; risk and trigger datasets in HXL | `aa_out/repository/aa_data_package_<stamp>.zip`, `aa_data_package_latest.zip` |
| `aa_p3_aap_engine.py` | 3 Anticipatory action | Anticipatory action plans kept in two spreadsheets (rules, season, targets, budget, funding and release rule, leads, M&E, validation); checks them at every run; moves plans normal -> readiness -> activated; checklists with due dates; activation reports | AAPs developed; AAPs validated; plans in readiness or activated; readiness stages reached; AAPs activated (validated plans only) | `aap_status_latest.csv`, `aap_checklist_latest.md`, `aap_activation_log.csv`, `aap_reports/*.md` |
| `aa_p3_simulation.py` | 3 Anticipatory action | Replays past seasons through a plan (same rules as the engine), drills with a raised river or injected alerts, multi-season review of hits, late, misses and false alarms; exercise packs with injects and an evaluation sheet | Simulation packs prepared; exercises conducted (once `conducted_date` is filled); retrospective plan tests | `aa_out/simulations/SIM-.../` (exercise_pack.md, timeline.csv, evaluation.csv, hydrograph.png) |
| `aa_p5_dissemination.py` | 5 Coordination (also 2, local languages) | National and state TWG-AA situation briefs with decisions needed; SMS (<= 160 characters) and radio scripts per county in every language with a validated template; distribution plan per coordination group; feedback and meetings logs | Briefs prepared; warning messages prepared; subnational TWG-AA groups active; radio hubs / community groups registered; languages with validated templates | `aa_out/dissemination/latest/`, `dissemination_log.csv` |
| `aa_p5_indicator_tracker.py` | 5 Coordination | Quarterly progress report against yearly targets for the TWG-AA meeting: last four quarters, year to date, % achieved, plan decisions, gaps, next steps | Reads all of the above, plus meetings held, items sent and community feedback | `p5_indicator_report_<YYYYQn>.md/.csv/.png` |

## How they connect to the app

```
nightly altimetry  -> merged_altimetry_stations.csv, station_status.csv              (ALTIMETRY_OUT_DIR)
county bulletin    -> county_bulletin_latest.csv, county_station_link.csv,
                      counties_dissolved.geojson, sudd_trigger_log.csv               (BULLETIN_OUT_DIR)
repository data/   -> population, flood assessments, DTM displacement, settlements, exposure_cache.json

weekly    aa_p1_risk_profile -> aa_p2_trigger_scorecard -> aa_p5_indicator_tracker
each run  aa_p3_aap_engine -> aa_p5_dissemination -> aa_p2_data_package
on demand aa_p3_simulation
```

Every script writes to `aa_out/` and reads its editable settings from `aa_config/` (both created next to the
scripts; override with `AA_OUT_DIR`, `AA_CONFIG_DIR`, `AA_DATA_DIR`). Each one appends its indicator values to
`aa_out/aa_indicator_ledger.csv`, which the tracker turns into the quarterly report.

## Setting up

1. Copy the seven `aa_*.py` files to the repository root, next to `county_bulletin.py`.
2. Add `matplotlib` to `requirements-bulletin.txt` (charts are skipped without it; everything else runs).
3. Optional: copy `aa-addons.yml` to `.github/workflows/`. It runs after each county bulletin, uses the same
   secrets, rebuilds the weekly pieces on Mondays, uploads the data package as a run artifact and commits
   `aa_config/` and `aa_out/` (not the zips or dated folders, to keep the repository small).
4. In Colab: set `BULLETIN_OUT_DIR` and `ALTIMETRY_OUT_DIR` to your Drive folders and run the scripts in the order above.

Every script has `--selftest` (synthetic data, no inputs needed).

## What the TWG-AA fills in (`aa_config/`, templates written on the first run)

| File | What to enter |
|---|---|
| `aap_plans.csv`, `aap_actions.csv` | The plans and their pre-agreed actions. The first run writes draft examples for the six highest-risk counties with a gauge; replace them and set `status` to `validated` with `validated_by` / `validated_date` once adopted |
| `county_vulnerability.csv` | Vulnerability (`v_*`, more = more vulnerable) and coping (`c_*`, more = more capacity) columns, e.g. IPC phase, IDP share |
| `county_livelihood_zones.csv` | FEWS NET livelihood zone per county (share per zone if a county spans several) |
| `message_templates.csv` | Translations of the English templates; a language is used once `text` and `validated_by` are filled |
| `recipient_groups.csv` | Coordination groups and radio hubs, their channel, languages and alert threshold (no personal contacts) |
| `simulation_injects.csv` | Exercise injects and expected responses |
| `meetings_log.csv`, `feedback_log.csv` | TWG-AA meetings, and what communities heard, understood and did |
| `indicator_targets.csv` | Yearly targets 2026-2030 for each indicator |

Trigger levels are confirmed in `aa_out/aa_triggers.csv` (`validated_by`, `validated_date`); the scorecard keeps
validated levels on later runs.

## Writing plan rules

Rules are short expressions over named values, for example:

```
river_level_m >= activation_level_m or (alert_level == 'red' and alert_hazard == 'flood / waterlogging')
```

`python aa_p3_aap_engine.py --list-variables` prints every name (bulletin alert `alert_level` / `alert_rank` /
`alert_stage`, rain and soil values, river level, age and rate, seasonal percentile `river_pctile`, rise since the
dry-season low `river_rise_m`, 2/5/10-year levels, the county's `readiness_value` / `activation_value` /
`regional_value` from the scorecard, the Sudd trigger `sudd_upstream_pct`, flooded area now, days since a wet day
`dry_spell_days`, chance of soil recovery `p_soil_recovery`, news reports `news_flood` / `news_drought`) with today's
values. Only comparisons, `and` / `or` / `not`, numbers, text and arithmetic are accepted. `aa_triggers.csv` gives
each county a suggested readiness and activation rule; example plans follow those suggestions until the TWG-AA
edits them, and a draft plan restarts from normal when its rules change.

`alert_stage` spells out, in the Roadmap's own words, the AA stage each bulletin level corresponds to: green =
monitoring, yellow = warning, orange = readiness, red = activation -- the readiness/activation names line up with
this engine's own plan stages, so a rule can read `alert_stage == 'activation'` as a more readable alternative to
`alert_level == 'red'`.

`dry_spell_days` and `p_soil_recovery` are listed as variables but the county bulletin does not currently produce
them (see "not currently wired into the live bulletin" above), so a rule using either always evaluates to unknown
until that's reinstated; `sudd_upstream_pct` is unaffected since it comes straight from `sudd_trigger_log.csv`.

A red bulletin alert means activation in every suggested rule. Red is reached either way, whichever comes first --
a news report is supporting evidence, never a requirement, and its absence never holds back a red the data has
already earned. This either/or design lives entirely in `bulletin_extras.py` (one of the add-ons' read-only inputs,
never modified by the add-ons themselves) and is live now:
- **Flood**: a high chance of heavy rain together with **either** (a) more than 10,000 people, or at least 50% of
  the **county's** (not one payam's) schools or health facilities, on flood-prone ground, **or** (b) a news report
  of flooding or heavy rainfall in the county (`data/news.json`, last 21 days) on its own.
- **Drought**: a news report of drought or a dry spell in the county (`data/news.json`, last 21 days) on its own.

Three pieces designed alongside this round are **not currently wired into the live bulletin**, pending the
repository owner's decision on whether/how to reinstate them as genuine standalone add-ons (they touched
`county_bulletin.py` and `exposure_cache.py` directly, which was out of scope, so those two files were reverted to
their pre-existing state; `bulletin_extras.py` kept the logic that uses their output, which is why it degrades
safely rather than erroring):
- County-level buildings and settlement-extent shares (JRC GHS-OBAT 2020 buildings, GHSL built-up-surface
  settlement extent) for the severe flood-exposure bar -- only schools and health facilities are aggregated at
  county level right now, so flood red by exposure alone is currently reachable only through those two.
- The numeric drought-red path (more than 21 days without a wet day and less than 60% chance that 2 weeks of rain,
  net of expected evapotranspiration, refill the soil deficit) -- `dry_spell_days` and `p_soil_recovery_2wk` are not
  currently produced by the bulletin, so drought red is reachable only via a confirming news report for now.
- The Nov-Jan Sudd post-rains special case (river flooding lags the rain by weeks to months, so the experimental
  Sudd river trigger at watch/elevated can stand in for rain likelihood after the rains stop) -- the rule exists in
  `bulletin_extras.py` (`county_alert`'s `sudd` argument) but the bulletin does not currently pass it a value.

A drought plan can use `alert_hazard == 'drought / dry spell' and alert_level == 'red'`.

## Safeguards

- A missing or stale reading (river pass older than `max_data_age_days`, default 20) counts as "not met" and is
  reported, so a dead gauge cannot trigger a plan.
- Plans activate once per season by default; `confirm_runs` can require several distinct satellite passes.
- Community messages about a plan are only drafted for **validated** plans; draft-plan crossings appear in the
  TWG-AA briefs and are logged separately from "AAPs activated".
- Nothing is sent automatically. Messages and briefs are labelled for SSMS / MHADM validation, as SSMS issues the
  official warnings.
- The proposed trigger levels are evidence for a decision, not a decision: satellite passes are 10-35 days apart and
  the displacement record is incomplete. The design note flags any level that shows no skill.
- The repository is public: keep budgets or names you do not want published out of `aa_config/` (or point
  `AA_CONFIG_DIR` to a private folder).

## Testing done

All seven self-tests pass on pandas 3.0 and pandas 2.2 (Colab). The full chain was run on a copy of the repository
with its real `data/` files and county-gauge links, and synthetic stand-ins for the Drive files (altimetry series,
station status, bulletin, county shapes). The numbers in those test outputs are not results; run the scorecard on
the real altimetry before discussing levels with partners.
