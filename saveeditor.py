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
    save = ss.autosave  # TODO: Choose via CLI arg instead of hardcoding

    if args.naples:
        naples(save=save)

    elif args.antiquarian:
        antiquarian(args.quality, args.value, save=save)

    elif args.value:
        change(args.quality, args.value, args.add, save=save)

    else:
        for q in sorted(save.qualities.find(args.quality), key=lambda _: _.name.lower()):
            print(q)
        return

    if args.save:
        save.save()
    else:
        log.info("Test run, not saving. Use --save to apply changes")


def change(query, amount, add=False, save=None):
    if save is None:
        save = ss.autosave
    quality = save.qualities.fetch(query, partial=True, add=True)
    value = quality.value  # save old value, for logging purposes

    if add:
        quality.increase_by(amount)
    else:
        quality.set_to(amount)

    log.info("Changed [%s] '%s' from %s to %s (%+d)",
             quality.id, quality.name, value, quality.value, quality.value - value)


def naples(save=None):
    def purchase(name, cap=0):
        squality = save.qualities.fetch(name)
        for action in event.actions:
            if squality.quality == action.quality_bought:
                break
        else:
            raise sunlesssea.Error("No action to buy %s in Naples", name)
        value = squality.value
        qty = min(max(value, cap or value + free) - value, free)
        log.debug("%s + %s", squality, qty)
        qty = action.do(qty, save=save)
        if qty:
            log.info("Purchased %2d x %s: %d => %d",
                     squality.value - value, squality.name, value, squality.value)
        return qty

    if save is None:
        save = ss.autosave

    event = save.ss.events.fetch('In Naples')
    free = save.hold - save.cargo
    log.debug("Free cargo: %s", free)
    if free <= 0:
        raise sunlesssea.Error("Error in Autosave Cargo/Hold, possibly corrupt: %s/%s",
                               save.cargo, save.hold)
    free += 12  # Account for the travel back to Avernus and Cumaen: 11 fuel + 1 supplies
    free -= purchase('Fuel', 21)
    free -= purchase('Supplies')


def antiquarian(query, amount, save=None):
    if not query:
        raise sunlesssea.Error("QUALITY is required for --antiquarian")

    if save is None:
        save = ss.autosave

    event = save.ss.events.fetch('The Alarming Scholar')
    quality = save.ss.qualities.fetch(query, partial=True)

    for action in event.actions:
        if quality == action.quality_sold:
            break
    else:
        raise sunlesssea.Error("No action to sell %s in %s", quality, event)

    # Not using an attached SaveQuality, Effect.apply() will create *if* necessary
    # Hence the need to get updated new value after results, if any.
    old = quality.fetch_from_save(save=save, add=False).value
    results = action.do(amount or old, save=save, output=list)
    log.debug(results)
    if len(results):
        new = quality.fetch_from_save(save=save, add=False).value
        log.info("Sold %2d x %s: %d => %d", old - new, quality.name, old, new)


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
