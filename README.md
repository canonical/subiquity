# subiquity
> Ubuntu Server Installer

# building installer
`make installer`

# running installer
`make run`

# running the UI locally
`make ui-view`

with `--dry-run`

`make dryrun`

# overrides
```
make RELEASE=[wily, vivid, trusty] ARCH=[amd64, i386, armf, arm64, ppc64el] installer
make RELEASE=wily ARCH=arm64 run
```
