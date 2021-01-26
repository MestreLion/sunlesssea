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

    parser.add_argument('-s', '--save',
                        default=False,
                        action="store_true",
                        help="Apply changes and save.")

    group = parser.add_mutually_exclusive_group()
    group.add_argument('-N', '--naples',
                        default=False,
                        action="store_true",
                        help="Buy Fuel up to 21 and Supplies up to remaining Hold  "
                        " as if in Naples (Surface), already accounting for trip back.")

    group.add_argument('-A', '--antiquarian', '--alarming-scholar',
                        default=False,
                        action="store_true",
                        help="Sell VALUE units of QUALITY to the Alarming Scholar.")

    group.add_argument('-a', '--add',
                        default=False,
                        action="store_true",
                        help="Consider VALUE as an increase to QUALITY.")

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

    if args.naples:
        naples()

    elif args.antiquarian:
        antiquarian(args.quality, args.value)

    elif args.value:
        change(args.quality, args.value, args.add)

    else:
        for q in sorted(ss.autosave.qualities.find(args.quality), key=lambda _: _.name.lower()):
            print(q)
        return

    if args.save:
        ss.autosave.save()
    else:
        log.info("Test run, not saving. Use --save to apply changes")


def change(quality, amount, add=False):
    if not isinstance(quality, sunlesssea.SaveQuality):
        quality = ss.autosave.qualities.fetch(quality, partial=True)

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


def naples():
    free = ss.autosave.hold - ss.autosave.cargo
    log.debug("Free cargo: %s", free)
    if free <= 0:
        raise sunlesssea.Error("Error in Autosave Cargo/Hold, possibly corrupt: %s/%s",
                               ss.autosave.cargo, ss.autosave.hold)

    def add_cap(name, price, cap=0):
        quality = ss.autosave.qualities.fetch(name)
        value = quality.value
        diff = min(max(value, cap or value + free) - value, free)
        log.debug("%s + %s", quality, diff)
        if diff:
            add_amount(quality, diff)
            add_amount('Echo', -(price * diff))
        return diff

    free += 12  # 11 fuel, 1 supplies
    free -= add_cap('Fuel',     15, 21)
    free -= add_cap('Supplies', 5)


def antiquarian(query, amount):
    event = ss.events.fetch('The Alarming Scholar')
    print(event.pretty())

    if not query:
        raise sunlesssea.Error("QUALITY is required for --antiquarian")

    squality = ss.autosave.qualities.fetch(query, partial=True)

    for action in event.actions:
        if not squality.quality == action.quality_sold:
            continue
        for _ in range(amount or squality.value):
            if not action.check(ss.autosave): break
            # FIXME: choose a single outcome!
            for outcome in action.outcomes:
                outcome.apply(ss.autosave)


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except sunlesssea.Error as e:
        log.error(e)
        sys.exit(3)
    except Exception as e:
        log.critical(e, exc_info=True)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(2)
