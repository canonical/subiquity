#!/bin/sh
tarball=$1

if [ -z "$tarball" ]
then
    echo Must specify path to launchpad-export-tar.gz as argument
    exit 1
fi

if [ ! -d po ]
then
    echo Please run from subiquity top level dir
    exit 1
fi

tar -xvf $tarball

for po in po/subiquity-*.po
do
    lang_po=$(echo $po | sed 's/subiquity-//')
    mv $po $lang_po
done

make i18n
git add po/*.po

