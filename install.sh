#!/bin/bash

KDIR="${HOME}/klipper"
KENV="${HOME}/klippy-env"

if [ ! -d "$KDIR" ] && [ -d "/data/klipper" ]; then
    KDIR="/data/klipper"
fi
if [ ! -d "$KENV" ] && [ -d "/data/klippy-env" ]; then
    KENV="/data/klippy-env"
fi

BKDIR="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"

if [ ! -d "$KDIR" ]; then
    echo "idm: klipper directory doesn't exist"
    exit 1
fi

# Install IDM requirements in Klipper's environment when available.
echo "idm: installing python requirements to env, this may take 10+ minutes."
if [ -x "${KENV}/bin/pip" ]; then
    "${KENV}/bin/pip" install --break-system-packages -r "${BKDIR}/requirements.txt"
else
    python3 -m pip install --break-system-packages -r "${BKDIR}/requirements.txt"
fi

# Update links to Klipper extra modules.
echo "IDM: linking modules into klipper"
for file in idm.py scanner.py scanner_touch_mesh.py; do
    if [ -e "${KDIR}/klippy/extras/${file}" ]; then
        rm "${KDIR}/klippy/extras/${file}"
    fi
    ln -s "${BKDIR}/${file}" "${KDIR}/klippy/extras/${file}"
    if ! grep -q "klippy/extras/${file}" "${KDIR}/.git/info/exclude"; then
        echo "klippy/extras/${file}" >> "${KDIR}/.git/info/exclude"
    fi
done
echo "idm: installation successful."
