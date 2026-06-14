#!/usr/bin/env bash
# Requires Python 3.12 with cadquery installed:
#   py -3.12 -m pip install cadquery
set -e
py -3.12 -m src.build
