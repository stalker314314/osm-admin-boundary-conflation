"""
This script semi-automatically adds level8 ids to OSM.
"""

import os
import sys
import time

import osmapi
import overpy
import yaml

current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from common import get_polygon_by_cadastre_id, load_level9_features


def main(config, overpass_api, input_csv_file):
    level9_features = load_level9_features(input_csv_file)

    level8_map = {}  # maps (level6 name, level8 name) -> level8 id
    for level9_feature in level9_features:
        level6_name = level9_feature['level6_name']
        level8_name = level9_feature['level8_name']
        level8_id = level9_feature['level8_id']
        if (level6_name, level8_name) not in level8_map:
            level8_map[(level6_name, level8_name)] = level8_id

    api = osmapi.OsmApi(passwordfile='osm-password',
                        changesetauto=True, changesetautosize=20, changesetautotags=
                        {u"comment": u"Serbian lint bot - adding missing {}".format(config['level8_ref_key']),
                         u"tag": u"mechanical=yes", u"source": config['changeset_source']})
    for i, level6_name_level8_name in enumerate(level8_map.keys()):
        level6_name = level6_name_level8_name[0]
        level8_name = level6_name_level8_name[1]
        level8_id = level8_map[level6_name_level8_name]
        overpass_level8_polygon, osm_level8_name, osm_relation_id, national_border = \
            get_polygon_by_cadastre_id(overpass_api, 8, level8_id, country=config['country'], id_key=config['level8_ref_key'])

        if overpass_level8_polygon is None:
            print(f'Skipping {level6_name}/{level8_name}')
            continue
        time.sleep(1)
        relation = api.RelationGet(osm_relation_id)
        if relation['tag']['boundary'] != 'administrative' or relation['tag']['type'] != 'boundary':
            print(f'Something fishy with relation {level6_name}/{level8_name}, skipping it:\n {relation["tag"]}')
            continue
        if 'ref:RS:opstina' in relation['tag']:
            print(f'Already done {level6_name}/{level8_name}, skipping it')
            continue

        for k, v in relation['tag'].items():
            if k == 'metadata':
                continue
            if k.startswith('tag_') or k.startswith('val_') or k == 'boundary' or k == 'type':
                continue
            print(f'{k}: {v}')
        print(f'https://www.openstreetmap.org/relation/{relation["id"]}')
        accepted = False
        while True:
            response = input(f'({i}/{len(level8_map)}) Are you sure you want to add {config["level8_ref_key"]} {level8_id} to {level6_name}/{level8_name} (Y/n/c)?')
            if response == '' or response.lower() == 'y':
                accepted = True
            if response.lower() == u'c':
                new_answer = input('Again: ')
                if new_answer == '':
                    continue
                else:
                    accepted = True
            break
        if not accepted:
            continue
        relation['tag'][config["level8_ref_key"]] = level8_id
        api.RelationUpdate(relation)
    api.flush()


if __name__ == '__main__':
    with open('config.yml', 'r') as config_yml_file:
        config = yaml.safe_load(config_yml_file)

    overpass_api = overpy.Overpass(url=config['overpass_url'])

    if len(sys.argv) != 2:
        print("Usage: ./extras/add_level8_id_to_osm.py <input_csv_file>")
        exit()
    input_csv_file = sys.argv[1]
    main(config, overpass_api, input_csv_file)
