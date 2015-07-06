#!/bin/bash -x

CMD="-v --showtrace install -c /tmp/subiquity-config.yaml cp:///"
CURTIN="/usr/local/curtin/bin/curtin"
OUTPUT="/tmp/.curtin_wrap_ran"

if [ -e $CURTIN ]; then 
   $CURTIN $CMD | tee -a $OUTPUT
   RV=$?
else
   RV=1
   echo "$CURTIN not found" > $OUTPUT
   echo $CURTIN $CMD | tee -a $OUTPUT
fi
if [ $RV == 0 ]; then
    echo "Shutting down after running $CURTIN $CMD"
    #telinit 0
else
    echo "Error running curting, exiting..."
    exit 1;
fi
