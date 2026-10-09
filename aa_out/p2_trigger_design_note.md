# River triggers - design note (proposal for validation)

Generated 2026-10-09 14:03 UTC by aa_p2_trigger_scorecard.py (Roadmap on Anticipatory Action, Pillar 2: Trigger and Early Warning Systems).

## Proposed rule
- **Activation (counties with a reliable gauge): S85+U55** (best TSS among rules with FAR <= 35% that caught >= 30% of flood seasons on time, a median of >= 14 days before displacement; median 36 days before displacement).
- **Readiness: S85** (a lower rule of the same kind that catches at least 60% of flood seasons on time and as many as activation; best TSS; median 46 days before displacement).
- Names: P = percentile of the gauge record; 2yr/5yr/10yr = return levels; S = seasonal percentile (how unusual for the time of year); R = rise since the dry-season low against the gauge's usual rise; U = Sudd regional upstream index x100; A+U = both.
- Counties without a reliable gauge use the regional rule if they are Sudd counties (readiness U60, activation U70), otherwise the bulletin flood alert. Each county's values and suggested plan rules are in aa_triggers.csv.

## Evidence
169 county-seasons with a recorded flood impact, seasons 2020-2025 (July-January); 108 county-seasons scored at 18 counties with a reliable gauge. Regional index: 21 Sudd counties with recorded flood displacement, 47 upstream gauges.

### Every rule (impact = displacement or listed in a flood assessment; used for the choice)
| family | candidate | county_seasons | events | hits | late | misses | false_alarms | POD | FAR | CSI | TSS | median_lead_days |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| level | 2yr+0.25m | 108 | 52 | 30 | 4 | 18 | 21 | 58% | 38% | 0.41 | 0.20 | -1 |
| level | P95 | 108 | 52 | 25 | 9 | 18 | 19 | 48% | 36% | 0.35 | 0.14 | 38 |
| level | P90 | 108 | 52 | 35 | 6 | 11 | 32 | 67% | 44% | 0.42 | 0.10 | 2 |
| level | 5yr | 108 | 52 | 17 | 7 | 28 | 13 | 33% | 35% | 0.26 | 0.09 | 10 |
| level | 2yr | 108 | 52 | 42 | 6 | 4 | 40 | 81% | 45% | 0.46 | 0.09 | 26 |
| level | P80 | 108 | 52 | 43 | 6 | 3 | 44 | 83% | 47% | 0.45 | 0.04 | 23 |
| level | 2yr-0.25m | 108 | 52 | 45 | 3 | 4 | 49 | 87% | 51% | 0.45 | -0.01 | 22 |
| level | P70 | 108 | 52 | 47 | 3 | 2 | 52 | 90% | 51% | 0.45 | -0.02 | 22 |
| level | 10yr | 108 | 52 | 1 | 1 | 50 | 3 | 2% | 60% | 0.02 | -0.03 |  |
| level | P60 | 108 | 52 | 47 | 3 | 2 | 56 | 90% | 53% | 0.44 | -0.10 | 36 |
| level | 2yr-0.50m | 108 | 52 | 45 | 3 | 4 | 54 | 87% | 53% | 0.42 | -0.10 | 36 |
| regional | U75 | 108 | 52 | 40 | 7 | 5 | 25 | 77% | 35% | 0.52 | 0.32 | 0 |
| regional | U80 | 108 | 52 | 37 | 10 | 5 | 25 | 71% | 35% | 0.48 | 0.27 | 0 |
| regional | U70 | 108 | 52 | 46 | 6 | 0 | 38 | 88% | 42% | 0.51 | 0.21 | 31 |
| regional | U50 | 108 | 52 | 50 | 2 | 0 | 56 | 96% | 52% | 0.46 | -0.04 | 62 |
| regional | U55 | 108 | 52 | 50 | 2 | 0 | 56 | 96% | 52% | 0.46 | -0.04 | 61 |
| regional | U60 | 108 | 52 | 50 | 2 | 0 | 56 | 96% | 52% | 0.46 | -0.04 | 31 |
| regional | U65 | 108 | 52 | 47 | 5 | 0 | 56 | 90% | 52% | 0.44 | -0.10 | 46 |
| rise | R50 | 108 | 52 | 34 | 4 | 14 | 25 | 65% | 40% | 0.44 | 0.21 | 38 |
| rise | R75 | 108 | 52 | 16 | 2 | 34 | 11 | 31% | 38% | 0.25 | 0.11 | 54 |
| rise | R90 | 108 | 52 | 9 | 2 | 41 | 4 | 17% | 27% | 0.16 | 0.10 | -2 |
| seasonal | S85 | 108 | 52 | 35 | 3 | 14 | 23 | 67% | 38% | 0.47 | 0.26 | 46 |
| seasonal | S90 | 108 | 52 | 29 | 3 | 20 | 17 | 56% | 35% | 0.42 | 0.25 | 45 |
| seasonal | S80 | 108 | 52 | 39 | 2 | 11 | 30 | 75% | 42% | 0.48 | 0.21 | 52 |
| seasonal | S70 | 108 | 52 | 45 | 2 | 5 | 39 | 87% | 45% | 0.49 | 0.17 | 53 |
| seasonal | S95 | 108 | 52 | 19 | 3 | 30 | 14 | 37% | 39% | 0.29 | 0.12 | 21 |
| seasonal+regional | S85+U70 | 108 | 52 | 27 | 7 | 18 | 11 | 52% | 24% | 0.43 | 0.32 | -1 |
| seasonal+regional | S85+U55 | 108 | 52 | 34 | 4 | 14 | 19 | 65% | 33% | 0.48 | 0.31 | 36 |
| seasonal+regional | S85+U60 | 108 | 52 | 32 | 5 | 15 | 18 | 62% | 33% | 0.46 | 0.29 | 24 |
| seasonal+regional | S80+U70 | 108 | 52 | 30 | 7 | 15 | 17 | 58% | 31% | 0.43 | 0.27 | -2 |
| seasonal+regional | S90+U55 | 108 | 52 | 28 | 4 | 20 | 16 | 54% | 33% | 0.41 | 0.25 | 36 |
| seasonal+regional | S80+U55 | 108 | 52 | 38 | 3 | 11 | 27 | 73% | 40% | 0.48 | 0.25 | 50 |
| seasonal+regional | S80+U60 | 108 | 52 | 37 | 4 | 11 | 27 | 71% | 40% | 0.47 | 0.23 | 24 |
| seasonal+regional | S90+U70 | 108 | 52 | 19 | 6 | 27 | 8 | 37% | 24% | 0.32 | 0.22 | -1 |
| seasonal+regional | S90+U60 | 108 | 52 | 24 | 5 | 23 | 15 | 46% | 34% | 0.36 | 0.19 | 22 |

### The chosen rules, impact = flood displacement only
| candidate | events | hits | late | misses | false_alarms | POD | FAR | CSI | TSS | median_lead_days |
|---|---|---|---|---|---|---|---|---|---|---|
| S85 | 19 | 11 | 3 | 5 | 47 | 58% | 77% | 0.17 | 0.05 | 46 |
| S85+U55 | 19 | 10 | 4 | 5 | 43 | 53% | 75% | 0.16 | 0.04 | 36 |

## Counties
Rule used: bulletin flood alert 47, seasonal + regional 18, regional 14.
At or above a proposed value now: 14: Panyijiar (activation), Fangak (activation), Leer (activation), Ayod (activation), Twic East (activation), Guit (activation), Panyikang (activation), Duk (activation), Fashoda (activation), Renk (activation), Koch (activation), Bor South (activation), Juba (activation), Pariang (activation)

## How to read and validate
- POD: share of flood seasons caught on time. FAR: share of the seasons a rule fired with no impact recorded. CSI and TSS combine both; higher is better. Late = fired after displacement had begun (counted as a miss).
- Small samples: one or two seasons can swing the numbers. Prefer rules that also make physical sense.
- Satellite passes are 10-35 days apart; displacement and assessment records miss floods nobody counted.
- Confirm per county with SSMS / MWRI and the state TWG-AA; record the decision in aa_triggers.csv (validated_by, validated_date) before using the values in an anticipatory action plan.
