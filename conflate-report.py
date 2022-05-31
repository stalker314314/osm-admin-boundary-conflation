import pickle
import pprint
import sys
from collections import OrderedDict

from jinja2 import Environment, FileSystemLoader

from processing_state import ProcessingState

errors = {
    ProcessingState.NO: 'Not yet considered.',
    ProcessingState.CHECKED_POSSIBLE: 'Checked and way can be conflated without problems, but conflation not yet done.',
    ProcessingState.CONFLATED: 'Conflated (already done).',
    ProcessingState.ERROR_END_POINTS_FAR_APART: 'First or last node from cadastre and OSM are too far apart. This can happen when way between two entities is split. Additional context is mentioning exact distance they are apart.',
    ProcessingState.ERROR_GEOMETRY_WRONG: 'User rejected conflation.',
    ProcessingState.ERROR_SHARED_WAY_NOT_FOUND: 'Way to be conflated is shared between two entities, but no such way is found in OSM. This should not be common situation and it might mean that border in OSM is converted to single node or that entities to not touch at all. diruju. This error requires human investigation.',
    ProcessingState.ERROR_WAY_NOT_FOUND: 'Way to be conflated is touching only one entity, but no such way is found in OSM. This might mean that border between two entites from cadastre have a gap, but in there is no gap in OSM and border in OSM is shared (and it should not be). Human need to find this situation and split border to two separate ways.',
    ProcessingState.ERROR_MULTIPLE_SHARED_WAYS: 'Way to be conflated is shared between two entities, but in OSM there are multiple such shared ways. They should probably be merged (unless there are lower level admin boundaries conected to them). Additional context is listing all found OSM ways.',
    ProcessingState.ERROR_MULTIPLE_SINGLE_WAY: 'Way to be conflated is touching only one entity, but in OSM there are multiple such single ways. They should probably be merged (unless there are lower level admin boundaries conected to them). Additional context is listing all found OSM ways.',
    ProcessingState.ERROR_NODES_WITH_TAGS: 'Some nodes in found way do contain unexpected tags. Human need to check these tags and either remove them, or ungle those nodes from way. Additional context is listing all those nodes.',
    ProcessingState.ERROR_NATIONAL_BORDER: 'Found way is national border (admin_level=2) and no conflation is possible. This is kind of error that is not fixable without further discussion between two national communities.',
    ProcessingState.ERROR_UNEXPECTED_TAG: 'Found way contains unexpected tags. Human need to either remove those tags or split way into two different ways. Additional context is listing those tags.',
    ProcessingState.ERROR_NODE_IN_OTHER_WAYS: 'Found way is containing node that is shared with some other ways that are not administrative borders. Sometimes they should be unglued, sometimes it is actually untagged border. Additional context is listing those other ways.',
    ProcessingState.ERROR_NODE_IN_NATIONAL_BORDER: 'Found way contains node that is shared with national border and it should not be moved. Additional context is listing way of national border.',
    ProcessingState.ERROR_NODE_IN_OTHER_RELATION: 'Found way contains node that is part of some other relation that is not administrative border and it should not be moved. Additional context contains that other relation.',
    ProcessingState.ERROR_NODE_IN_NATIONAL_RELATION: 'Found way contains node that is part of national border and it should not be moved. Additional context contains tway of national border.',
    ProcessingState.ERROR_INVALID_SHAPE: 'Invalid shape read from .osm file.',
    ProcessingState.ERROR_CLOSED_SHAPE: 'Way to be conflated is closed shape (enclave or exclave). This tool does not support conflation of closed shaped yet. Human need to do manual conflation.',
    ProcessingState.ERROR_OVERLAPPING_WAYS: 'Way to be conflated contains more than 2 entities. This means that some of the entities overlap which usually means error in cadastre data. Check manually or contact authoritative source.',
    ProcessingState.ERROR_TOO_MANY_NODES: 'Way to be conflated contains more than 2000 nodes which is above OSM limit for number of nodes in the way. Please simplify this way manually.'
}

errors = OrderedDict(sorted(errors.items(), key=lambda x: x[0].value))


def main(progress_file, output_html_file):
    env = Environment(loader=FileSystemLoader(searchpath='./templates'))
    template = env.get_template('index_template.html')

    with open(progress_file, 'rb') as p:
        source_data = pickle.load(p)
    total_ways = len(source_data['ways'])
    processed_ways = len([w for w in source_data['ways'].values() if w['processed'] != ProcessingState.NO])
    ways_with_osm_ways_found = len([w for w in source_data['ways'].values() if w['osm_way'] is not None])
    count_per_error = {}
    for w in source_data['ways'].values():
        if w['processed'] not in count_per_error:
            count_per_error[w['processed']] = 0
        count_per_error[w['processed']] += 1
        if w['error_context'] is None:
            w['error_context'] = ''
        if w['processed'] in (ProcessingState.ERROR_MULTIPLE_SHARED_WAYS, ProcessingState.ERROR_MULTIPLE_SINGLE_WAY,
                              ProcessingState.ERROR_NODE_IN_OTHER_WAYS, ProcessingState.ERROR_NODE_IN_NATIONAL_BORDER):
            ways = w['error_context'].split(',')
            w['error_context'] = ','.join(['<a href="https://www.openstreetmap.org/way/{0}" target="_blank">{0}</a>'.format(w) for w in ways]).replace('"', '\\"')
        elif w['processed'] in (ProcessingState.ERROR_NODES_WITH_TAGS,):
            nodes = w['error_context'].split(',')
            w['error_context'] = ','.join(['<a href="https://www.openstreetmap.org/node/{0}" target="_blank">{0}</a>'.format(n) for n in nodes]).replace('"', '\\"')
        elif w['processed'] in (ProcessingState.ERROR_NODE_IN_OTHER_RELATION,):
            relations = w['error_context'].split(',')
            w['error_context'] = ','.join(['<a href="https://www.openstreetmap.org/relation/{0}" target="_blank">{0}</a>'.format(r) for r in relations]).replace('"', '\\"')
        elif w['processed'] in (ProcessingState.ERROR_END_POINTS_FAR_APART,):
            w['error_context'] = '{:.2f}m'.format(float(w['error_context']))
    print('Total ways: {0}'.format(total_ways))
    print('Processed ways: {0}'.format(processed_ways))
    print('Ways with OSM way found: {0}'.format(ways_with_osm_ways_found))
    pp = pprint.PrettyPrinter(indent=4)
    print('Count per error:\n{0}'.format(pp.pformat(count_per_error)))
    count_per_error = OrderedDict(sorted(count_per_error.items(), key=lambda x: x[1], reverse=True))

    source_data = {k: source_data['ways'][k] for k in list(source_data['ways'])[0:-1]}
    output = template.render(total_ways=total_ways, processed_ways=processed_ways, errors=errors,
                             count_per_error=count_per_error, ways_with_osm_ways_found=ways_with_osm_ways_found,
                             source_data=source_data)
    with open(output_html_file, 'w', encoding='utf-8') as fh:
        fh.write(output)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: ./conflate-report.py <progress_file> <output_html_file>")
        exit()
    progress_file = sys.argv[1]
    output_html_file = sys.argv[2]
    main(progress_file, output_html_file)
