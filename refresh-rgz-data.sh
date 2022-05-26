#!/bin/bash

set -euo pipefail

# Clean everything
rm -f input/*.csv
rm -f output/osm/*.osm
rm -f output/shp/*4326.*
rm -f output/shp/*32634.*

echo "Downloading CSV files from RGZ"
mkdir -p input/
python3 download_rgz_data.py

echo "Creating shapefiles from CSV files"
mkdir -p output
mkdir -p output/shp
mkdir -p output/osm
python3 rpj-to-geometry.py

echo "Convering shapefile geometry from EPSG:32634 to EPSG:4326"
export SHAPE_ENCODING="UTF-8"
ogr2ogr -f "ESRI Shapefile" output/shp/upravni_okrug4326.shp output/shp/upravni_okrug32634.shp -s_srs EPSG:32634 -t_srs EPSG:4326 # Produces upravni_okrug4326.shp
ogr2ogr -f "ESRI Shapefile" output/shp/grad4326.shp output/shp/grad32634.shp -s_srs EPSG:32634 -t_srs EPSG:4326 # Produces grad4326.shp
ogr2ogr -f "ESRI Shapefile" output/shp/opstina4326.shp output/shp/opstina32634.shp -s_srs EPSG:32634 -t_srs EPSG:4326 # Produces opstina4326.shp
ogr2ogr -f "ESRI Shapefile" output/shp/naselje4326.shp output/shp/naselje32634.shp -s_srs EPSG:32634 -t_srs EPSG:4326 # Produces naselje4326.shp
ogr2ogr -f "ESRI Shapefile" output/shp/mesna_zajednica4326.shp output/shp/mesna_zajednica32634.shp -s_srs EPSG:32634 -t_srs EPSG:4326 # Produces mesna_zajednica4326.shp

echo "Creating shapefiles also for all okrug"
for filename in output/shp/okrug-*32634.shp; do
    newname=${filename/32634/4326}
    echo "Creating $newname out of $filename"
    ogr2ogr -f "ESRI Shapefile" $newname $filename -s_srs EPSG:32634 -t_srs EPSG:4326
done

echo "Producing .osm file"
python3 ../ogr2osm/ogr2osm.py -t translation.py -f --split-ways=1 -o output/osm/naselje.osm output/shp/naselje4326.shp # Produces naselje.osm to import in JOSM

echo "Creating .osm files also for all okrug"
for filename in output/shp/okrug-*4326.shp; do
    newname=${filename/-4326.shp/.osm}
    newname=${newname/\/shp/\/osm}
    echo "Creating $newname out of $filename"
    python3 ../ogr2osm/ogr2osm.py -t translation.py -f --split-ways=1 -o $newname $filename
done

# Drop intermediate files
rm -f output/shp/*32634.*

