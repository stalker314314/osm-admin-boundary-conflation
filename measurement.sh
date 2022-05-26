#!/bin/bash

set -euo pipefail

date

currentdate=`date +%Y%m%d`
yesterday=`date -d 'now - 1day' +%Y%m%d`

echo "Current date is $currentdate, yesterday is $yesterday"

# Check if there is overpass set up at all
response=$(curl --write-out "%{http_code}\n" --silent --output /dev/null "http://localhost:12345/api/interpreter?data=%3Cprint%20mode=%22body%22/%3E" || true)
overpass_works=0
if [[ $response == "200" ]]; then
  echo "Overpass works"
  overpass_works=1
else
  echo "Overpass is not working"
fi

shopt -s nullglob
shp_files=( ./output/shp/*.shp )
found_files=( ${#shp_files[@]} )
echo "Found $found_files"

if [[ $found_files -eq "0" ]]; then
  echo "No shp files, recreating them from scratch (losing diff from RGZ from yesterday)"
  ./refresh-rgz-data.sh
fi

echo "Setting up yesterday data"
./refresh-osm-data.sh yesterday

# Do baseline measurement
rm -f output/opstine.csv
python3 measure_quality_opstine.py
mv output/opstine.csv output/opstine-baseline-$yesterday.csv
sort -o output/opstine-baseline-$yesterday.csv output/opstine-baseline-$yesterday.csv

python3 measure_quality_naselja.py
mv output/naselja.csv output/naselja-baseline-$yesterday.csv
sort -o output/naselja-baseline-$yesterday.csv output/naselja-baseline-$yesterday.csv

# Refresh RGZ and do measurements now
echo "Refreshing RGZ data"
./refresh-rgz-data.sh
sleep 10

echo "Measuring opstine after RGZ is refreshed"
python3 measure_quality_opstine.py
mv output/opstine.csv output/opstine-rgz-$currentdate.csv
sort -o output/opstine-rgz-$currentdate.csv output/opstine-rgz-$currentdate.csv
diff -u output/opstine-baseline-$yesterday.csv output/opstine-rgz-$currentdate.csv > output/opstine-rgz-$currentdate.diff || true
python3 send_notification.py rgz opstina output/opstine-baseline-$yesterday.csv output/opstine-rgz-$currentdate.csv

echo "Measuring naselja after RGZ is refreshed"
python3 measure_quality_naselja.py
mv output/naselja.csv output/naselja-rgz-$currentdate.csv
sort -o output/naselja-rgz-$currentdate.csv output/naselja-rgz-$currentdate.csv
diff -u output/naselja-baseline-$yesterday.csv output/naselja-rgz-$currentdate.csv > output/naselja-rgz-$currentdate.diff || true
python3 send_notification.py rgz naselje output/naselja-baseline-$yesterday.csv output/naselja-rgz-$currentdate.csv

# Refresh OSM and do measurements now
echo "Refreshing OSM data"
./refresh-osm-data.sh today
sleep 10

echo "Measuring opstine after OSM is refreshed"
python3 measure_quality_opstine.py
mv output/opstine.csv output/opstine-osm-$currentdate.csv
sort -o output/opstine-osm-$currentdate.csv output/opstine-osm-$currentdate.csv
diff -u output/opstine-baseline-$yesterday.csv output/opstine-osm-$currentdate.csv > output/opstine-osm-$currentdate.diff || true
python3 send_notification.py osm opstina output/opstine-baseline-$yesterday.csv output/opstine-osm-$currentdate.csv
cp output/opstine-osm-$currentdate.csv output/opstine-baseline-$currentdate.csv

echo "Measuring naselja after OSM is refreshed"
python3 measure_quality_naselja.py
mv output/naselja.csv output/naselja-osm-$currentdate.csv
sort -o output/naselja-osm-$currentdate.csv output/naselja-osm-$currentdate.csv
diff -u output/naselja-baseline-$yesterday.csv output/naselja-osm-$currentdate.csv > output/naselja-osm-$currentdate.diff || true
python3 send_notification.py osm naselje output/naselja-baseline-$yesterday.csv output/naselja-osm-$currentdate.csv
cp output/naselja-osm-$currentdate.csv output/naselja-baseline-$currentdate.csv

echo "Measurement done for $currentdate"
sleep 10
