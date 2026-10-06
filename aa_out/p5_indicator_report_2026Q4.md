# Anticipatory action roadmap - progress report 2026Q4

Prepared 2026-10-06 08:16 UTC by aa_p5_indicator_tracker.py for the quarterly TWG-AA meeting (South Sudan Roadmap on Anticipatory Action 2025-2030, Pillars 1, 2, 3 and 5).

Snapshot indicators show the latest value in the quarter; event indicators are counts in the quarter.

## Pillar 1 - Risk knowledge

| Indicator | 2026Q1 | 2026Q2 | 2026Q3 | 2026Q4 | Year to date | Target | Achieved | Verification |
|---|---|---|---|---|---|---|---|---|
| Counties with a flood risk profile |  |  |  | 79 | 79 |  |  | p1_county_risk_profile.csv |
| Livelihood zones with exposure analysis |  |  |  | 0 | 0 |  |  | p1_zone_profile.csv |
| Vulnerability and coping indicators in use |  |  |  | 0 | 0 |  |  | aa_config/county_vulnerability.csv |
| Risk maps produced |  |  |  | 6 | 6 |  |  | p1_risk_map.png |
| Risk datasets exported in HXL for the IMS |  |  |  | 6 | 6 |  |  | p1_county_risk_profile_hxl.csv |
| Risk and trigger datasets in HXL for the IMS |  |  |  | 2 | 2 |  |  | aa_indicator_ledger.csv |

## Pillar 2 - Trigger and early warning systems

| Indicator | 2026Q1 | 2026Q2 | 2026Q3 | 2026Q4 | Year to date | Target | Achieved | Verification |
|---|---|---|---|---|---|---|---|---|
| Hazards with defined thresholds and data requirements |  |  |  | 3 | 3 |  |  | p2_trigger_design_note.md |
| Counties with proposed river trigger levels |  |  |  | 33 | 33 |  |  | aa_triggers.csv |
| Counties with validated river trigger levels |  |  |  | 0 | 0 |  |  | aa_triggers.csv |
| Trigger skill evaluations against recorded impacts |  |  |  | 6 | 6 |  |  | p2_trigger_skill_season.csv |
| Datasets packaged and validated for the repository |  |  |  | 42 | 42 |  |  | aa_data_package_*.zip |
| Languages with validated warning templates |  |  |  | 1 | 1 |  |  | aa_config/message_templates.csv |
| Datasets failing validation |  |  |  | 0 | 0 |  |  | aa_indicator_ledger.csv |

## Pillar 3 - Anticipatory action

| Indicator | 2026Q1 | 2026Q2 | 2026Q3 | 2026Q4 | Year to date | Target | Achieved | Verification |
|---|---|---|---|---|---|---|---|---|
| Anticipatory action plans developed |  |  |  | 6 | 6 |  |  | aa_config/aap_plans.csv |
| Anticipatory action plans validated |  |  |  | 0 | 0 |  |  | aa_config/aap_plans.csv |
| Simulation exercise packs prepared |  |  |  |  |  |  |  | aa_out/simulations |
| Simulation exercises conducted |  |  |  |  |  |  |  | simulations/*/evaluation.csv (conducted_date) |
| Readiness stages reached |  |  |  | 1 | 1 |  |  | aap_activation_log.csv |
| AAPs activated |  |  |  |  |  |  |  | aap_activation_log.csv; aap_reports |
| Draft-plan activation levels reached (not counted as activations) |  |  |  | 2 | 2 |  |  | aa_indicator_ledger.csv |
| Plans in readiness or activated now |  |  |  | 0 | 0 |  |  | aa_indicator_ledger.csv |

## Pillar 5 - Coordination and legal framework

| Indicator | 2026Q1 | 2026Q2 | 2026Q3 | 2026Q4 | Year to date | Target | Achieved | Verification |
|---|---|---|---|---|---|---|---|---|
| Subnational TWG-AA groups active (state / county) |  |  |  | 0 | 0 |  |  | aa_config/recipient_groups.csv |
| TWG-AA meetings held |  |  |  |  |  |  |  | aa_config/meetings_log.csv |
| TWG-AA situation briefs prepared |  |  |  | 63 | 63 |  |  | aa_out/dissemination |
| Community groups / radio listening hubs registered |  |  |  | 0 | 0 |  |  | aa_config/recipient_groups.csv |
| Early warning messages prepared |  |  |  | 416 | 416 |  |  | dissemination/*/messages.csv |
| Early warning items sent |  |  |  |  |  |  |  | dissemination_log.csv (status sent) |
| Community feedback records |  |  |  |  |  |  |  | aa_config/feedback_log.csv |

## Plan decisions in 2026Q4
| Date | Plan | County | Change | Plan status |
|---|---|---|---|---|
| 2026-10-05 13:58 | AAP-FL-AYOD | Ayod | normal -> activated | draft (example) - not validated |
| 2026-10-05 13:58 | AAP-FL-TWICEAST | Twic East | normal -> activated | draft (example) - not validated |
| 2026-10-05 13:58 | AAP-FL-GUIT | Guit | normal -> readiness | draft (example) - not validated |

## No data yet
Simulation exercise packs prepared, Simulation exercises conducted, AAPs activated, TWG-AA meetings held, Early warning items sent, Community feedback records

## Suggested next steps
- Agree vulnerability indicators (e.g. IPC phase, IDP share) and fill aa_config/county_vulnerability.csv.
- Add FEWS NET livelihood zones in aa_config/county_livelihood_zones.csv for the zone profile.
- Validate the proposed river trigger levels with SSMS / MWRI (aa_triggers.csv: validated_by, validated_date).
- Take the draft anticipatory action plans to the TWG-AA for validation (aa_config/aap_plans.csv).
- Run a simulation exercise with a pack from aa_p3_simulation.py and record conducted_date.
- Translate and validate the warning templates in at least two local languages.
- Register the state TWG-AA groups that exist (aa_config/recipient_groups.csv, active = yes).
- Log TWG-AA meetings in aa_config/meetings_log.csv so the quarterly-meeting indicator is counted.
