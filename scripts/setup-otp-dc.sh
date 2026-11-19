#!/usr/bin/env bash
# Builds an OpenTripPlanner graph for Washington, DC from WMATA's schedules and OpenStreetMap,
# then prints the command that starts the trip planner. Rerun weekly to pick up schedule changes.
#
#   WMATA_API_KEY=... scripts/setup-otp-dc.sh [data-dir]
set -euo pipefail

: "${WMATA_API_KEY:?Set WMATA_API_KEY to your free key from https://developer.wmata.com}"
OTP_IMAGE="opentripplanner/opentripplanner:${OTP_VERSION:-2.8.1}"
MEMORY="${OTP_MEMORY:-3g}"
DIR="${1:-otp-data}"

mkdir -p "$DIR"
DIR="$(cd "$DIR" && pwd)"

echo "Downloading DC street map..."
curl -fL --progress-bar -o "$DIR/dc.osm.pbf" \
  https://download.geofabrik.de/north-america/us/district-of-columbia-latest.osm.pbf

echo "Downloading WMATA bus and rail schedules..."
# OpenTripPlanner only picks up schedule files with "gtfs" in the name.
curl -fL --progress-bar -H "api_key: $WMATA_API_KEY" -o "$DIR/wmata-bus-gtfs.zip" \
  https://api.wmata.com/gtfs/bus-gtfs-static.zip
curl -fL --progress-bar -H "api_key: $WMATA_API_KEY" -o "$DIR/wmata-rail-gtfs.zip" \
  https://api.wmata.com/gtfs/rail-gtfs-static.zip

echo "Building the trip planner graph (a few minutes)..."
docker run --rm -e JAVA_TOOL_OPTIONS="-Xmx$MEMORY" -v "$DIR:/var/opentripplanner" "$OTP_IMAGE" --build --save

cat <<EOF

Done. Start the trip planner (it keeps running and restarts with Docker):

  docker rm -f otp 2>/dev/null; docker run -d --name otp --restart unless-stopped \\
    -p 127.0.0.1:8080:8080 -e JAVA_TOOL_OPTIONS="-Xmx$MEMORY" \\
    -v "$DIR:/var/opentripplanner" $OTP_IMAGE --load --serve

It's ready when http://127.0.0.1:8080 shows the OpenTripPlanner page.
EOF
