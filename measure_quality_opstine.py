import csv
import os
import sys
import time

import fiona
import overpy
from shapely.geometry import shape
import pyproj
from common import retry_on_error, create_geometry_from_osm_response, get_polygon_by_mb
from concurrent.futures import ThreadPoolExecutor, as_completed, ProcessPoolExecutor
from threading import Lock
import multiprocessing

csv.field_size_limit(sys.maxsize)
geod = pyproj.Geod(ellps='WGS84')
progress_file = 'output/opstine.csv'
csv_write_mutex = Lock()
results = []


@retry_on_error()
def get_opstina_polygon_by_name(api, district, municapality):
    response = api.query("""
area["name"="Србија"]["admin_level"=2]->.sr;
(
area(area.sr)["name"~"{0}$", i]["admin_level"=6]->.district;
(
    relation(area.district)["boundary"="administrative"]["admin_level"=8]["name"~"{1}$", i];
);
);
(._;>;);
out;
// &contact=https://gitlab.com/stalker314314/prostorne-jedinice-import/
""".format(district, municapality))
    time.sleep(10)

    print('relations found: {0}'.format(len(response.relations)))
    if len(response.relations) != 1:
        return None, None, None
    polygon = create_geometry_from_osm_response(response.relations[0], response)
    return polygon, response.relations[0].tags['name'], response.relations[0].id


def get_current_results():
    # Load saved state
    results = []
    if os.path.isfile(progress_file):
        with open(progress_file) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                results.append(
                    {'district': row['district'], 'municipality': row['municipality'], 'is_city': row['is_city'],
                     'osm_municipality': row['osm_municipality'], 'relation_id': row['relation_id'],
                     'area_diff': row['area_diff'], 'area_not_shared': row['area_not_shared'],
                     'national_border': row['national_border']})
    return results


def get_cities():
    cities = {}
    with fiona.open("output/shp/grad4326.shp", "r", encoding='utf-8') as input:
        for i in input:
            grad = i['properties']['grad']
            grad_mb = i['properties']['grad_mb']
            cities[grad] = grad_mb
    return cities


def get_opstine_from_shapefile():
    opstine = []
    with fiona.open("output/shp/opstina4326.shp", "r", encoding='utf-8') as input:
        for i in input:
            rgz_municipality_polygon = shape(i['geometry'])
            district = i['properties']['okrug']
            district_sifra = i['properties']['okrug_sfr']
            municipality = i['properties']['opstina']
            municipality_maticni_broj = int(i['properties']['opstina_mb'])
            # Skip if Kosovo
            if int(district_sifra) in (25, 26, 27, 28, 29):
                continue
            opstine.append({'rgz_municipality_polygon': rgz_municipality_polygon,
                            'district': district,
                            'district_sifra': district_sifra,
                            'municipality': municipality,
                            'municipality_maticni_broj': municipality_maticni_broj})
    return opstine


def write_results(current_result):
    with csv_write_mutex:
        with open(progress_file, 'w') as out_csv:
            writer = csv.DictWriter(out_csv, fieldnames=['district', 'municipality', 'is_city', 'osm_municipality',
                                                         'relation_id', 'area_diff', 'area_not_shared',
                                                         'national_border'])
            writer.writeheader()
            for data in current_result:
                writer.writerow(data)


def process_opstina(overpass_api, opstina, cities, count_processed, total_to_process):
    print('Processed {0}/{1}'.format(count_processed, total_to_process))

    rgz_municipality_polygon = opstina['rgz_municipality_polygon']
    district = opstina['district']
    district_sifra = opstina['district_sifra']
    municipality = opstina['municipality']
    municipality_maticni_broj = opstina['municipality_maticni_broj']

    print('Processing {0} {1}'.format(district, municipality))
    overpass_municipality_polygon, osm_municipality_name, osm_relation_id, national_border = \
        get_polygon_by_mb(overpass_api, 8, municipality_maticni_broj, mb_key='ref:RS:opstina')
    if overpass_municipality_polygon is None:
        print('District {0} and municipality {1} not found using ref:RS:opstina'.format(district, municipality))
        overpass_municipality_polygon, osm_municipality_name, osm_relation_id = \
            get_opstina_polygon_by_name(overpass_api, district, municipality)
        if overpass_municipality_polygon is None:
            print('District {0} and municipality {1} not found at all'.format(district, municipality))
            if municipality in cities:
                overpass_municipality_polygon, osm_municipality_name, osm_relation_id, national_border = \
                    get_polygon_by_mb(overpass_api, 7, cities[municipality], mb_key='ref:RS:grad')
                if overpass_municipality_polygon is None:
                    print('District {0} and city {1} not found using ref:RS:grad'.format(district, municipality))
                    result = {'district': district, 'municipality': municipality, 'is_city': 1,
                            'osm_municipality': '', 'relation_id': -1, 'area_diff': -1, 'area_not_shared': -1,
                            'points_diff': -1, 'national_border': national_border}
                    results.append(result)
                    return result
            else:
                result = {'district': district, 'municipality': municipality, 'is_city': 0, 'osm_municipality': '',
                          'relation_id': -1, 'area_diff': -1, 'area_not_shared': -1, 'national_border': national_border}
                results.append(result)
                if count_processed % 10 == 0:
                    write_results(results)
                return result

    rgz_area = rgz_municipality_polygon.area
    intersection_area = rgz_municipality_polygon.intersection(overpass_municipality_polygon).area
    area_diff = intersection_area / rgz_area

    a_minus_b = rgz_municipality_polygon.difference(overpass_municipality_polygon)
    b_minus_a = overpass_municipality_polygon.difference(rgz_municipality_polygon)
    a_minus_b_union_b_minus_a = a_minus_b.union(b_minus_a)
    a_union_b = rgz_municipality_polygon.union(overpass_municipality_polygon)
    area_not_shared = a_minus_b_union_b_minus_a.area / a_union_b.area

    print(district, municipality, osm_municipality_name, 100 * intersection_area/rgz_area, area_diff)
    result = {
        'district': district, 'municipality': municipality, 'is_city': municipality in cities,
        'osm_municipality': osm_municipality_name, 'relation_id': osm_relation_id,
        'area_diff': round(area_diff, 6), 'area_not_shared': round(area_not_shared, 6),
        'national_border': national_border}
    results.append(result)
    return result


def measure_quality_opstine(overpass_api):
    global results
    results = get_current_results()
    cities = get_cities()
    opstine = get_opstine_from_shapefile()
    count_processed = 1

    all_futures = []
    thread_count = 1 if 'localhost' not in overpass_api.url else multiprocessing.cpu_count()
    print('Using {0} threads'.format(thread_count))
    with ProcessPoolExecutor(max_workers=thread_count) as executor:
        for opstina in opstine:
            # Skip if already processed
            district = opstina['district']
            municipality = opstina['municipality']
            if any((r for r in results if r['district'] == district and r['municipality'] == municipality)):
                print('District {0} and municipality {1} already processed'.format(district, municipality))
                continue
            future = executor.submit(process_opstina, overpass_api, opstina, cities, count_processed, len(opstine))
            all_futures.append(future)
            count_processed = count_processed + 1
        for future in as_completed(all_futures):
            results.append(future.result())
    write_results(results)


if __name__ == '__main__':
    #overpass_api = overpy.Overpass(url='https://lz4.overpass-api.de/api/interpreter')
    #overpass_api = overpy.Overpass(url='http://overpass-api.de/api/interpreter')
    overpass_api = overpy.Overpass(url='http://localhost:12345/api/interpreter')
    measure_quality_opstine(overpass_api)

