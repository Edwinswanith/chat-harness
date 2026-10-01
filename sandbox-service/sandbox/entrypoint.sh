#!/bin/sh
set -eu
chown sandbox:sandbox /output
exec setpriv --reuid="$(id -u sandbox)" --regid="$(id -g sandbox)" --clear-groups -- "$@"
