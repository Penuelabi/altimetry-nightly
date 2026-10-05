# Anticipatory action add-ons for the Sudd hydro-climate platform

Seven standalone Python scripts that extend the "Rainfall Outlook and Observed River Level Status" app
(repository `altimetry-nightly`) so its outputs serve the **South Sudan Roadmap on Anticipatory Action 2025-2030**,
Pillars 1, 2, 3 and 5. They read the files the app already produces and never modify the existing scripts.

## The add-ons

| File | Pillar | Actions (roadmap activities served) | Indicators logged | Main outputs |
|---|---|---|---|---|
| `aa_p1_risk_profile.py` | 1 Risk knowledge | County flood-risk profile (INFORM-style: hazard and impact history, exposure, vulnerability, lack of coping); profile by livelihood zone; risk map; HXL export for the IMS | Counties with a risk profile; livelihood zones analysed; vulnerability indicators in use; risk maps produced; risk datasets exported in HXL | `p1_county_risk_profile.csv`, `_hxl.csv`, `p1_zone_profile.csv`, `p1_risk_map.png`, method notes with a validation checklist |
| `aa_p2_trigger_scorecard.py` | 2 Triggers and EWS | Proposes a readiness and an activation river level for every county gauge, scored against recorded flood displacement (hit rate, false alarms, CSI, TSS, lead time); trigger design note for SSMS / MWRI | Hazards with defined thresholds; counties with proposed and with validated trigger levels; skill evaluations | `aa_triggers.csv`, skill tables, county track record, `p2_trigger_design_note.md`, hydrographs |
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

`python aa_p3_aap_engine.py --list-variables` prints every name (bulletin alert, rain and soil values, river level,
age and rate, 2/5/10-year levels, readiness and activation levels, Sudd trigger, flooded area now) with today's values.
Only comparisons, `and` / `or` / `not`, numbers, text and arithmetic are accepted.

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
