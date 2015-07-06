#!/bin/bash -x

CMD="-v --showtrace install -c /tmp/subiquity-config.yaml cp:///"
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

if tail -n 1 $OUTPUT | grep -q "$INSTALL_OK"; then
    echo "Curtin installed OK, shutting down (Press Any Key)"
    read a
    echo "Shutting down after running $CURTIN $CMD"
    telinit 0
else
    echo "Error running curting, exiting..."
    exit 1;
fi
