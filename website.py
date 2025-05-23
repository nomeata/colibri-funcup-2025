#!/usr/bin/env python3

# Generates the website

import json
import os
import jinja2
import math
import shutil
import datetime
import re
import numpy as np
import pandas as pd
import folium
import csv

import constants

now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

hike_and_fly_re = re.compile(r'\bhike\b', re.IGNORECASE)

from jinja2 import Environment, FileSystemLoader, select_autoescape
env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape()
)

def full_name(f):
    return f['FirstName'] + ' ' + f['LastName']

def pretty_duration(s):
    s = int(s)
    if s < 60:
        return f"{s}s"
    elif s < 60*60:
        return f"{math.floor(s/60)} min"
    else:
        return f"{math.floor(s/(60*60))} h {math.floor((s % (60*60))/60)} min"

def pretty_landepunktabstand(d):
    if d < 200:
        return f"{d} m"
    else:
        return ""

# prepare output directory

try:
    os.mkdir('_out')
except FileExistsError:
    pass
shutil.copytree('templates/static', '_out/static', dirs_exist_ok=True)

# Last year's points
old_data = json.load(open('data2024.json'))
old_points = {}
for pilot_data in old_data["pilots"]:
    if pilot_data["stats"]["flighttime"] >= 3600:
        old_points[pilot_data["pid"]] = pilot_data["points"]["total"]

# Last year's median
# (TODO)


flight_data = json.load(open('_tmp/flights.json'))

flights = {}
# Group flights by pilot, read stats
for flight in flight_data:
    id = flight['IDFlight']
    pid = flight['FKPilot']

    # add stats
    #print(f"Reading stats for {id}")
    flight['stats'] = json.load(open(f'_stats/{id}.stats.json'))

    if pid not in flights:
        flights[pid] = []
    flights[pid].append(flight)

# Sort by date
for pid, pflights in flights.items():
    pflights.sort(key = lambda f: f['FlightStartTime'])

# Latest flight
if flight_data:
    latest_flight = max([f['FlightStartTime'] for f in flight_data])
else:
    latest_flight = "(noch keinen gesehen)"

def finalize_stats(stats, covered):
    stats['sektoren'] = len(covered)
    if stats['left_turns'] > stats['right_turns']:
        stats['drehrichtung'] = "(nach links)"
        stats['drehueberschuss'] = stats['left_turns'] - stats['right_turns']
    elif stats['left_turns'] < stats['right_turns']:
        stats['drehrichtung'] = "(nach rechts)"
        stats['drehueberschuss'] = stats['right_turns'] - stats['left_turns']
    stats['prettyflighttime'] = pretty_duration(stats['flighttime'])

def points_of_stats(stats):
    points = {
        'schauiflights':   stats['schauiflights']   * 5,
        'lindenflights':   stats['lindenflights']   * 5,
        'flighttime':      stats['flighttime']      // 60,
        'hikes':           stats['hikes']           * 120,
        'fotos':           stats['fotos']           * 3,
        'sektoren':        stats['sektoren']        * 23,
        #'landepunkt1':     stats['landepunkt1']     * 100,
        #'landepunkt2':     stats['landepunkt2']     * 25,
        #'landepunkt3':     stats['landepunkt3']     * 5,
        'drehueberschuss': stats['drehueberschuss'] * -1,
        'sonderwertung':   stats['sonderwertung']   * 400,
    }
    points['total'] = sum(points.values())
    return points

# Create per pilot website, and gather stats
pilots = []
pilottemplate = env.get_template("pilot.html")
sektor_pilots = {}
sektor_flights = {}
all_flights = []
for pid, pflights in flights.items():
    name = full_name(pflights[0])
    covered = set()

    # stats
    stats = {
        'schauiflights': 0,
        'lindenflights': 0,
        'flighttime': 0,
        'hikes': 0,
        'fotos': 0,
        'sektoren': 0,
        #'landepunkt1': 0,
        #'landepunkt2': 0,
        #'landepunkt3': 0,
        'drehrichtung': "",
        'drehueberschuss': 0,
        'left_turns': 0,
        'right_turns': 0,
        'sonderwertung': 0,
    }

    # if pid == '10564':
    #     stats['sonderwertung'] += 1
    # if pid == '14869':
    #     stats['sonderwertung'] += 3
    # if pid == '12218':
    #     stats['sonderwertung'] += 2
    # if pid == '771':
    #     stats['sonderwertung'] += 1

    data = {}
    # data['lpradius1'] = constants.lpradius1
    # data['lpradius2'] = constants.lpradius2
    # data['lpradius3'] = constants.lpradius3
    data['flights'] = []
    for n, f in enumerate(pflights):
        id = f['IDFlight']

        sektoren = f['stats']['sektoren']
        for s in sektoren:
            if s not in sektor_flights:
                sektor_flights[s] = 0
            sektor_flights[s] += 1

        # Neue sektoren
        new = set(sektoren).difference(covered)
        covered.update(new)

        # update stats
        stats['flighttime'] += int(f['FlightDuration'])
        stats['left_turns'] += f['stats']['left_turns']
        stats['right_turns'] += f['stats']['right_turns']
        # if f['stats']['landepunktabstand'] < constants.lpradius1:
        #     stats['landepunkt1'] += 1
        # elif f['stats']['landepunktabstand'] < constants.lpradius2:
        #     stats['landepunkt2'] += 1
        # elif f['stats']['landepunktabstand'] < constants.lpradius3:
        #     stats['landepunkt3'] += 1

        if f['TakeoffWaypointName'] == "Schauinsland":
            stats['schauiflights'] += 1
        if f['TakeoffWaypointName'] == "Lindenberg":
            stats['lindenflights'] += 1

        is_hike = False
        if f['TakeoffWaypointName'] == "Schauinsland" and int(f['CountComments']) > 0:
            comments = json.load(open(f'_flights/{id}.comments.json'))
            for c in comments['data']:
                if c['FKAuthor'] == pid and bool(hike_and_fly_re.search(c["CommentText"])):
                    is_hike = True

        if is_hike:
            stats['hikes'] += 1

        has_fotos = int(f['HasPhotos']) > 0
        if has_fotos:
            stats['fotos'] += 1

        fd = {
          'pid': pid,
          'name': name,
          'n': n+1,
          'id': id,
          'datum': datetime.date.fromisoformat(f['FlightDate']).strftime("%d.%m."),
          'landeplatz': f['TakeoffWaypointName'],
          'flugzeit_sekunden': f['FlightDuration'],
          'flugzeit': pretty_duration(f['FlightDuration']),
          'linkskreise': f['stats']['left_turns'],
          'rechtskreise': f['stats']['right_turns'],
          #'landepunktabstand_meter': f['stats']['landepunktabstand'],
          #'landepunktabstand': pretty_landepunktabstand(f['stats']['landepunktabstand']),
          'neue_sektoren': " ".join(sorted(list(new))),
          'neue_sektoren_anzahl': len(new),
          'fotos': has_fotos,
          'hike': is_hike,
          'url': f"https://de.dhv-xc.de/flight/{id}",
        }
        data['flights'].append(fd)
        all_flights.append(fd)

    # Finalize stats
    finalize_stats(stats, covered)

    # Sektor heat map
    for s in covered:
        if s not in sektor_pilots:
            sektor_pilots[s] = 0
        sektor_pilots[s] += 1

    # Calculate points
    points = points_of_stats(stats)

    # Relative points
    if pid in old_points:
        points["old"] = old_points[pid]
        points["relative"] = points["total"] / old_points[pid]
    else:
        points["relative"] = None

    pilots.append({
        'pid': pid,
        'name': name,
        'stats': stats,
        'points': points,
    })

    # Write per-pilot website
    data['pid'] = pid
    data['name'] = name
    data['stats'] = stats
    data['points'] = points
    data['now'] = now
    data['latest_flight'] = latest_flight
    data['count_flight'] = len(flight_data)
    pilottemplate\
      .stream(data) \
      .dump(open(f'_out/pilot{pid}.html', 'w'))


# Sort pilots
pilots.sort(key = lambda p: - p['points']['total'])
for i, p in enumerate(pilots):
    p['rank'] = i + 1

pilots_new = [ p.copy() for p in pilots if p['points']["relative"] is None ]
for i, p in enumerate(pilots_new):
    p['rank'] = i + 1

pilots_rel = [ p.copy() for p in pilots if p['points']["relative"] is not None ]
pilots_rel.sort(key = lambda p: - p['points']['relative'])
for i, p in enumerate(pilots_rel):
    p['rank'] = i + 1

# Turn statistics
turn_stats = {
  'least_rel_diff': min(
    [ (p['name'], p['pid'],
      100 * abs(p['stats']['left_turns'] - p['stats']['right_turns']) / \
      (p['stats']['left_turns'] + p['stats']['right_turns']))
    for p in pilots if (p['stats']['left_turns'] + p['stats']['right_turns']) > 100
    ], key = lambda pair: pair[2]),
  'max_rel_diff_left': max(
    [ (p['name'], p['pid'],
      100 * (p['stats']['left_turns'] - p['stats']['right_turns']) / \
      (p['stats']['left_turns'] + p['stats']['right_turns']))
    for p in pilots if (p['stats']['left_turns'] + p['stats']['right_turns']) > 100
    ], key = lambda pair: pair[2]),
  'max_abs_diff_left': max(
    [ (p['name'], p['pid'], (p['stats']['left_turns'] - p['stats']['right_turns']))
    for p in pilots if (p['stats']['left_turns'] + p['stats']['right_turns']) > 100
    ], key = lambda pair: pair[2]),
  'max_rel_diff_right': max(
    [ (p['name'], p['pid'],
      100 * (p['stats']['right_turns'] - p['stats']['left_turns']) / \
      (p['stats']['left_turns'] + p['stats']['right_turns']))
    for p in pilots if (p['stats']['left_turns'] + p['stats']['right_turns']) > 100
    ], key = lambda pair: pair[2]),
  'max_abs_diff_right': max(
    [ (p['name'], p['pid'], (p['stats']['right_turns'] - p['stats']['left_turns']))
    for p in pilots if (p['stats']['left_turns'] + p['stats']['right_turns']) > 100
    ], key = lambda pair: pair[2]),
}

# Write main website
data = {}
data['pilots'] = pilots
data['pilots_new'] = pilots_new
data['pilots_rel'] = pilots_rel
data['now'] = now
data['latest_flight'] = latest_flight
data['count_flight'] = len(flight_data)
data['turn_stats'] = turn_stats
env.get_template("index.html") \
  .stream(data) \
  .dump(open(f'_out/index.html', 'w'))

# Write main data as CSV
with open('_out/data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=4)

# Write Flight data to CSV file

with open('flights.csv', 'w', newline='') as csvfile:
    w = csv.DictWriter(csvfile, all_flights[0].keys())
    w.writeheader()
    for fd in all_flights:
        w.writerow(fd)
