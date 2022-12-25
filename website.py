#!/usr/bin/env python3

# Generates the website

import json
import os
import jinja2
import math
import shutil
import datetime
import re
import pandas as pd
import folium

import constants

hike_and_fly_re = re.compile(r'hike', re.IGNORECASE)

from jinja2 import Environment, FileSystemLoader, select_autoescape
env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape()
)

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
    os.mkdir('schauinsland2022/out')
except FileExistsError:
    pass
shutil.copytree('templates/static', 'schauinsland2022/out/static', dirs_exist_ok=True)

flight_data = json.load(open('schauinsland2022/flights.json'))

flights = {}

# Group flights by pilot, read stats
for flight in flight_data['data']:
    id = flight['IDFlight']
    pid = flight['FKPilot']

    flight['stats'] = json.load(open(f'schauinsland2022/{id}.stats.json'))

    if pid not in flights:
        flights[pid] = []
    flights[pid].append(flight)

# Sort by date
for pid, pflights in flights.items():
    pflights.sort(key = lambda f: f['FlightStartTime'])

# Create per pilot website, and gather stats
pilots = []
pilottemplate = env.get_template("pilot.html")
sektor_pilots = {}
sektor_flights = {}
for pid, pflights in flights.items():
    name = pflights[0]['FirstName'] + ' ' + pflights[0]['LastName']
    covered = set()

    # stats
    stats = {
        'schauiflights': 0,
        'lindenflights': 0,
        'flighttime': 0,
        'hikes': 0,
        'fotos': 0,
        'sektoren': 0,
        'landepunkt1': 0,
        'landepunkt2': 0,
        'landepunkt3': 0,
        'drehrichtung': "",
        'drehueberschuss': 0,
        'left_turns': 0,
        'right_turns': 0,
    }


    data = {}
    data['lpradius1'] = constants.lpradius1
    data['lpradius2'] = constants.lpradius2
    data['lpradius3'] = constants.lpradius3
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
        if f['stats']['landepunktabstand'] < constants.lpradius1:
            stats['landepunkt1'] += 1
        elif f['stats']['landepunktabstand'] < constants.lpradius2:
            stats['landepunkt2'] += 1
        elif f['stats']['landepunktabstand'] < constants.lpradius3:
            stats['landepunkt3'] += 1

        if f['TakeoffWaypointName'] == "Schauinsland":
            stats['schauiflights'] += 1
        if f['TakeoffWaypointName'] == "Lindenberg":
            stats['lindenflights'] += 1

        is_hike = False
        if int(f['CountComments']) > 0:
            comments = json.load(open(f'schauinsland2022/{id}.comments.json'))
            for c in comments['data']:
                if bool(hike_and_fly_re.search(c["CommentText"])):
                    is_hike = True

        if is_hike:
            stats['hikes'] += 1

        has_fotos = int(f['HasPhotos']) > 0
        if has_fotos:
            stats['fotos'] += 1

        data['flights'].append({
          'n': n+1,
          'id': id,
          'datum': datetime.date.fromisoformat(f['FlightDate']).strftime("%d.%m."),
          'flugzeit': pretty_duration(f['FlightDuration']),
          'linkskreise': f['stats']['left_turns'],
          'rechtskreise': f['stats']['right_turns'],
          'landepunktabstand': pretty_landepunktabstand(f['stats']['landepunktabstand']),
          'neue_sektoren': " ".join(sorted(list(new))),
          'neue_sektoren_anzahl': len(new),
          'fotos': has_fotos,
          'hike': is_hike,
          'url': f"https://de.dhv-xc.de/flight/{id}",
        })

    # Finalize stats
    stats['sektoren'] = len(covered)
    if stats['left_turns'] > stats['right_turns']:
        stats['drehrichtung'] = "(nach links)"
        stats['drehueberschuss'] = stats['left_turns'] - stats['right_turns']
    elif stats['left_turns'] < stats['right_turns']:
        stats['drehrichtung'] = "(nach rechts)"
        stats['drehueberschuss'] = stats['right_turns'] - stats['left_turns']
    stats['prettyflighttime'] = pretty_duration(stats['flighttime'])

    for s in covered:
        if s not in sektor_pilots:
            sektor_pilots[s] = 0
        sektor_pilots[s] += 1

    # Calculate points
    points = {
        'schauiflights': stats['schauiflights'] * 5,
        'lindenflights': stats['lindenflights'] * 10,
        'flighttime': stats['flighttime'] // 60,
        'hikes': stats['hikes'] * 20,
        'fotos': stats['fotos'] * 50,
        'sektoren': stats['sektoren'] * 100,
        'landepunkt1': stats['landepunkt1'] * 100,
        'landepunkt2': stats['landepunkt2'] * 100,
        'landepunkt3': stats['landepunkt3'] * 100,
        'drehueberschuss': stats['drehueberschuss'] * -20,
    }
    points['total'] = sum(points.values())

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
    pilottemplate\
      .stream(data) \
      .dump(open(f'schauinsland2022/out/pilot{pid}.html', 'w'))


# Write main website
pilots.sort(key = lambda p: - p['points']['total'])
for i, p in enumerate(pilots):
    p['rank'] = i + 1

data = {}
data['pilots'] = pilots
env.get_template("index.html") \
  .stream(data) \
  .dump(open(f'schauinsland2022/out/index.html', 'w'))

# Write main map

m = folium.Map(
    location=constants.schaui,
    zoom_start=12,
    tiles = 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
    maxZoom = 17,
    attr = 'Map data: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, <a href="http://viewfinderpanoramas.org">SRTM</a> | Map style: &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (<a href="https://creativecommons.org/licenses/by-sa/3.0/">CC-BY-SA</a>)'
    )
# Draw sektoren
folium.features.Choropleth(
 geo_data = "sektoren.json",
 key_on = 'feature.id',
 columns = ['sektor', 'pilots'],
 data = pd.DataFrame({'sektor': sektor_pilots.keys(), 'pilots': sektor_pilots.values()}),
 fill_color = 'Blues',
 nan_fill_opacity = 0.2,
 legend_name = "Piloten, die diesen Sektor erreicht haben",
 overlay = False,
).add_to(m)


m.save("schauinsland2022/out/map.html")
