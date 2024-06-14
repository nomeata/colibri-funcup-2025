#!/usr/bin/env python3

from itertools import combinations
import os
import subprocess
import json
import shlex

os.makedirs("_stats", exist_ok=True)
with open("_tmp/flights.json") as f:
    flights_data = json.load(f)

# Group flights by date
flights_by_date = {}
for flight in flights_data:
    date = flight["FlightDate"]
    if date not in flights_by_date:
        flights_by_date[date] = []
    flights_by_date[date].append(flight)

scripttime1 = max([
    os.path.getmtime("./flightstats.py"),
    os.path.getmtime("./constants.py"),
])
scripttime2 = max([
    os.path.getmtime("./kurbeln.py"),
    os.path.getmtime("./constants.py"),
])

# Recalculate stats for all flights for which new data from that day is present
for date in sorted(flights_by_date.keys()):
    flights = flights_by_date[date]
    print(f"Date: {date}")
    newest = max([os.path.getmtime(f"_flights/{flight['IDFlight']}.igc.gz") for flight in flights])

    for flight in flights:
        id = flight["IDFlight"]
        stats_file = f"_stats/{id}.stats.json"
        stats_file_tmp = f"_stats/{id}.stats.json.tmp"
        if not os.path.exists(stats_file) or \
            os.path.getmtime(stats_file) < scripttime1 or \
            os.path.getmtime(stats_file) < os.path.getmtime(f"_flights/{id}.igc.gz"):
            print(f"Stats for flight {id}")
            args = ["./flightstats.py", "-i", f"_flights/{id}.igc.gz"]
            subprocess.run(args, stdout=open(stats_file_tmp, "w"), check=True)
            subprocess.run(["mv", stats_file_tmp, stats_file])

    for flight1, flight2 in combinations(flights,2):
        if flight1["FlightEndTime"] < flight2["FlightStartTime"]:
            continue
        if flight2["FlightEndTime"] < flight1["FlightStartTime"]:
            continue
        id1 = flight1["IDFlight"]
        id2 = flight2["IDFlight"]
        stats_file = f"_stats/{id1}-{id2}.stats.json"
        if not os.path.exists(stats_file) or \
            os.path.getmtime(stats_file) < scripttime2 or \
            os.path.getmtime(stats_file) < os.path.getmtime(f"_flights/{id1}.igc.gz") or \
            os.path.getmtime(stats_file) < os.path.getmtime(f"_flights/{id2}.igc.gz"):
            print(f"Kurbelstats for flights {id1} and {id2}")
            args = ["./kurbeln.py", f"_flights/{id1}.igc.gz", f"_flights/{id2}.igc.gz"]
            # print(shlex.join(args))
            subprocess.run(args, stdout=open(stats_file_tmp, "w"), check=True)
            subprocess.run(["mv", stats_file_tmp, stats_file])
