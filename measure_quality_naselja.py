import csv
import os
import sys
import time

import fiona
import overpy
from shapely.geometry import shape
import pyproj
from common import retry_on_error, create_geometry_from_osm_response, get_polygon_by_mb
from common import get_municipality_district, get_settlement_municipality, get_district_name_by_id
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from threading import Lock
import multiprocessing

csv.field_size_limit(sys.maxsize)
geod = pyproj.Geod(ellps='WGS84')
progress_file = 'output/naselja.csv'
csv_write_mutex = Lock()
results = []

schema = {
    'geometry': ['Polygon', 'MultiPolygon'],
    'properties': {
        'naselje' : 'str',
        'opstina': 'str',
        'okrug': 'str',
        'naselje_mb': 'str',
        'opstina_mb': 'str',
        'okrug_sfr': 'str',
    }
}


@retry_on_error()
def get_naselje_polygon_by_name(api, district, municapality):
    for admin_level in (8,7):
        response = api.query("""
area["name"="Србија"]["admin_level"=2]->.sr;
(
	area(area.sr)["name"~"{0}$", i]["admin_level"={1}]->.district;
  	(
  		relation(area.district)["boundary"="administrative"]["admin_level"=9]["name"~"^{2}$", i];
    );
);
(._;>;);
out;
// &contact=https://gitlab.com/stalker314314/prostorne-jedinice-import/
    """.format(district, admin_level, municapality))
        time.sleep(10)

        print('relations found for level {0}: {1}'.format(admin_level, len(response.relations)))
        if len(response.relations) != 1:
            continue
        polygon = create_geometry_from_osm_response(response.relations[0], response)
        return polygon, response.relations[0].tags['name'], response.relations[0].id
    return None, None, None


def get_current_results():
    # Load saved state
    results = []
    if os.path.isfile(progress_file):
        with open(progress_file) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                results.append(
                    {'district': row['district'], 'municipality': row['municipality'], 'settlement': row['settlement'],
                     'osm_settlement': row['osm_settlement'], 'relation_id': row['relation_id'],
                     'area_diff': row['area_diff'], 'area_not_shared': row['area_not_shared'],
                     'national_border': row['national_border']})
    return results


def get_naselja_from_shapefile(districts_by_id, municipality_district, settlement_municipality):
    naselja = []
    with fiona.open("output/shp/naselje4326.shp", "r", encoding='utf-8') as input:
        for i in input:
            rgz_municipality_polygon = shape(i['geometry'])
            municipality = i['properties']['opstina']
            settlement = i['properties']['naselje']
            settlement_maticni_broj = int(i['properties']['naselje_mb'])
            district = districts_by_id[municipality_district[settlement_municipality[settlement_maticni_broj]]]
            naselja.append({'rgz_municipality_polygon': rgz_municipality_polygon, 'municipality': municipality,
                            'settlement': settlement, 'settlement_maticni_broj': settlement_maticni_broj,
                            'district': district})
    return naselja


def write_results(current_results):
    with csv_write_mutex:
        with open(progress_file, 'w') as out_csv:
            writer = csv.DictWriter(out_csv, fieldnames=['district', 'municipality', 'settlement', 'osm_settlement',
                                                         'relation_id', 'area_diff', 'area_not_shared', 'national_border'])
            writer.writeheader()
            for data in current_results:
                writer.writerow(data)


def process_naselje(overpass_api, naselje, count_processed, total_to_process):
    global results
    print('Processed {0}/{1}'.format(count_processed, total_to_process))

    rgz_municipality_polygon = naselje['rgz_municipality_polygon']
    municipality = naselje['municipality']
    settlement = naselje['settlement']
    settlement_maticni_broj = naselje['settlement_maticni_broj']
    district = naselje['district']

    print('Processing {0} {1}'.format(municipality, settlement))

    overpass_municipality_polygon, osm_settlement_name, osm_relation_id, national_border = \
        get_polygon_by_mb(overpass_api, 9, settlement_maticni_broj, mb_key='ref:RS:naselje')
    if overpass_municipality_polygon is None:
        print('Municipality {0} and settlement {1} not found using ref:RS:naselje'.format(municipality, settlement))
        overpass_municipality_polygon, osm_settlement_name, osm_relation_id, national_border = \
            get_naselje_polygon_by_name(overpass_api, municipality, settlement)
        if overpass_municipality_polygon is None:
            print('Municipality {0} and settlement {1} not found at all'.format(municipality, settlement))
            result = {'district': district, 'municipality': municipality, 'settlement': settlement,
                      'osm_settlement': '', 'relation_id': -1, 'area_diff': -1, 'area_not_shared': -1,
                      'national_border': national_border}
            results.append(result)
            return result

    rgz_area = rgz_municipality_polygon.area
    intersection_area = rgz_municipality_polygon.intersection(overpass_municipality_polygon).area

    a_minus_b = rgz_municipality_polygon.difference(overpass_municipality_polygon)
    b_minus_a = overpass_municipality_polygon.difference(rgz_municipality_polygon)
    a_minus_b_union_b_minus_a = a_minus_b.union(b_minus_a)
    a_union_b = rgz_municipality_polygon.union(overpass_municipality_polygon)
    area_not_shared = a_minus_b_union_b_minus_a.area / a_union_b.area

    print(municipality, settlement, osm_settlement_name, 100 * intersection_area/rgz_area, area_not_shared)
    result = {'district': district, 'municipality': municipality, 'settlement': settlement,
              'osm_settlement': osm_settlement_name, 'relation_id': osm_relation_id,
              'area_diff': round(intersection_area/rgz_area, 5),
              'area_not_shared': round(area_not_shared, 5),
              'national_border': national_border}
    results.append(result)
    return result


def measure_quality_naselja(overpass_api):
    global results
    results = get_current_results()

    districts_by_id = get_district_name_by_id()
    municipality_district = get_municipality_district()
    settlement_municipality = get_settlement_municipality()

    naselja = get_naselja_from_shapefile(districts_by_id, municipality_district, settlement_municipality)

    count_processed = 1
    all_futures = []
    thread_count = 1 if 'localhost' not in overpass_api.url else multiprocessing.cpu_count()
    print('Using {0} threads'.format(thread_count))
    with ProcessPoolExecutor(max_workers=thread_count) as executor:
        for naselje in naselja:
            # Skip if already processed
            municipality = naselje['municipality']
            settlement = naselje['settlement']
            if any((r for r in results if r['municipality'] == municipality and r['settlement'] == settlement)):
                print('District {0} and municipality {1} already processed'.format(municipality, settlement))
                continue

            future = executor.submit(process_naselje, overpass_api, naselje, count_processed, len(naselja))
            all_futures.append(future)
            count_processed = count_processed + 1
        for future in as_completed(all_futures):
            results.append(future.result())
    write_results(results)


if __name__ == '__main__':
    #overpass_api = overpy.Overpass(url='https://lz4.overpass-api.de/api/interpreter')
    #overpass_api = overpy.Overpass(url='http://overpass-api.de/api/interpreter')
    overpass_api = overpy.Overpass(url='http://localhost:12345/api/interpreter')
    measure_quality_naselja(overpass_api)
