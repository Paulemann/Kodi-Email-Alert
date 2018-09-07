# Kodi-Email-Alert

Python script to send notfication to kodi and trigger execution of 'Security Cam Overlay' addon on incoming email.

Motivated by the fact that my security cam's only option to notify on motion detected is email, I started this project to ensure a prompt processing of the received mail for triggering the execution of the 'Securoty Cam Overlay' addon on my kodi host. 

To this purpose I am leveraging imaplib's idle call to keep connection to my imap server to be immediately informed on the receipt of new mail.

