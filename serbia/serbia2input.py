"""
This script generate input files in proper CSV format
"""

import csv
import os
import shutil
import sys
import time
import zipfile

import pyproj
import requests
from bs4 import BeautifulSoup
from shapely import wkt
from shapely.ops import transform

csv.field_size_limit(sys.maxsize)

wgs84 = pyproj.CRS('EPSG:4326')
utm = pyproj.CRS('EPSG:32634')
project = pyproj.Transformer.from_crs(utm, wgs84, always_xy=True).transform


def reproject_wkt(wkt_text):
    wkt_obj = wkt.loads(wkt_text)
    return transform(project, wkt_obj)


def download_cadastre_data(username, password):
    """
    Logs in to opendata.geosrbija.rs and downloads zips with data.
    It will clean zip files and leave input/naselje.csv which contains level9 data.
    """
    s = requests.Session()
    # Go to login page
    r = s.get('https://opendata.geosrbija.rs/loginopendata')
    soup = BeautifulSoup(r.text, 'lxml')
    csrf_token = soup.select_one('#csrf_token')['value']

    # Login
    headers = {}
    headers['content-type'] = 'application/x-www-form-urlencoded'
    r = s.post('https://opendata.geosrbija.rs/loginopendata', headers=headers,
               data={'username': username, 'password': password, 'csrf_token': csrf_token})

    if not os.path.exists('input'):
        os.mkdir('input')

    # Get okrug
    print('Downloading level6 data')
    r = s.get('https://opendata.geosrbija.rs/okrug?f=csv&user={0}'.format(username), stream=True)
    with open('input/okrug.zip', 'wb') as fd:
        for chunk in r.iter_content(chunk_size=1023):
            fd.write(chunk)
    with zipfile.ZipFile('input/okrug.zip', 'r') as zip_ref:
        zip_ref.extractall('./input')
    os.remove('input/okrug.zip')
    time.sleep(5)

    # Get grad
    print('Downloading level7 data')
    r = s.get('https://opendata.geosrbija.rs/gradovi?f=csv&user={0}'.format(username), stream=True)
    with open('input/grad.zip', 'wb') as fd:
        for chunk in r.iter_content(chunk_size=1024):
            fd.write(chunk)
    with zipfile.ZipFile('input/grad.zip', 'r') as zip_ref:
        zip_ref.extractall('./input')
    os.remove('input/grad.zip')
    time.sleep(5)

    # Get opstina
    print('Downloading level8 data')
    r = s.get('https://opendata.geosrbija.rs/opstina?f=csv&user={0}'.format(username), stream=True)
    with open('input/opstina.zip', 'wb') as fd:
        for chunk in r.iter_content(chunk_size=1024):
            fd.write(chunk)
    with zipfile.ZipFile('input/opstina.zip', 'r') as zip_ref:
        zip_ref.extractall('./input')
    os.remove('input/opstina.zip')
    time.sleep(5)

    # Get naselje
    print('Downloading level9 data')
    r = s.get('https://opendata.geosrbija.rs/naselje?f=csv&user={0}'.format(username), stream=True)
    with open('input/naselje.zip', 'wb') as fd:
        for chunk in r.iter_content(chunk_size=1024):
            fd.write(chunk)
    with zipfile.ZipFile('input/naselje.zip', 'r') as zip_ref:
        source = zip_ref.open('tmp/data/ready/naselja/naselje.csv')
        target = open('./input/naselje.csv', "wb")
        with source, target:
            shutil.copyfileobj(source, target)
    os.remove('input/naselje.zip')
    time.sleep(5)


def load_level9_features():
    level9_features = []
    with open('input/naselje.csv') as level9_csv:
        reader = csv.DictReader(level9_csv)
        for row in reader:
            level9_features.append({
                'level9_name': row['naselje_ime'],
                'level9_id': row['naselje_maticni_broj'],
                'level8_id': row['opstina_maticni_broj'],
                'wkt': reproject_wkt(row['wkt'])
            })
    return level9_features


def write_level9_features(level9, output_csv_filename):
    with open(output_csv_filename, 'w') as out_csv:
        writer = csv.DictWriter(out_csv, fieldnames=['level9_id', 'level9_name', 'level8_id', 'level8_name', 'level7_id', 'level7_name', 'level6_id', 'level6_name', 'wkt'])

        writer.writeheader()
        for data in level9:
            writer.writerow(data)


# Map of level8_id => (level8_name, level6_id)
def load_level8_features() -> dict:
    level8_features = {}
    with open('input/opstina.csv') as level8_csv:
        reader = csv.DictReader(level8_csv)
        for row in reader:
            level8_id = row['opstina_maticni_broj']
            level8_name = row['opstina_ime']
            level6_id = row['okrug_sifra']
            level8_features[level8_id] = (level8_name, level6_id)
    return level8_features


# Map of level6_id => level6_name
def load_level6_features() -> dict:
    level6_features = {}
    with open('input/okrug.csv') as level6_csv:
        reader = csv.DictReader(level6_csv)
        for row in reader:
            level6_id = row['okrug_sifra']
            level6_name = row['okrug_ime']
            level6_features[level6_id] = level6_name
    return level6_features


def main(output_csv_file: str):
    if not os.path.exists('rgz-password'):
        print('Please create file rgz-password with RGZ credentials in the form of <username>:<password> in it')
        exit()
    with open('rgz-password') as f:
        line = f.readline()
    username = line.split(":")[0].strip()
    password = line.split(":")[1].strip()
    download_cadastre_data(username, password)

    print('Merging level9 data')
    level9_features = load_level9_features()
    level8_features = load_level8_features()
    level6_features = load_level6_features()
    for level9_feature in level9_features:
        level9_feature['level8_name'] = level8_features[level9_feature['level8_id']][0]
        level9_feature['level7_id'] = None
        level9_feature['level7_name'] = None
        level9_feature['level6_id'] = level8_features[level9_feature['level8_id']][1]
        level9_feature['level6_name'] = level6_features[level9_feature['level6_id']]
    print(f'Writing level9 data to {output_csv_file}')
    write_level9_features(level9_features, output_csv_file)
    print('Done')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: ./serbia2input.py <output_csv_file>")
        exit()
    output_csv_file = sys.argv[1]
    main(output_csv_file)
