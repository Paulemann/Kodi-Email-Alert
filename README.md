# Kodi-Email-Alert

Python script to send notfication to kodi and trigger execution of 'Security Cam Overlay' addon on incoming email.

Motivated by the fact that my security cam's only option to notify on detected motion is email, I started this project to ensure a prompt processing of the received mail for triggering the execution of the 'Security Cam Overlay' addon on my kodi host. 

To this purpose I am leveraging imaplib's idle call to keep connection to my imap server and be immediately informed on the receipt of new mail.

The sender's email address is then compared to the configured email address of the security cam. On match the script makes two JSON-RPC calls to send out a notifaction and trigger execution of the 'Security Cam Overlay' addon.

Since, commonly, the idle connections is terminated after 30 mins of inactivity, which also makes the script exit, I recommend starting the script with a systemd unit file 'kodi_alert.service' which has 'restart on-success' configured. Thus, the script is automatically restarted after a 'graceful' exit due to termination of the idle loop and resumes its task.

Update: I added a background process (thread) which forces termination of the idle loop every 15 minutes to prevent an inactivity timeout. This way, the kodi_alert.service 'restart on-success' option isn't required any more.

The required parameters for the kodi JSON-RPC connection, email account, security cam email adress(es) and alert notifications must be confifured in the file 'kodi_alert.ini' in the same folder with 'kodi_alert.py'. See 'kodi_alert.ini.template' for what configuration values must be set.

Since my kodi system goes into sleep mode when idle I am running the script on a rasperry pi which is up 24x7. There is no wake-on-lan on email receipt since the time it takes to fully wake up the host and tv would probably not allow capturing the actual motion on screen. 

I also added an option to execute a local command on receipt of a security cam email, e.g., as in my case, to start the conversion of the security cam's rtsp video stream into a sequence of jpeg files to feed the 'Security Cam Overlay' addon.

For the curious people: The following command generates a snapshot jpeg file every 1/2 second (fps=2) from the rtsp input stream. 

    ffmpeg -nostdin -i rtsp://${security_cam_ip_address}:554/${stream} -f segment -segment_time 0.0001 -segment_format singlejpeg -segment_wrap 5 -vf fps=2 -vsync 0 ${snapshot_folder}/snapshot%d.jpg >/dev/null 2>&1

I let the output rotate over 5 files and then select the latest file via: 

    snapshot = $(ls -t ${snapshot_folder}/snapshot* | head -1)

If not copied directly the file can be sent to stdout:

    echo "Content-Type: image/jpeg"
    echo ""
    cat ${snapshot}



