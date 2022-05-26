#!/bin/bash

set -euo pipefail

# This script downloads and restarts/refresh overpass server with Serbia map. It takes around 10 minutes.

# Details how to install here: https://wiki.openstreetmap.org/wiki/Overpass_API/Installation
# or here: http://overpass-api.de/no_frills.html
# Copy this in overpass server directory
# Create ./build directory inside overpass server directory where you will build it
# Change ./build/bin/rules_loop.sh such that it doesn't do infinite loop, but does areas only once

if [[ $# -ne 1 ]]; then
    echo 'Too many/few arguments, expecting one' >&2
    exit 1
fi

if [ $1 = "yesterday" ]; then
  yesterday=`date -d 'now - 2day' +%y%m%d`
  url="http://download.geofabrik.de/europe/serbia-$yesterday.osm.pbf"
else
  url="http://download.geofabrik.de/europe/serbia-latest.osm.pbf"
fi

echo "Using URL $url"
docker stop overpass_serbia
docker rm overpass_serbia
rm -rf /home/branko/src/prostorne-jedinice-import/overpass_db/*

docker run \
  -e OVERPASS_META=yes \
  -e OVERPASS_MODE=init \
  -e OVERPASS_PLANET_URL=$url \
  -e OVERPASS_RULES_LOAD=10 \
  -e OVERPASS_PLANET_PREPROCESS='mv /db/planet.osm.bz2 /db/planet.osm.pbf && osmium cat -o /db/planet.osm.bz2 /db/planet.osm.pbf && rm /db/planet.osm.pbf' \
  -v /home/branko/src/prostorne-jedinice-import/overpass_db/:/db \
  -p 12345:80 \
  -i \
  --name overpass_serbia wiktorn/overpass-api

docker start overpass_serbia

echo "Waiting for container to boot up"
until [ "`docker inspect -f {{.State.Health.Status}} overpass_serbia`" == "healthy" ]; do
    date
    echo "Still waiting for container to boot up"
    sleep 5
done;

sleep 10

