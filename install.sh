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

if [ ! -d "$KDIR" ] || [ ! -d "$KENV" ]; then
    echo "idm: klipper or klippy env doesn't exist"
    exit 1
fi

# install idm requirements to env
echo "idm: installing python requirements to env, this may take 10+ minutes."
"${KENV}/bin/pip" install -r "${BKDIR}/requirements.txt"

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
