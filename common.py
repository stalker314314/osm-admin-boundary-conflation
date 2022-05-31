import csv
import functools
import http.client
import socket
import sys
import time
import urllib.error
from collections import OrderedDict

import shapely.geometry as geometry
from overpy.exception import OverpassTooManyRequests, OverpassGatewayTimeout, OverpassUnknownContentType
from shapely.ops import linemerge, unary_union, polygonize

csv.field_size_limit(sys.maxsize)


def retry_on_error(timeout_in_seconds=60):
    def decorate(func):
        def call(*args, **kwargs):
            retries = 5
            while retries > 0:
                try:
                    result = func(*args, **kwargs)
                except (ConnectionRefusedError, ConnectionResetError,
                        OverpassTooManyRequests, OverpassGatewayTimeout, OverpassUnknownContentType,
                        socket.timeout, urllib.error.URLError, http.client.RemoteDisconnected):
                    retries = retries - 1
                    print('Connection refused, retrying')
                    time.sleep(timeout_in_seconds)
                    continue
                return result
            raise Exception('Exhausted retries for connection refused, quitting')
        return call
    return decorate


def create_geometry_from_osm_response(relation, response):
    # Try to build shapely polygon out of this data
    outer_ways = [way.ref for way in relation.members if way.role == 'outer']
    inner_ways = [way.ref for way in relation.members if way.role == 'inner']
    lss = []
    for ii_w, way in enumerate(response.ways):
        if way.id not in outer_ways:
            continue
        ls_coords = []
        for node in way.nodes:
            ls_coords.append((node.lon, node.lat))
        lss.append(geometry.LineString(ls_coords))

    merged = linemerge([*lss])
    borders = unary_union(merged)
    polygons = list(polygonize(borders))
    print('polygons found {0}'.format(len(polygons)))
    polygon = functools.reduce(lambda p,x: p.union(x), polygons[1:], polygons[0])
    if len(inner_ways) > 0:
        lss_inner = []
        for ii_w, way in enumerate(response.ways):
            if way.id not in inner_ways:
                continue
            ls_coords = []
            for node in way.nodes:
                ls_coords.append((node.lon, node.lat))
            lss_inner.append(geometry.LineString(ls_coords))
        merged = linemerge([*lss_inner])
        borders = unary_union(merged)
        inner_polygons = list(polygonize(borders))
        for inner_polygon in inner_polygons:
            polygon = polygon.symmetric_difference(inner_polygon)
    return polygon


@retry_on_error(timeout_in_seconds=2*60)
def get_polygon_by_cadastre_id(api, admin_level, cadastre_id, country, id_key):
    response = api.query("""
    area["name"="{0}"]["admin_level"=2]->.c;
    relation(area.c)["admin_level"={1}]["{2}"={3}];
    (._;>;);
    out;
    // &contact=https://github.com/stalker314314/osm-admin-boundary-conflation/
    """.format(country, admin_level, id_key, cadastre_id))
    print('relations found for cadastre id {0}: {1}'.format(cadastre_id, len(response.relations)))
    national_border = any([w.tags['admin_level'] == '2' if 'admin_level' in w.tags else False for w in response.ways])
    if len(response.relations) != 1:
        return None, None, None, None
    polygon = create_geometry_from_osm_response(response.relations[0], response)
    return polygon, response.relations[0].tags['name'], response.relations[0].id, national_border


def load_level9_features(input_csv_file):
    """
    List of all level9 features with their name, id and (level8, level7, level6) names and ids
    """
    level9_features = []
    with open(input_csv_file) as input_csv:
        reader = csv.DictReader(input_csv)
        for row in reader:
            level9_features.append({
                'level9_id': row['level9_id'],
                'level9_name': row['level9_name'],
                'level8_id': row['level8_id'],
                'level8_name': row['level8_name'],
                'level7_id': row['level7_id'],
                'level7_name': row['level7_name'],
                'level6_id': row['level6_id'],
                'level6_name': row['level6_name'],
                'wkt': row['wkt'],
            })
    return level9_features


def get_municipality_settlements():
    """
    :return: Map of level8_id => list(level8 entities)
    """
    municipality_settlements = {}
    municipality_names = {}
    with open('input/naselje.csv') as settlement_csv:
        reader = csv.DictReader(settlement_csv)
        for row in reader:
            if row['opstina_maticni_broj'] not in municipality_names:
                municipality_names[row['opstina_maticni_broj']] = row['opstina_ime']
            if row['opstina_maticni_broj'] not in municipality_settlements:
                municipality_settlements[row['opstina_maticni_broj']] = []
            municipality_settlements[row['opstina_maticni_broj']].append(row['naselje_maticni_broj'])
    municipality_settlements = OrderedDict(sorted(municipality_settlements.items(), key=lambda x: x))
    return municipality_settlements


def get_settlement_municipality():
    """
    :return: Map of level9_id => level8_id
    """
    settlements_municipality = {}
    with open('input/naselje.csv') as naselja_csv:
        reader = csv.DictReader(naselja_csv)
        for row in reader:
            settlements_municipality[int(row['naselje_maticni_broj'])] = int(row['opstina_maticni_broj'])
    return settlements_municipality


def get_municipality_district():
    """
    :return: Map of level8_id => level6
    """
    municipality_district = {}
    with open('input/opstina.csv') as naselja_csv:
        reader = csv.DictReader(naselja_csv)
        for row in reader:
            municipality_district[int(row['opstina_maticni_broj'])] = int(row['okrug_sifra'])
    return municipality_district


def get_district_name_by_id():
    """
    :return: Map of level6_id => level6
    """
    districts = {}
    with open('input/opstina.csv') as naselja_csv:
        reader = csv.DictReader(naselja_csv)
        for row in reader:
            districts[int(row['okrug_sifra'])] = row['okrug_ime']
    return districts
