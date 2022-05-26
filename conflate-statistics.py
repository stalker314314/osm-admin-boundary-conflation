import pickle
import pprint
from collections import OrderedDict
from enum import Enum

from jinja2 import Environment, PackageLoader, FileSystemLoader


class ProcessingState(Enum):
    NO = 1
    CHECKED_POSSIBLE = 2
    CONFLATED = 3
    ERROR_END_POINTS_FAR_APART = 4
    ERROR_GEOMETRY_WRONG = 5
    ERROR_SHARED_WAY_NOT_FOUND = 6
    ERROR_WAY_NOT_FOUND = 7
    ERROR_MULTIPLE_SHARED_WAYS = 8
    ERROR_MULTIPLE_SINGLE_WAY = 9
    ERROR_NODES_WITH_TAGS = 10
    ERROR_NATIONAL_BORDER = 11
    ERROR_UNEXPECTED_TAG = 12
    ERROR_NODE_IN_OTHER_WAYS = 13
    ERROR_NODE_IN_NATIONAL_BORDER = 14
    ERROR_NODE_IN_OTHER_RELATION = 15
    ERROR_NODE_IN_NATIONAL_RELATION = 16
    ERROR_INVALID_SHAPE = 17
    ERROR_CLOSED_SHAPE = 18
    ERROR_OSM_WAY_IS_MORE_COMPLEX = 19
    ERROR_OVERLAPPING_WAYS = 20
    ERROR_TOO_MANY_NODES = 21


errors = {
    ProcessingState.NO: 'Neispitano',
    ProcessingState.CHECKED_POSSIBLE: 'Nema problema da se sredi takvo kakvo je, ali nije još sređeno',
    ProcessingState.CONFLATED: 'Sređeno (odranije ili u ovom prolazu)',
    ProcessingState.ERROR_END_POINTS_FAR_APART: 'Početna ili krajnja tačka puta iz RPJ-a i OSM-a su previše udaljene. Ovo često bude zato što se put između dva naselja u nekom trenutku razdeli. U dodatku za grešku piše i za koliko metara',
    ProcessingState.ERROR_GEOMETRY_WRONG: 'Korisnik je označio da granica iz RPJ-a i iz OSM-a nisu iste. Ova greška ne može da se nađe u ovom izveštaju',
    ProcessingState.ERROR_SHARED_WAY_NOT_FOUND: 'Way koji treba da prođe između dva naselja nije nađen u OSM-u. Ovo ne treba da je često i uglavnom znači da je u OSM-u ta granica pretvorena u jednu tačku ili da se naselja uopšte ne dodiruju. Treba ručno pregledati',
    ProcessingState.ERROR_WAY_NOT_FOUND: 'Way koji treba da dodiruje samo jedno naselje nije nađen. Ovo obično znači da u RPJ-u granica između dva naselja ima "gap", a u OSM-u nema, pa je granica deljena (a ne treba da bude deljena) i put koji pripada samo jednom naselju ne može da se nađe. Treba ga naći i podeliti na dva odvojena way-a',
    ProcessingState.ERROR_MULTIPLE_SHARED_WAYS: 'Između dva naselja je nađeno više od jednog way-a. Verovatno ih treba merge-ovati. U dodatku za greške su navedeni svi takvi way-ovi',
    ProcessingState.ERROR_MULTIPLE_SINGLE_WAY: 'Umesto jednog, nađeno je više way-ova koji treba da pripadaju samo jednom naselju. Verovatno ih treba merge-ovati. U dodatku za greške su navedeni svi takvi way-ovi',
    ProcessingState.ERROR_NODES_WITH_TAGS: 'Neki node-ovi u way-u imaju tagove. Treba ispitati ručno šta su ti tagovi i ukloniti tagove ili razbiti node na dva node-a. U dodatku za greške su navedeni svi takvi node-ovi',
    ProcessingState.ERROR_NATIONAL_BORDER: 'Way je državna granica i ne sme da se pomera. Ovo je greška koja nikako ne može da se "popravi" i ostaje ovako zauvek.',
    ProcessingState.ERROR_UNEXPECTED_TAG: 'Way ima tag koji nije očekivani. U dodatku za greške je upisano koji je to tag',
    ProcessingState.ERROR_NODE_IN_OTHER_WAYS: 'Way ima node koji je deljen sa drugim way-ovima koji nisu "obične" granice. U dodatku za greške je upisano koji je to dodatni way koji je spojen sa ovim. Nekad ih treba odvojiti, a nekad je to veza sa granicom koja prosto nije tagovana.',
    ProcessingState.ERROR_NODE_IN_NATIONAL_BORDER: 'Way ima node koji je deljen sa državnom granicom i ne sme da se pomera. U dodatku za greške je upisani koji je to way',
    ProcessingState.ERROR_NODE_IN_OTHER_RELATION: 'Way ima node koji je deo nekog drugog relation-a koji nije "obična" granica i ne sme da se pomera',
    ProcessingState.ERROR_NODE_IN_NATIONAL_RELATION: 'Way ima node koji je deo relation-a državne granice i ne sme da se pomera',
    ProcessingState.ERROR_INVALID_SHAPE: 'Neispravan oblik pročitan iz .osm fajla',
    ProcessingState.ERROR_CLOSED_SHAPE: 'Way je prsten (zatvoren) i ovaj program ne podržava pomeranje takvog puta još. Treba ga ručno pomeriti',
    ProcessingState.ERROR_OSM_WAY_IS_MORE_COMPLEX: 'Way u OSM-u ima više tačaka od RPJ way-a i program još to ne podržava. Treba ga ručno pomeriti',
    ProcessingState.ERROR_OVERLAPPING_WAYS: 'Way ima vezu u RPJ-u sa više od 2 naselja, što jedino može da znači da se neka naselja preklapaju. Mora da se vidi sa RGZ-om i ručno da se ispegla',
    ProcessingState.ERROR_TOO_MANY_NODES: 'Way u RGZ-u ima više od 2000 tačaka, a OSM ima ograničenje da way može da ima samo do 2000 tačaka. Treba uprostiti way ručno'
}

errors = OrderedDict(sorted(errors.items(), key=lambda x: x[0].value))


def main():
    env = Environment(loader=FileSystemLoader(searchpath='./templates'))
    template = env.get_template('index_template.html')

    with open('conflate-progress.pickle', 'rb') as p:
        source_data = pickle.load(p)
    total_ways = len(source_data['ways'])
    processed_ways = len([w for w in source_data['ways'].values() if w['processed'] != ProcessingState.NO])
    ways_with_osm_ways_found = len([w for w in source_data['ways'].values() if w['osm_way'] is not None])
    count_per_error = {}
    for w in source_data['ways'].values():
        if w['processed'] not in count_per_error:
            count_per_error[w['processed']] = 0
        count_per_error[w['processed']] += 1
        if w['error_context'] is None:
            w['error_context'] = ''
        if w['processed'] in (ProcessingState.ERROR_MULTIPLE_SHARED_WAYS, ProcessingState.ERROR_MULTIPLE_SINGLE_WAY,
                              ProcessingState.ERROR_NODE_IN_OTHER_WAYS, ProcessingState.ERROR_NODE_IN_NATIONAL_BORDER):
            ways = w['error_context'].split(',')
            w['error_context'] = ','.join(['<a href="https://www.openstreetmap.org/way/{0}" target="_blank">{0}</a>'.format(w) for w in ways]).replace('"', '\\"')
        elif w['processed'] in (ProcessingState.ERROR_NODES_WITH_TAGS,):
            nodes = w['error_context'].split(',')
            w['error_context'] = ','.join(['<a href="https://www.openstreetmap.org/node/{0}" target="_blank">{0}</a>'.format(n) for n in nodes]).replace('"', '\\"')
        elif w['processed'] in (ProcessingState.ERROR_NODE_IN_OTHER_RELATION,):
            relations = w['error_context'].split(',')
            w['error_context'] = ','.join(['<a href="https://www.openstreetmap.org/relation/{0}" target="_blank">{0}</a>'.format(r) for r in relations]).replace('"', '\\"')
        elif w['processed'] in (ProcessingState.ERROR_END_POINTS_FAR_APART,):
            w['error_context'] = '{:.2f}m'.format(float(w['error_context']))
    print('Total ways: {0}'.format(total_ways))
    print('Processed ways: {0}'.format(processed_ways))
    print('Ways with OSM way found: {0}'.format(ways_with_osm_ways_found))
    pp = pprint.PrettyPrinter(indent=4)
    print('Count per error:\n{0}'.format(pp.pformat(count_per_error)))
    count_per_error = OrderedDict(sorted(count_per_error.items(), key=lambda x: x[1], reverse=True))

    source_data = {k: source_data['ways'][k] for k in list(source_data['ways'])[0:-1]}
    output = template.render(total_ways=total_ways, processed_ways=processed_ways, errors=errors,
                             count_per_error=count_per_error, ways_with_osm_ways_found=ways_with_osm_ways_found,
                             source_data=source_data)
    with open('output/index.html', 'w', encoding='utf-8') as fh:
        fh.write(output)


if __name__ == '__main__':
    main()
