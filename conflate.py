import math
import os
import pickle
import sys
import time
import xml.etree.ElementTree as ET

import matplotlib.pyplot as plt
import overpy
import pyproj
import shapely.geometry as geometry
import yaml

from osmapi import OsmApi
from shapely.ops import linemerge

from common import retry_on_error
from processing_state import ProcessingState


def load_osm(path):
    nodes = {}
    ways = {}
    relations = {}
    root = ET.parse(path).getroot()
    for node in root.findall('node'):
        nodes[int(node.attrib['id'])] = {
            'lat': float(node.attrib['lat']),
            'lon': float(node.attrib['lon'])
        }

    for way in root.findall('way'):
        way_nodes = []
        for child in way.iter('nd'):
            way_nodes.append(int(child.attrib['ref']))
        ways[int(way.attrib['id'])] = {
            'nodes': way_nodes,
            'relations': '',
            'processed': ProcessingState.NO,
            'error_context': None,
            'osm_way': None
        }

    for relation in root.findall('relation'):
        relation_ways = []
        for child in relation.iter('member'):
            relation_ways.append(
                {
                    'ref': int(child.attrib['ref']),
                    'role': child.attrib['role'],
                    'type': child.attrib['type']
                })
        tags = {}
        for child in relation.iter('tag'):
            tags[child.attrib['k']] = child.attrib['v']
        relations[int(relation.attrib['id'])] = {
            'ways': relation_ways,
            'tags': tags
        }

    return {'relations': relations, 'ways': ways, 'nodes': nodes}


@retry_on_error()
def get_osm_shared_ways(api, r1, r2, country, id_key):
    response = api.query(f"""
        area["name"="{country}"]["admin_level"=2]->.a;
        relation(area.a)["boundary"="administrative"]["admin_level"=9]["{id_key}"="{r1}"]->.firstRelation;
        relation(area.a)["boundary"="administrative"]["admin_level"=9]["{id_key}"="{r2}"]->.secondRelation;
        (.firstRelation;>;)->.a1;
        (.secondRelation;>;)->.a2;
        (.a1;- .a2;)->.a3;
        (.a1;- .a3;)->.a4;
        way.a4;
        (._;>;);
        out;
        // &contact=https://github.com/stalker314314/osm-admin-boundary-conflation/
    """)
    return response


@retry_on_error()
def get_osm_single_way(api, r1, country, id_key):
    response = api.query(f"""
        area["name"="{country}"]["admin_level"=2]->.a;
        relation(area.a)["boundary"="administrative"]["admin_level"=9]["{id_key}"="{r1}"]->.firstRelation;
        relation(area.a)["boundary"="administrative"]["admin_level"=9]["{id_key}"!="{r1}"]->.secondRelation;
        (.firstRelation ;>;) -> .a1;
        (.secondRelation;>;) -> .a2;
        (way.a1;- way.a2;) -> .a3;
        way.a3;
        (._;>;);
        out;
        // &contact=https://github.com/stalker314314/osm-admin-boundary-conflation/
    """)
    return response


@retry_on_error()
def get_entities_shared_with_way(api, way_id):
    response = api.query("""
        way({0});
        ._;>;
        ._;<;
        out;
        // &contact=https://github.com/stalker314314/osm-admin-boundary-conflation/
        """.format(way_id))
    return response


def create_geometry_from_osm_way(way, response):
    # Try to build shapely polygon out of this data
    lss = []
    ls_coords = []
    for node in way.nodes:
        ls_coords.append((node.lon, node.lat))
    lss.append(geometry.LineString(ls_coords))

    merged = linemerge([*lss])
    return merged


def create_geometry_from_osm_file_data(source_data, way):
    # Try to build shapely polygon out of .osm data
    lss = []
    ls_coords = []
    for node_id in way['nodes']:
        node = source_data['nodes'][node_id]
        ls_coords.append((node['lon'], node['lat']))
    lss.append(geometry.LineString(ls_coords))

    merged = linemerge([*lss])
    return merged


def unglue_ways(config, osmapi, way_boundary_id, way_other_id):
    """
    Given admin boundary way and other way that shares some nodes with it, unglues those shared nodes into separate ones
    It adds new node and changes boundary to remove shared one and adds new one at the same place.
    It will not unglue endpoints
    """
    auto_proceed = config['auto_proceed']

    way_boundary = osmapi.WayGet(way_boundary_id)
    way_other = osmapi.WayGet(way_other_id)
    if len(way_other['tag']) == 0 or len(way_boundary['tag']) == 0:
        print('One of glued ways do not have any tag. This might be boundary in disguise, skipping')
        return False
    shared_nodes = set(way_boundary['nd']) & set(way_other['nd'])
    before_removing_endpoints = len(shared_nodes)
    if way_boundary['nd'][0] in shared_nodes:
        shared_nodes.remove(way_boundary['nd'][0])
    if way_boundary['nd'][-1] in shared_nodes:
        shared_nodes.remove(way_boundary['nd'][-1])

    if len(shared_nodes) == 0:
        if before_removing_endpoints > 0:
            print('There are glued nodes, but they are endpoints and script will not unglue them')
        return False

    print('{0} nodes will be unglued from boundary https://www.openstreetmap.org/way/{1} and way '
          'https://www.openstreetmap.org/way/{2}'.format(len(shared_nodes), way_boundary_id, way_other_id))
    if len(shared_nodes) > 0 and not auto_proceed:
        proceed = input('Proceed (Y/n)')
        if not (proceed == '' or proceed.lower() == 'y' or proceed.lower() == u'з'):
            return False

    done_any = False
    i = 1
    for shared_node in shared_nodes:
        node = osmapi.NodeGet(shared_node)
        if len(node['tag']) > 0:
            print('Node to be unglued has tags, skipping')
            continue
        added_node = {'id': -i, 'lon': node['lon'], 'lat': node['lat'], 'tag': {}}
        i = i + 1
        osmapi.NodeCreate(added_node)
        index = way_boundary['nd'].index(shared_node)
        del way_boundary['nd'][index]
        way_boundary['nd'].insert(index, added_node['id'])
        done_any = True
    if done_any:
        osmapi.WayUpdate(way_boundary)
        osmapi.flush()
        return True
    else:
        return False


def is_conflate_possible(config, osmapi, overpass_api, shapely_source_way, found_osm_way, shapely_found_osm_way):
    # Check if source or targets are not huge (we need this as we want to put conflation of way in a single changeset)
    assert len(shapely_source_way.coords) < 3000
    assert len(shapely_found_osm_way.coords) < 2000

    unglue_ways_as_needed = config['unglue_ways_as_needed']
    max_distance_end_points_to_consider_in_meters = config['max_distance_end_points_to_consider_in_meters']

    # Check if way is not national border
    if 'admin_level' in found_osm_way.tags and int(found_osm_way.tags['admin_level']) <= 2:
        print('Shared way is national border, skipping')
        return ProcessingState.ERROR_NATIONAL_BORDER, None

    # Check if way in OSM do not have any tags
    for tag in found_osm_way.tags:
        if tag in ('admin_level', 'boundary', 'note', 'source', 'fixme', 'type', 'int_name'):
            continue
        if tag.startswith('name'):
            continue
        print('Found unexpected tag {0} in way to conflate, skipping'.format(tag))
        return ProcessingState.ERROR_UNEXPECTED_TAG, tag

    # Check if nodes in way don't belong to any other way or relation
    response = get_entities_shared_with_way(overpass_api, found_osm_way.id)
    for way in response.ways:
        if 'admin_level' in way.tags and int(way.tags['admin_level']) <= 2:
            print(f'Way to conflate contains node which is also part of way https://www.openstreetmap.org/way/{way.id} which is national border, skipping')
            return ProcessingState.ERROR_NODE_IN_NATIONAL_BORDER, str(way.id)
        if 'boundary' not in way.tags:
            print(f'Way to conflate contains node which is also part of way https://www.openstreetmap.org/way/{way.id} which do not have boundary tag, skipping')
            if unglue_ways_as_needed:
                one_way = unglue_ways(config, osmapi, found_osm_way.id, way.id)
                if not one_way:
                    other_way = unglue_ways(config, osmapi, way.id, found_osm_way.id)
                    if not other_way:
                        return ProcessingState.ERROR_NODE_IN_OTHER_WAYS, str(way.id)
            else:
                return ProcessingState.ERROR_NODE_IN_OTHER_WAYS, str(way.id)
        elif way.tags['boundary'] != 'administrative':
            print(f'Way to conflate contains node which is also part of way https://www.openstreetmap.org/way/{way.id} which boundary tag != administrative, skipping')
            if unglue_ways_as_needed:
                one_way = unglue_ways(config, osmapi, found_osm_way.id, way.id)
                if not one_way:
                    other_way = unglue_ways(config, osmapi, way.id, found_osm_way.id)
                    if not other_way:
                        return ProcessingState.ERROR_NODE_IN_OTHER_WAYS, str(way.id)
            else:
                return ProcessingState.ERROR_NODE_IN_OTHER_WAYS, str(way.id)
    for relation in response.relations:
        is_city = 'place' in relation.tags and relation.tags['place'] == 'city'
        if 'admin_level' not in relation.tags:
            if not is_city:
                print(f'Way to conflate belongs to relation https://www.openstreetmap.org/relation/{relation.id} which do not have admin_level tag, skipping')
                return ProcessingState.ERROR_NODE_IN_OTHER_RELATION, str(relation.id)
        elif int(relation.tags['admin_level']) <= 2:
            print(f'Way to conflate belongs to relation https://www.openstreetmap.org/relation/{relation.id} which is national border, skipping')
            return ProcessingState.ERROR_NODE_IN_NATIONAL_RELATION, str(relation.id)
        if 'type' not in relation.tags:
            print(f'Way to conflate belongs to relation https://www.openstreetmap.org/relation/{relation.id} which do not have type tag, skipping')
            return ProcessingState.ERROR_NODE_IN_OTHER_RELATION, str(relation.id)
        elif relation.tags['type'] != 'boundary' and not is_city:
            print(f'Way to conflate belongs to relation https://www.openstreetmap.org/relation/{relation.id} where type != boundary, skipping')
            return ProcessingState.ERROR_NODE_IN_OTHER_RELATION, str(relation.id)
        if 'boundary' not in relation.tags:
            if not is_city:
                print(f'Way to conflate belongs to relation https://www.openstreetmap.org/relation/{relation.id} which do not have boundary tag, skipping')
                return ProcessingState.ERROR_NODE_IN_OTHER_RELATION, str(relation.id)
        elif relation.tags['boundary'] != 'administrative' and relation.tags['boundary'] != 'census':
            print(f'Way to conflate belongs to relation https://www.openstreetmap.org/relation/{relation.id} where boundary != administrative or census, skipping')
            return ProcessingState.ERROR_NODE_IN_OTHER_RELATION, str(relation.id)

    # Check if nodes on way in OSM are not having any tags
    nodes_with_tags = [n for n in found_osm_way.nodes if len(n.tags) > 0 and not (len(n.tags) == 1 and 'created_by' in n.tags)]
    if len(nodes_with_tags) > 0:
        return ProcessingState.ERROR_NODES_WITH_TAGS, ','.join([str(n.id) for n in nodes_with_tags])

    # Check if end points are close enough
    distance, should_reverse = get_bigger_endpoint_difference(shapely_source_way, shapely_found_osm_way)
    if distance > max_distance_end_points_to_consider_in_meters:
        print(f'End points of ways to conflate are different for more that {max_distance_end_points_to_consider_in_meters}m ({distance}m), skipping')
        return ProcessingState.ERROR_END_POINTS_FAR_APART, str(distance)
    if should_reverse:
        shapely_source_way.coords = list(shapely_source_way.coords[::-1])

    return ProcessingState.CHECKED_POSSIBLE, None


def get_bigger_endpoint_difference(shapely_source_way, shapely_found_osm_way):
    should_reverse = False
    geod = pyproj.Geod(ellps='WGS84')
    _, _, distance11 = geod.inv(shapely_found_osm_way.coords[0][0], shapely_found_osm_way.coords[0][1],
                              shapely_source_way.coords[0][0], shapely_source_way.coords[0][1])
    _, _, distance12 = geod.inv(shapely_found_osm_way.coords[0][0], shapely_found_osm_way.coords[0][1],
                              shapely_source_way.coords[-1][0], shapely_source_way.coords[-1][1])
    if distance12 < distance11:
        should_reverse = True
    distance1 = min(distance11, distance12)
    if should_reverse:
        _, _, distance2 = geod.inv(shapely_found_osm_way.coords[-1][0], shapely_found_osm_way.coords[-1][1],
                                   shapely_source_way.coords[0][0], shapely_source_way.coords[0][1])
    else:
        _, _, distance2 = geod.inv(shapely_found_osm_way.coords[-1][0], shapely_found_osm_way.coords[-1][1],
                                   shapely_source_way.coords[-1][0], shapely_source_way.coords[-1][1])
    return max(distance1, distance2), should_reverse


def is_same_geometry(shapely_source_way, shapely_found_osm_way):
    if shapely_source_way.is_closed != shapely_found_osm_way.is_closed:
        return False
    if shapely_source_way.is_ring != shapely_found_osm_way.is_ring:
        return False
    if len(shapely_source_way.coords) != len(shapely_found_osm_way.coords):
        return False
    # Check distance of endpoints and figure out if ways should be reversed
    distance, should_reverse = get_bigger_endpoint_difference(shapely_source_way, shapely_found_osm_way)
    if distance > 1:
        return False
    if should_reverse:
        shapely_source_way.coords = list(shapely_source_way.coords[::-1])
    # Go for each node and check distance
    geod = pyproj.Geod(ellps='WGS84')
    for p1, p2 in zip(shapely_source_way.coords, shapely_found_osm_way.coords):
        _, _, distance = geod.inv(p1[0], p1[1], p2[0], p2[1])
        if distance > 1:
            return False
    return True


def calculate_initial_compass_bearing(pointA, pointB):
    """
    Calculates the bearing between two points.
    The formulae used is the following:
        θ = atan2(sin(Δlong).cos(lat2),
                  cos(lat1).sin(lat2) − sin(lat1).cos(lat2).cos(Δlong))
    :Parameters:
      - `pointA: The tuple representing the latitude/longitude for the
        first point. Latitude and longitude must be in decimal degrees
      - `pointB: The tuple representing the latitude/longitude for the
        second point. Latitude and longitude must be in decimal degrees
    :Returns:
      The bearing in degrees
    :Returns Type:
      float
    """
    if (type(pointA) != tuple) or (type(pointB) != tuple):
        raise TypeError("Only tuples are supported as arguments")

    lat1 = math.radians(pointA[0])
    lat2 = math.radians(pointB[0])

    diffLong = math.radians(pointB[1] - pointA[1])

    x = math.sin(diffLong) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1)
            * math.cos(lat2) * math.cos(diffLong))

    initial_bearing = math.atan2(x, y)

    # Now we have the initial bearing but math.atan2 return values
    # from -180° to + 180° which is not what we want for a compass bearing
    # The solution is to normalize the initial bearing as shown below
    initial_bearing = math.degrees(initial_bearing)
    compass_bearing = (initial_bearing + 360) % 360

    return compass_bearing


def conflate_way(config, osmapi, overpass_api, source_data, source_way, found_osm_way):
    auto_proceed = config['auto_proceed']
    dry_run = config['dry_run']

    shapely_found_osm_way = create_geometry_from_osm_way(found_osm_way, None)
    shapely_source_way = create_geometry_from_osm_file_data(source_data, source_way)

    if len(source_way['nodes']) >= 2000:
        # OSM does not support this many nodes in way, human will need to simplify this
        print('Way has too many nodes ({0}) and 2000 is allowed'.format(len(source_way['nodes'])))
        return ProcessingState.ERROR_TOO_MANY_NODES, None

    if not shapely_found_osm_way.is_valid or not shapely_source_way.is_valid:
        print('Shape is invalid, skipping')
        return ProcessingState.ERROR_INVALID_SHAPE, None
    if shapely_found_osm_way.is_closed or shapely_found_osm_way.is_ring or \
            shapely_source_way.is_closed or shapely_source_way.is_ring:
        print('Shape is closed loop, cannot handle it, skipping')
        return ProcessingState.ERROR_CLOSED_SHAPE, None

    if is_same_geometry(shapely_source_way, shapely_found_osm_way):
        print('Way to conflate seems already conflated, skipping')
        return ProcessingState.CONFLATED, None
    is_conflate_possible_error, error_context = is_conflate_possible(config, osmapi, overpass_api, shapely_source_way,
                                                                     found_osm_way, shapely_found_osm_way)
    if is_conflate_possible_error != ProcessingState.CHECKED_POSSIBLE:
        return is_conflate_possible_error, error_context

    # Do basic check that can cut off lot of already-almost conflated ways
    # Shapes are same if dilated way can fit inside other way and if angle (degrees) of end points is less than 5 degree
    almost_same_ways = shapely_source_way.within(shapely_found_osm_way.buffer(0.005))
    angle1 = calculate_initial_compass_bearing(shapely_found_osm_way.coords[0], shapely_found_osm_way.coords[-1])
    angle2 = calculate_initial_compass_bearing(shapely_source_way.coords[0], shapely_source_way.coords[-1])
    heuristically_same = almost_same_ways and math.fabs(angle1-angle2) < 5
    if not heuristically_same:
        if not auto_proceed:
            # # TODO: use something better, like https://stackoverflow.com/questions/56448933/plotting-shapely-polygon-on-cartopy
            plt.figure()
            plt.plot(*shapely_found_osm_way.coords.xy, color='red')
            plt.plot(*shapely_source_way.coords.xy, color='green')
            plt.show()
            plt.pause(1)

            proceed = input('Does these shapes match? (Y/n)')
            if not (proceed == '' or proceed.lower() == 'y' or proceed.lower() == u'з'):
                return ProcessingState.ERROR_GEOMETRY_WRONG, None
    else:
        print('Detected almost same ways, skipping human check')

    osm_way_nodes_to_conflate = osmapi.WayFull(found_osm_way.id)
    osm_way_to_conflate = osmapi.WayGet(found_osm_way.id)
    nodes_to_delete = []
    assert len(osm_way_nodes_to_conflate) == len(osm_way_to_conflate['nd']) + 1
    for i in range(len(osm_way_to_conflate['nd'])-1):
        # since we are in-place modifying this list, we need to offset it by this much,
        # this is why we substact len of nodes_to_delete
        node_id_to_conflate = osm_way_to_conflate['nd'][i-len(nodes_to_delete)]
        node_to_conflate = next(n['data'] for n in osm_way_nodes_to_conflate if n['data']['id'] == node_id_to_conflate)
        if i < len(shapely_source_way.coords) - 1:
            geod = pyproj.Geod(ellps='WGS84')
            _, _, distance = geod.inv(node_to_conflate['lon'], node_to_conflate['lat'],
                                      shapely_source_way.coords[i][0], shapely_source_way.coords[i][1])
            node_to_conflate['lon'] = shapely_source_way.coords[i][0]
            node_to_conflate['lat'] = shapely_source_way.coords[i][1]
            if not dry_run:
                osmapi.NodeUpdate(node_to_conflate)
        else:
            nodes_to_delete.append(node_to_conflate)
            osm_way_to_conflate['nd'].remove(node_to_conflate['id'])
    for i in range(len(osm_way_to_conflate['nd'])-1, len(shapely_source_way.coords) - 1):
        added_node = {'id': -i, 'lon': shapely_source_way.coords[i][0], 'lat': shapely_source_way.coords[i][1], 'tag': {}}
        if not dry_run:
            osmapi.NodeCreate(added_node)
        osm_way_to_conflate['nd'].insert(-1, added_node['id'])
    # Fix last node
    last_node_id = osm_way_to_conflate['nd'][-1]
    last_node_to_conflate = next(n['data'] for n in osm_way_nodes_to_conflate if n['data']['id'] == last_node_id)
    _, _, distance = geod.inv(last_node_to_conflate['lon'], last_node_to_conflate['lat'],
                              shapely_source_way.coords[-1][0], shapely_source_way.coords[-1][1])

    last_node_to_conflate['lon'] = shapely_source_way.coords[-1][0]
    last_node_to_conflate['lat'] = shapely_source_way.coords[-1][1]
    if not dry_run:
        osmapi.NodeUpdate(last_node_to_conflate)

    if not dry_run:
        osmapi.WayUpdate(osm_way_to_conflate)
        # Deleting nodes needs to happen after we update way
        for node_to_delete in nodes_to_delete:
            osmapi.NodeDelete(node_to_delete)
        osmapi.flush()
        time.sleep(5)
        return ProcessingState.CONFLATED, None
    else:
        return ProcessingState.CHECKED_POSSIBLE, None


def main(input_osm_file, progress_file):
    with open('config.yml', 'r') as config_yml_file:
        config = yaml.safe_load(config_yml_file)

    overpass_api = overpy.Overpass(url=config['overpass_url'])
    auto_proceed = config['auto_proceed']
    country = config['country']
    level9_ref_key = config['level9_ref_key']

    osmapi = OsmApi(passwordfile='osm-password',
                    changesetauto=True,
                    changesetautosize=10000, changesetautotags=
                    {
                        u"comment": config['changeset_comment'],
                        u"tag": u"mechanical=yes", u"source": config['changeset_source']
                    })

    if not os.path.isfile(progress_file):
        print(f'Cannot find {progress_file}, starting from scratch')
        source_data = load_osm(input_osm_file)
        print(f'Loaded .osm file {input_osm_file}')
    else:
        with open(progress_file, 'rb') as p:
            source_data = pickle.load(p)

    # Iterate for each way in .osm
    count_processed = 0
    for way_id, way in sorted(source_data['ways'].items(), key=lambda x: x[0], reverse=True):
        count_processed = count_processed + 1
        print('Processing {0}/{1}'.format(count_processed, len(source_data['ways'])))
        if way['processed'] != ProcessingState.NO:
            continue
        # Find relations this way is part of
        relations = []
        for relation_id, relation in source_data['relations'].items():
            ways = [w for w in relation['ways'] if w['ref'] == way_id]
            assert len(ways) <= 1
            if len(ways) == 1:
                relations.append(relation)
        assert len(relations) > 0
        if len(relations) == 2:
            relation_text = "{0} (ref: {1}) - {2} (ref: {3})".format(
                relations[0]['tags']['name'], relations[0]['tags']['level9_id'],
                relations[1]['tags']['name'], relations[1]['tags']['level9_id'])
        elif len(relations) == 1:
            relation_text = "{0} (ref: {1})".format(
                relations[0]['tags']['name'], relations[0]['tags']['level9_id'])
        elif len(relations) == 3:
            relation_text = "{0} (ref: {1}) - {2} (ref: {3}) - {4} (ref: {5})".format(
                relations[0]['tags']['name'], relations[0]['tags']['level9_id'],
                relations[1]['tags']['name'], relations[1]['tags']['level9_id'],
                relations[2]['tags']['name'], relations[2]['tags']['level9_id'])
        way['relations'] = relation_text

        # If way is shared between two relations, we try to find it in OSM using that information,
        # Otherwise, if it is part of just one relation, we try to find it in OSM with that.
        if len(relations) == 2:
            settlement0_id = relations[0]['tags']['level9_id']
            settlement1_id = relations[1]['tags']['level9_id']
            osm_response = get_osm_shared_ways(overpass_api, settlement0_id, settlement1_id, country, level9_ref_key)
            if len(osm_response.ways) == 0:
                print('Cannot find shared way in OSM between settlements {0} (ref: {1}) and {2} (ref: {3}), skipping'.
                      format(relations[0]['tags']['name'], settlement0_id,
                             relations[1]['tags']['name'], settlement1_id))
                way['processed'] = ProcessingState.ERROR_SHARED_WAY_NOT_FOUND
                way['error_context'] = None
            elif len(osm_response.ways) > 1:
                print('More than 1 shared way in OSM between settlements {0} (ref: {1}) and {2} (ref: {3}), '
                      'fix by merging ways manually, skipping'.
                      format(relations[0]['tags']['name'], settlement0_id,
                             relations[1]['tags']['name'], settlement1_id))
                way['processed'] = ProcessingState.ERROR_MULTIPLE_SHARED_WAYS
                way['error_context'] = ','.join([str(w.id) for w in osm_response.ways])
            else:
                print('Processing way https://www.openstreetmap.org/way/{0} shared between {1} and {2}'.format(
                    osm_response.ways[0].id, relations[0]['tags']['name'], relations[1]['tags']['name']))
                processed, error_context = conflate_way(config, osmapi, overpass_api, source_data, way, osm_response.ways[0])
                way['processed'] = processed
                way['osm_way'] = osm_response.ways[0].id
                way['error_context'] = error_context
        elif len(relations) == 1:
            settlement_id = relations[0]['tags']['level9_id']
            osm_response = get_osm_single_way(overpass_api, settlement_id, country, level9_ref_key)
            if len(osm_response.ways) == 0:
                print('Cannot find way in OSM that belongs only to settlement {0} (ref: {1}), skipping'.
                      format(relations[0]['tags']['name'], settlement_id))
                way['processed'] = ProcessingState.ERROR_WAY_NOT_FOUND
                way['error_context'] = None
            elif len(osm_response.ways) > 1:
                print('More than 1 way in OSM that belongs only to settlement {0} (ref: {1}), '
                      'fix by merging ways manually, skipping'.format(
                    relations[0]['tags']['name'], settlement_id))
                way['processed'] = ProcessingState.ERROR_MULTIPLE_SINGLE_WAY
                way['error_context'] = ','.join([str(w.id) for w in osm_response.ways])
            else:
                print('Processing way https://www.openstreetmap.org/way/{0} belonging only to {1}'.format(
                    osm_response.ways[0].id, relations[0]['tags']['name']))
                processed, error_context = conflate_way(config, osmapi, overpass_api, source_data, way, osm_response.ways[0])
                way['processed'] = processed
                way['osm_way'] = osm_response.ways[0].id
                way['error_context'] = error_context
        elif len(relations) > 2:
            way['processed'] = ProcessingState.ERROR_OVERLAPPING_WAYS
            way['osm_way'] = None
            way['error_context'] = None

        # Dump current progress
        with open(progress_file, 'wb') as h:
            pickle.dump(source_data, h, protocol=pickle.DEFAULT_PROTOCOL)

        if not auto_proceed:
            proceed = input('Continue with next way? (Y/n)?')
            if proceed == '' or proceed.lower() == 'y' or proceed.lower() == u'з':
                continue
            break
        else:
            time.sleep(2)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: ./conflate.py <input_osm_file> <progress_file>")
        exit()
    input_osm_file = sys.argv[1]
    progress_file = sys.argv[2]
    main(input_osm_file, progress_file)
