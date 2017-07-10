# Created by jongwonkim on 09/07/2017.

import os
import logging
import boto3
import json
import re
from src.dynamodb.votes import DbVotes
from src.dynamodb.teams import DbTeams
from urllib.parse import unquote
from urllib.parse import urlencode
import requests



log = logging.getLogger()
log.setLevel(logging.DEBUG)
db_votes = DbVotes(os.environ['VOTES_TABLE'])
db_teams = DbTeams(os.environ['TEAMS_TABLE'])
sns = boto3.client('sns')


def get_slack_event(event):
    return {
        'slack': json.loads(unquote(event['body'][8:]))
    }


def get_channel(event):
    params = {
        'token': event['teams']['access_token'],
        'channel': event['slack']['channel']['id']
    }
    url = 'https://slack.com/api/channels.info?' + urlencode(params)
    response = requests.get(url).json()
    print('!!! RESPONSE !!!')
    print(response)
    if 'ok' in response and response['ok'] is True:
        event['channel'] = response['channel']
        return
    raise Exception('Failed to get a Slack channel info!')


def get_team(event):
    event['teams'] = db_teams.retrieve_team(event['slack']['team']['id'])


def update_message(event):
    vote_count = len(event['votes'])
    channel = event['slack']['channel']['id']
    original_message = event['slack']['original_message']
    text = original_message['text']
    attachments = original_message['attachments']
    time_stamp = original_message['ts']
    bot_token = event['teams']['bot']['bot_access_token']
    access_token = event['teams']['access_token']

    member_count = len(event['channel']['members'])

    print('attachments')
    print(attachments)
    if len(attachments) == 1:
        attachments.append({})
    if vote_count == 0:
        attachments[1] = {
            'text': 'No vote has been placed.'
        }
    elif vote_count == 1:
        attachments[1] = {
            'color': '#3AA3E3',
            'text': '1 vote has been placed.'
        }
    else:
        attachments[1] = {
            'color': '#3AA3E3',
            'text': '{} votes have been placed.'.format(vote_count)
        }

    # For testing purpose, I won't override the voting message.
    if vote_count == member_count - 1:  # Including the bot.
        text = 'Voting is completed. I will show you the result shortly.'
        attachments = None
        sns_event = {
            'team_id': event['slack']['team']['id'],
            'channel_id': event['slack']['channel']['id'],
            'token': bot_token,
            'api_token': access_token,
            'votes': event['votes'],
            'members': event['channel']['members'],
            'round': event['slack']['callback_id']
        }
        # Please comment this out if you want to keep the voting buttons up.
        sns.publish(
            TopicArn=os.environ['EVALUATE_VOTES_SNS_ARN'],
            Message=json.dumps({'default': json.dumps(sns_event)}),
            MessageStructure='json'
        )

    sns_event = {
        'token': bot_token,
        'channel': channel,
        'text': text,
        'attachments': attachments,
        'ts': time_stamp,
        'as_user': True
    }
    print('!!! SNS EVENT !!!')
    print(sns_event)
    return sns.publish(
        TopicArn=os.environ['UPDATE_MESSAGE_SNS_ARN'],
        Message=json.dumps({'default': json.dumps(sns_event)}),
        MessageStructure='json'
    )


def store_vote(event):
    db_votes.store_vote(item={
        'team_id': event['slack']['team']['id'],
        'channel_id': event['slack']['channel']['id'],
        'user_id': '_' + event['slack']['user']['id'],
        'event_id': event['slack']['actions'][0]['value']
    })


def retrieve_votes(event):
    db_response = db_votes.fetch_votes(event['slack']['channel']['id'])
    print('!!! db_response !!!')
    print(db_response)
    event['votes'] = db_response


def handler(event, context):
    log.info(json.dumps(event))
    response = {
        "statusCode": 200
    }
    try:
        event = get_slack_event(event)
        get_team(event)
        get_channel(event)
        log.info(event)
        store_vote(event)
        retrieve_votes(event)
        update_message(event)
        log.info(response)
    except Exception as e:
        log.error(json.dumps({"message": str(e)}))
    finally:
        return response