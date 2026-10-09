# County flood risk profile - method notes

Generated 2026-10-09 14:02 UTC by aa_p1_risk_profile.py (Roadmap on Anticipatory Action, Pillar 1: Risk Knowledge).

## What the score means
Each indicator is scaled 0-10 across the counties (log scale for counts; values above the 95th percentile score 10). Indicators are averaged within a dimension; hazard and exposure form one dimension, as in INFORM. Dimensions are combined by a geometric mean offset by 1 (((d1+1)(d2+1)...)^(1/n) - 1), so a county needs both hazard/exposure and vulnerability to rank high, but one empty dimension does not erase the score.
Dimensions used this run: hazard_exposure, vulnerability.

The scores RANK counties within South Sudan; they are not probabilities of loss, and they are only as good as the records behind them (assessment coverage, DTM coverage, satellite exposure layers).

## Indicators
| Indicator | Dimension | Scale | Meaning | Source |
|---|---|---|---|---|
| flood_years_share | hazard | lin | Share of the flood assessments (2021-2025) that listed the county | data/flood_affected_county_year.csv |
| affected_pct_mean | hazard | lin | Mean share of the 2025 population affected per assessment (%) | data/flood_affected_county_year.csv |
| pop_flood_prone | exposure | log | People living on ground mapped as water or flooded before | county bulletin exposure layer (JRC GSW + Global Flood Database, WorldPop shares) |
| flood_prone_share | exposure | lin | Share of the population on flood-prone ground | county bulletin exposure layer |
| cropland_km2 | exposure | log | Cropland area (km2) | ESA WorldCover 2021 via the county bulletin |
| flooded_settlement_pop | exposure | log | People in settlements reported flooded, Sept 2025 | data/flood_settlements_sept2025.csv |
| displaced_per_1000 | hazard | log | Flood displacement 2020-2025 per 1,000 people (impact history) | data/flood_displacement_county_month.csv (IOM DTM) |
| displacement_years | hazard | lin | Years with flood displacement recorded, 2020-2025 (impact history) | data/flood_displacement_county_month.csv (IOM DTM) |
| v_ipc_phase | vulnerability | lin | user indicator (aa_config/county_vulnerability.csv) | aa_config/county_vulnerability.csv |

## Classes
Very high >= 6.5, High >= 5.0, Medium >= 3.5, Low >= 2.0, otherwise Very low.

## Ten highest-ranked counties
| Rank | County | State | Score | Class | People on flood-prone ground | Displaced 2020-2025 | Completeness |
|---|---|---|---|---|---|---|---|
| 1 | Panyijiar | Unity | 9.0 | Very high | 4,064 | 92,563 | 100% |
| 2 | Fangak | Jonglei | 8.9 | Very high | 4,546 | 199,169 | 100% |
| 3 | Leer | Unity | 8.6 | Very high | 985 | 37,458 | 100% |
| 4 | Ayod | Jonglei | 8.6 | Very high | 7,356 | 106,649 | 100% |
| 5 | Twic East | Jonglei | 8.4 | Very high | 6,132 | 11,516 | 100% |
| 6 | Guit | Unity | 8.4 | Very high | 3,497 | 15,181 | 100% |
| 7 | Mayendit | Unity | 8.1 | Very high | 2,032 | 3,095 | 100% |
| 8 | Rubkona | Unity | 7.9 | Very high | 16,480 | 56,898 | 100% |
| 9 | Panyikang | Upper Nile | 7.3 | Very high | 1,376 | 39,647 | 100% |
| 10 | Canal/Pigi | Jonglei | 7.3 | Very high | 2,399 | 18,158 | 100% |

Counties flagged 'low data' (< 60% of indicators): none.

## Validation checklist (state TWG-AA / partners)
- Does the ranking match local knowledge of where floods hurt most? Note disagreements per county.
- Are the flood assessments and DTM records complete for these counties, or missing because no one assessed them?
- Add vulnerability (v_*) and coping (c_*) indicators agreed with partners, e.g. IPC phase, IDP share, health facilities per 10,000 people, market access.
- Add FEWS NET livelihood zones (aa_config/county_livelihood_zones.csv) for the zone profile.
- Record the validation (date, who, changes) before the profile is used to target anticipatory action.

## Inputs used
- population: data/ssd_county_population_2025.csv
- bulletin exposure: /home/runner/work/altimetry-nightly/altimetry-nightly/bulletin/county_bulletin_latest.csv
- exposure cache: data/exposure_cache.json
- flood assessments: data/flood_affected_county_year.csv
- displacement: data/flood_displacement_county_month.csv
- settlements: data/flood_settlements_sept2025.csv
- county boundaries: /home/runner/work/altimetry-nightly/altimetry-nightly/bulletin/counties_dissolved.geojson

Zone profile: livelihood zone (12 zones), see p1_zone_profile.csv.
