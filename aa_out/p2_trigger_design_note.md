# River triggers - design note (proposal for validation)

Generated 2026-11-09 20:10 UTC by aa_p2_trigger_scorecard.py (Roadmap on Anticipatory Action, Pillar 2: Trigger and Early Warning Systems).

## Proposed rule
- **Activation (counties with a reliable gauge): 2yr+0.25m+U70** (no rule met the false-alarm and lead-time limits; best TSS used; median -1 days before displacement).
- **Readiness: 2yr** (a lower rule of the same kind that catches at least 60% of flood seasons on time and as many as activation; best TSS; median 28 days before displacement).
- Names: P = percentile of the gauge record; 2yr/5yr/10yr = return levels; S = seasonal percentile (how unusual for the time of year); R = rise since the dry-season low against the gauge's usual rise; U = Sudd regional upstream index x100; A+U = both.
- Counties without a reliable gauge use the regional rule if they are Sudd counties (readiness U70, activation U75), otherwise the bulletin flood alert. Each county's values and suggested plan rules are in aa_triggers.csv.

## Evidence
169 county-seasons with a recorded flood impact, seasons 2020-2025 (July-January); 156 county-seasons scored at 26 counties with a reliable gauge. Regional index: 21 Sudd counties with recorded flood displacement, 47 upstream gauges.

### Every rule (impact = displacement or listed in a flood assessment; used for the choice)
| family | candidate | county_seasons | events | hits | late | misses | false_alarms | POD | FAR | CSI | TSS | median_lead_days |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| level | 2yr+0.25m | 156 | 61 | 34 | 3 | 24 | 46 | 56% | 55% | 0.32 | 0.07 | -1 |
| level | 2yr | 156 | 61 | 47 | 5 | 9 | 71 | 77% | 58% | 0.36 | 0.02 | 28 |
| level | P80 | 156 | 61 | 51 | 5 | 5 | 81 | 84% | 59% | 0.36 | -0.02 | 23 |
| level | P70 | 156 | 61 | 56 | 3 | 2 | 90 | 92% | 60% | 0.37 | -0.03 | 24 |
| level | P95 | 156 | 61 | 29 | 7 | 25 | 48 | 48% | 57% | 0.27 | -0.03 | 28 |
| level | 2yr-0.25m | 156 | 61 | 52 | 2 | 7 | 85 | 85% | 61% | 0.36 | -0.04 | 24 |
| level | P90 | 156 | 61 | 39 | 5 | 17 | 66 | 64% | 60% | 0.31 | -0.06 | -1 |
| level | P60 | 156 | 61 | 56 | 3 | 2 | 95 | 92% | 62% | 0.36 | -0.08 | 39 |
| level | 10yr | 156 | 61 | 2 | 1 | 58 | 12 | 3% | 80% | 0.03 | -0.09 |  |
| level | 2yr-0.50m | 156 | 61 | 54 | 3 | 4 | 94 | 89% | 62% | 0.35 | -0.10 | 39 |
| level | 5yr | 156 | 61 | 14 | 6 | 41 | 35 | 23% | 64% | 0.15 | -0.14 | -1 |
| level+regional | 2yr+0.25m+U70 | 156 | 61 | 33 | 4 | 24 | 28 | 54% | 43% | 0.37 | 0.25 | -1 |
| level+regional | 2yr+0.25m+U60 | 156 | 61 | 33 | 4 | 24 | 38 | 54% | 51% | 0.33 | 0.14 | -1 |
| level+regional | 2yr+0.25m+U55 | 156 | 61 | 33 | 4 | 24 | 46 | 54% | 55% | 0.31 | 0.06 | -1 |
| regional | U75 | 156 | 61 | 48 | 7 | 6 | 49 | 79% | 47% | 0.44 | 0.27 | 16 |
| regional | U80 | 156 | 61 | 46 | 9 | 6 | 49 | 75% | 47% | 0.42 | 0.24 | 77 |
| regional | U70 | 156 | 61 | 52 | 8 | 1 | 70 | 85% | 54% | 0.40 | 0.12 | 46 |
| regional | U50 | 156 | 61 | 58 | 3 | 0 | 95 | 95% | 61% | 0.37 | -0.05 | 62 |
| regional | U55 | 156 | 61 | 58 | 3 | 0 | 95 | 95% | 61% | 0.37 | -0.05 | 31 |
| regional | U60 | 156 | 61 | 56 | 5 | 0 | 95 | 92% | 61% | 0.36 | -0.08 | 31 |
| regional | U65 | 156 | 61 | 54 | 7 | 0 | 95 | 89% | 61% | 0.35 | -0.11 | 46 |
| rise | R50 | 156 | 61 | 37 | 5 | 19 | 54 | 61% | 56% | 0.32 | 0.04 | 51 |
| rise | R90 | 156 | 61 | 7 | 1 | 53 | 8 | 11% | 50% | 0.10 | 0.03 | 2 |
| rise | R75 | 156 | 61 | 14 | 2 | 45 | 27 | 23% | 63% | 0.16 | -0.05 | 46 |
| seasonal | S80 | 156 | 61 | 47 | 0 | 14 | 67 | 77% | 59% | 0.37 | 0.07 | 51 |
| seasonal | S70 | 156 | 61 | 54 | 0 | 7 | 79 | 89% | 59% | 0.39 | 0.05 | 50 |
| seasonal | S85 | 156 | 61 | 34 | 1 | 26 | 50 | 56% | 59% | 0.31 | 0.03 | 46 |
| seasonal | S90 | 156 | 61 | 27 | 2 | 32 | 41 | 44% | 59% | 0.26 | 0.01 | 26 |
| seasonal | S95 | 156 | 61 | 17 | 4 | 40 | 35 | 28% | 62% | 0.18 | -0.09 | 50 |
| seasonal+regional | S80+U70 | 156 | 61 | 34 | 6 | 21 | 31 | 56% | 44% | 0.37 | 0.23 | -1 |
| seasonal+regional | S70+U70 | 156 | 61 | 42 | 6 | 13 | 50 | 69% | 51% | 0.38 | 0.16 | 14 |
| seasonal+regional | S70+U60 | 156 | 61 | 51 | 2 | 8 | 71 | 84% | 57% | 0.39 | 0.09 | 27 |
| seasonal+regional | S70+U55 | 156 | 61 | 51 | 2 | 8 | 72 | 84% | 58% | 0.38 | 0.08 | 27 |
| seasonal+regional | S80+U55 | 156 | 61 | 44 | 3 | 14 | 62 | 72% | 57% | 0.36 | 0.07 | 23 |
| seasonal+regional | S80+U60 | 156 | 61 | 44 | 3 | 14 | 62 | 72% | 57% | 0.36 | 0.07 | 23 |

### The chosen rules, impact = flood displacement only
| candidate | events | hits | late | misses | false_alarms | POD | FAR | CSI | TSS | median_lead_days |
|---|---|---|---|---|---|---|---|---|---|---|
| 2yr | 19 | 10 | 5 | 4 | 108 | 53% | 88% | 0.08 | -0.26 | 28 |
| 2yr+0.25m+U70 | 19 | 5 | 4 | 10 | 56 | 26% | 86% | 0.07 | -0.15 | -1 |

## Counties
Rule used: bulletin flood alert 39, level + regional 26, regional 14.
At or above a proposed value now: 17: Panyijiar (readiness), Fangak (readiness), Leer (readiness), Ayod (readiness), Twic East (readiness), Guit (readiness), Mayendit (readiness), Rubkona (readiness), Duk (readiness), Canal/Pigi (activation), Panyikang (readiness), Malakal (readiness), Fashoda (readiness), Bor South (readiness), Koch (readiness), Manyo (activation), Melut (readiness)

## How to read and validate
- POD: share of flood seasons caught on time. FAR: share of the seasons a rule fired with no impact recorded. CSI and TSS combine both; higher is better. Late = fired after displacement had begun (counted as a miss).
- Small samples: one or two seasons can swing the numbers. Prefer rules that also make physical sense.
- Satellite passes are 10-35 days apart; displacement and assessment records miss floods nobody counted.
- Confirm per county with SSMS / MWRI and the state TWG-AA; record the decision in aa_triggers.csv (validated_by, validated_date) before using the values in an anticipatory action plan.
