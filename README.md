# Kodi-Email-Alert

Python script to send notfication to kodi and trigger execution of 'Security Cam Overlay' addon on incoming email.

Motivated by the fact that my security cam's only option to notify on detected motion is email, I started this project to ensure a prompt processing of the received mail for triggering the execution of the 'Security Cam Overlay' addon on my kodi host. 

To this purpose I am leveraging imaplib's idle call to keep connection to my imap server and be immediately informed on the receipt of new mail.

The sender's email address is then compared to the configured email address of the security cam. On match the sript makes two JSON-RPC calls to send out a notifaction and trigger execution of the 'Security Cam Overlay' addon.

Since, commonly, the idle connections is terminated after 30 mins of inactivity, which also makes the script exit, I recommend starting the script with a systemd unit file 'kodi_alert.service' which has 'restart on-success' configured. Thus, the script is automatically restarted after a 'graceful' exit due to termination of the idle loop and continues email monitoring.

The required parameters for the kodi JSON-RPC connection, email account, security cam email adress(es) and alert notifications mus be confifured in the file 'kodi_alert.ini' in the same folder with 'kodi_alert.py'. See 'kodi_alert.ini.template' for what configuration values must be set.

Since my kodi system goes into sleep mode when idle I am running the script on a rasperry pi which is up 24x7. There is no wake-on-lan on email receipt since the time it takew to wake up the host would probable not allow capturing the actual motion on screen. 

I added an option to execute a local command on receipt of security cam email.

