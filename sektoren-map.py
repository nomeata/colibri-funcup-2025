#!/usr/bin/env python3

from itertools import combinations
import pandas as pd
import folium
import math
import sys
import subprocess
import igc
import json
import os

import constants
from constants import *
import kurbeln
import sektoren
import landepunkt


def write_map(outfile, flights, all=False, show_tracks=True):
    print(f"Writing {outfile}")

    # Read flights
    tracks = []
    seen = set()
    sektor_piloten = {}
    lps = []
    for flight in flights:
        id = flight['IDFlight']
        pid = flight['FKPilot']

        # Track
        if show_tracks:
            gunzip = subprocess.Popen(('gunzip',), stdin=open(f'_flights/{id}.igc.gz'), stdout=subprocess.PIPE)
            track = igc.parse(gunzip.stdout)
            if all:
                # reduce track complexity when showing all flights
                track = track[::5]
            tracks += [ [(round(p['lat'],5), round(p['lon'],5)) for p in track ] ]

        # Remember landepunkte and segments
        stats = json.load(open(f'_stats/{id}.stats.json'))
        for sektor in stats['sektoren']:
            if sektor not in sektor_piloten:
                sektor_piloten[sektor] = set()
            sektor_piloten[sektor].add(pid)
        lps += [ stats['landepunkt'] ]
        seen.update(stats['sektoren'])

    # Create map
    m = folium.Map(
        location=schaui,
        zoom_start=12,
        max_zoom=19,
        tiles = None,
        )

    tile_layer = folium.TileLayer(
        tiles = 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
        attr = 'Map data: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, <a href="http://viewfinderpanoramas.org">SRTM</a> | Map style: &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (<a href="https://creativecommons.org/licenses/by-sa/3.0/">CC-BY-SA</a>)',
        max_native_zoom=17,
        name='OpenTopoMap',
        control=False,
    )
    tile_layer.add_to(m)


    # Draw sektoren

    if all:
        folium.features.Choropleth(
            geo_data = "sektoren.json",
            key_on = 'feature.id',
            columns = ['sektor', 'pilots'],
            data = pd.DataFrame({'sektor': sektor_piloten.keys(), 'pilots': [len(s) for s in sektor_piloten.values()]}),
            fill_color = 'Blues',
            nan_fill_opacity = 0.2,
            legend_name = "Piloten, die diesen Sektor erreicht haben",
            overlay = False,
        ).add_to(m)
    else:
        sektoren_layer = folium.FeatureGroup(name="Sektoren").add_to(m)
        # Only draw those that are actually seen
        def style_function(feature):
            if feature['id'] in seen:
                return { 'weight': 2 }
            else:
                return {'fill': False, 'stroke': False}
        folium.features.GeoJson(
        data = "sektoren.json",
        style_function = style_function,
        overlay = False,
        ).add_to(sektoren_layer)

    # Draw target
    if False:
        target_layer = folium.FeatureGroup(name="Zielscheibe").add_to(m)
        for r in [lpradius1, lpradius2, lpradius3]:
            folium.Circle(radius = r, location=constants.landepunkt, color = 'green', fill=True).add_to(target_layer)

    # Draw tracks
    if show_tracks:
        track_layer = folium.FeatureGroup(name="Tracks").add_to(m)
        for track in tracks:
            folium.PolyLine([track], color="crimson").add_to(track_layer)

    # Draw Landepunkt
    if False:
        landing_layer = folium.FeatureGroup(name="Landepunkte").add_to(m)
        for lp in lps:
            folium.Circle(radius = 3, location = lp, color="black", fill=True, fill_opacity = 1, stroke=False).add_to(landing_layer)

    # Draw Meetings
    kurbel_layer = folium.FeatureGroup(name="Gekurbel").add_to(m)
    if all and not show_tracks:
        for flight1, flight2 in combinations(flights, 2):
            data = kurbeln.load(flight1, flight2)
            if data:
                id1 = flight1['IDFlight']
                id2 = flight2['IDFlight']
                folium.Marker(
                    location = (data['lat2'], data['lon2']),
                    popup=folium.Popup(
                        html = f"🔄 {flight1['FirstName']} {flight1['LastName']} and "
                            f"{flight2['FirstName']} {flight2['LastName']} ({data['duration']} s)",
                        parse_html=False),
                    icon=folium.Icon(icon='refresh'),
                ).add_to(kurbel_layer)

                gunzip = subprocess.Popen(('gunzip',), stdin=open(f'_flights/{id1}.igc.gz'), stdout=subprocess.PIPE)
                track1 = igc.parse(gunzip.stdout)
                track1 = track1[data['index_start1']:data['index_end1']]
                track1 = [(round(p['lat'],5), round(p['lon'],5)) for p in track1 ]
                folium.PolyLine([track1], color="crimson").add_to(kurbel_layer)

                gunzip = subprocess.Popen(('gunzip',), stdin=open(f'_flights/{id2}.igc.gz'), stdout=subprocess.PIPE)
                track2 = igc.parse(gunzip.stdout)
                track2 = track2[data['index_start2']:data['index_end2']]
                track2 = [(round(p['lat'],5), round(p['lon'],5)) for p in track2 ]
                folium.PolyLine([track2], color="blue").add_to(kurbel_layer)
    if not all:
        for flight in flights:
            for other_flight in all_flights:
                data = kurbeln.load(flight, other_flight)
                if data:
                    other_id = other_flight['IDFlight']
                    folium.Marker(
                        location = (data['lat2'], data['lon2']),
                        popup=folium.Popup(
                            html = f"🔄 {other_flight['FirstName']} {other_flight['LastName']} ({data['duration']} s)",
                            parse_html=False),
                        icon=folium.Icon(icon='refresh'),
                    ).add_to(kurbel_layer)
                    gunzip = subprocess.Popen(('gunzip',), stdin=open(f'_flights/{other_id}.igc.gz'), stdout=subprocess.PIPE)
                    track = igc.parse(gunzip.stdout)
                    track = track[data['index_start2']:data['index_end2']]
                    track = [(round(p['lat'],5), round(p['lon'],5)) for p in track ]
                    folium.PolyLine([track], color="blue").add_to(kurbel_layer)

    if not all: # does not work well with Choropleth
        folium.LayerControl(collapsed = False).add_to(m)

    m.save(outfile)

# Read flight data, grouped by pilot

print("Reading _tmp/flights.json")
flight_data = json.load(open('_tmp/flights.json'))

flights = {}
all_flights = []

for flight in flight_data:
    pid = flight['FKPilot']

    if pid not in flights:
        flights[pid] = []
    flights[pid].append(flight)
    all_flights.append(flight)

for pid, pflights in flights.items():
    if len(sys.argv) > 1:
        if pid not in sys.argv[1:]:
            continue

    write_map(f"_out/map{pid}.html", pflights)

if len(sys.argv) == 1 or "map" in sys.argv:
    write_map(f"_out/map.html", all_flights, all= True, show_tracks = False)
if len(sys.argv) == 1 or "all" in sys.argv:
    write_map(f"_out/map_all.html", all_flights, all = True, show_tracks = True)

