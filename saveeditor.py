#!/usr/bin/env python3
#
# This file is part of SunlessSea, see <https://github.com/MestreLion/SunlessSea>
# Copyright (C) 2020 Rodrigo Silva (MestreLion) <linux@rodrigosilva.com>
# License: GPLv3 or later, at your choice. See <http://www.gnu.org/licenses/gpl>

"""
Sunless Sea savegame editor
"""

import argparse
import logging
import os
import sys

import sunlesssea

ERR = 3

COPYRIGHT="""
Copyright (C) 2020 Rodrigo Silva (MestreLion) <linux@rodrigosilva.com>
License: GPLv3 or later, at your choice. See <http://www.gnu.org/licenses/gpl>
"""

log = logging.getLogger(os.path.basename(os.path.splitext(__file__)[0]))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=COPYRIGHT,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument('-q', '--quiet',
                       dest='loglevel',
                       const=logging.WARNING,
                       default=logging.INFO,
                       action="store_const",
                       help="Suppress informative messages.")

    group.add_argument('-v', '--verbose',
                       dest='loglevel',
                       const=logging.DEBUG,
                       action="store_const",
                       help="Verbose mode, output extra info.")

    parser.add_argument('-s', '--save',
                        default=False,
                        action="store_true",
                        help="Apply changes and save.")

    parser.add_argument('-i', '--id',
                        default=False,
                        action="store_true",
                        help="Match QUALITY by ID instead of by name.")

    parser.add_argument(dest='quality',
                        metavar="QUALITY",
                        help="Quality to look for.")

    parser.add_argument(nargs='?',
                        dest='value',
                        type=int,
                        metavar="VALUE",
                        help="New value for QUALITY.")

    args = parser.parse_args(argv)
    args.debug = args.loglevel == logging.DEBUG
    return args


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=args.loglevel,
                        format='%(levelname)-5.5s: %(message)s')
    log.debug(args)

    ss = sunlesssea.SunlessSea()

    if args.id:
        try:
            qid = int(args.quality)
        except ValueError:
            log.error("When using --id, QUALITY must be an integer: %s", args.quality)
            return ERR
        qualities = []
        quality = ss.autosave.qualities.get(qid)
        if quality:
            qualities.append(quality)
    else:
        qualities = ss.autosave.qualities.find(args.quality)

    found = len(qualities)
    if not found:
        log.error("Quality not found in Autosave: %s", args.quality)
        return ERR

    if args.value is None:
        for q in qualities:
            print(q)
        return

    if found > 1:
        log.error("Can not change value, %s qualities match '%s':",
                  found, args.quality)
        for q in qualities:
            log.error("\t%s", q)
        return ERR

    quality = qualities[0]
    log.debug(repr(quality))
    log.info("Changing quality [%s] '%s' from %s to %s",
             quality.id, quality.name, quality.value, args.value)
    quality.value = args.value

    if args.save:
        log.debug(repr(quality))
        ss.autosave.save()
    else:
        log.info("Test run, not saving. Use --save to apply changes")



if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:
        log.critical(e, exc_info=True)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(2)
