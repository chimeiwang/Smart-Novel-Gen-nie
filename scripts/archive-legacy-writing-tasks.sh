#!/bin/sh
set -eu
umask 077
PYTHONDONTWRITEBYTECODE=1
export PYTHONDONTWRITEBYTECODE
exec python3 "$(dirname "$0")/archive_legacy_writing_tasks.py" "$@"
