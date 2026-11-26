#!/bin/bash

# slimy-update-snap.sh $old_snap $new_snap

set -eux

src="$(dirname "$(dirname "$(readlink -f "${0}")")")"
old="$(readlink -f "${1}")"
new="$(readlink -f "${2}")"

tmpdir="$(mktemp -d)"
cd "${tmpdir}"

_MOUNTS=()

do_mount_existing () {
    local mountpoint="${!#}"
    mount "$@"
    _MOUNTS=("${mountpoint}" "${_MOUNTS[@]+"${_MOUNTS[@]}"}")
}

do_mount () {
    local mountpoint="${!#}"
    mkdir "${mountpoint}"
    do_mount_existing "$@"
}

add_overlay() {
    local lower="$1"
    local mountpoint="$2"
    local work="$(mktemp -dp "${tmpdir}")"
    if [ -n "${3-}" ]; then
        local upper="${3}"
    else
        local upper="$(mktemp -dp "${tmpdir}")"
    fi
    chmod go+rx "${work}" "${upper}"
    do_mount -t overlay overlay \
        -o lowerdir="${lower}",upperdir="${upper}",workdir="${work}" \
        "${mountpoint}"
}


cleanup () {
    for m in "${_MOUNTS[@]+"${_MOUNTS[@]}"}"; do
        umount "${m}"
    done
    rm -rf "${tmpdir}"
}

trap cleanup EXIT

do_mount $old old

add_overlay old new

shopt -s nullglob
site_packages=(new/lib/python3.*/site-packages)
shopt -u nullglob
if [ "${#site_packages[@]}" -ne 1 ] ; then
    echo "expected one lib/python3.*/site-packages, found ${#site_packages[@]}" >&2
    exit 1
fi
py_site="${site_packages[0]}"

# The launcher is the interpreter that runs the server. The site-packages
# directory is the fallback when this snap has no subiquity-server script.
snap_py_site="${py_site#*python}"
snap_py_site="${snap_py_site%%/*}"
snap_py="${snap_py_site}"
if [ -f new/bin/subiquity-server ] ; then
    snap_py_launcher="$(grep -oE 'python3\.[0-9]+' new/bin/subiquity-server | head -1 || true)"
    snap_py_launcher="${snap_py_launcher#python}"
    if [ -n "${snap_py_launcher}" ] ; then
        snap_py="${snap_py_launcher}"
    fi
fi

# snapcraft.yaml is the Subiquity runtime pin. pyproject.toml only selects
# Black's target and is not used when the two differ.
subiquity_py="$(grep -oE 'python3\.[0-9]+' "${src}/snapcraft.yaml" | head -1 || true)"
subiquity_py="${subiquity_py#python}"
if [ -z "${subiquity_py}" ] ; then
    echo "could not read the Python pin from snapcraft.yaml" >&2
    exit 1
fi

rm -rf "${py_site}/curtin"
rm -rf "${py_site}/probert"

if [ -d "${py_site}/subiquity" ] ; then
    subiquity_dest="${py_site}"
    bin_dest=new/system_scripts/
elif [ -d new/bin/subiquity/subiquity ] ; then
    subiquity_dest=new/bin/subiquity
    bin_dest=new/bin/subiquity/system_scripts/
else
    echo "unrecognized snap" >&2
    exit 1
fi

rm -rf "${subiquity_dest}/subiquity"
rm -rf "${subiquity_dest}/subiquitycore"

(cd "${src}" && ./scripts/update-part.py curtin)
(cd "${src}" && ./scripts/update-part.py probert)

rsync -a --chown 0:0 $src/curtin/curtin "${py_site}"
rsync -a --chown 0:0 $src/probert/probert "${py_site}"
rsync -a --chown 0:0 $src/subiquity $src/subiquitycore $subiquity_dest
rsync -a --chown 0:0 $src/system_scripts/ $bin_dest

if [ "${snap_py}" != "${subiquity_py}" ] ; then
    if ! command -v black >/dev/null 2>&1 ; then
        echo "black is required to reformat injected sources for Python ${snap_py}" >&2
        exit 1
    fi
    before="$(mktemp -d)"
    cp -a "${subiquity_dest}/subiquity" "${subiquity_dest}/subiquitycore" "${before}/"
    # Black keeps an unparenthesized except list once it sees one, so a
    # py312 run does not put the parentheses back. Python before 3.14
    # cannot import that form.
    snap_py_minor="${snap_py#3.}"
    if [ "${snap_py_minor}" -lt 14 ] ; then
        python3 - "${subiquity_dest}/subiquity" "${subiquity_dest}/subiquitycore" <<'PY'
import pathlib, re, sys
pat = re.compile(r"^([ \t]*except[ \t]+)([^:\n]*?,[^:\n]*):[ \t]*$", re.M)
def repl(match):
    expr = match.group(2).strip()
    if expr.startswith("("):
        return match.group(0)
    return f"{match.group(1)}({expr}):"
for root in sys.argv[1:]:
    for path in pathlib.Path(root).rglob("*.py"):
        text = path.read_text()
        new = pat.sub(repl, text)
        if new != text:
            path.write_text(new)
PY
    fi
    black_target="py${snap_py//./}"
    black_cfg="$(mktemp)"
    cat > "${black_cfg}" <<EOF
[tool.black]
target-version = ['${black_target}']
EOF
    black --config "${black_cfg}" --target-version "${black_target}" \
        "${subiquity_dest}/subiquity" "${subiquity_dest}/subiquitycore"
    rm -f "${black_cfg}"
    if ! diff -rq "${before}/subiquity" "${subiquity_dest}/subiquity" >/dev/null \
        || ! diff -rq "${before}/subiquitycore" "${subiquity_dest}/subiquitycore" >/dev/null
    then
        echo "warning: injected subiquity and subiquitycore were rewritten for Python ${snap_py}." >&2
        echo "warning: this snap runs Python ${snap_py}, while subiquity is pinned to Python ${subiquity_py}. The unadjusted copy does not import on the snap's interpreter." >&2
    fi
    rm -rf "${before}"
fi

snapcraft pack new --output $new
