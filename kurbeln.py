#!/usr/bin/env python3

import itertools
import math
import constants
import sys
import json
import argparse
import igc
import subprocess
import os

MAX_DISTANCE = 250
CONST_DISTANCE_TOLERANCE = 50
ALT_TOLERANCE = 50
MIN_SECONDS = 60

def add_index(track):
    for i in range(len(track)):
        track[i]['index'] = i

# convert WGS-84 coordinates to cartesian coordinates (in meters) relative to schaui
def wgs84_to_cartesian(track):
    lat_schaui, lon_schaui = constants.schaui
    for t in track:
        R = 6371*1000  # Radius of the Earth in meters

        lat_rad = math.radians(t['lat'])
        lon_rad = math.radians(t['lon'])
        lat_schaui_rad = math.radians(lat_schaui)
        lon_schaui_rad = math.radians(lon_schaui)

        t['x'] = (lon_rad - lon_schaui_rad) * R * math.cos(lat_schaui_rad)
        t['y'] = (lat_rad - lat_schaui_rad) * R

# find track entries that are two seconds apart and fill them in
def fix_track(track, verbose):
    out = []
    i = 0
    for i in range(len(track)):
        out.append(track[i])
        if i + 1 < len(track) and track[i+1]['time'] == track[i]['time'] + 2:
            if verbose:
                print(f"filling gap between {track[i]['time']} and {track[i+1]['time']}")
            t = track[i]
            t2 = track[i+1]
            out.append({
                'time': t['time'] + 1,
                'lat': (t['lat'] + t2['lat'])/2,
                'lon': (t['lon'] + t2['lon'])/2,
                'alt': (t['alt'] + t2['alt'])/2,
                'x': (t['x']+t2['y'])/2,
                'y': (t['y']+t2['y'])/2,
                'index': t['index'],
            })
    return out

# checks that the time field increments by one second for each entry
def check_track(track, verbose):
    bad = 0
    for i in range(1, len(track)):
        if track[i]['time'] - track[i-1]['time'] != 1:
            bad += 1
    ratio = bad / len(track)
    if verbose:
        print(f"bad ratio: {ratio*100:.2f}% ({bad}/{len(track)})")
    return ratio < 0.05

# finds common sequences with time increasing by the second
def join_tracks(track1, track2):
    assert(track1 != track2)
    # early exit if they do not overlap in time
    if track1[-1]['time'] < track2[0]['time']:
        return []
    if track2[-1]['time'] < track1[0]['time']:
        return []
    i = 0
    j = 0
    segments = []
    out_track1 = []
    out_track2 = []
    next_time = None
    while i < len(track1) and j < len(track2):
        if track1[i]['time'] == track2[j]['time'] and \
            (next_time is None or track1[i]['time'] == next_time):
            # extend segment
            out_track1.append(track1[i])
            out_track2.append(track2[j])
            # TODO: add back when the rest works
            next_time = track1[i]['time'] + 1
            i += 1
            j += 1
        else:
            # segment done, store if present
            if out_track1 and out_track2:
                segments.append((out_track1, out_track2))
                out_track1 = []
                out_track2 = []
            # keep searching for next segment
            next_time = None
            if track1[i]['time'] < track2[j]['time']:
                i += 1
            else:
                j += 1
    if out_track1 and out_track2:
        segments.append((out_track1, out_track2))
    return segments

# adds distance, alt difference and direction of travel
def segment_data(segment):
    track1 = segment[0]
    track2 = segment[1]
    assert(track1 != track2)
    out = []
    for i in range(len(track1)):
        t1 = track1[i]
        t2 = track2[i]
        r = { "t1": t1, "t2": t2, }

        r["alt_distance"] = t1['alt'] - t2['alt']

        xrel = t1['x'] - t2['x']
        yrel = t1['y'] - t2['y']
        r["distance"] = math.sqrt(xrel**2 + yrel**2)

        if i + 1 < len(track1):
            t1b = track1[i+1]
            t2b = track2[i+1]
            dx1 = t1b['x'] - t1['x']
            dy1 = t1b['y'] - t1['y']
            bearing1 = math.degrees(math.atan2(dy1, dx1))
            dx2 = t2b['x'] - t2['x']
            dy2 = t2b['y'] - t2['y']
            bearing2 = math.degrees(math.atan2(dy2, dx2))

            r["bearing"] = abs((360 + bearing1 - bearing2) % 360 - 180)
        else:
            r["bearing"] = 0
        
        r["good"] = \
            r["alt_distance"] <= ALT_TOLERANCE and \
            r["distance"] <= MAX_DISTANCE
        
        # r["bearing"] <= BEARING_TOLERANCE

        
        out.append(r)
    return out

# splits segments into subsequence that are `is_good`
def nearby_tracks(segments, verbose):
    out = []
    for segment in segments:
        data = segment_data(segment)
        groups = [ (k, list(s)) for k, s in itertools.groupby(data, lambda x: x["good"])]
        for k, s in groups:
            if k: out.append(s)
        
        for i in range(1,len(groups)-1):
            s = groups[i][1]
            if len(s) < 30 and verbose:
                print(f"discarding {len(s)} bad entries betwen {len(groups[i-1][1])} and {len(groups[i+1][1])} good entries")
                for r in s:
                    print(f'distance: {r["distance"]:.1f} alt_distance: {r["alt_distance"]:.1f} bearing: {r["bearing"]:.1f}')
    return out

# finds longest sequence with distance constant (up to 40m)
def longest_constant_distance(segments, verbose):
    best = None
    for seg in segments:
        for i in range(len(seg)):
            r = seg[i]
            d = r["distance"]
            mind = d
            maxd = d
            for j in range(i+1, len(seg)):
                if j - i > MIN_SECONDS and (not best or j - i > len(best)):
                    best = seg[i:j]

                d = seg[j]["distance"]
                if d < mind:
                    mind = d
                if d > maxd:
                    maxd = d
                if maxd - mind > CONST_DISTANCE_TOLERANCE:
                    if verbose:
                        print(f"breaking at {i} - {j} with distance {maxd - mind:.1f}")
                    break

                # check that at least 1/4 of tracks shows pilots moving in opposite directions
                # this distinguishes kurbeln from just flying together
                if j - i >= MIN_SECONDS:
                    if 4 * sum(1 for r in seg[i:j] if r["bearing"] < 90) < (j-i):
                        if verbose:
                            print(f"breaking at {i} - {j} with not enough opposing bearings")
                        break

    return best

def kurbeln(track1, track2, verbose):
    if not check_track(track1, verbose):
        if verbose: print("track1 is not valid")
        return None
    if not check_track(track2, verbose):
        if verbose: print("track2 is not valid")
        return None

    add_index(track1)
    add_index(track2)
    wgs84_to_cartesian(track1)
    wgs84_to_cartesian(track2)
    track1 = fix_track(track1, verbose)
    track2 = fix_track(track2, verbose)

    segments = join_tracks(track1, track2)
    if verbose:
        print(f"found {len(segments)} common segment of lengths {[len(s[0]) for s in segments]}")

    segments = nearby_tracks(segments, verbose)
    if verbose:
        print(f"found {len(segments)} nearby segment of lengths {[len(s) for s in segments]}")

    segments = [ s for s in segments if len(s) >= MIN_SECONDS ]
    if verbose:
        print(f"found {len(segments)} long enough segment of lengths {[len(s) for s in segments]}")

    best = longest_constant_distance(segments, verbose)
    if best:
        return {
            'index_start1': best[0]["t1"]['index'],
            'index_start2': best[0]["t2"]['index'],
            'index_end1': best[-1]["t1"]['index']+1,
            'index_end2': best[-1]["t2"]['index']+1,
            'duration': best[-1]["t1"]['time'] - best[0]["t1"]['time'],
            'lat1': best[-1]["t1"]['lat'],
            'lon1': best[-1]["t1"]['lon'],
            'lat2': best[-1]["t2"]['lat'],
            'lon2': best[-1]["t2"]['lon'],
        }
    else:
        return None

def flip_stats(stats):
    return {
        'index_start1': stats['index_start2'],
        'index_start2': stats['index_start1'],
        'index_end1': stats['index_end2'],
        'index_end2': stats['index_end1'],
        'duration': stats['duration'],
        'lat1': stats['lat2'],
        'lon1': stats['lon2'],
        'lat2': stats['lat1'],
        'lon2': stats['lon1'],
    }

def load(flight1, flight2):
    id1 = flight1['IDFlight']
    id2 = flight2['IDFlight']
    if id1 == id2:
        return None
    if flight1['FlightDate'] != flight2['FlightDate']:
        return None
    if flight1['FlightEndTime'] < flight2['FlightStartTime']:
        return None
    if flight2['FlightEndTime'] < flight1['FlightStartTime']:
        return None
    stats_file1 = f"_stats/{id1}-{id2}.stats.json"
    stats_file2 = f"_stats/{id2}-{id1}.stats.json"
    if os.path.exists(stats_file1):
        data = json.load(open(stats_file1))
        if data is not None:
            data['other_flight'] = flight2
            return data
    elif os.path.exists(stats_file2):
        data = json.load(open(stats_file2))
        if data is not None:
            data = flip_stats(data)
            data['other_flight'] = flight2
            return data
    return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='TODO')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('track1', type=str, help='Gzipped IGC file to analyzse')
    parser.add_argument('track2', type=str, help='Gzipped IGC file to analyzse')
    args = parser.parse_args()

    with open(args.track1) as f:
        gunzip = subprocess.Popen(('gunzip',), stdin=f, stdout=subprocess.PIPE)
        track1 = igc.parse(gunzip.stdout)
    with open(args.track2) as f:
        gunzip = subprocess.Popen(('gunzip',), stdin=f, stdout=subprocess.PIPE)
        track2 = igc.parse(gunzip.stdout)

    res = kurbeln(track1, track2, verbose = args.verbose)
    json.dump(res, sys.stdout, indent=True)
