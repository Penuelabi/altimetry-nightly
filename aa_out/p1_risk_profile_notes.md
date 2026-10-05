# County flood risk profile - method notes

Generated 2026-10-05 17:46 UTC by aa_p1_risk_profile.py (Roadmap on Anticipatory Action, Pillar 1: Risk Knowledge).

## What the score means
Each indicator is scaled 0-10 across the counties (log scale for counts; values above the 95th percentile score 10). Indicators are averaged within a dimension; hazard and exposure form one dimension, as in INFORM. Dimensions are combined by a geometric mean offset by 1 (((d1+1)(d2+1)...)^(1/n) - 1), so a county needs both hazard/exposure and vulnerability to rank high, but one empty dimension does not erase the score.
Dimensions used this run: hazard_exposure. No vulnerability or coping columns were filled in aa_config/county_vulnerability.csv, so this run ranks hazard (impact history) and exposure only. Adding agreed vulnerability indicators (e.g. IPC phase, IDP share) completes the index.

The scores RANK counties within South Sudan; they are not probabilities of loss, and they are only as good as the records behind them (assessment coverage, DTM coverage, satellite exposure layers).

## Indicators
| Indicator | Dimension | Scale | Meaning | Source |
|---|---|---|---|---|
| flood_years_share | hazard | lin | Share of the flood assessments (2021-2025) that listed the county | data/flood_affected_county_year.csv |
| affected_pct_mean | hazard | lin | Mean share of the 2025 population affected per assessment (%) | data/flood_affected_county_year.csv |
| pop_flood_prone | exposure | log | People living on ground mapped as water or flooded before | county bulletin exposure layer (JRC GSW + Global Flood Database, WorldPop shares) |
| flood_prone_share | exposure | lin | Share of the population on flood-prone ground | county bulletin exposure layer |
| cropland_km2 | exposure | log | Cropland area (km2) | ESA WorldCover 2021 via the county bulletin |
| area_risk_share | exposure | lin | Share of county area at risk (Sentinel-1 baseline + current extent) | data/exposure_cache.json |
| facilities_risk_share | exposure | lin | Share of schools and health facilities at risk | data/exposure_cache.json |
| roads_risk_km | exposure | log | Road length at risk (km) | data/exposure_cache.json (GRIP4 roads) |
| flooded_settlement_pop | exposure | log | People in settlements reported flooded, Sept 2025 | data/flood_settlements_sept2025.csv |
| displaced_per_1000 | hazard | log | Flood displacement 2020-2025 per 1,000 people (impact history) | data/flood_displacement_county_month.csv (IOM DTM) |
| displacement_years | hazard | lin | Years with flood displacement recorded, 2020-2025 (impact history) | data/flood_displacement_county_month.csv (IOM DTM) |

## Classes
Very high >= 6.5, High >= 5.0, Medium >= 3.5, Low >= 2.0, otherwise Very low.

## Ten highest-ranked counties
| Rank | County | State | Score | Class | People on flood-prone ground | Displaced 2020-2025 | Completeness |
|---|---|---|---|---|---|---|---|
| 1 | Panyijiar | Unity | 8.6 | Very high | 4,064 | 92,563 | 100% |
| 2 | Fangak | Jonglei | 7.9 | Very high | 4,546 | 199,169 | 100% |
| 3 | Leer | Unity | 7.9 | Very high | 985 | 37,458 | 100% |
| 4 | Ayod | Jonglei | 7.9 | Very high | 7,356 | 106,649 | 100% |
| 5 | Twic East | Jonglei | 7.4 | Very high | 6,132 | 11,516 | 100% |
| 6 | Guit | Unity | 7.2 | Very high | 3,497 | 15,181 | 100% |
| 7 | Mayendit | Unity | 6.9 | Very high | 2,032 | 3,095 | 100% |
| 8 | Rubkona | Unity | 6.8 | Very high | 16,480 | 56,898 | 100% |
| 9 | Renk | Upper Nile | 6.7 | Very high | 4,300 | 83,827 | 100% |
| 10 | Bor South | Jonglei | 6.3 | High | 7,498 | 22,799 | 100% |

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

Zone profile: state (add aa_config/county_livelihood_zones.csv for livelihood zones) (11 zones), see p1_zone_profile.csv.
