#!/usr/bin/env python3

import math
import sys
import subprocess
import igc
import json

from constants import *
import kreise
import sektoren
import landepunkt
import kurbeln

valid = 0
invalid = 0

for f in sys.argv[1:]:
    gunzip = subprocess.Popen(('gunzip',), stdin=open(f), stdout=subprocess.PIPE)
    track = igc.parse(gunzip.stdout)
    if not kurbeln.check_track(track):
        print(f"File {f} is not valid")
        invalid += 1
    else:
        valid += 1 

print(f"Valid: {valid}")
print(f"Invalid: {invalid}")
print(f"Percentage: {valid / (valid + invalid) * 100}%")
