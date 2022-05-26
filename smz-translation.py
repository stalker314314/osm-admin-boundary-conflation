import geom

import csv
import os

__location__ = os.path.dirname(os.path.realpath(__file__))


def filterTags(tags):
    if tags is None:
        return
    newtags = {}
    newtags["name"] = tags["NA_IME"]
    newtags["naselje_mb"] = tags["NA_MB"]
    newtags["boundary"] = "administrative"
    newtags["admin_level"] = "9"
    newtags["type"] = "boundary"
    newtags["source"] = "open Croatian cadastre data Jan 2021"
    return newtags


def splitWay(way, corners, features_map):
    idxs = [i for i, c in enumerate(way.points) if c in corners]
    splitends = 0 in idxs or (len(way.points) - 1) in idxs
    new_points = list()
    left = 0
    for cut in idxs:
        if cut != 0:
            new_points.append(way.points[left:(cut + 1)])
        left = cut
    # remainder
    if left < len(way.points) - 1:
        # closed way
        if not splitends and isClosed(way):
            new_points[0] = way.points[left:-1] + new_points[0]
        else:
            new_points.append(way.points[left:])
    # ~ print(len(way.points),[len(p) for p in new_points])

    new_ways = [way, ] + [geom.Way() for i in range(len(new_points) - 1)]

    if way in features_map:
        way_tags = features_map[way].tags

        for new_way in new_ways:
            if new_way != way:
                feat = geom.Feature()
                feat.geometry = new_way
                feat.tags = way_tags
                new_way.addparent(feat)

    for new_way, points in zip(new_ways, new_points):
        new_way.points = points
        if new_way.id != way.id:
            for point in points:
                point.removeparent(way, shoulddestroy=False)
                point.addparent(new_way)
    return new_ways


def mergeIntoNewRelation(way_parts):
    new_relation = geom.Relation()
    feat = geom.Feature()
    feat.geometry = new_relation
    new_relation.members = [(way, "outer") for way in way_parts]
    for way in way_parts:
        way.addparent(new_relation)
    return feat


def splitWayInRelation(rel, way_parts):
    way_roles = [m[1] for m in rel.members if m[0] == way_parts[0]]
    way_role = "" if len(way_roles) == 0 else way_roles[0]
    for way in way_parts[1:]:
        way.addparent(rel)
        rel.members.append((way, way_role))


def findSharedVertices(geometries):
    points = [g for g in geometries if isinstance(g, geom.Point)]
    vertices = list()
    for p in points:
        neighbors = set()
        for way in p.parents:
            for idx in findAll(way, p):
                for step in [-1, 1]:
                    pt = way.points[(idx + step) % len(way.points)]
                    if pt != p:
                        neighbors.add(pt)
        if len(neighbors) > 2:
            vertices.append(p)
    return vertices


def findSelfIntersections(way):
    intersections = list()
    seen = set()
    points = way.points
    if isClosed(way):
        points = points[:-1]
    for point in points:
        if point in seen:
            intersections.append(point)
        seen.add(point)
    return intersections


def similar(way1, way2):
    if len(way1.points) != len(way2.points):
        return False
    w1 = [w.id for w in way1.points]
    w2 = [w.id for w in way2.points]
    if w1[0] not in w2:
        return False
    if set(w1) != set(w2):
        return False
    # closed way
    if w1[0] == w1[-1]:
        idx1 = w1.index(min(w1))
        w1 = w1[idx1:-1] + w1[:idx1]
        if w2[0] == w2[-1]:
            idx2 = w2.index(min(w2))
            w2 = w2[idx2:-1] + w2[:idx2]
        # second way is not closed
        else:
            return False
        if w1 == w2:
            return True
        if w1 == w2[:1] + w2[1:][::-1]:
            return True
    else:
        if w1 == w2:
            return True
        if w1 == w2[::-1]:
            return True
    return False


def isClosed(way):
    return way.points[0] == way.points[-1]


def findAll(way, node, start=0):
    i = start - 1
    while True:
        try:
            i = way.points.index(node, i + 1)
            yield i
        except ValueError:
            break


def preOutputTransform(geometries, features):
    if geometries is None and features is None:
        return
    lint(geometries, features, "At entry", True)
    print("Patching features")
    for f in features:
        if f not in f.geometry.parents:
            f.geometry.addparent(f)
    lint(geometries, features, "After parent fix", True)
    print("Moving tags to relations")
    # move tags, remove member ways as Features.
    rels = [g for g in geometries if isinstance(g, geom.Relation)]
    featuresmap = {feature.geometry: feature for feature in features}
    for rel in rels:
        relfeat = featuresmap[rel]
        # splitWayInRelation does not add the relation as a parent.
        for member, role in rel.members:
            if rel not in member.parents:
                member.addparent(rel)
        if relfeat.tags == {}:
            outers = [m[0] for m in rel.members if m[1] == "outer"]
            relfeat.tags.update(featuresmap[outers[0]].tags)
            for member, role in rel.members:
                if member in featuresmap:
                    memberfeature = featuresmap[member]
                    del featuresmap[member]
                    member.removeparent(memberfeature)
                    features.remove(memberfeature)
        else:
            pass
            # ~ print("Relation {} has tags.".format(rel.id),relfeat.tags)
    # create relations for ways that are features.
    ways = [g for g in geometries if isinstance(g, geom.Way)]
    for way in ways:
        if way in featuresmap:
            feature = featuresmap[way]
            newrel = geom.Relation()
            way.addparent(newrel)
            newrel.members.append((way, "outer"))
            feature.replacejwithi(newrel, way)
            featuresmap[newrel] = feature
            del featuresmap[way]
    lint(geometries, features, "Before split")
    print("Finding shared vertices")
    corners = set(findSharedVertices(geometries))
    print("Splitting ways")
    for way in ways:
        is_way_in_relation = len([p for p in way.parents if isinstance(p, geom.Relation)]) > 0
        thesecorners = corners.intersection(way.points)
        # ~ if intersections:
        # ~ print(len(intersections))
        if len(thesecorners) > 0:
            way_parts = splitWay(way, thesecorners, featuresmap)
            if not is_way_in_relation:
                rel = mergeIntoNewRelation(way_parts)
                featuresmap[rel.geometry] = rel
                if way in featuresmap:
                    rel.tags.update(featuresmap[way].tags)
                for wg, role in rel.geometry.members:
                    if wg in featuresmap:
                        wg.removeparent(featuresmap[wg])
            else:
                for parent in way.parents:
                    if isinstance(parent, geom.Relation):
                        splitWayInRelation(parent, way_parts)
    lint(geometries, features, "After split")
    print("Merging relations")
    worklist = sorted([g for g in geometries if isinstance(g, geom.Way)], key=lambda g: len(g.points))
    # combine duplicate ways.
    removed = list()
    comparisons = 0
    for i, way in enumerate(list(worklist)):
        if i % 1000 == 0: print(i, len(list(worklist)))
        # skip ways that are already gone
        worklist.remove(way)
        if way in removed:
            continue
        for otherway in worklist:
            if len(otherway.points) > len(way.points):
                break
            comparisons += 1
            if similar(way, otherway):
                for parent in list(otherway.parents):
                    if isinstance(parent, geom.Relation):
                        parent.replacejwithi(way, otherway)
                removed.append(otherway)
    print("Comparisons:", comparisons)
    # ~ # results in duplicates
    # ~ worklist = [g for g in geometries if isinstance(g, geom.Way)]
    # ~ for way in worklist:
    # ~ # similar ways must share first point
    # ~ for otherway in way.points[0].parents:
    # ~ # skip self and ways that are already merged
    # ~ if otherway==way or way in removed:
    # ~ continue
    # ~ \            if similar(way,otherway):
    # ~ for parent in list(otherway.parents):
    # ~ if isinstance(parent, geom.Relation):
    # ~ parent.replacejwithi(way, otherway)
    # ~ removed.append(otherway)

    # merge adjacent ways
    # ~ ways = [g for g in geometries if isinstance(g, geom.Way)]
    # ~ junctions=set()
    # ~ for way in ways:
    # ~ for point in [way.points[0],way.points[-1]]:
    # ~ if len(point.parents) == 2:
    # ~ junctions.add(point)
    # ~ print(len(junctions))
    # ~ c=0
    # ~ for j in junctions:
    # ~ for p in j.parents:
    # ~ for p2 in p.parents:
    # ~ for p3 in p2.parents:
    # ~ print(j.id,p3.tags["name"],len(p.points))
    # ~ if c==10:
    # ~ break
    # ~ c+=1
    # add tags to all ways
    print("Tagging member ways")
    ways = [g for g in geometries if isinstance(g, geom.Way)]
    featuresmap = {feature.geometry: feature for feature in features}
    for way in ways:
        maticni = []
        for parent in way.parents:
            admin_levels = []
            boundaries = []
            if parent in featuresmap:
                parfeat = featuresmap[parent]
                if "admin_level" in parfeat.tags:
                    admin_levels.append(parfeat.tags["admin_level"])
                if "boundary" in parfeat.tags:
                    boundaries.append(parfeat.tags["boundary"])
                    maticni.append(parfeat.tags['naselje_mb'])
        newtags = {}
        if admin_levels:
            newtags["admin_level"] = min(admin_levels, key=int)
        if boundaries:
            newtags["boundary"] = boundaries.pop()
        newtags['naselje_mb'] = ','.join(maticni)
        if newtags:
            if way not in featuresmap:
                feat = geom.Feature()
                feat.geometry = way
                way.addparent(feat)
            else:
                feat = featuresmap[way]
            feat.tags.update(newtags)
    lint(geometries, features, "After combine.")
    for feat in features:
        if isinstance(feat.geometry, geom.Relation):
            feat.tags["type"] = "boundary"


def lint(geometries, features, message="", blat=False):
    if False:
        return
    ways = [g for g in geometries if isinstance(g, geom.Way)]
    rels = [g for g in geometries if isinstance(g, geom.Relation)]
    results = list()
    # check for geometries with no parents.
    noparents = list()
    results.append(("{} geometries with no parents.", noparents))
    for geo in geometries:
        if len(geo.parents) == 0:
            noparents.append(geo)
    # check for features not listed as parents
    notlisted = list()
    results.append(("{} features not used as parents.", notlisted))
    for f in features:
        if f not in f.geometry.parents:
            notlisted.append(f)
    # check for duplicate nodes in ways
    dupenodes = list()
    results.append(("{} duplicate nodes in ways.", dupenodes))
    onenodeways = list()
    results.append(("{} one node ways.", onenodeways))
    count = 0
    for way in ways:
        for i in range(1, len(way.points)):
            if way.points[i - 1] == way.points[i]:
                dupenodes.append(way, i)
                count += 1
        if len(way.points) == 1:
            onenodeways.append(way)
            count += 1
    if message and any(result[1] for result in results):
        print(message)
    for msg, result in results:
        if result:
            print(msg.format(len(result)))
            if blat:
                for p in result:
                    print(p)
