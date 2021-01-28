#!/usr/bin/env python3
#
# This file is part of SunlessSea, see <https://github.com/MestreLion/SunlessSea>
# Copyright (C) 2020 Rodrigo Silva (MestreLion) <linux@rodrigosilva.com>
# License: GPLv3 or later, at your choice. See <http://www.gnu.org/licenses/gpl>

"""
Sunless Sea testing
"""

import logging
import random
import os
import sys

import sunlesssea


ss = None

log = logging.getLogger(os.path.basename(os.path.splitext(__file__)[0]))


# Add new functions here, moving old ones down


def eval_all():
    def do_adv(qualops, func):
        for qualop in qualops:
            if any(op for op in qualop.operator if 'Advanced' in op):
                try:
                    func(qualop)
                except ValueError as e:
                    log.error("Error in %r: %s", qualop, e)

    def check_adv_requirements(entity):
        do_adv(entity.requirements, sunlesssea.Requirement.check)

    def apply_adv_effects(entity):
        do_adv(entity.effects, sunlesssea.Effect.apply)

    for event in ss.events:
        check_adv_requirements(event)
        apply_adv_effects(event)
        for action in event.actions:
            check_adv_requirements(action)
            for outcome in action.outcomes:
                apply_adv_effects(outcome)


def eval_test():
    for action in ss.events.fetch('Returning to London').actions:
        if action.name == 'Collect messages from the Harbourmaster':  # there's 2 of them!
            # [1 to [Favours: Antiquarian]] - [1 to 5] - (100 * [Doom: Scholar's Madness])
            action.do()
            break


def choose(chance, i=10000):
    a = 0
    for _ in range(i):
        if random.choices('ab', cum_weights=(chance, 100))[0] == 'a':
            a += 1
    print(f'{a / i:.2%}')


def gamenote():
    for event in ss.events:
        for action in event.actions:
            if action.gamenote:
                print(event.name)
                break


def printqualop(qualop):
    """Old testing for Requirements and Effects and Advanced parsing"""
    #[q:120917]+[q:120960]+[d:[q:120959]]
    print("REPR:\t{}".format(repr(qualop)))
    print(u"STR:\t{}".format(qualop))
    print(u"PRETTY:\t{}".format(qualop.pretty()))
    print(u"WIKI:\t{}".format(qualop.wiki()))
    print("")

#     try:
#         args = sys.argv[1]
#     except Exception:
#         args = None
#         #opstr = "[q:120960] is better when [d:10] is applied to [q:677846]"
#         #args = "[q:120917]+[q:120960]+[d:[q:120959]]"
#
#     for opstr in (args,) if args else (
#        "[q:120917]+[q:12060]+[d:[q:120959]]",
#        "[d:99+[q:102898]+[q:567*2]]",
#        "[d:[q:108665]] - [d:5] - (100 * [q:115785])",
#        "[d:[q:108665]] - [d:5] - (100 * [q:115785])",
#     ):
#         #print _parse_adv(opstr, "([[{quality}]])")
#         print _parse_adv(opstr, qnamefmt="[q:[[{}]]]")
#     sys.exit()
#
#
#     event = ss.events.get(208079)
#     for qualop in (
#         event.requirements[-1],
#         event.actions[0].outcomes[0].effects[0],
#         event.actions[0].outcomes[0].effects[1],
#         event.actions[1].requirements[1],
#         event.actions[1].requirements[2],
#         event.actions[1].outcomes[0].effects[0],
#         event.actions[1].outcomes[0].effects[1],
#     ):
#         printqualop(qualop)
#
#     if True:
#         for shop in ss.shops:
#             for item in shop.items:
#                 if item.currency.id == 111726:
#                     print item


def equipable():
    """Print owned equipable qualities (Ship Equipment and Officers) and their slots"""
    for item in ss.autosave.qualities:
        q = item.quality
        if q.assign and item.value > 0:
        #if q.category in (200, 106) and item.value > 0:  # Cargo, officers
            print(item, "({0.id} {0.name})".format(q.assign))


def trade(name, qty, unitprice, save=False):
    change_quality(name, qty)
    change_quality('Echo', -qty * unitprice)

    if save:
        log.info("Saved")
        ss.autosave.save()


def change_quality(name, value, save=False):
    """Prototype version with using old API. Use saveeditor.py for the modern way"""
    try:
        item = ss.autosave.qualities.find(name)[0]
    except IndexError:
        log.error("Quality not found in Autosave: %s", name)
        raise

    old = item.value
    item.value += value
    print("{item.id} {item.name}:"
          " from {old} to {item.value} ({value:+d})".format(**locals()))
    if save:
        log.info("Saved")
        ss.autosave.save()


def demo():
    """Old API demo, can be improved"""
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
    loglevel = logging.INFO
    # Lame argparse
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

    def try_int(value):
        try:
            return int(value)
        except ValueError:
            return value
    args = [try_int(_) for _ in args]

    try:
        globals()[func](*args)
    except TypeError as e:
        log.error(e)


if __name__ == '__main__':
    main()
