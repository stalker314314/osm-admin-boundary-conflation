import csv
import os
import sys
import time

import fiona
import overpy
from shapely.geometry import shape
import pyproj
from common import retry_on_error, create_geometry_from_osm_response, get_polygon_by_mb

csv.field_size_limit(sys.maxsize)
geod = pyproj.Geod(ellps='WGS84')

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


def measure_quality_naselja(overpass_api):
    #districts_by_id = get_district_name_by_id()
    #settlement_municipality = get_settlement_municipality()
    #municipality_district = get_municipality_district()

    # Load saved state
    progress_file = 'output/measure_quality_naselja-hr.csv'
    results = []
    if os.path.isfile(progress_file):
        with open(progress_file) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                results.append(
                    {'municipality': row['municipality'], 'settlement': row['settlement'],
                     'osm_settlement': row['osm_settlement'], 'relation_id': row['relation_id'],
                     'area_diff': row['area_diff'], 'area_not_shared': row['area_not_shared']})

    with fiona.open("shp/smz.shp", "r", encoding='utf-8') as input:
        count_processed = 1
        for i in input:
            print('Processed {0}/{1}'.format(count_processed, len(input)))
            count_processed = count_processed + 1

            rgz_municipality_polygon = shape(i['geometry'])
            municipality = i['properties']['JLS_IME']
            settlement = i['properties']['NA_IME']
            settlement_maticni_broj = i['properties']['NA_MB']
            #district = districts_by_id[municipality_district[settlement_municipality[settlement_maticni_broj]]]

            # Skip if already processed
            if any((r for r in results if r['municipality'] == municipality and r['settlement'] == settlement)):
                print('District {0} and municipality {1} already processed'.format(municipality, settlement))
                continue

            print('Processing {0} {1}'.format(municipality, settlement))
            overpass_municipality_polygon, osm_settlement_name, osm_relation_id, _ = \
                get_polygon_by_mb(overpass_api, 8, settlement_maticni_broj, 'Hrvatska', 'ref:hr:maticni_broj')
            if overpass_municipality_polygon is None:
                print('Municipality {0} and settlement {1} not found using ref:hr:maticni_broj'.format(municipality, settlement))
                continue

            rgz_area = rgz_municipality_polygon.area
            intersection_area = rgz_municipality_polygon.intersection(overpass_municipality_polygon).area

            a_minus_b = rgz_municipality_polygon.difference(overpass_municipality_polygon)
            b_minus_a = overpass_municipality_polygon.difference(rgz_municipality_polygon)
            a_minus_b_union_b_minus_a = a_minus_b.union(b_minus_a)
            a_union_b = rgz_municipality_polygon.union(overpass_municipality_polygon)
            area_not_shared = a_minus_b_union_b_minus_a.area / a_union_b.area

            print(municipality, settlement, osm_settlement_name, 100 * intersection_area/rgz_area)
            results.append({'municipality': municipality, 'settlement': settlement,
                            'osm_settlement': osm_settlement_name, 'relation_id': osm_relation_id,
                            'area_diff': round(intersection_area/rgz_area, 5),
                            'area_not_shared': round(area_not_shared, 5)})
            with open(progress_file, 'w') as out_csv:
                writer = csv.DictWriter(out_csv, fieldnames=['municipality', 'settlement', 'osm_settlement',
                                                             'relation_id', 'area_diff', 'area_not_shared'])
                writer.writeheader()
                for data in results:
                    writer.writerow(data)
            time.sleep(0.5)


def measure_quality_opstine(overpass_api):
    # Load saved state
    progress_file = 'output/measure_quality_opstine-hr.csv'
    results = []
    if os.path.isfile(progress_file):
        with open(progress_file) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                results.append(
                    {'district': row['district'], 'municipality': row['municipality'], 'is_city': row['is_city'],
                     'osm_municipality': row['osm_municipality'], 'relation_id': row['relation_id'],
                     'area_diff': row['area_diff'], 'area_not_shared': row['area_not_shared']})

    cities = set()
    with open('grad.csv') as csvfile:
        reader = csv.DictReader(csvfile)
        for i, row in enumerate(reader):
            city = row['grad_ime']
            cities.add(city)

    with fiona.open("output/opstina4326.shp", "r", encoding='utf-8') as input:
        count_processed = 1
        for i in input:
            print('Processed {0}/{1}'.format(count_processed, len(input)))
            count_processed = count_processed + 1

            rgz_municipality_polygon = shape(i['geometry'])
            district = i['properties']['okrug']
            district_sifra = i['properties']['okrug_sfr']
            municipality = i['properties']['opstina']
            municipality_maticni_broj = int(i['properties']['opstina_mb'])
            # Skip if already processed
            if any((r for r in results if r['district'] == district and r['municipality'] == municipality)):
                print('District {0} and municipality {1} already processed'.format(district, municipality))
                continue
            # Skip if Kosovo
            if int(district_sifra) in (25, 26, 27, 28, 29):
                print('Skipping Kosovo districts')
                continue

            print('Processing {0} {1}'.format(district, municipality))
            overpass_municipality_polygon, osm_municipality_name, osm_relation_id, _ = \
                get_polygon_by_mb(overpass_api, 8, municipality_maticni_broj)
            if overpass_municipality_polygon is None:
                print('District {0} and municipality {1} not found using ref:sr:maticni_broj'.format(district, municipality))
                overpass_municipality_polygon, osm_municipality_name, osm_relation_id = \
                    get_opstina_polygon_by_name(overpass_api, district, municipality)
                if overpass_municipality_polygon is None:
                    print('District {0} and municipality {1} not found at all'.format(district, municipality))
                    is_city = municipality in cities
                    results.append(
                        {'district': district, 'municipality': municipality, 'is_city': 1 if is_city else 0,
                         'osm_municipality': '', 'relation_id': -1, 'area_diff': -1, 'area_not_shared': -1})
                    continue

            rgz_area = rgz_municipality_polygon.area
            intersection_area = rgz_municipality_polygon.intersection(overpass_municipality_polygon).area
            area_diff = intersection_area / rgz_area

            a_minus_b = rgz_municipality_polygon.difference(overpass_municipality_polygon)
            b_minus_a = overpass_municipality_polygon.difference(rgz_municipality_polygon)
            a_minus_b_union_b_minus_a = a_minus_b.union(b_minus_a)
            a_union_b = rgz_municipality_polygon.union(overpass_municipality_polygon)
            area_not_shared = a_minus_b_union_b_minus_a.area / a_union_b.area

            print(district, municipality, osm_municipality_name, 100 * intersection_area/rgz_area)
            results.append({'district': district, 'municipality': municipality, 'is_city': 0,
                            'osm_municipality': osm_municipality_name, 'relation_id': osm_relation_id,
                            'area_diff': round(area_diff, 6), 'area_not_shared': round(area_not_shared, 6)})
            with open(progress_file, 'w') as out_csv:
                writer = csv.DictWriter(out_csv, fieldnames=['district', 'municipality', 'is_city', 'osm_municipality',
                                                             'relation_id', 'area_diff', 'area_not_shared'])
                writer.writeheader()
                for data in results:
                    writer.writerow(data)


if __name__ == '__main__':
    overpass_api = overpy.Overpass(url='https://lz4.overpass-api.de/api/interpreter')
    if len(sys.argv) == 2 and sys.argv[1] == 'opstine':
        measure_quality_opstine(overpass_api)
    else:
        measure_quality_naselja(overpass_api)

