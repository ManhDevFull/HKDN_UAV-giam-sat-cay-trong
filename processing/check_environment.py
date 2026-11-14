"""Run after pip install -e .; Survey3 RAW does not require rawpy."""

import sys

import numpy
import PIL
import processing

print(f"Python: {sys.version.split()[0]}")
print(f"NumPy: {numpy.__version__}; Pillow: {PIL.__version__}")
print(f"Processing: {processing.__version__}; Survey3 packed RAW decoder ready")
