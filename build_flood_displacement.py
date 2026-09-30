"""County x year x month flood-triggered displacement (IOM DTM event tracking) from Sudd_data010726.xlsx."""
import pandas as pd, re, sys
f = sys.argv[1]
e = pd.read_excel(f, sheet_name='Event tracking _Sudd').iloc[:, :16]
e.columns = ['c0', 's', 'county_src', 'payam_src', 'dest_state', 'dest_county', 'pcode', 'p', 'dp', 'cat', 'trigger', 'year', 'month', 'date', 'hh', 'ind']
e['t'] = e.trigger.astype(str).str.strip().str.lower()
e['flood'] = e.t.str.contains('flood')
e['nd'] = e.t.eq('natural disaster') | e.t.eq('natural disaster (other)')
e['cls'] = e.flood.map({True: 'flood'}).fillna(e.nd.map({True: 'natural disaster (unspecified)'})).fillna('other')
pop = pd.read_csv('data/ssd_county_population_2025.csv')
n = lambda s: re.sub(r'[^a-z]', '', str(s).lower())
idx = {n(c): c for c in pop.county}
alias = {'panyijar': 'panyijiar', 'mayiendit': 'mayendit', 'pariangruweng': 'pariang', 'abyeiadministrativearea': 'abyeiregion'}
e['county'] = e.dest_county.map(lambda x: idx.get(alias.get(n(x), n(x))))
print('unmatched', e[e.county.isna()].dest_county.unique())
e = e.dropna(subset=['county', 'year', 'month'])
fl = e[e.cls != 'other']
pv = fl.pivot_table(index=['county', 'year', 'month'], columns='cls', values='ind', aggfunc='sum', fill_value=0).reset_index()
pv = pv.merge(pop[['state', 'county', 'pop_2025']], on='county')
pv['flood'] = pv.get('flood', 0)
pv['pct_of_pop2025'] = (100 * pv.flood / pv.pop_2025).round(1)
yr = fl[fl.cls == 'flood'].groupby(['county', 'year']).ind.sum().unstack().fillna(0).astype(int)
mo = fl[fl.cls == 'flood'].groupby(['year', 'month']).ind.sum().unstack().fillna(0).astype(int)
print(yr.sum()); print(mo)
pv.sort_values(['year', 'month', 'county']).to_csv('data/flood_displacement_county_month.csv', index=False)
with pd.ExcelWriter('data/flood_displacement_county_month.xlsx') as w:
    pv.sort_values(['county', 'year', 'month']).to_excel(w, sheet_name='County_year_month', index=False)
    yr.reset_index().to_excel(w, sheet_name='County_by_year', index=False)
    mo.to_excel(w, sheet_name='Month_totals')
    pd.DataFrame({'note': [
        'Source: IOM DTM South Sudan emergency event tracking (sheet "Event tracking _Sudd" of Sudd_data010726.xlsx). Individuals = people displaced (IDPs and returnees) per tracked event, summed per destination county and assessment month.',
        'flood = movement trigger says flooding. "natural disaster (unspecified)" is a separate column: flood is likely but not stated.',
        'Covers the 17 Sudd counties in Unity, Jonglei and Upper Nile only. A county-month with no row means no event was tracked, not zero.',
        'This is displacement, a subset of people affected. It is not comparable with the flood-affected totals from the OCHA response files.']}).to_excel(w, sheet_name='Notes', index=False)
