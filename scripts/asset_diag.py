import json
import ee
import ee_util

ee_util.init_ee()
A = 'projects/ee-penuelabi/assets/SSD_2025q2_populacehealthdataorg'
info = ee.data.getAsset(A)
print('props', json.dumps(info.get('properties', {})), flush=True)
print('time', info.get('startTime'), flush=True)
img = ee.Image(A)
pr = img.projection()
pi = pr.getInfo()
print('transform', pi.get('transform'), flush=True)
print('nominalScale', pr.nominalScale().getInfo(), flush=True)
b = img.getInfo()['bands'][0]
print('band', json.dumps(b)[:400], flush=True)
payam = ee.FeatureCollection('users/penuelabi/ssd_payam')
def tot(g):
    r = img.reduceRegion(ee.Reducer.sum().combine(ee.Reducer.max(), sharedInputs=True).combine(ee.Reducer.count(), sharedInputs=True), g, crs=pr, maxPixels=1e10, tileScale=8).getInfo()
    return {k: round(v, 1) for k, v in r.items()}
for name in ('Juba Town', 'Munuki', 'Kator', 'Padiet', 'Lobonok', 'Narus', 'Jie', 'Wau North'):
    g = payam.filter(ee.Filter.eq('ADM3_EN', name)).first().geometry()
    print(name, round(g.area(1).getInfo() / 1e6, 1), 'km2', tot(g), flush=True)
