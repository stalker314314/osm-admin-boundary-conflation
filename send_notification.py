import csv
import datetime
import os
import sys
import time

import requests


def telegram_sendtext(bot_message: str):
    bot_token = os.environ['TELEGRAM_BOT_TOKEN']
    bot_chat_id = os.environ['TELEGRAM_CHAT_ID']
    send_text = 'https://api.telegram.org/bot' + bot_token + '/sendMessage?chat_id=' + bot_chat_id + '&parse_mode=Markdown&text=' + bot_message
    response = requests.get(send_text)
    time.sleep(3)
    return response.json()


def process(diff_type: str, entity_type: str, baseline_csv: str, new_csv: str) -> int:
    # Load saved state
    baseline_entities = {}
    with open(baseline_csv) as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            baseline_entities[row['relation_id']] = {
                'district': row['level6'],
                'name': row['level8'] if entity_type == 'level8' else row['level9'],
                'relation_id': row['relation_id'], 'area_not_shared': float(row['area_not_shared'])
            }
    new_entities = {}
    with open(new_csv) as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            new_entities[row['relation_id']] = {
                'level6': row['level6'],
                'name': row['level8'] if entity_type == 'level8' else row['level9'],
                'area_not_shared': float(row['area_not_shared'])
            }

    messages_sent = 0
    for new_relation_id, new_entity in new_entities.items():
        if messages_sent > 10:
            telegram_sendtext('{0} refreshed and compared with {1}, but there are more than 10 regressions, stopping with sending'.format(
                diff_type, entity_type
            ))
            break
        if new_relation_id not in baseline_entities:
            telegram_sendtext('{0} refreshed. Relation {1} ({2} {3}) exist now and it didn\'t existed before.'.format(
                diff_type, new_relation_id, entity_type, new_entity['name']
            ))
            messages_sent += 1
            continue
        baseline_area_not_shared = baseline_entities[new_relation_id]['area_not_shared']
        new_area_not_shared = new_entity['area_not_shared']
        if new_area_not_shared > 0 and (new_area_not_shared - baseline_area_not_shared) > 0:  # It was: new_area_not_shared > 0.01
            telegram_sendtext('{0} refreshed and {1} {2} (district {3}, relation {4}) was different {5}%, but now it is {6}%'.format(
                diff_type, entity_type, new_entity['name'], new_entity['level6'], new_relation_id,
                100 * baseline_area_not_shared, 100 * new_area_not_shared)
            )
            messages_sent += 1

    for baseline_relation_id, baseline_entity in baseline_entities.items():
        if messages_sent > 10:
            telegram_sendtext('{0} refreshed and compared with {1}, but there are more than 10 regressions, stopping with sending'.format(
                diff_type, entity_type
            ))
            break
        if baseline_relation_id not in new_entities:
            telegram_sendtext('{0} refreshed. Relation {1} ({2} {3}) existed before and it doesn\'t exist now.'.format(
                diff_type, baseline_relation_id, entity_type, new_entity['name']
            ))
            messages_sent += 1

    return messages_sent


def main():
    if len(sys.argv) != 5:
        print("Not enough arguments, quitting")
        exit()
    diff_type = sys.argv[1].upper()
    if diff_type not in ('CADASTRE', 'OSM'):
        print('First argument (diff type) need to be Cadastre or OSM')
        exit()
    entity_type = sys.argv[2]
    if entity_type not in ('level8', 'level9'):
        print('Second argument (entity type) need to be level8 or level9')
        exit()

    baseline_csv = sys.argv[3]
    new_csv = sys.argv[4]
    messages_sent = process(diff_type, entity_type, baseline_csv, new_csv)
    if messages_sent == 0:
        telegram_sendtext(f'Cadastre analysis done for {entity_type} {diff_type} diff type for '
                          f'{datetime.date.strftime(datetime.date.today(), "%d.%m.%Y")}')


if __name__ == '__main__':
    main()
