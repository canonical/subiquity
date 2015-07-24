#!/bin/bash -x

CONFIGS="-c /tmp/subiquity-config.yaml -c /tmp/subiquity-postinst.yaml"
CMD="-v --showtrace install $CONFIGS cp:///"
CURTIN="/usr/local/curtin/bin/curtin"
OUTPUT="/tmp/.curtin_wrap_ran"
INSTALL_OK="Installation finished. No error reported."

if [ -e $CURTIN ]; then 
   $CURTIN $CMD | tee -a $OUTPUT
   RV=$?
else
   RV=1
   echo "$CURTIN not found" > $OUTPUT
   echo $CURTIN $CMD | tee -a $OUTPUT
fi

clear
if tail -n 2 $OUTPUT | grep -q "$INSTALL_OK"; then
    echo "Ubuntu Server is now installed, press any key to reboot into the new system."
    read a
    echo "Rebooting down after running $CURTIN $CMD"
    telinit 6
else
    echo "Error running curting, exiting..."
    exit 1;
fi
