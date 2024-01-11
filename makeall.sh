#!/usr/bin/env bash

set -e


./prepare.sh
./fetch-flights.sh
./fetch-igc.sh
./update-flightstats.py

./sektoren-map.py
./website.py
