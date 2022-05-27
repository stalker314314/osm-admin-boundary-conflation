#!/bin/bash

set -euo pipefail

# This script downloads and restarts/refresh overpass server with map of some country. It takes around 10 minutes for Serbia, YMMV.

# Details how to install here: https://wiki.openstreetmap.org/wiki/Overpass_API/Installation
# or here: http://overpass-api.de/no_frills.html
# Copy this in overpass server directory
# Create ./build directory inside overpass server directory where you will build it
# Change ./build/bin/rules_loop.sh such that it doesn't do infinite loop, but does areas only once

if [[ $# -ne 4 ]]; then
    echo 'Too many/few arguments, expecting two, call it with: ./refresh-osm-data.sh <continent> <country> <today|yesterday> <overpass_db_dir>' >&2
    exit 1
fi

continent=$1
region=$2
rel_overpass_db=$4

if [ $3 = "yesterday" ]; then
  yesterday=`date -d 'now - 2day' +%y%m%d` # Two days as geofabrik releases data in early morning UTC time
  url="http://download.geofabrik.de/$continent/$region-$yesterday.osm.pbf"
else
  url="http://download.geofabrik.de/$continent/$region-latest.osm.pbf"
fi

echo "Using URL $url"

if [ ! -z "`docker ps | grep overpass_$region`" ]; then
  docker stop overpass_$region
fi
if [ ! -z "`docker ps -a | grep overpass_$region`" ]; then
  docker rm overpass_$region
fi

absolute_overpass_dir=`realpath $rel_overpass_db`
echo "Absolute path to overpass dir: $absolute_overpass_dir"
rm -rf $absolute_overpass_dir/*

docker run \
  -e OVERPASS_META=yes \
  -e OVERPASS_MODE=init \
  -e OVERPASS_PLANET_URL=$url \
  -e OVERPASS_RULES_LOAD=10 \
  -e OVERPASS_PLANET_PREPROCESS='mv /db/planet.osm.bz2 /db/planet.osm.pbf && osmium cat -o /db/planet.osm.bz2 /db/planet.osm.pbf && rm /db/planet.osm.pbf' \
  -v $absolute_overpass_dir/:/db \
  -p 12345:80 \
  -i \
  --name overpass_$region wiktorn/overpass-api

docker start overpass_$region

echo "Waiting for container to boot up"
until [ "`docker inspect -f {{.State.Health.Status}} overpass_$region`" == "healthy" ]; do
    date
    echo "Still waiting for container to boot up"
    sleep 5
done;

sleep 10
