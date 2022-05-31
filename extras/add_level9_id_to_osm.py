"""
This script semi-automatically adds level9 ids to OSM.
"""

import os
import sys
import time
import yaml

import osmapi
import overpy

current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from common import get_polygon_by_cadastre_id, load_level9_features


def main(config, overpass_api, input_csv_file):
    level9_features = load_level9_features(input_csv_file)

    level9_map = {}  # maps (level8 name, level9 name) -> level9 id
    for level9_feature in level9_features:
        level8_name = level9_feature['level8_name']
        level9_name = level9_feature['level9_name']
        level9_id = level9_feature['level9_id']
        if (level8_name, level9_name) not in level9_map:
            level9_map[(level8_name, level9_name)] = level9_id

    api = osmapi.OsmApi(passwordfile='osm-password',
                        changesetauto=True, changesetautosize=20, changesetautotags=
                        {u"comment": f"Bot - adding missing {config['level9_ref_key']}",
                         u"tag": u"mechanical=yes", u"source": config['changeset_source']})

    for i, level8_name_level9_name in enumerate(level9_map.keys()):
        level8_name = level8_name_level9_name[0]
        level9_name = level8_name_level9_name[1]
        level9_id = level9_map[level8_name_level9_name]
        overpass_level9_polygon, osm_level9_name, osm_relation_id, national_border = \
            get_polygon_by_cadastre_id(overpass_api, 9, level9_id, country=config['country'], id_key=config['level9_ref_key'])

        if overpass_level9_polygon is None:
            print(f'Skipping {level8_name}/{level9_name}')
            continue
        time.sleep(3)
        relation = api.RelationGet(osm_relation_id)
        if relation['tag']['boundary'] != 'administrative' or relation['tag']['type'] != 'boundary':
            print(f'Something fishy with relation {level8_name}/{level9_name}, skipping it:\n {relation["tag"]}')
            continue
        if config['level9_ref_key'] in relation['tag']:
            print(f'Already done {level8_name}/{level9_name}, skipping it')
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
            response = input(f'({i}/{len(level9_map)}) Are you sure you want to add {config["level9_ref_key"]} {level9_id} to {level8_name}/{level9_name} (Y/n/c)?')
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
        relation['tag'][config["level9_ref_key"]] = level9_id
        api.RelationUpdate(relation)
    api.flush()


if __name__ == '__main__':
    with open('config.yml', 'r') as config_yml_file:
        config = yaml.safe_load(config_yml_file)

    overpass_api = overpy.Overpass(url=config['overpass_url'])

    if len(sys.argv) != 2:
        print("Usage: ./extras/add_level9_id_to_osm.py <input_csv_file>")
        exit()
    input_csv_file = sys.argv[1]
    main(config, overpass_api, input_csv_file)