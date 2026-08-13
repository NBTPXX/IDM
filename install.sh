#!/bin/bash

KDIR="${KLIPPER_DIR:-}"
if [ -z "$KDIR" ]; then
    for candidate in /data/klipper "${HOME}/klipper"; do
        if [ -d "$candidate" ]; then
            KDIR="$candidate"
            break
        fi
    done
fi

BKDIR="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"

if [ -z "$KDIR" ] || [ ! -d "$KDIR" ]; then
    echo "idm: set KLIPPER_DIR to the Klipper directory"
    exit 1
fi

KENV="${KLIPPY_ENV:-${KDIR%/klipper}/klippy-env}"

# The /data Klipper installation manages its Python dependencies separately.
case "$KDIR" in
    /data/*)
        echo "idm: skipping python requirements for Klipper under /data"
        ;;
    *)
        echo "idm: installing python requirements to env, this may take 10+ minutes."
        if [ -x "${KENV}/bin/pip" ]; then
            "${KENV}/bin/pip" install --break-system-packages -r "${BKDIR}/requirements.txt"
        else
            python3 -m pip install --break-system-packages -r "${BKDIR}/requirements.txt"
        fi
        ;;
esac

# Update links to Klipper extra modules.
echo "IDM: linking modules into klipper"
for file in idm.py scanner.py scanner_touch_mesh.py; do
    if [ -e "${KDIR}/klippy/extras/${file}" ]; then
        rm "${KDIR}/klippy/extras/${file}"
    fi
    ln -s "${BKDIR}/${file}" "${KDIR}/klippy/extras/${file}"
    exclude_file="${KDIR}/.git/info/exclude"
    if [ -d "${KDIR}/.git/info" ]; then
        touch "$exclude_file"
        if ! grep -q "klippy/extras/${file}" "$exclude_file"; then
            echo "klippy/extras/${file}" >> "$exclude_file"
        fi
    fi
done
echo "idm: installation successful."
