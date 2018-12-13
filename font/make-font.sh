#!/bin/bash
set -eux
SUBIQUITY_FONT_DIR=$(realpath $(dirname $0))
tmp=$(mktemp -d)
cleanup () {
    rm -rf $tmp
}
trap cleanup EXIT
apt source console-setup
cd console-setup-*/Fonts
./bdf2psf \
    --log ${SUBIQUITY_FONT_DIR}/subiquity.log \
    ${SUBIQUITY_FONT_DIR}/subiquity.bdf+./bdf/georgian16.bdf+./bdf/unifont.bdf+./bdf/h16.bdf+./bdf/etl16-unicode.bdf \
    ./standard.equivalents+${SUBIQUITY_FONT_DIR}/subiquity.equivalents \
    ${SUBIQUITY_FONT_DIR}/subiquity.set+./ascii.set+./linux.set+./fontsets/Uni2.512+:./useful.set \
    512 \
    ${SUBIQUITY_FONT_DIR}/subiquity.psf

