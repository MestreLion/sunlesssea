#!/usr/bin/env python
'''
Created on Mar 8, 2016

@author: rodrigo
'''
import sys, re
import logging

import sunlesssea
from sunlesssea import format_obj

ss = sunlesssea.SunlessSea()
self = ss.events[0].requirements[0]
#self.re_adv = re.compile('\[(?P<key>[dq]):(?P<value>(?:[^][]+|\[[^]]+])+)]')   # v10
#self.re_adv = re.compile('\[(?P<key>[dq]):(?P<value>(?:[^][]+|\[[^]]+])+)]')
self.re_adv = re.compile('\[(?P<key>[a-z]):(?P<value>(?:[^][]+|\[[^][]+])+)]')  # v11


log = logging.getLogger()
logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)

def _parse_adv(opstr,                        # Search string
               qfmt="[{name}]",               # Quality format, attributes and 'quality'
               dfmt="[1 to {}]",              # Dice roll format
               qnotfoundfmt="[Quality({})]",  # Formatter for Quality ID not found
               qnamefmt="[<{}>])"):          # Quality format for non-IDs

    result = opstr
    for match in re.finditer(self.re_adv, opstr):
        mstr, (key, value) = match.group(), match.group('key', 'value')
        log.debug("%r - %r - %r", mstr, key, value)
        subst = None

        if key == 'q':
            if value.isdigit():
                if self.ss and self.ss.qualities:
                    quality = self.ss.qualities.get(int(value))
                else:
                    quality = None

                if quality:
                    subst = format_obj(qfmt, quality, quality=quality)
                else:
                    subst = qnotfoundfmt.format(value)
                    log.warning("Could not find Quality ID %s for %r.%r in %r",
                                value, self.parent, self, opstr)

            else:
                subst = qnamefmt.format(value)
                #log.error("Nested values in [q:]: %r", value)
                pass
                #subst = _parse_adv(value, qfmt, dfmt, *args, **kwargs)

        elif key == 'd':
            subst = dfmt.format(_parse_adv(value, qfmt, dfmt, qnotfoundfmt, qnamefmt))

        else:
            log.warn("Unknown key in %r: %r", opstr, key)

        if subst:
            result = result.replace(mstr, subst, 1)

    return result

#[q:120917]+[q:120960]+[d:[q:120959]]

def printqualop(qualop):
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


    # Autosave:
    # Favors Antiquarian PyramidalNumber: XP

#     for name, value in (
# #         ('Favours: A Drop of Darkness', -75),
# #         ('Searing Enigma', +1),
#
#         # Naples trading
#         ('Supplies', +100),
#         ('Echo',     -500),
#     ):

def trade(name, qty, unitprice, save=False):
    change_quality(name, qty)
    change_quality('Echo', -qty * unitprice)

    if save:
        log.info("Saved")
        ss.autosave.save()


def change_quality(name, value, save=False):
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


if __name__ == '__main__':
    pass
    op = qname = ""
    value = price = save = 0
    if len(sys.argv) >= 2: op    = sys.argv[1]
    if len(sys.argv) >= 3: qname = sys.argv[2]
    if len(sys.argv) >= 4: value = int(sys.argv[3])
    if len(sys.argv) >= 5: price = int(sys.argv[4])
    if len(sys.argv) >= 6: save  = bool(sys.argv[5])

    if op in ("change", "trade") and qname and value:
        try:
            if op == "change":   change_quality(qname, value, save)
            if op == "trade" and price: trade(qname, value, price, save)
        except IndexError:
            pass


    sys.exit()
    for item in ss.autosave.qualities:
        q = item.quality
        if q.assign and item.value > 0:
        #if q.category in (200, 106) and item.value > 0:  # Cargo, officers
            print(item, "({0.id} {0.name})".format(q.assign))
