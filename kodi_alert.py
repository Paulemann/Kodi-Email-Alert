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
import socket

from threading import *
from email.header import decode_header
from email.utils import parseaddr

import signal


# global settings
_log_file_ = os.path.splitext(os.path.basename(__file__))[0] + '.log'
_log_enable_ = False

_config_file_ = 'kodi_alert.ini'
_addon_id_ = 'script.securitycam'


class GracefulExit(Exception):
    pass


def signal_handler(signum, frame):
    raise GracefulExit()

signal.signal(signal.SIGTERM, signal_handler)


def is_email(a):
  try:
    t = a.split('@')[1].split('.')[1]
  except:
    return False

  return True


def is_hostname(h):
  try:
    t = h.split('.')[2]
  except:
    return False

  return True


def is_int(n):
  try:
    t = int(n)
  except:
    return False

  return True


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
  global _exec_local_

  if not os.path.exists(_config_file_):
    log('Could not find configuration file \'{}\'.'.format(_config_file_), level='ERROR')
    return False

  log('Reading configuration from file ...')

  try:
    # Read the config file
    config = ConfigParser.ConfigParser()

    config.read([os.path.abspath('kodi_alert.ini')])

    _kodi_          = config.get('KODI JSON-RPC', 'hostname')
    _kodi_port_     = config.get('KODI JSON-RPC', 'port')
    _kodi_user_     = config.get('KODI JSON-RPC', 'username')
    _kodi_passwd_   = config.get('KODI JSON-RPC', 'password')

    if not  is_hostname(_kodi_) or not is_int(_kodi_port_):
      log('Wrong or missing value(s) in configuration file.')
      return False

    _imap_server_   = config.get('Mail Account', 'servername')
    _imap_user_     = config.get('Mail Account', 'username')
    _imap_passwd_   = config.get('Mail Account', 'password')

    if not is_hostname(_imap_server_) or not is_email(_imap_user_) or not _imap_passwd_:
      log('Wrong or missing value(s) in configuration file.')
      return False

    #_alert_sender_  = config.get('Alert Trigger', 'sender')
    _alert_sender_  = [p.strip().replace('"', '').replace('\'', '') for p in config.get('Alert Trigger', 'sender').split(',')]

    for sender in _alert_sender_:
      if  not is_email(sender):
        log('Wrong or missing value(s) in configuration file.')
        return False

    _notify_title_  = config.get('Alert Notification', 'title')
    _notify_text_   = config.get('Alert Notification', 'text')

    _exec_local_    = config.get('Local', 'command')

  except:
    log('Could not process configuration file.', level='ERROR')
    return False

  log('Configuration OK.')

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
    raise Exception("IDLE not handled? Response: \'%s\'" % response)
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


def host_is_up(host, port):
  try:
    sock = socket.create_connection((host, port), timeout=3)
  #except socket.timout:
  #  return False
  except:
    return False

  return True


def alert(title, message):
  if not host_is_up(_kodi_, _kodi_port_):
    log('Host {} is down. Requests canceled.'.format(_kodi_))
    return

  if title and message:
    log('Sending notification \'{}: {}\' ...'.format(title, message))
    kodi_request('GUI.ShowNotification', '{{"title":"{}","message":"{}", "displaytime":2000}}'.format(title, message))

  log('Requsting execution of addon \'{}\' ...'.format(_addon_id_))
  kodi_request('Addons.ExecuteAddon', '{{"addonid":"{}"}}'.format(_addon_id_))


def msg_is_alert(message):
  global _notify_text_

  sender = parseaddr(decodeHeader(message['From']))[1]

  if sender in _alert_sender_:
    if _notify_text_ == '{subject}':
      _notify_text_ = decodeHeader(message['Subject'])

    log('Mail has matching criteria: Sender={}.'.format(sender))
    alert(_notify_title_, _notify_text_)
    if _exec_local_:
      try:
        os.system(_exec_local_)
      except:
        log('Could not execute local command \'{}\'.'.format(_exec_local_) , level='ERROR')
        pass

    return True

  return False


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

    #
    # Unseen mails might be of interest in case new
    # mails were received betwenn exit and restart:
    #
    # Cuurently, whole block is unused.
    #
    #log('Checking mail server ...')
    #today = datetime.date.today().strftime("%d-%b-%Y")
    #for each sender in _alert_sender_:
    #  try:
    #    status, data = conn.search(None, 'UNSEEN', 'FROM', sender, 'ON', today)
    #  except:
    #    continue
    #  if status == 'OK':
    #    if data[0]:
    #      uid_list = data[0]
    #      for uid in uid_list.split():
    #        try:
    #          status, data = mail.fetch(uid, '(BODY.PEEK[HEADER])')
    #        except:
    #          log('Failed to fetch mail data.', level='ERROR')
    #          continue
    #        message = email.message_from_string(data[0][1])
    #        if msg_is_alert(message):
    #          mail.store(uid,'+FLAGS','\\Seen')

    log('Waiting for new mail ...')

    loop = True
    while loop:

      try:
        for uid, msg in mail.idle():

          if msg == "EXISTS":
            log('New mail received.')
            mail.done()

            try:
              status, data = mail.fetch(uid, '(BODY.PEEK[HEADER])')

            except:
              log('Failed to fetch mail data.', level='ERROR')
              continue

            message = email.message_from_string(data[0][1])
            if msg_is_alert(message):
              mail.store(uid,'+FLAGS','\\Seen')
              #mail.store(uid,'+FLAGS','(\\Deleted)')
              #mail.expunge()

          else:
            mail.done()
            mail.noop()

      except (KeyboardInterrupt, SystemExit, GracefulExit):
        loop = False
        log('Abort requested by user or system.')
        break

      except Exception as e:
        loop = False
        log('Closing connection due to exception: \'{}\' ...'.format(e))
        break

  finally:
    try:
      mail.close()
    except:
      pass
    mail.logout()
    log('Logged out.')
