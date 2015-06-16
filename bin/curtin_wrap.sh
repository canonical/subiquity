#!/bin/bash

CMD="-v --showtrace install cp:///"
CURTIN="/usr/local/curtin/bin/curtin"
OUTPUT="/tmp/.curtin_wrap_ran"

if [ -e $CURTIN ]; then 
   $CURTIN $CMD | tee -a $OUTPUT
else
   echo "$CURTIN not found" > $OUTPUT
   echo $CURTIN $CMD | tee -a $OUTPUT
fi
echo "Shutting down after running $CURTIN $CMD"
telinit 0
