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

    if args.antiquarian:
        antiquarian(args.quality, args.value)

    elif args.value:
        change(args.quality, args.value, args.add)

    else:
        for q in sorted(find(args.quality), key=lambda _: _.name.lower()):
            print(q)
        return

    if args.save:
        ss.autosave.save()
    else:
        log.info("Test run, not saving. Use --save to apply changes")


def find(query, exact=False, entities=None):
    if entities is None:
        entities = ss.autosave.qualities
    qualities = entities.find('^{}$'.format(query) if exact else query)
    if query and not qualities:
        raise sunlesssea.Error("Quality not found in %s: %s", entities, query)
    return qualities


def fetch(query, exact=True, entities=None):
    qualities = find(query, exact=exact, entities=entities)
    found = len(qualities)
    if found > 1:
        raise sunlesssea.Error("%s qualities match '%s':\n\t%s",
            found, query, "\n\t".join(str(_) for _ in qualities))
    return qualities[0]


def change(quality, amount, add=False):
    if not isinstance(quality, sunlesssea.SaveQuality):
        quality = fetch(quality, exact=False)

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
        quality = fetch(name)
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
    try:
        event = ss.events.find('The Alarming Scholar')[0]
    except IndexError:
        raise sunlesssea.Error("Could not find the Alarming Scholar event!")
    print(event.pretty())

    if not query:
        raise sunlesssea.Error("QUALITY is required for --antiquarian")

    squality = fetch(query, exact=False)

    def trade_quality(action):
        """Trade action is defined by having all of:
            - A single requirement, in the strict form of 'quality >= 1'
            - All outcomes contain one effect 'echo += X' and one 'quality -= 1'
              (it may contain additional effects)
        """
        if not len(action.requirements) == 1:
            return
        requirement = action.requirements[0]
        if (   not len(requirement.operator) == 1
            or not requirement.operator.get('MinLevel') == 1
        ):
            return
        quality = requirement.quality
        echo = fetch('Echo', entities=ss.qualities)
        for outcome in action.outcomes:
            qok = eok = False
            for effect in outcome.effects:
                if (
                    effect.quality == quality and
                    len(effect.operator) == 1 and
                    effect.operator.get('Level') == -1
                ):
                    qok = True
                    continue
                if (
                    effect.quality ==  echo and
                    len(effect.operator) == 1 and
                    effect.operator.get('Level') > 0
                ):
                    eok = True
                    continue
            if not (qok and eok):
                return
        return quality

    for action in event.actions:
        if not squality.quality == trade_quality(action):
            continue
        while action.check(ss.autosave) and (not amount or squality.value > amount):
            # FIXME: choose a single outcome!
            for outcome in action.outcomes:
                outcome.apply(ss.autosave, amount or squality.value)


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
