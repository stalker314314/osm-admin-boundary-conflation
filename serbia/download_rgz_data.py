"""
Helper script to download opendata from official Serbian cadastre
"""

import requests
from bs4 import BeautifulSoup
import zipfile
import os
import shutil
import time

if not os.path.exists('rgz-password'):
    print('Please create file rgz-password with RGZ credentials in the form of <username>:<password> in it')
    exit()

with open('rgz-password') as f:
    line = f.readline()
username = line.split(":")[0].strip()
password = line.split(":")[1].strip()

s = requests.Session()
# Go to login page
r = s.get('https://opendata.geosrbija.rs/loginopendata')
soup = BeautifulSoup(r.text, 'lxml')
csrf_token = soup.select_one('#csrf_token')['value']

# Login
headers = {}
headers['content-type'] = 'application/x-www-form-urlencoded'
r = s.post('https://opendata.geosrbija.rs/loginopendata', headers=headers, data={'username': username, 'password': password, 'csrf_token': csrf_token})

if not os.path.exists('input'):
    os.mkdir('input')

# Get okrug
r = s.get('https://opendata.geosrbija.rs/okrug?f=csv&user={0}'.format(username), stream=True)
with open('input/okrug.zip', 'wb') as fd:
    for chunk in r.iter_content(chunk_size=1023):
        fd.write(chunk)
with zipfile.ZipFile('input/okrug.zip', 'r') as zip_ref:
    zip_ref.extractall('./input')
os.remove('input/okrug.zip')
time.sleep(5)

# Get grad
r = s.get('https://opendata.geosrbija.rs/gradovi?f=csv&user={0}'.format(username), stream=True)
with open('input/grad.zip', 'wb') as fd:
    for chunk in r.iter_content(chunk_size=1024):
        fd.write(chunk)
with zipfile.ZipFile('input/grad.zip', 'r') as zip_ref:
    zip_ref.extractall('./input')
os.remove('input/grad.zip')
time.sleep(5)

# Get opstina
r = s.get('https://opendata.geosrbija.rs/opstina?f=csv&user={0}'.format(username), stream=True)
with open('input/opstina.zip', 'wb') as fd:
    for chunk in r.iter_content(chunk_size=1024):
        fd.write(chunk)
with zipfile.ZipFile('input/opstina.zip', 'r') as zip_ref:
    zip_ref.extractall('./input')
os.remove('input/opstina.zip')
time.sleep(5)

# Get naselje
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

# Get mesne zajednice
r = s.get('https://opendata.geosrbija.rs/mesna_zajednica?f=csv&user={0}'.format(username), stream=True)
with open('input/mesna_zajednica.zip', 'wb') as fd:
    for chunk in r.iter_content(chunk_size=1024):
        fd.write(chunk)
with zipfile.ZipFile('input/mesna_zajednica.zip', 'r') as zip_ref:
    source = zip_ref.open('tmp/data/ready/mz/mesna_zajednica.csv')
    target = open('./input/mesna_zajednica.csv', "wb")
    with source, target:
        shutil.copyfileobj(source, target)
os.remove('input/mesna_zajednica.zip')
