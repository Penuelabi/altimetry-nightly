# River-level triggers - design note (proposal for validation)

Generated 2026-10-05 13:58 UTC by aa_p2_trigger_scorecard.py (Roadmap on Anticipatory Action, Pillar 2: Trigger and Early Warning Systems).

## Proposed rule
- **Activation**: water level at the county's gauge at or above its **2yr-0.25m** level (no level kept FAR <= 50%; the lowest FAR was used).
- **Readiness**: at or above its **2yr-0.50m** level (a lower level that caught at least 60% of displacement seasons on time, and at least as many as activation; best TSS).
- On time = crossed no later than 15 days after the first displacement month began. Both levels are judged per flood season (July-January), as a plan activates once per season.
- Levels in metres for every county are in aa_triggers.csv.

> **Warning:** 2yr-0.50m, 2yr-0.25m shows no skill over chance in this record (TSS <= 0). Treat the level as a placeholder until SSMS/MWRI and the TWG-AA agree a level from local flood marks or bankfull data.

## Evidence
Impact record: 107 county-months with flood displacement, 2020-2025 (IOM DTM; flood + unspecified natural disaster). River signal: satellite levels at the linked gauge.

### Per season, on time (used for the choice)
| candidate | county_seasons | events | hits | misses | false_alarms | POD | FAR | CSI | TSS | median_lead_days |
|---|---|---|---|---|---|---|---|---|---|---|
| P50 | 438 | 55 | 39 | 16 | 380 | 71% | 91% | 0.09 | -0.28 | 43 |
| P60 | 438 | 55 | 37 | 18 | 375 | 67% | 91% | 0.09 | -0.31 | 30 |
| P70 | 438 | 55 | 34 | 21 | 363 | 62% | 91% | 0.08 | -0.33 | 30 |
| 2yr-0.50m | 438 | 55 | 40 | 15 | 365 | 73% | 90% | 0.10 | -0.23 | 42 |
| P75 | 438 | 55 | 31 | 24 | 343 | 56% | 92% | 0.08 | -0.33 | 30 |
| 2yr-0.25m | 438 | 55 | 39 | 16 | 352 | 71% | 90% | 0.10 | -0.21 | 30 |
| P80 | 438 | 55 | 25 | 30 | 314 | 45% | 93% | 0.07 | -0.37 | 32 |
| P85 | 438 | 55 | 21 | 34 | 274 | 38% | 93% | 0.06 | -0.33 | 32 |
| 2yr | 438 | 55 | 28 | 27 | 280 | 51% | 91% | 0.08 | -0.22 | 30 |
| P90 | 438 | 55 | 19 | 36 | 235 | 35% | 93% | 0.07 | -0.27 | 30 |
| 2yr+0.25m | 438 | 55 | 12 | 43 | 151 | 22% | 93% | 0.06 | -0.18 | 16 |
| P95 | 438 | 55 | 14 | 41 | 165 | 25% | 92% | 0.06 | -0.18 | 28 |
| 5yr | 438 | 55 | 9 | 46 | 142 | 16% | 94% | 0.05 | -0.21 | 16 |
| 10yr | 438 | 55 | 0 | 55 | 41 | 0% | 100% | 0.00 | -0.11 |  |

### Per season, other impact definitions (chosen levels)
| impact_definition | timing | candidate | county_seasons | events | hits | misses | false_alarms | POD | FAR | CSI |
|---|---|---|---|---|---|---|---|---|---|---|
| flood displacement | any time in season | 2yr-0.50m | 438 | 55 | 52 | 3 | 365 | 95% | 88% | 0.12 |
| displacement or listed in flood assessment | any time in season | 2yr-0.50m | 438 | 154 | 147 | 7 | 270 | 95% | 65% | 0.35 |
| flood displacement | any time in season | 2yr-0.25m | 438 | 55 | 52 | 3 | 352 | 95% | 87% | 0.13 |
| displacement or listed in flood assessment | any time in season | 2yr-0.25m | 438 | 154 | 145 | 9 | 259 | 94% | 64% | 0.35 |

### Monthly (flood-season county-months, river signal 1 month earlier)
Monthly scores look poor by design: a level stays high for months while displacement is recorded in one or two of them. Use them to compare lead times, not to judge a level.
| candidate | n | events | hits | misses | false_alarms | POD | FAR | CSI | TSS |
|---|---|---|---|---|---|---|---|---|---|
| P50 | 2699 | 72 | 55 | 17 | 1961 | 76% | 97% | 0.03 | 0.02 |
| P60 | 2699 | 72 | 51 | 21 | 1690 | 71% | 97% | 0.03 | 0.07 |
| P70 | 2699 | 72 | 42 | 30 | 1377 | 58% | 97% | 0.03 | 0.06 |
| 2yr-0.50m | 2699 | 72 | 60 | 12 | 1686 | 83% | 97% | 0.03 | 0.19 |
| P75 | 2699 | 72 | 39 | 33 | 1204 | 54% | 97% | 0.03 | 0.08 |
| 2yr-0.25m | 2699 | 72 | 52 | 20 | 1320 | 72% | 96% | 0.04 | 0.22 |
| P80 | 2699 | 72 | 34 | 38 | 1019 | 47% | 97% | 0.03 | 0.08 |
| P85 | 2699 | 72 | 30 | 42 | 818 | 42% | 96% | 0.03 | 0.11 |
| 2yr | 2699 | 72 | 35 | 37 | 836 | 49% | 96% | 0.04 | 0.17 |
| P90 | 2699 | 72 | 23 | 49 | 596 | 32% | 96% | 0.03 | 0.09 |
| 2yr+0.25m | 2699 | 72 | 17 | 55 | 397 | 24% | 96% | 0.04 | 0.08 |
| P95 | 2699 | 72 | 11 | 61 | 345 | 15% | 97% | 0.03 | 0.02 |
| 5yr | 2699 | 72 | 8 | 64 | 281 | 11% | 97% | 0.02 | 0.00 |
| 10yr | 2699 | 72 | 0 | 72 | 56 | 0% | 100% | 0.00 | -0.02 |

## Status now: 26 counties at or above a proposed level
Fangak (activation), Leer (activation), Ayod (activation), Twic East (activation), Guit (readiness), Mayendit (activation), Renk (readiness), Bor South (activation), Koch (readiness), Duk (activation), Canal/Pigi (activation), Melut (activation), Yirol East (activation), Gogrial East (readiness), Aweil East (readiness) and 11 more (see aa_triggers.csv)

## How to read and validate
- POD: share of displacement months the level caught. FAR: share of crossings with no displacement recorded. CSI and TSS combine both; higher is better. Lead time: days from first crossing to the first displacement month (see p2_trigger_track_record.csv).
- Small samples: one or two seasons can swing the numbers. Prefer rules that also make physical sense (bankfull levels known to MWRI, local flood marks).
- Satellite levels are sampled every 10-35 days, so a peak can be missed; displacement records miss floods where nobody moved or nobody counted.
- Confirm per county with SSMS / MWRI and the state TWG-AA; record the decision (date, who, levels) in aa_triggers.csv (columns validated_by, validated_date) before using the levels in an anticipatory action plan.
