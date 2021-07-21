#!/bin/bash

set -eux

# make-edge-iso.sh $old_iso $new_iso

LIVEFS_EDITOR="${LIVEFS_EDITOR-$(readlink -f "$(dirname $(dirname ${0}))/livefs-editor")}"
[ -d $LIVEFS_EDITOR ] || git clone https://github.com/mwhudson/livefs-editor $LIVEFS_EDITOR

OLD_ISO="$(readlink -f "${1}")"
NEW_ISO="$(readlink -f "${2}")"

PYTHONPATH=$LIVEFS_EDITOR python3 -m livefs_edit $OLD_ISO $NEW_ISO --add-snap-from-store subiquity edge
