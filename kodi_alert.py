#!/usr/bin/python
# -*- coding: utf-8 -*-

import imaplib
import email
import time
import datetime
import requests
import HTMLParser

import logging
import ConfigParser
import os
import sys

from threading import *
from email.header import decode_header
from email.utils import parseaddr

import signal


_log_file_ = os.path.splitext(os.path.basename(__file__))[0] + '.log'
_log_enable_ = False


class GracefulExit(Exception):
    pass


def signal_handler(signum, frame):
    raise GracefulExit()

signal.signal(signal.SIGTERM, signal_handler)


def log(message, level='INFO'):
  if _log_enable_:
    if level == 'DEBUG':
      logging.debug(message)
    if level == 'INFO':
      logging.info(message)
    if level == 'WARNING':
      logging.warning(message)
    if level == 'ERROR':
       logging.error(message)
    if level == 'CRITICAL':
     logging.crtitcal(message)
  else:
    print '[' + level + ']: ' + message


def read_config():
  global _kodi_, _kodi_port_, _kodi_user_, _kodi_passwd_
  global _imap_server_, _imap_user_, _imap_passwd_
  global _alert_sender_, _notify_title_, _notify_text_

  if not os.path.exists('kodi_alert.ini'):
    log('Config file \'kodi_alert.ini\' not found.', level='ERROR')
    return False

  log('Reading config from file \'kodi_alert.ini\' ...')

  try:
    # Read the config file
    config = ConfigParser.ConfigParser()

    config.read([os.path.abspath('kodi_alert.ini')])

    _kodi_          = config.get('KODI JSON-RPC', 'hostname')
    _kodi_port_     = config.get('KODI JSON-RPC', 'port')
    _kodi_user_     = config.get('KODI JSON-RPC', 'username')
    _kodi_passwd_   = config.get('KODI JSON-RPC', 'password')

    _imap_server_   = config.get('Mail Account', 'servername')
    _imap_user_     = config.get('Mail Account', 'username')
    _imap_passwd_   = config.get('Mail Account', 'password')

    #_alert_sender_  = config.get('Alert Trigger', 'sender')
    _alert_sender_  = [p.strip().replace('"', '').replace('\'', '') for p in config.get('Alert Trigger', 'sender').split(',')]

    _notify_title_  = config.get('Alert Notification', 'title')
    _notify_text_   = config.get('Alert Notification', 'text')

  except:
    log('Could not process configuration file.', level='ERROR')
    return False

  return True


# to unescape xml entities
_parser = HTMLParser.HTMLParser()

def decodeHeader(header):
  values = []
  if header and header.startswith('"=?'):
    header = header.replace('"', '')

  for value, encoding in decode_header(header):
    if encoding:
       value = value.decode(encoding)
    values.append( _parser.unescape(value))

  decoded = ' '.join([v for v in values])
  return decoded


def idle(connection):
  # https://github.com/athoune/imapidle
  tag = connection._new_tag()
  connection.send("%s IDLE\r\n" % tag)
  response = connection.readline()
  if response != '+ idling\r\n':
    raise Exception("IDLE timed out? Response was: %s" % response)
  connection.loop = True
  while connection.loop:
    try:
      resp = connection._get_response()
      uid, message = resp.split()[1:]
      yield uid, message
    except connection.abort:
      connection.done()
    except (KeyboardInterrupt, SystemExit, GracefulExit):
      connection.done()
      raise
    except:
      pass


def done(connection):
  connection.send("DONE\r\n")
  connection.loop = False


def kodi_request(method, params):
  url  = 'http://{}:{}/jsonrpc'.format(_kodi_, _kodi_port_)
  headers = {'content-type': 'application/json'}
  data = '{{"jsonrpc":"2.0","method":"{}","params":{},"id":1}}'.format(method, params)

  if _kodi_user_ and _kodi_passwd_:
    base64str = base64.encodestring('{}:{}'.format(_kodi_user_, _kodi_passwd_))[:-1]
    header['Authorization'] = 'Basic {}'.format(base64str)

  try:
    response = requests.post(url, data=data, headers=headers, timeout=10)
  except:
    return False

  data = response.json()
  return (data['result'] == 'OK')


def kodi_alert(title, message):
  if kodi_request('GUI.ShowNotification', '{{"title":"{}","message":"{}", "displaytime":2000}}'.format(title, message)):
    log('Sent notification \'{}: {}\''.format(title, message))
    kodi_request('Addons.ExecuteAddon', '{"addonid":"script.securitycam"}')


#imaplib.Debug = 4
imaplib.IMAP4.idle = idle
imaplib.IMAP4.done = done


if __name__ == '__main__':
  if _log_enable_:
    logging.basicConfig(filename=_log_file_, format='%(asctime)s [%(levelname)s]: %(message)s', datefmt='%m/%d/%Y %H:%M:%S', filemode='w', level=logging.DEBUG)

  if not read_config():
    sys.exit(1)

  mail = imaplib.IMAP4_SSL(_imap_server_)

  try:
    mail.login(_imap_user_, _imap_passwd_)
    mail.select('INBOX')

    log('Logged in.')

    loop = True
    while loop:

      #mail.noop() # will keep connection up during inactivity period > 30 min ?
      try:
        for uid, msg in mail.idle():

          if msg == "EXISTS":
            log('New mail received.')
            mail.done()

            try:
              status, data = mail.fetch(uid, '(BODY.PEEK[HEADER])')
              message = email.message_from_string(data[0][1])

              from_address = parseaddr(decodeHeader(message['From']))
              sender = from_address[1]
              if _notify_text_ == '{subject}':
                _notify_text_ = subject = decodeHeader(message['Subject'])

            except:
              log('Something went wrong while fetching mail data.', level='ERROR')
              continue

            if sender in _alert_sender_:
              log('New mail matches criteria for alert.')
              kodi_alert(_notify_title_, _notify_text_)
              mail.store(uid,'+FLAGS','\\Seen')
              #mail.store(uid,'+FLAGS','(\\Deleted)')
              #mail.expunge()

      except (KeyboardInterrupt, SystemExit, GracefulExit):
        loop = False
        log('Abort due to KeyboardInterrupt/SystemExit exception.', level='ERROR')
        break

      except Exception as e:
        loop = False
        log('Abort due to exception: \'{}\''.format(e), level='ERROR')
        break

  finally:
    try:
      mail.close()
    except:
      pass
    mail.logout()
    log('Logged out.')
