import sys
import csv
import osmapi
import time

csv.field_size_limit(sys.maxsize)


def main():
    # Load naselja
    settlements = {}  # maps (district, municipality) -> maticni broj
    with open('naselje.csv') as naselja_csv:
        reader = csv.DictReader(naselja_csv)
        for row in reader:
            settlements[(row['opstina_ime'], row['naselje_ime'])] = row['naselje_maticni_broj']

    # Load saved state obtained in measure_quality.py
    progress_file = 'output/measure_quality_naselja.csv'
    results = []
    with open(progress_file) as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            results.append(
                {'district': row['district'],
                 'municipality': row['municipality'],
                 'relation_id': row['relation_id'],
                 'area_diff': float(row['area_diff'])})

    api = osmapi.OsmApi(passwordfile='osm-password',
                        changesetauto=True, changesetautosize=20, changesetautotags=
                        {u"comment": u"Serbian lint bot - adding missing ref:RS:naselje "
                                     "(https://lists.openstreetmap.org/pipermail/imports/2020-January/006149.html). ",
                         u"tag": u"mechanical=yes", u"source": u"RGZ_Import"})
    for i, result in enumerate(results):
        maticni_broj = settlements[(result['district'], result['municipality'])]

        if result['relation_id'] == -1:
            print('Skipping {0}/{1}'.format(result['district'], result['municipality']))
            continue
        if result['area_diff'] < 0.9:
            print('Too low area diff, skipping {0}/{1}'.format(result['district'], result['municipality']))
            continue
        time.sleep(3)
        relation = api.RelationGet(result['relation_id'])
        if relation['tag']['boundary'] != 'administrative' or relation['tag']['type'] != 'boundary':
            print('Something fishy with relation {0}/{1}, skipping it:\n {2}'.format(result['district'], result['municipality'], relation['tag']))
            continue
        if 'ref:RS:naselje' in relation['tag']:
            print('Already done {0}/{1}, skipping it'.format(result['district'], result['municipality']))
            continue

        for k, v in relation['tag'].items():
            if k == 'metadata':
                continue
            if k.startswith('tag_') or k.startswith('val_') or k == 'boundary' or k == 'type':
                continue
            print('{0}: {1}'.format(k, v))
        print('https://www.openstreetmap.org/relation/{0}'.format(relation['id']))
        accepted = False
        while True:
            response = input('({0}/{1}) Are you sure you want to add ref:RS:naselje {2} to {3}/{4} (Y/n/c)?'.format(
                i, len(results), maticni_broj, result['district'], result['municipality']))
            if response == '' or response.lower() == 'y' or response.lower() == u'з':
                accepted = True
            if response.lower() == u'c' or response.lower() == u'ц':
                new_answer = input('Again: ')
                if new_answer == '':
                    continue
                else:
                    accepted = True
            break
        if not accepted:
            continue
        relation['tag']['ref:RS:naselje'] = maticni_broj
        api.RelationUpdate(relation)
    api.flush()


if __name__ == '__main__':
    main()