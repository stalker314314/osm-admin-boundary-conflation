import csv
import sys
import os

import osmapi
import overpy

current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from common import get_polygon_by_cadastre_id, load_level9_features

csv.field_size_limit(sys.maxsize)

# Simple optimization not to get relation id for all settlements
# if number of subareas == number of settlements in municipality
ASSUME_SUBAREA_EQUAL_IF_EQUAL_NUMBER = True


def get_level9_from_osm(overpass_api, level9_ids):
    level9_features = {}
    i = 0
    for level9_id in level9_ids:
        i = i + 1
        print(f'Fetching level9 id: {level9_id}')
        _, osm_relation_name, osm_relation_id, _ = get_polygon_by_cadastre_id(overpass_api, 9, level9_id)
        print('    ({}/{}) Found level 9: {}'.format(i, len(level9_ids), osm_relation_name))
        level9_features[osm_relation_id] = osm_relation_name
    return level9_features


def main(input_csv_file):
    api = osmapi.OsmApi(passwordfile='osm-password',
                        changesetauto=True, changesetautosize=20, changesetautotags=
                        {u"comment": u"OSM admin boundary conflation - adding missing subarea",
                         u"tag": u"mechanical=yes", u"source": u"Import"})
    overpass_api = overpy.Overpass(url='https://lz4.overpass-api.de/api/interpreter')

    level9_features = load_level9_features(input_csv_file)
    level8_ids = set([level9_feature['level8_id'] for level9_feature in level9_features])

    counter = 0
    for level8_id in level8_ids:
        level9_ids = set([level9_feature['level9_id'] for level9_feature in level9_features if level9_feature['level8_id'] == level8_id])
        counter = counter + 1
        _, _, osm_relation_id, _ = get_polygon_by_cadastre_id(overpass_api, 8, level8_id, id_key='ref:RS:opstina')
        if osm_relation_id is None:
            print(f'Skipping level8 with id {level8_id}, not found in OSM')
            continue
        level8_feature = api.RelationGet(osm_relation_id)
        print('Processing level 8 {}'.format(level8_feature['tag']['name']))
        subarea_refs = [m for m in level8_feature['member'] if m['role'] == 'subarea']
        if ASSUME_SUBAREA_EQUAL_IF_EQUAL_NUMBER and len(subarea_refs) == len(level9_ids):
            print(f'({counter}/{len(level8_ids)}) Skipping {level8_feature["tag"]["name"]} '
                  f'object as it seems it already have all ({len(subarea_refs)}) subareas')
            continue
        level9_osm_features_in_this_level8 = get_level9_from_osm(overpass_api, level9_ids)
        anything_changed = False
        # Delete those that do not exist anymore
        for subarea_ref in subarea_refs:
            if subarea_ref['ref'] not in level9_osm_features_in_this_level8:
                input('Removing subarea rel https://www.openstreetmap.org/relation/{} from municipality {}, confirm?'.
                      format(subarea_ref['ref'], level8_feature['tag']['name']))
                level8_feature['member'].remove(subarea_ref)
                anything_changed = True
        # Add those that do not exist
        for level9_osm_id in level9_osm_features_in_this_level8.keys():
            if level9_osm_id not in [m['ref'] for m in subarea_refs]:
                print('Adding settlement {} https://www.openstreetmap.org/relation/{} to municipality {}'.format(
                    level9_osm_features_in_this_level8[level9_osm_id], level9_osm_id, level8_feature['tag']['name']))
                level8_feature['member'].append({'type': 'relation', 'ref': level9_ids, 'role': 'subarea'})
                anything_changed = True
        if anything_changed:
            accepted = False
            while True:
                response = input(
                    '({0}/{1}) Are you sure you want to update level 8 {2} (Y/n/c)?'.format(
                        counter, len(level8_ids), level8_feature['tag']['name']))
                if response == '' or response.lower() == 'y':
                    accepted = True
                if response.lower() == u'c':
                    new_answer = input('Again: ')
                    if new_answer == '':
                        continue
                    else:
                        accepted = True
                break
            if accepted:
                api.RelationUpdate(level8_feature)
                api.flush()


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: ./extras/add_subarea_settlements.py <input_csv_file>")
        exit()
    input_csv_file = sys.argv[1]
    main(input_csv_file)
