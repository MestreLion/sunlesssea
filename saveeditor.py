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


def change(query, amount, add=False):
    quality = ss.autosave.qualities.fetch(query, partial=True)
    value = quality.value

    if add:
        quality.increment(amount)
    else:
        quality.value = amount

    log.info("Changed [%s] '%s' from %s to %s (%+d)",
             quality.id, quality.name, value, quality.value, quality.value - value)


def naples():
    def purchase(name, cap=0):
        squality = ss.autosave.qualities.fetch(name)
        for action in event.actions:
            if squality.quality == action.quality_bought:
                break
        else:
            raise sunlesssea.Error("No action to buy %s in Naples", name)
        value = squality.value
        qty = min(max(value, cap or value + free) - value, free)
        log.debug("%s + %s", squality, qty)
        qty = action.do(ss.autosave, qty)
        if qty:
            log.info("Purchased %s: %d => %d (%+d)",
                     squality.name, value, squality.value, squality.value - value)
        return qty

    event = ss.events.fetch('In Naples')
    free = ss.autosave.hold - ss.autosave.cargo
    log.debug("Free cargo: %s", free)
    if free <= 0:
        raise sunlesssea.Error("Error in Autosave Cargo/Hold, possibly corrupt: %s/%s",
                               ss.autosave.cargo, ss.autosave.hold)
    free += 12  # Account for the travel back to Avernus and Cumaen: 11 fuel + 1 supplies
    free -= purchase('Fuel', 21)
    free -= purchase('Supplies')


def antiquarian(query, amount):
    if not query:
        raise sunlesssea.Error("QUALITY is required for --antiquarian")

    event = ss.events.fetch('The Alarming Scholar')
    squality = ss.autosave.qualities.fetch(query, partial=True)
    value = squality.value
    qty = amount or value

    for action in event.actions:
        if squality.quality == action.quality_sold:
            break
    else:
        raise sunlesssea.Error("No action to sell %s in %s", squality.quality, event)

    qty = action.do(ss.autosave, qty)
    if qty:
        log.info("Sold %s: %d => %d (%+d)",
                 squality.name, value, squality.value, squality.value - value)


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
