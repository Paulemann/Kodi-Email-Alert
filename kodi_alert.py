#!/usr/bin/python
# -*- coding: utf-8 -*-

import imaplib
import email
import time
import datetime
import requests
import json
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
#_config_file_ = os.path.splitext(os.path.basename(__file__))[0] + '.ini'
#_log_file_ = None
#_addon_id_ = 'script.securitycam'
#_debug_ = True

import argparse


class GracefulExit(Exception):
    pass


def signal_handler(signum, frame):
    raise GracefulExit()

signal.signal(signal.SIGTERM, signal_handler)


def is_mailaddress(a):
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
  if _log_file_:
    if level == 'DEBUG' and _debug_:
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
     if level != 'DEBUG' or _debug_:
       print '[' + level + ']: ' + message


def read_config():
  global _kodi_hosts_, _kodi_port_, _kodi_user_, _kodi_passwd_
  global _imap_server_, _imap_user_, _imap_passwd_
  global _alert_address_, _notify_title_, _notify_text_
  global _exec_local_

  if not os.path.exists(_config_file_):
    log('Could not find configuration file \'{}\'.'.format(_config_file_), level='ERROR')
    return False

  log('Reading configuration from file ...')

  try:
    # Read the config file
    config = ConfigParser.ConfigParser()

    config.read([os.path.abspath(_config_file_)])

    _kodi_hosts_    = [p.strip(' "\'') for p in config.get('KODI JSON-RPC', 'hostname').split(',')]
   #_kodi_          = config.get('KODI JSON-RPC', 'hostname')
    _kodi_port_     = config.get('KODI JSON-RPC', 'port')
    _kodi_user_     = config.get('KODI JSON-RPC', 'username')
    _kodi_passwd_   = config.get('KODI JSON-RPC', 'password')

    for host in _kodi_hosts_:
      if not is_hostname(host):
        log('Wrong or missing value(s) in configuration file (section: [KODI JSON-RPC]).')
        return False
    if not is_int(_kodi_port_):
      log('Wrong or missing value(s) in configuration file (section: [KODI JSON-RPC]).')
      return False

    _imap_server_   = config.get('Mail Account', 'servername')
    _imap_user_     = config.get('Mail Account', 'username')
    _imap_passwd_   = config.get('Mail Account', 'password')

    if not is_hostname(_imap_server_) or not is_mailaddress(_imap_user_) or not _imap_passwd_:
      log('Wrong or missing value(s) in configuration file (section [Mail Account]).')
      return False

    _alert_address_  = [p.strip(' "\'') for p in config.get('Alert Trigger', 'mailaddress').split(',')]

    if not _alert_address_ == '{any}':
      for address in _alert_address_:
        if not is_mailaddress(address):
          log('Wrong or missing value(s) in configuration file (section [Alert Trigger]).')
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
#_parser = HTMLParser.HTMLParser()

#def decodeHeader(header):
#  values = []
#  if header and header.startswith('"=?'):
#    header = header.replace('"', '')

#  for value, encoding in decode_header(header):
#    if encoding:
#       value = value.decode(encoding)
#    values.append( _parser.unescape(value))

#  decoded = ' '.join([v for v in values])
#  return decoded


def idle(connection):
  # https://github.com/athoune/imapidle
  tag = connection._new_tag()
  connection.send("%s IDLE\r\n" % tag)
  response = connection.readline()
  log('IDLE Response (start): \'{}\''.format(response.replace('\r\n', '')), level='DEBUG')
  if not response.startswith('+'):
    raise Exception("IDLE not handled? Response: \'%s\'" % response)
  connection.loop = True
  while connection.loop:
    try:
      #response = connection._get_response()
      response = connection.readline().strip()
      log('IDLE Response (loop): \'{}\''.format(response.replace('\r\n', '')), level='DEBUG')
      if not response or response.startswith('* BYE '):
        connection.done()
      elif response.endswith('EXISTS') or response.endswith('EXPUNGE'):
        num, message = response.split()[1:3]
        yield num, message
    except connection.abort:
      #log('IDLE connection.abort, Last Response: {}'.format(resp), level='DEBUG') # --> raise exception
      connection.done()
      raise Exception("IDLE connection.abort, Last Response: \'%s\'" % resp)
    except (KeyboardInterrupt, SystemExit, GracefulExit):
      connection.done()
      raise
    #except Exception as e:
    #  log('IDLE Exception: {}'.format(e), level='DEBUG')
    except:
      pass


def done(connection):
  connection.send("DONE\r\n")
  connection.loop = False


def kodi_request(host, method, params):
  url  = 'http://{}:{}/jsonrpc'.format(host, _kodi_port_)
  headers = {'content-type': 'application/json'}
  data = {'jsonrpc': '2.0', 'method': method, 'params': params,'id': 1}

  if _kodi_user_ and _kodi_passwd_:
    base64str = base64.encodestring('{}:{}'.format(_kodi_user_, _kodi_passwd_))[:-1]
    header['Authorization'] = 'Basic {}'.format(base64str)

  try:
    response = requests.post(url, data=json.dumps(data), headers=headers, timeout=10)
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


def alert():
  for host in _kodi_hosts_:
    if not host_is_up(host, _kodi_port_):
      log('Host {} is down. Requests canceled.'.format(host))
      return

    if _notify_title_ and _notify_text_:
      log('Requesting notification \'{}: {}\' on host {} ...'.format(_notify_title_, _notify_text_, host))
      kodi_request(host, 'GUI.ShowNotification', {'title': _notify_title_, 'message': _notify_text_, 'displaytime': 2000})

    if _addon_id_:
      log('Requesting execution of addon \'{}\' on host {} ...'.format(_addon_id_, host))
      kodi_request(host, 'Addons.ExecuteAddon', {'addonid': _addon_id_})


def msg_is_alert(message):
  global _notify_title_, _notify_text_

  try:
    from_name, from_address = parseaddr(message['From'])
    if not from_address:
      log('Could not parse sender\'s mail address from header.', level='DEBUG')
      return False

    name, encoding = decode_header(from_name)[0]
    if encoding:
      from_name = name.decode(encoding).encode('utf-8')
    else:
      from_name = name
  except:
    from_name = ''
    pass

  try:
    line = []
    for subject, encoding in decode_header(message['Subject']):
      if encoding:
        line.append(subject.decode(encoding).encode('utf-8'))
      else:
        line.append(subject)
    subject = ' '.join([l for l in line])
  except:
    subject = ''
    pass

  if not from_name:
    log('From:    {}'.format(from_address), level='DEBUG')
  else:
    log('From:    {} <{}>'.format(from_name, from_address), level='DEBUG')
  log('Subject: {}'.format(subject), level='DEBUG')

  if from_address in _alert_address_ or from_address == '{any}':
    if _notify_title_ == '{from}':
      if from_name:
        _notify_title_ = from_name
      else:
       _notify_title_ = from_address
    if _notify_text_ == '{subject}' and subject:
      _notify_text_ = subject

    log('Mail has matching criteria: From Address={}.'.format(from_address))
    if _exec_local_:
      try:
        os.system(_exec_local_)
      except:
        log('Could not execute local command \'{}\'.'.format(_exec_local_) , level='ERROR')
        pass
    alert()

    return True

  return False


class TimerThread(Thread):
  def __init__(self, connection):
    Thread.__init__(self)
    self.event = Event()
    self.connection = connection

  def run(self):
    while not self.event.wait(15*60):
      log('Force idle stop.', level='DEBUG')
      self.connection.done()

  def stop(self):
    self.event.set()


#imaplib.Debug = 4
imaplib.IMAP4.idle = idle
imaplib.IMAP4.done = done


if __name__ == '__main__':
  global _config_file_, _log_file_, _addon_id_, _debug_

  parser = argparse.ArgumentParser(description='Sends a notification to a kodi host and triggers addon execution on email receipt')

  parser.add_argument('-d', '--debug', dest='debug', action='store_true', help="Output debug messages (Default: False)")
  parser.add_argument('-l', '--logfile', dest='log_file', default=None, help="Path to log file (Default: None=stdout)")
  parser.add_argument('-c', '--config', dest='config_file', default=os.path.splitext(os.path.basename(__file__))[0] + '.ini', help="Path to config file (Default: <Script Name>.ini)")
  parser.add_argument('-a', '--addonid', dest='addon_id', default='script.securitycam', help="Addon ID (Default: script.securitycam)")

  args = parser.parse_args()

  _config_file_ = args.config_file
  _log_file_ = args.log_file
  _addon_id_ = args.addon_id
  _debug_ = args.debug

  if _log_file_:
    logging.basicConfig(filename=_log_file_, format='%(asctime)s [%(levelname)s]: %(message)s', datefmt='%m/%d/%Y %H:%M:%S', filemode='w', level=logging.DEBUG)

  log('Output Debug: {}'.format(_debug_), level='DEBUG')
  log('Log file:     {}'.format(_log_file_), level='DEBUG')
  log('Config file:  {}'.format(_config_file_), level='DEBUG')
  log('Addon ID:     {}'.format(_addon_id_), level='DEBUG')

  if not read_config():
    sys.exit(1)

  mail = imaplib.IMAP4_SSL(_imap_server_)

  timer = TimerThread(mail)
  timer.start()

  try:
    mail.login(_imap_user_, _imap_passwd_)
    status, data = mail.select('INBOX')
    if status == 'OK':
      total_msgs = int(data[0])
      log('There are {} messages in INBOX'.format(total_msgs), level='DEBUG')
    else:
      raise Exception('Mailbox \'INBOX\' does not exist')

    #
    # Currently, this init block is not required.
    #
    #log('Checking mail server ...')
    #today = datetime.date.today().strftime("%d-%b-%Y")
    #for each address in _alert_address_:
    #  try:
    #    status, data = mail.uid('search', None, 'UNSEEN', 'FROM', address, 'ON', today)
    #  except:
    #    continue
    #  if status == 'OK':
    #    if data[0]:
    #      uid_list = data[0]
    #      for uid in uid_list.split():
    #        try:
    #          status, data = mail.uid('fetch', uid, '(BODY.PEEK[HEADER])')
    #        except:
    #          log('Failed to fetch mail data.', level='ERROR')
    #          continue
    #        if status == 'OK':
    #          message = email.message_from_string(data[0][1])
    #          if msg_is_alert(message):
    #            mail.uid('store', uid,'+FLAGS','\\Seen')
    #        else:
    #          log('Fetch mail returned a status <> OK.', level='DEBUG')
    #  else:
    #    log('Search mail returned a status <> OK.', level='DEBUG')

    log('Waiting for new mail ...')

    loop = True
    while loop:

      try:
        for num, msg in mail.idle():

          if msg == 'EXISTS' and int(num) > total_msgs:
            log('New mail received.')
            mail.done()
            total_msgs = int(num)

            try:
              status, data = mail.fetch(num, 'UID')

              if status != 'OK':
                continue

              msg_uid = None
              for item in data:
                resp = [i.strip('()') for i in item.split()]
                if resp[0] == num and resp[1] == 'UID':
                  msg_uid = resp[2]
                  log('Sequence number: {}, Unique ID: {}.'.format(num, msg_uid), level='DEBUG')
                  break

              if not msg_uid:
                continue

              #status, data = mail.fetch(num, '(BODY.PEEK[HEADER])')
              status, data = mail.uid('fetch', msg_uid, '(BODY.PEEK[HEADER])')

            except:
              log('Failed to fetch mail data.', level='ERROR')
              continue

            if status == 'OK':
              message = email.message_from_string(data[0][1])
              if msg_is_alert(message):
                #mail.store(num, '+FLAGS', '(\\Seen)')
                mail.uid('store', msg_uid, '+FLAGS', '(\\Seen)')
                #mail.store(num, '+FLAGS', '(\\Deleted)')
                #mail.expunge()
            else:
              log('Fetch mail returned a status <> OK.', level='DEBUG')

          #elif msg == 'EXISTS':
          #  total_msgs = int(num)

          elif msg == 'EXPUNGE':
            total_msgs -= 1
            log('Mail deleted. Remaining {} messages in INBOX'.format(total_msgs), level='DEBUG')

      except (KeyboardInterrupt, SystemExit, GracefulExit):
        loop = False
        log('Abort requested by user or system.')
        break

      except Exception as e:
        loop = False
        log('Abort due to exception: \"{}\"'.format(e))
        break

  except Exception as e:
    log('An error occured: {}'.format(e))
    pass

  finally:
    timer.stop()
    try:
      mail.close()
    except:
      pass
    mail.logout()
    log('Logged out.')
