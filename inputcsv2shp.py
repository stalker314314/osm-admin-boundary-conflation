import csv
import sys

import fiona
from fiona.crs import from_epsg
from shapely.geometry import mapping
from shapely.wkt import loads

from common import load_level9_features

csv.field_size_limit(sys.maxsize)

schema = {
    'geometry': ['Polygon', 'MultiPolygon'],
    'properties': {
        'level9id': 'str',
        'level9name': 'str',
        'level8id': 'str',
        'level8name': 'str',
        'level7id': 'str',
        'level7name': 'str',
        'level6id': 'str',
        'level6name': 'str'
    }
}


def main(input_csv_file: str, output_shp_file: str):
    print(f'Loading level9 data from {input_csv_file}')
    level9_features = load_level9_features(input_csv_file)

    print(f'Writing level9 data to {output_shp_file}')
    with fiona.collection(output_shp_file, "w", "ESRI Shapefile", schema, crs=from_epsg(4326), encoding='utf-8') as output:
        for level9_feature in level9_features:
            geometry = loads(level9_feature['wkt'])
            output.write({
                'properties': {
                    'level9id': level9_feature['level9_id'],
                    'level9name': level9_feature['level9_name'],
                    'level8id': level9_feature['level8_id'],
                    'level8name': level9_feature['level8_name'],
                    'level7id': level9_feature['level7_id'],
                    'level7name': level9_feature['level7_name'],
                    'level6id': level9_feature['level6_id'],
                    'level6name': level9_feature['level6_name']
                },
                'geometry': mapping(geometry)})
    print('Done')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: ./inputcsv2shp.py <input_csv_file> <output_shp_file>")
        exit()
    input_csv_file = sys.argv[1]
    output_shp_file = sys.argv[2]
    main(input_csv_file, output_shp_file)
