#!/bin/bash
# Daily pipeline run, started by launchd (see the README's Daily schedule section).
# Can also be run by hand: scripts/daily_run.sh

# launchd starts jobs with a minimal PATH that doesn't include these tools.
export PATH="$HOME/.docker/bin:/opt/homebrew/bin:$HOME/.local/bin:/usr/bin:/bin"

cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
exec >> logs/daily.log 2>&1

echo "=== $(date '+%F %T %Z') started"

make up && make ingest && make transform
status=$?

echo "=== $(date '+%F %T %Z') finished with exit code $status"

if [ "$status" -ne 0 ]; then
    osascript -e "display notification \"Exit code $status. See logs/daily.log.\" with title \"Flights pipeline failed\""
fi

exit "$status"
