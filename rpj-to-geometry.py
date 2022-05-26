import sys
import csv

from common import get_municipality_district, get_settlement_municipality

from shapely.geometry import mapping
from shapely.wkt import loads
import fiona
import fiona.crs

schema = {
    'geometry': ['Polygon', 'MultiPolygon'],
    'properties': {
        'naselje' : 'str',
        'opstina': 'str',
        'okrug': 'str',
        'grad': 'str',
        'grad_mb': 'str',
        'naselje_mb': 'str',
        'opstina_mb': 'str',
        'okrug_sfr': 'str',
        'mz': 'str',
        'mz_mb': 'str'
    }
}

csv.field_size_limit(sys.maxsize)


def csv2shp(csv_filename, shp_filename, filter_district=None):
    settlement_municipality = get_settlement_municipality()
    municipality_district = get_municipality_district()

    print('Producing {0} from {1}'.format(shp_filename, csv_filename))
    with open(csv_filename) as csvfile:
        with fiona.collection(shp_filename, "w", "ESRI Shapefile", schema, encoding='utf-8') as output:
            reader = csv.DictReader(csvfile)
            for i, row in enumerate(reader):
                # Filter if possible
                if filter_district is not None:
                    if 'naselje_maticni_broj' in row:
                        municipality = settlement_municipality[int(row['naselje_maticni_broj'])]
                        district = municipality_district[municipality]
                        if district != filter_district:
                            continue
                    elif 'opstina_maticni_broj' in row:
                        district = municipality_district[int(row['opstina_maticni_broj'])]
                        if district != filter_district:
                            continue
                    elif 'okrug_sifra' in row:
                        district = int(row['okrug_sifra'])
                        if district != filter_district:
                            continue

                geometry = row['wkt']
                geometry = loads(geometry)
                output.write({
                    'properties': {
                        'naselje': row['naselje_ime'] if 'naselje_ime' in row else '',
                        'opstina': row['opstina_ime'] if 'opstina_ime' in row else '',
                        'okrug': row['okrug_ime'] if 'okrug_ime' in row else '',
                        'grad': row['grad_ime'] if 'grad_ime' in row else '',
                        'grad_mb': row['grad_maticni_broj'] if 'grad_maticni_broj' in row else '',
                        'naselje_mb': row['naselje_maticni_broj'] if 'naselje_maticni_broj' in row else '',
                        'opstina_mb': row['opstina_maticni_broj'] if 'opstina_maticni_broj' in row else '',
                        'okrug_sfr': row['okrug_sifra'] if 'okrug_sifra' in row else '',
                        'mz_mb': row['mz_maticni_broj'] if 'mz_maticni_broj' in row else '',
                        'mz': row['mz_ime'] if 'mz_ime' in row else ''},
                    'geometry': mapping(geometry)})


if __name__ == '__main__':
    csv2shp('input/okrug.csv', 'output/shp/upravni_okrug32634.shp')
    csv2shp('input/gradovi.csv', 'output/shp/grad32634.shp')
    csv2shp('input/opstina.csv', 'output/shp/opstina32634.shp')
    csv2shp('input/naselje.csv', 'output/shp/naselje32634.shp')
    csv2shp('input/mesna_zajednica.csv', 'output/shp/mesna_zajednica32634.shp')

    with open('input/okrug.csv') as upravni_okrug_csv:
        reader = csv.DictReader(upravni_okrug_csv)
        for row in reader:
            district = int(row['okrug_sifra'])
            rap_sifra = int(row['rap_sifra'])
            if rap_sifra == 9:  # Skip Kosovo
                continue
            district_ime_latin = row['okrug_imel'].replace(' UPRAVNI', '').replace(' OKRUG', '')
            district_ime_latin = district_ime_latin.lower().replace(' ', '_')
            district_ime_latin = district_ime_latin.replace('č', 'c').replace('š', 's').replace('ć', 'c'). \
                replace('ž', 'z').replace('đ', 'dj')
            csv2shp('input/naselje.csv', 'output/shp/okrug-{0}-32634.shp'.format(district_ime_latin), district)
