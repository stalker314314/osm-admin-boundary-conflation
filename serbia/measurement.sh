#!/bin/bash

# Main script that can be run daily (in cron) to find differences and report result.
# Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID if you want to get updates over Telegram.
# You can use it for base for your region.

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
echo "Found $found_files files"

if [[ $found_files -eq "0" ]]; then
  echo "No shp files, recreating them from scratch (losing diff from Serbia cadastre from yesterday)"
  ./refresh-cadastre-data.sh
fi

echo "Setting up yesterday data"
../refresh-osm-data.sh europe serbia yesterday ../overpass_db

# Do baseline measurement
python3 measure_quality.py
mv output/level9.csv output/level9-baseline-$yesterday.csv
sort -o output/level9-baseline-$yesterday.csv output/level9-baseline-$yesterday.csv

# Refresh cadastre and do measurements now
echo "Refreshing cadastre data"
python3 serbia2input.py input/all.csv
python3 ../inputcsv2shp.py input/all.csv output/shp/all.shp
../shp2osm.sh output/shp/all.shp output/osm/all.osm
sleep 10

echo "Measuring settlements after cadastre is refreshed"
python3 measure_quality.py
mv output/level9.csv output/level9-cadastre-$currentdate.csv
sort -o output/level9-cadastre-$currentdate.csv output/level9-cadastre-$currentdate.csv
diff -u output/level9-baseline-$yesterday.csv output/level9-cadastre-$currentdate.csv > output/level9-cadastre-$currentdate.diff || true
python3 send_notification.py cadastre level9 output/level9-baseline-$yesterday.csv output/level9-cadastre-$currentdate.csv

# Refresh OSM and do measurements now
echo "Refreshing OSM data"
./refresh-osm-data.sh europe serbia today
sleep 10

echo "Measuring settlements after OSM is refreshed"
python3 measure_quality.py
mv output/level9.csv output/level9-osm-$currentdate.csv
sort -o output/level9-osm-$currentdate.csv output/level9-osm-$currentdate.csv
diff -u output/level9-baseline-$yesterday.csv output/level9-osm-$currentdate.csv > output/level9-osm-$currentdate.diff || true
python3 send_notification.py osm level9 output/level9-baseline-$yesterday.csv output/level9-osm-$currentdate.csv
cp output/level9-osm-$currentdate.csv output/level9-baseline-$currentdate.csv

echo "Measurement done for $currentdate"
sleep 10
