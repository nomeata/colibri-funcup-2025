#!/usr/bin/env bash

set -e

mkdir -p _flights

for id in $(jq -r '.[]["IDFlight"]' < _tmp/flights.json | sort -n ); do

  if [ ! -e "_flights/$id.igc.gz" ]; then
    echo "$id: fetching"
    wget \
      --no-verbose \
      --header 'Accept: application/x-igc' \
      --load-cookies _tmp/cookies.txt \
      --save-cookies _tmp/cookies.txt \
      --keep-session-cookies \
      "https://de.dhv-xc.de/flight/$id/igc" \
      -O "_flights/$id.igc"
    if file "_flights/$id.igc" | grep -q HTML
    then
      echo "This does not look like an igc file, aborting"
      exit 1
    fi
    gzip -9 "_flights/$id.igc"
  fi

done

for id in $(jq -r '.[] | select(.CountComments != "0") | .IDFlight' < _tmp/flights.json | sort -n ); do
  if [ ! -e "_flights/$id.comments.json" ]; then
    echo "$id: comments"
    wget \
        --no-verbose \
	--header 'Accept: application/x-igc' \
	--load-cookies _tmp/cookies.txt \
        --save-cookies _tmp/cookies.txt \
        --keep-session-cookies \
	"https://de.dhv-xc.de/api/fli/comments?fkflight=$id" \
	-O "_flights/$id.comments.json"
  fi
done
