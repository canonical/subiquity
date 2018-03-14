#!/bin/bash

set -eux

# make-edge-iso.sh $old_iso $new_iso

INJECT_SNAP=$(readlink -f "$(dirname ${0})/inject-subiquity-snap.sh")

OLD_ISO="$(readlink -f "${1}")"
NEW_ISO="$(readlink -f "${2}")"

tmpdir="$(mktemp -d)"
cd "${tmpdir}"

cleanup () {
    rm -rf "${tmpdir}"
}

trap cleanup EXIT

snap download --channel edge subiquity
$INJECT_SNAP $OLD_ISO subiquity_*.snap $NEW_ISO
