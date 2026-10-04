#!/bin/sh
# Wrapper for the python script that summarizes the last 12 (by 
# default) hours of Mastodon posts and saves to an XML format file on a
# remote server. Subscribe to the XML file with an RSS reader to catch up with
# your Mastodon timeline at the start and end of the day or whenever you 
# schedule your summary

set -eu

# Set private variables in .env.

BASE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
HOMEDIR=$(dirname -- "$BASE")
PY="$BASE/venv/bin/python"

ENV_FILE="$BASE/.env"
DIGEST_ARGS=''
FEED_ARGS=''
OUT_DIR_ARG=''

# Forwarded flags are collected shell quoted, so values may contain spaces.
# $1 is digest, feed, or both; the rest are the words to forward.
forward() {
    _to=$1; shift
    for _arg; do
        _q="'$(printf %s "$_arg" | sed "s/'/'\\\\''/g")'"
        [ "$_to" = feed ] || DIGEST_ARGS="$DIGEST_ARGS $_q"
        [ "$_to" = digest ] || FEED_ARGS="$FEED_ARGS $_q"
    done
}

need_value() {
    [ "$2" -ge 2 ] || { echo "$1 needs a value" >&2; exit 2; }
}

while [ $# -gt 0 ]; do
    case $1 in
        --env_file)
            need_value "$1" $#; ENV_FILE=$2; shift 2 ;;
        --env_file=*)
            ENV_FILE=${1#--env_file=}; shift ;;

        # mastodon-digest.py only
        --hours|--provider|--model|--output)
            need_value "$1" $#; forward digest "$1" "$2"; shift 2 ;;
        --hours=*|--provider=*|--model=*|--output=*)
            forward digest "$1"; shift ;;

        # build_feed.py only
        --feed-url)
            need_value "$1" $#; forward feed "$1" "$2"; shift 2 ;;
        --feed-url=*)
            forward feed "$1"; shift ;;

        # both, and it also moves what gets copied and pruned below
        --output-dir)
            need_value "$1" $#; OUT_DIR_ARG=$2; forward both "$1" "$2"; shift 2 ;;
        --output-dir=*)
            OUT_DIR_ARG=${1#--output-dir=}; forward both "$1"; shift ;;

        -h|--help)
            echo "usage: $0 [--env_file /path/to/.env] [--output-dir DIR]"
            echo "          [--hours N] [--provider NAME] [--model NAME]"
            echo "          [--output verbose|terse] [--feed-url URL]"
            echo "flags other than --env_file are forwarded to the python scripts"
            exit 0 ;;
        *)
            echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

# Validate the log path before redirecting output to it.

case $ENV_FILE in
    /*) ;;
    *) echo "--env_file must be a fully qualified path: $ENV_FILE" >&2; exit 2 ;;
esac
[ -f "$ENV_FILE" ] || { echo "no such env file: $ENV_FILE" >&2; exit 2; }

exec >> "$BASE/run.log" 2>&1
echo "=== $(date) ==="

echo "env: $ENV_FILE"
set -a; . "$ENV_FILE"; set +a
[ -z "$OUT_DIR_ARG" ] || OUT_DIR=$OUT_DIR_ARG

: "${OUT_DIR:?not set in $ENV_FILE}"
: "${FEED_URL:?not set in $ENV_FILE}"
: "${DEST:?not set in $ENV_FILE}"
: "${SSH_KEY:?not set in $ENV_FILE}"

eval "\"\$PY\" \"\$BASE/mastodon-digest.py\"$DIGEST_ARGS"
eval "\"\$PY\" \"\$BASE/build_feed.py\"$FEED_ARGS"

scp -i "$SSH_KEY" -o StrictHostKeyChecking=yes "$OUT_DIR/atom.xml" "$DEST"

echo done
