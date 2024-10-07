#!/bin/bash -eux

# modify an existing subiquity-like snap in the live environment.
# change this script down below to add bindpatch call(s) and run it in the live
# environment.

if [ "$(id -u)" != "0" ] ; then
    echo "root required"
    exit 1
fi

if [ -d "/snap/subiquity" ] ; then
    SNAPNAME=subiquity
    INTERMEDIATE=lib/python3.12/site-packages
elif [ -d "/snap/ubuntu-desktop-installer" ] ; then
    SNAPNAME=ubuntu-desktop-installer
    INTERMEDIATE=bin/subiquity
elif [ -d "/snap/ubuntu-desktop-bootstrap" ] ; then
    SNAPNAME=ubuntu-desktop-bootstrap
    INTERMEDIATE=bin/subiquity
else
    echo "subiquity-like snap not found"
    exit 1
fi

SNAP="/snap/$SNAPNAME/current"

function bindpatch
{
    input="$1"
    shift
    [ "$#" = "0" ] && set -- "vi"
    tmp_file=/tmp/$(echo "$input" | sed 's,/,_,g')
    cp "$SNAP/$INTERMEDIATE/$input" "$tmp_file"
    "$@" "$tmp_file"
    mount --bind "$tmp_file" "$SNAP/$INTERMEDIATE/$input"
}

echo "modify the script to configure a call to bindpatch"
exit 1

# example 1: edit subiquity/server/server.py with vi
# bindpatch subiquity/server/server.py

# example 2: run command foo on the file
# bindpatch path/to/file.py foo

snap restart "$SNAPNAME"
