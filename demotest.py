#!/usr/bin/env python3
#
# This file is part of SunlessSea, see <https://github.com/MestreLion/SunlessSea>
# Copyright (C) 2020 Rodrigo Silva (MestreLion) <linux@rodrigosilva.com>
# License: GPLv3 or later, at your choice. See <http://www.gnu.org/licenses/gpl>

"""
Sunless Sea testing
"""

import logging
import os
import sys

import sunlesssea


log = logging.getLogger(os.path.basename(os.path.splitext(__file__)[0]))
ss = None


# Add new functions here, moving old ones down


def demo():
    for event in ss.events.at(name="Pigmote Isle"):  # ID = 102804
        print(event.pretty())
        print()
    location = ss.locations.get(102004)
    print(repr(location))
    print(location)
    locations = ss.locations.find("pigmote")
    print(locations)
    for location in ss.locations[3:6]:
        print(location.pretty())
    for event in ss.events.at(name="Pigmote Isle").find("rose"):
        print(repr(event))




def main():
    global ss
    # Lame argparse
    loglevel = logging.INFO
    if '-v' in sys.argv[1:]:
        loglevel = logging.DEBUG
        sys.argv.remove('-v')
    logging.basicConfig(level=loglevel, format='%(levelname)-5.5s: %(message)s')

    ss = sunlesssea.SunlessSea()

    funcs = tuple(k for k, v in globals().items() if callable(v) and k not in ('main',))
    if len(sys.argv) < 2:
        print("Usage: {} FUNCTION [ARGS...]\nAvailable functions:\n\t{}".format(
            __file__, "\n\t".join(funcs)))
        return

    func = sys.argv[1]
    args = sys.argv[2:]
    if func not in funcs:
        log.error("Function %r does not exist! Try one of:\n\t%s",  "\n\t".join(funcs))
        return

    try:
        globals()[func](*args)
    except TypeError as e:
        log.error(e)

if __name__ == '__main__':
    main()
