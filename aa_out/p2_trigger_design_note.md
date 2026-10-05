# River triggers - design note (proposal for validation)

Generated 2026-10-05 14:34 UTC by aa_p2_trigger_scorecard.py (Roadmap on Anticipatory Action, Pillar 2: Trigger and Early Warning Systems).

## Proposed rule
- **Activation (counties with a reliable gauge): S85+U55** (best TSS among rules with FAR <= 35% that caught >= 30% of flood seasons on time, a median of >= 14 days before displacement; median 36 days before displacement).
- **Readiness: S85** (a lower rule of the same kind that catches at least 60% of flood seasons on time and as many as activation; best TSS; median 44 days before displacement).
- Names: P = percentile of the gauge record; 2yr/5yr/10yr = return levels; S = seasonal percentile (how unusual for the time of year); R = rise since the dry-season low against the gauge's usual rise; U = Sudd regional upstream index x100; A+U = both.
- Counties without a reliable gauge use the regional rule if they are Sudd counties (readiness U55, activation U70), otherwise the bulletin flood alert. Each county's values and suggested plan rules are in aa_triggers.csv.

## Evidence
169 county-seasons with a recorded flood impact, seasons 2020-2025 (July-January); 144 county-seasons scored at 24 counties with a reliable gauge. Regional index: 21 Sudd counties with recorded flood displacement, 47 upstream gauges.

### Every rule (impact = displacement or listed in a flood assessment; used for the choice)
| family | candidate | county_seasons | events | hits | late | misses | false_alarms | POD | FAR | CSI | TSS | median_lead_days |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| level | 2yr+0.25m | 144 | 76 | 40 | 7 | 29 | 23 | 53% | 33% | 0.40 | 0.19 | 12 |
| level | P95 | 144 | 76 | 34 | 11 | 31 | 21 | 45% | 32% | 0.35 | 0.14 | 18 |
| level | 5yr | 144 | 76 | 25 | 9 | 42 | 14 | 33% | 29% | 0.28 | 0.12 | 9 |
| level | P90 | 144 | 76 | 45 | 9 | 22 | 34 | 59% | 39% | 0.41 | 0.09 | 16 |
| level | 2yr | 144 | 76 | 58 | 8 | 10 | 48 | 76% | 42% | 0.47 | 0.06 | 30 |
| level | P80 | 144 | 76 | 54 | 10 | 12 | 47 | 71% | 42% | 0.44 | 0.02 | 32 |
| level | 10yr | 144 | 76 | 3 | 3 | 70 | 3 | 4% | 33% | 0.04 | -0.00 |  |
| level | 2yr-0.25m | 144 | 76 | 66 | 5 | 5 | 61 | 87% | 46% | 0.48 | -0.03 | 23 |
| level | P70 | 144 | 76 | 64 | 5 | 7 | 61 | 84% | 47% | 0.47 | -0.05 | 26 |
| level | P60 | 144 | 76 | 67 | 6 | 3 | 65 | 88% | 47% | 0.48 | -0.07 | 30 |
| level | 2yr-0.50m | 144 | 76 | 66 | 5 | 5 | 66 | 87% | 48% | 0.46 | -0.10 | 40 |
| regional | U75 | 144 | 76 | 55 | 13 | 8 | 28 | 72% | 29% | 0.53 | 0.31 | 0 |
| regional | U80 | 144 | 76 | 49 | 19 | 8 | 28 | 64% | 29% | 0.47 | 0.23 | 0 |
| regional | U70 | 144 | 76 | 63 | 12 | 1 | 45 | 83% | 38% | 0.52 | 0.17 | 30 |
| regional | U50 | 144 | 76 | 73 | 3 | 0 | 68 | 96% | 47% | 0.51 | -0.04 | 61 |
| regional | U55 | 144 | 76 | 73 | 3 | 0 | 68 | 96% | 47% | 0.51 | -0.04 | 61 |
| regional | U60 | 144 | 76 | 70 | 6 | 0 | 68 | 92% | 47% | 0.49 | -0.08 | 31 |
| regional | U65 | 144 | 76 | 64 | 12 | 0 | 68 | 84% | 47% | 0.44 | -0.16 | 30 |
| rise | R50 | 144 | 76 | 44 | 9 | 23 | 30 | 58% | 36% | 0.42 | 0.14 | 54 |
| rise | R90 | 144 | 76 | 10 | 3 | 63 | 7 | 13% | 35% | 0.12 | 0.03 | -2 |
| rise | R75 | 144 | 76 | 18 | 3 | 55 | 16 | 24% | 43% | 0.20 | 0.00 | 54 |
| seasonal | S85 | 144 | 76 | 46 | 5 | 25 | 24 | 61% | 32% | 0.46 | 0.25 | 44 |
| seasonal | S90 | 144 | 76 | 38 | 6 | 32 | 18 | 50% | 29% | 0.40 | 0.24 | 36 |
| seasonal | S80 | 144 | 76 | 52 | 3 | 21 | 32 | 68% | 37% | 0.48 | 0.21 | 48 |
| seasonal | S70 | 144 | 76 | 61 | 3 | 12 | 44 | 80% | 41% | 0.51 | 0.16 | 53 |
| seasonal | S95 | 144 | 76 | 24 | 4 | 48 | 15 | 32% | 35% | 0.26 | 0.10 | 21 |
| seasonal+regional | S85+U70 | 144 | 76 | 35 | 11 | 30 | 11 | 46% | 19% | 0.40 | 0.30 | -1 |
| seasonal+regional | S85+U55 | 144 | 76 | 45 | 6 | 25 | 20 | 59% | 28% | 0.47 | 0.30 | 36 |
| seasonal+regional | S85+U60 | 144 | 76 | 42 | 8 | 26 | 19 | 55% | 28% | 0.44 | 0.27 | 24 |
| seasonal+regional | S90+U55 | 144 | 76 | 37 | 7 | 32 | 17 | 49% | 28% | 0.40 | 0.24 | 30 |
| seasonal+regional | S80+U70 | 144 | 76 | 39 | 11 | 26 | 19 | 51% | 28% | 0.41 | 0.23 | -2 |
| seasonal+regional | S80+U55 | 144 | 76 | 50 | 5 | 21 | 29 | 66% | 35% | 0.48 | 0.23 | 40 |
| seasonal+regional | S90+U70 | 144 | 76 | 26 | 10 | 40 | 8 | 34% | 18% | 0.31 | 0.22 | -1 |
| seasonal+regional | S80+U60 | 144 | 76 | 48 | 7 | 21 | 29 | 63% | 35% | 0.46 | 0.21 | 24 |
| seasonal+regional | S90+U60 | 144 | 76 | 32 | 8 | 36 | 16 | 42% | 29% | 0.35 | 0.19 | 20 |

### The chosen rules, impact = flood displacement only
| candidate | events | hits | late | misses | false_alarms | POD | FAR | CSI | TSS | median_lead_days |
|---|---|---|---|---|---|---|---|---|---|---|
| S85 | 32 | 16 | 5 | 11 | 54 | 50% | 72% | 0.19 | 0.02 | 44 |
| S85+U55 | 32 | 15 | 6 | 11 | 50 | 47% | 70% | 0.18 | 0.02 | 36 |

## Counties
Rule used: bulletin flood alert 46, seasonal + regional 24, regional 9.
At or above a proposed value now: 0.

## How to read and validate
- POD: share of flood seasons caught on time. FAR: share of the seasons a rule fired with no impact recorded. CSI and TSS combine both; higher is better. Late = fired after displacement had begun (counted as a miss).
- Small samples: one or two seasons can swing the numbers. Prefer rules that also make physical sense.
- Satellite passes are 10-35 days apart; displacement and assessment records miss floods nobody counted.
- Confirm per county with SSMS / MWRI and the state TWG-AA; record the decision in aa_triggers.csv (validated_by, validated_date) before using the values in an anticipatory action plan.
