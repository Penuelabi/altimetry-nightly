"""Builds county x year flood-affected population from the OCHA/humanitarian assessment files (see SOURCES)."""
import pandas as pd, re, sys, os
U = sys.argv[1] if len(sys.argv) > 1 else '.'
n = lambda s: re.sub(r'[^a-z]', '', str(s).lower())
pop = pd.read_csv('data/ssd_county_population_2025.csv')
idx = {n(c): c for c in pop.county}
alias = {'pigicanal': 'canalpigi', 'panyijar': 'panyijiar', 'nasir': 'luakpinynasir', 'jur': 'jurriver',
         'bor': 'borsouth', 'ayodislands': 'ayod', 'abyeiadministrativearea': 'abyeiregion'}
m = lambda x: idx.get(alias.get(n(x), n(x)))
g = lambda f: os.path.join(U, f)
rows = []
a = pd.read_excel(g('dcdd8678-ss_floodsaffected_people_20211213.xlsx'), usecols='A:F').dropna(subset=['County'])
for _, r in a.iterrows():
    v = pd.to_numeric(r['Affected People'], errors='coerce')
    if pd.notna(v):
        rows.append((2021, r.County, v, r['Month Flood Incident'], '2021 assessment, 13 Dec 2021'))
b = pd.read_excel(g('8c60e84e-ssd_flood_response_211022.xlsx'), skiprows=[1])
b = b[b['Is the county assessed?'] == 'Yes']
for _, r in b.iterrows():
    rows.append((2022, r.County, r['Assessed number of flood-affected people'], None, '2022 response, 21 Oct 2022 (assessed only)'))
c = pd.read_excel(g('761b1e62-ssd_flood_response_20122024.xlsx'))
for _, r in c.dropna(subset=['Admin2_Pcode']).iterrows():
    rows.append((2024, r.Admin2, r.People_Affected, None, '2024 response, 20 Dec 2024'))
d = pd.read_excel(g('301ff901-ss_people_affected_and_displaced_by_floods_20251130.xlsx')).dropna(subset=['Admin2_PCODE'])
d.columns = ['a1', 'p1', 'a2', 'pc', 'aff', 'disp']
disp = {}
for _, r in d.iterrows():
    if pd.notna(r.aff):
        rows.append((2025, r.a2, r.aff, None, '2025 people affected, 30 Nov 2025'))
        disp[m(r.a2)] = r.disp
L = pd.DataFrame(rows, columns=['year', 'src_county', 'affected', 'month_raw', 'source'])
L['county'] = L.src_county.map(m)
assert L.county.notna().all(), L[L.county.isna()]
def mon(x):
    if pd.isna(x): return None
    if hasattr(x, 'month'): return x.month
    s = str(x).lower()
    for i, t in enumerate('jan feb mar apr may jun jul aug sep oct nov dec'.split(), 1):
        if t in s: return i
    mm = re.match(r'(\d+)/(\d+)/', s)
    return int(mm.group(2)) if mm else None
L['month'] = L.month_raw.map(mon)
L['affected'] = pd.to_numeric(L.affected)
L = L.merge(pop[['county', 'state', 'pop_2025']], on='county')
L['pct_of_pop2025'] = (100 * L.affected / L.pop_2025).round(1)
long = L[['year', 'month', 'state', 'county', 'affected', 'pct_of_pop2025', 'source', 'src_county']].sort_values(['year', 'state', 'county'])
tot = L.groupby(['state', 'county', 'year']).affected.sum().unstack('year')
tot.columns = [f'affected_{c}' for c in tot.columns]
tot = tot.reset_index().merge(pop[['county', 'pop_2025']], on='county', how='right')
tot['state'] = tot.state.fillna(tot.county.map(pop.set_index('county').state))
ac = [c for c in tot.columns if c.startswith('affected_')]
tot['max_share_pct'] = (100 * tot[ac].max(axis=1) / tot.pop_2025).round(1)
tot['years_reported'] = tot[ac].notna().sum(axis=1)
tot = tot.sort_values(['state', 'county'])
notes = pd.DataFrame({'note': [
    'Affected = people reported affected by floods in each source file (not displaced). Figures are cumulative snapshots as of the date in each source.',
    '2021: county assessment as of 13 Dec 2021; repeated county rows (Fangak) summed. 2022: only counties assessed by 21 Oct 2022; Mundri West and Mvolo had several rows and are summed. 2023: no file supplied. 2024: as of 20 Dec 2024. 2025: as of 30 Nov 2025.',
    'Blank = county not listed in that year (not assessed / not reported), which is not the same as zero.',
    'Month is available only for some 2021 rows (month of the flood incident). The other files are annual totals with no monthly breakdown.',
    'pct_of_pop2025 divides by the 2025 county population estimate, so it is approximate for earlier years.']})
os.makedirs('data', exist_ok=True)
long.to_csv('data/flood_affected_county_year.csv', index=False)
with pd.ExcelWriter('data/flood_affected_county_year.xlsx') as w:
    tot.to_excel(w, 'County_by_year', index=False)
    long.to_excel(w, 'All_records', index=False)
    notes.to_excel(w, 'Notes', index=False)
print(L.groupby('year').agg(counties=('county', 'nunique'), total=('affected', 'sum')))
print(tot.sort_values('max_share_pct', ascending=False).head(8)[['county'] + ac + ['max_share_pct']])
