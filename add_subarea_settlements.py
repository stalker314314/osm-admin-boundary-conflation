import csv
import sys

import osmapi
import overpy

from common import get_polygon_by_mb, get_municipality_settlements

csv.field_size_limit(sys.maxsize)

# Simple optimization not to get relation id for all settlements
# if number of subareas == number of settlements in municipality
ASSUME_SUBAREA_EQUAL_IF_EQUAL_NUMBER = True


def get_settlements(overpass_api, settlement_mbs):
    settlements = {}
    i = 0
    for settlement_mb in settlement_mbs:
        i = i + 1
        print('Fetching settlement {}'.format(settlement_mb))
        _, osm_relation_name, osm_relation_id, _ = get_polygon_by_mb(overpass_api, 9, settlement_mb)
        print('    ({}/{}) Found settlement {}'.format(i, len(settlement_mbs), osm_relation_name))
        settlements[osm_relation_id] = osm_relation_name
    return settlements


def main():
    api = osmapi.OsmApi(passwordfile='osm-password',
                        changesetauto=True, changesetautosize=20, changesetautotags=
                        {u"comment": u"Serbian lint bot - adding missing subarea "
                                     "(https://lists.openstreetmap.org/pipermail/imports/2020-January/006149.html). ",
                         u"tag": u"mechanical=yes", u"source": u"RGZ_Import"})
    overpass_api = overpy.Overpass(url='https://lz4.overpass-api.de/api/interpreter')


    municipality_settlements = get_municipality_settlements()

    counter = 0
    for municipality_mb, settlement_mbs in municipality_settlements.items():
        counter = counter + 1
        _, _, osm_relation_id, _ = get_polygon_by_mb(overpass_api, 8, municipality_mb)
        if osm_relation_id is None:
            print('Skipping municipality with maticni broj {}, not found in OSM'.format(municipality_mb))
            continue
        municipality = api.RelationGet(osm_relation_id)
        print('Processing municipality {}'.format(municipality['tag']['name']))
        subarea_refs = [m for m in municipality['member'] if m['role'] == 'subarea']
        if ASSUME_SUBAREA_EQUAL_IF_EQUAL_NUMBER and len(subarea_refs) == len(settlement_mbs):
            print('({}/{}) Skipping this municipality as it seems it already have all subareas'.format(
                counter, len(municipality_settlements)))
            continue
        settlements = get_settlements(overpass_api, settlement_mbs)
        anything_changed = False
        # Delete those that do not exist anymore
        for subarea_ref in subarea_refs:
            if subarea_ref['ref'] not in settlements:
                input('Removing subarea rel https://www.openstreetmap.org/relation/{} from municipality {}, confirm?'.
                      format(subarea_ref['ref'], municipality['tag']['name']))
                municipality['member'].remove(subarea_ref)
                anything_changed = True
        # Add those that do not exist
        for settlements_id in settlements.keys():
            if settlements_id not in [m['ref'] for m in subarea_refs]:
                print('Adding settlement {} https://www.openstreetmap.org/relation/{} to municipality {}'.format(
                    settlements[settlements_id], settlements_id, municipality['tag']['name']))
                municipality['member'].append({'type': 'relation', 'ref': settlements_id, 'role': 'subarea'})
                anything_changed = True
        if anything_changed:
            accepted = False
            while True:
                response = input(
                    '({0}/{1}) Are you sure you want to update municipality {2} (Y/n/c)?'.format(
                        counter, len(municipality_settlements), municipality['tag']['name']))
                if response == '' or response.lower() == 'y' or response.lower() == u'з':
                    accepted = True
                if response.lower() == u'c' or response.lower() == u'ц':
                    new_answer = input('Again: ')
                    if new_answer == '':
                        continue
                    else:
                        accepted = True
                break
            if accepted:
                api.RelationUpdate(municipality)
                api.flush()


if __name__ == '__main__':
    main()