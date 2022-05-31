import csv
import multiprocessing
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from threading import Lock

import overpy
import yaml
from shapely.wkt import loads

from common import retry_on_error, create_geometry_from_osm_response, get_polygon_by_cadastre_id, load_level9_features

csv.field_size_limit(sys.maxsize)
csv_write_mutex = Lock()
results = []


@retry_on_error()
def get_level9_polygon_by_name(api, country, level6_name, level8_name):
    for admin_level in (8, 7):
        response = api.query("""
area["name"="{0}"]["admin_level"=2]->.country;
(
	area(area.country)["name"~"{1}$", i]["admin_level"={2}]->.district;
  	(
  		relation(area.district)["boundary"="administrative"]["admin_level"=9]["name"~"^{3}$", i];
    );
);
(._;>;);
out;
// &contact=https://github.com/stalker314314/osm-admin-boundary-conflation/
    """.format(country, level6_name, admin_level, level8_name))
        time.sleep(10)

        print('relations found for level {0}: {1}'.format(admin_level, len(response.relations)))
        if len(response.relations) != 1:
            continue
        polygon = create_geometry_from_osm_response(response.relations[0], response)
        return polygon, response.relations[0].tags['name'], response.relations[0].id
    return None, None, None


def get_current_results(output_file):
    # Load saved state
    results = []
    if os.path.isfile(output_file):
        with open(output_file) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                results.append(
                    {'level6_name': row['level6_name'], 'level8_name': row['level8_name'],
                     'level9_name': row['level9_name'], 'osm_settlement_name': row['osm_settlement_name'],
                     'relation_id': row['relation_id'], 'area_diff': row['area_diff'],
                     'area_not_shared': row['area_not_shared'], 'national_border': row['national_border']})
    return results


def write_results(current_results, output_file):
    with csv_write_mutex:
        with open(output_file, 'w') as out_csv:
            writer = csv.DictWriter(out_csv, fieldnames=[
                'level6_name', 'level8_name', 'level9_name', 'osm_settlement_name',
                'relation_id', 'area_diff', 'area_not_shared', 'national_border'])
            writer.writeheader()
            for data in current_results:
                writer.writerow(data)


def process_level9(config, overpass_api, level9_entity, count_processed, total_to_process):
    global results
    print('Processed {0}/{1}'.format(count_processed, total_to_process))

    country = config['country']
    level9_ref_key = config['level9_ref_key']

    cadastre_level9_polygon = loads(level9_entity['wkt'])
    level6_name = level9_entity['level6_name']
    level8_name = level9_entity['level8_name']
    level9_name = level9_entity['level9_name']
    level9_id = level9_entity['level9_id']

    print('Processing {0} {1}'.format(level8_name, level9_name))

    overpass_level9_polygon, osm_settlement_name, osm_relation_id, national_border = \
        get_polygon_by_cadastre_id(overpass_api, admin_level=9, cadastre_id=level9_id, country=country, id_key=level9_ref_key)
    if overpass_level9_polygon is None:
        print(f'Level 8 {level8_name} and level 9 {level9_name} not found using {level9_ref_key}')
        overpass_level9_polygon, osm_settlement_name, osm_relation_id, national_border = \
            get_level9_polygon_by_name(overpass_api, country, level8_name, level9_name)
        if overpass_level9_polygon is None:
            print(f'Level8 {level8_name} and level9 {level9_name} not found at all')
            result = {'level6_name': level6_name, 'level8_name': level8_name, 'level9_name': level9_name,
                      'osm_settlement_name': '', 'relation_id': -1, 'area_diff': -1, 'area_not_shared': -1,
                      'national_border': national_border}
            results.append(result)
            return result

    cadastre_area = cadastre_level9_polygon.area
    intersection_area = cadastre_level9_polygon.intersection(overpass_level9_polygon).area

    a_minus_b = cadastre_level9_polygon.difference(overpass_level9_polygon)
    b_minus_a = overpass_level9_polygon.difference(cadastre_level9_polygon)
    a_minus_b_union_b_minus_a = a_minus_b.union(b_minus_a)
    a_union_b = cadastre_level9_polygon.union(overpass_level9_polygon)
    area_not_shared = a_minus_b_union_b_minus_a.area / a_union_b.area

    print(level8_name, level9_name, osm_settlement_name, 100 * intersection_area/cadastre_area, area_not_shared)
    result = {'level6_name': level6_name, 'level8_name': level8_name, 'level9_name': level9_name,
              'osm_settlement_name': osm_settlement_name, 'relation_id': osm_relation_id,
              'area_diff': round(intersection_area/cadastre_area, 5),
              'area_not_shared': round(area_not_shared, 5),
              'national_border': national_border}
    results.append(result)
    return result


def measure_quality(config, overpass_api, input_csv_file, output_file):
    global results
    results = get_current_results(output_file)
    level9_features = load_level9_features(input_csv_file)

    count_processed = 1
    all_futures = []
    thread_count = 1 if 'localhost' not in overpass_api.url else multiprocessing.cpu_count()
    print('Using {0} threads'.format(thread_count))
    with ProcessPoolExecutor(max_workers=thread_count) as executor:
        for level9_feature in level9_features:
            # Skip if already processed
            level8_name = level9_feature['level8_name']
            level9_name = level9_feature['level9_name']
            if any((r for r in results if r['level8'] == level8_name and r['level9'] == level9_name)):
                print('Level8 {0} and level9 {1} already processed'.format(level8_name, level9_name))
                continue

            future = executor.submit(process_level9, config, overpass_api, level9_feature, count_processed, len(level9_features))
            all_futures.append(future)
            count_processed = count_processed + 1
        for future in as_completed(all_futures):
            results.append(future.result())
    write_results(results, output_file)


if __name__ == '__main__':
    with open('config.yml', 'r') as config_yml_file:
        config = yaml.safe_load(config_yml_file)

    overpass_api = overpy.Overpass(url=config['overpass_url'])

    if len(sys.argv) != 3:
        print("Usage: ./measure_quality.py <input_csv_file> <output_csv_file>")
        exit()
    input_csv_file = sys.argv[1]
    output_csv_file = sys.argv[2]
    measure_quality(config, overpass_api, input_csv_file, output_csv_file)
