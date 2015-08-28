# subiquity
> Ubuntu Server Installer

# building installer
`make installer`

# running installer
`make run`

# running the UI locally in dry-run mode
`make`

# running the UI locally with a different machine profile (see examples/)
`MACHINE=examples/desktop.json make`

# overrides
```
make RELEASE=[wily, vivid, trusty] ARCH=[amd64, i386, armf, arm64, ppc64el] installer
make RELEASE=wily ARCH=arm64 run
```
