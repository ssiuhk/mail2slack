#!/usr/bin/env python
""" Connect to an mailbox via IMAP, read e-mail messages and send them through Slack """

import os
import sys
import imaplib
import email
import logging
import ConfigParser
import argparse
import time
from datetime import datetime
import requests


# Initialize LOGGER function
logging.basicConfig()
LOGGER = logging.getLogger('mail2slack')
LOGGER.setLevel(logging.INFO)


def send_slack_message(config, payload):
    """ Send slack message to endpoint given by caller """

    header = {'Content-Type': 'application/json'}

    response = requests.post(
        config['end_point'], data=payload,
        headers=header
    )
    if response.status_code != 200:
        LOGGER.error('Request to slack returned an error %s, the response is: %s',
                     response.status_code,
                     response.text
                    )



def get_text(message):
    """ Get content of email and return a string """

    for part in message.walk():  # in depth-first traversal order 1
        if part.get_content_maintype() == 'text':

            text = part.get_payload(decode=True)
            return part.get_content_type(), text
        if part.get_content_type() == 'multipart/alternative':
            # in an order of increasing faithfulness 3
            for altpart in reversed(part.get_payload()):
                text = get_text(altpart)
                if text is not None:
                    return text
        continue
    return None


def process_mailbox(config, mailbox):
    """ Main flow to process mailbox folder selected previously """

    receive, data = mailbox.search(None, "UNSEEN")
    if receive != 'OK':
        LOGGER.info('No messages found!')
        return

    for num in data[0].split():

        typ, data = mailbox.fetch(num, '(RFC822)')
        if typ != 'OK':
            LOGGER.error("ERROR getting %d message", num)
            return

        msg = email.message_from_string(data[0][1])
        LOGGER.info('Message %s: %s', num, msg['Subject'])
        LOGGER.info('Raw Date: %s', msg['Date'])

        sender = msg['from'].split()[-1]
        subject = msg['Subject']
        content = get_text(msg)
        LOGGER.debug("Message Type: %s", msg.get_content_type())
        LOGGER.debug("Message Body: \n%s", content[1])

        slack_msg = '{                                               \
            "username": "' + config['slack_sender'] + '",            \
            "icon_url": "' + config['icon_url'] + '",                \
            "attachments": [                                         \
                {                                                    \
                    "fallback": "' + config['slack_fallback'] + '",  \
                    "color": "warning",                              \
                    "pretext": "",                                   \
                    "author_name": "' + sender + '",                 \
                    "author_link": "",                               \
                    "author_icon": "",                               \
                    "title": "' + subject + '",                      \
                    "title_link": "",                                \
                    "text": "' + content[1].replace('"', '\\"') + '",\
                    "fields": [                                      \
                        {                                            \
                            "title": "Priority",                     \
                            "value": "Medium",                       \
                            "short": False                           \
                        }                                            \
                    ],                                               \
                    "image_url": "",                                 \
                    "thumb_url": "",                                 \
                    "footer": "Slack API",                           \
                    "footer_icon": "https://platform.slack-edge.com/img/default_application_icon.png", \
                    "ts": ' + str(int(time.time())) + '              \
                }                                                    \
            ]                                                        \
        }'


        LOGGER.debug("Slack Message payload: %s", slack_msg)
        send_slack_message(config, slack_msg)

        # Not too fast...
        time.sleep(1)


def process_alert():
    """ Main flow to process mailbox messages """


    parser = argparse.ArgumentParser(
        description="Script to read new e-mails from mailbox via IMAP, "
        "parse content and send to Slack endpoint"
    )

    parser.add_argument("-d", "--debug", action='store_true')
    parser.add_argument("-c", "--config",
                        default=os.path.dirname(os.path.abspath(
                            __file__)) + '/mail2slack.conf'
                       )

    args = parser.parse_args()

    if args.debug:
        LOGGER.setLevel(logging.DEBUG)
        LOGGER.debug("DEBUG Mode is ON")

    if not args.config:
        args.config = os.path.dirname(
            os.path.abspath(__file__)) + '/mail2slack.conf'

    LOGGER.debug("Config file path: %s", args.config)


    config = dict()

    config_f = ConfigParser.ConfigParser()

    try:
        config_f.readfp(open(args.config))
        config['end_point'] = config_f.get('slack', 'end_point')
        config['slack_sender'] = config_f.get('slack', 'sender')
        config['icon_url'] = config_f.get('slack', 'icon_url')
        config['slack_fallback'] = config_f.get('slack', 'fallback_msg')
        config['mailserver'] = config_f.get('mail', 'server')
        config['mail_login'] = config_f.get('mail', 'username')
        config['mail_pw'] = config_f.get('mail', 'password')
        config['folder'] = config_f.get('mail', 'folder')

    except ConfigParser.ParsingError:
        LOGGER.error("Unable to parse config from file %s!", args.config)
        sys.exit(1)

    mailbox = imaplib.IMAP4_SSL(config['mailserver'])

    try:
        mailbox.login(config['mail_login'], config['mail_pw'])
    except imaplib.IMAP4.error:
        LOGGER.error("IMAP LOGIN FAILED!!!")
        sys.exit(1)

    receive = mailbox.select(config['folder'])
    if receive[0] == 'OK':
        LOGGER.info("%s - Processing mailbox ...", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        # ... do something with emails, see below ...
        process_mailbox(config, mailbox)
        mailbox.close()

    else:
        LOGGER.error("Unable to read from mailbox %s!", config['folder'])

    mailbox.logout()


if __name__ == "__main__":
    process_alert()
