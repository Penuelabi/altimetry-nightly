import json
import ee
import ee_util

ee_util.init_ee()
for a in ('projects/ee-penuelabi/assets/SSD_2025q2_populacehealthdataorg', 'projects/ee-penuelabi/assets/SSD_Facilities',
          'projects/ee-penuelabi/assets/SDD_Schools', 'projects/ee-penuelabi/assets/SSD_Health'):
    print('=====', a, flush=True)
    try:
        info = ee.data.getAsset(a)
        print('type', info.get('type'), 'size', info.get('sizeBytes'), json.dumps(info.get('properties', {}))[:600], flush=True)
        if info['type'] == 'TABLE':
            fc = ee.FeatureCollection(a)
            print('count', fc.size().getInfo(), flush=True)
            print('first', json.dumps(fc.first().getInfo())[:1500], flush=True)
            for col in ('Facility subtype', 'Facility type', 'facility_subtype', 'subtype'):
                try:
                    h = fc.aggregate_histogram(col).getInfo()
                    if h:
                        print('hist', col, json.dumps(h), flush=True)
                except Exception as e:
                    pass
            print('geom types', json.dumps(fc.aggregate_histogram('system:index').size().getInfo()) if False else '', flush=True)
        else:
            img = ee.Image(a)
            print('bands', json.dumps(img.bandNames().getInfo()), flush=True)
            print('proj', json.dumps(img.projection().getInfo())[:300], flush=True)
            r = img.reduceRegion(ee.Reducer.sum().combine(ee.Reducer.max(), sharedInputs=True), ee.Geometry.Rectangle([30.5, 3.5, 32.5, 5.5]),
                                 crs=img.projection(), maxPixels=1e10, tileScale=8).getInfo()
            print('Juba box', json.dumps(r), flush=True)
    except Exception as e:
        print('ERR', str(e)[:300], flush=True)
