#!/bin/bash

set -euo pipefail


if [[ $# -ne 2 ]]; then
    echo 'Too many/few arguments, expecting two, call it with: ./shp2osm.sh <input-shp> <output-osm>' >&2
    exit 1
fi

inputShp=$1
outputOsm=$2

echo "Converting input shp '$1' to output OSM '$2'"

if [[ ! -d "ogr2osm/" ]]
then
    # TODO: switch to new ogr2osm version
    echo "ogr2osm does not exists, will git clone it now"
    git clone https://github.com/pnorman/ogr2osm.git
fi

python3 ogr2osm/ogr2osm.py -t translation.py -f --split-ways=1 -o $outputOsm $inputShp
