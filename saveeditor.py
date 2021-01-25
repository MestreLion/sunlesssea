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
ss = None


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

    parser.add_argument('-a', '--add',
                        default=False,
                        action="store_true",
                        help="Add instead of setting VALUE to QUALITY.")

    parser.add_argument('-s', '--save',
                        default=False,
                        action="store_true",
                        help="Apply changes and save.")

    parser.add_argument(nargs='?',
                        dest='quality',
                        metavar="QUALITY",
                        help="Quality to look for, either by name or ID.")

    parser.add_argument(nargs='?',
                        dest='value',
                        type=int,
                        metavar="VALUE",
                        help="New value for QUALITY.")

    args = parser.parse_args(argv)
    args.debug = args.loglevel == logging.DEBUG
    return args


def main(argv=None):
    global ss
    args = parse_args(argv)
    logging.basicConfig(level=args.loglevel,
                        format='%(levelname)-5.5s: %(message)s')
    log.debug(args)

    ss = sunlesssea.SunlessSea()

    if args.value:
        change(args.quality, args.value, args.add)

    else:
        for q in sorted(find(args.quality), key=lambda _: _.name.lower()):
            print(q)
        return

    if args.save:
        ss.autosave.save()
    else:
        log.info("Test run, not saving. Use --save to apply changes")


def find(query):
    qualities = ss.autosave.qualities.find(query)
    if query and not qualities:
        raise sunlesssea.Error("Quality not found in Autosave: %s", query)
    return qualities


def change(query, amount, add=False):
    if not isinstance(query, sunlesssea.SaveQuality):
        qualities = find(query)
        found = len(qualities)
        if found > 1:
            raise sunlesssea.Error(
                "Can not change value, %s qualities match '%s':\n\t%s",
                found, query, "\n\t".join(str(_) for _ in qualities)
            )
        quality = qualities[0]
    else:
        quality = query
    log.debug(repr(quality))

    value = amount
    if add:
        value += quality.value

    log.info("Change quality [%s] '%s' from %s to %s (%+d)",
             quality.id, quality.name, quality.value, value, value-quality.value)
    quality.value = value


def add_amount(query, amount):
    change(query, amount, add=True)


def set_amount(query, amount):
    change(query, amount, add=False)




if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except sunlesssea.Error as e:
        log.error(e)
        sys.exit(ERR)
    except Exception as e:
        log.critical(e, exc_info=True)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(2)
