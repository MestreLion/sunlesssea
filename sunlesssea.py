#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#    Copyright (C) 2016 Rodrigo Silva (MestreLion) <linux@rodrigosilva.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program. See <http://www.gnu.org/licenses/gpl.html>


"""
    Tools for Sunless Sea data dumps
"""

from __future__ import unicode_literals, print_function


import sys
import os
import argparse
import logging
import json
import re


log = logging.getLogger(os.path.basename(os.path.splitext(__file__)[0]))

# Linux and FreeBSD
if sys.platform.startswith("linux") or sys.platform.startswith("freebsd"):
    import xdg.BaseDirectory as xdg
    DATADIR=os.path.join(xdg.xdg_config_home, "unity3d/Failbetter Games/Sunless Sea")

# Mac OSX
elif sys.platform == "darwin":
    DATADIR=os.path.expanduser("~/Library/Application Support/Unity.Failbetter Games.Sunless Sea")

# Windows
elif sys.platform == "win32":
    DATADIR=os.path.expanduser("~\AppData\LocalLow\Failbetter Games\Sunless Sea")

else:
    DATADIR="."  # and pray for the best...




####################################################################################
# General helper functions

def safeprint(text=""):
    # print() chooses encoding based on stdout type, if it's a tty (terminal)
    # or file (redirect/pipe); For ttys it auto-detects the terminals's
    # preferred encoding, but for files and pipes, sys.stdout.encoding
    # defaults to None in Python 2.7, so ascii is used (ew!).
    # In this case we encode to UTF-8.
    # See https://stackoverflow.com/questions/492483
    print(unicode(text).encode(sys.stdout.encoding or 'UTF-8'))


def format_obj(fmt, obj, *args, **kwargs):
    objdict = {_:getattr(obj, _) for _ in vars(obj) if not _.startswith('_')}
    objdict.update(kwargs)
    return unicode(fmt).format(*args, **objdict)




####################################################################################
# Main() and helpers

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__)

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

    parser.add_argument('-d', '--datadir',
                        dest='datadir',
                        default=DATADIR,
                        help="Game data directory. [Default: %(default)s]")

    parser.add_argument('-f', '--format',
                        dest='format',
                        choices=('bare', 'pretty', 'wiki'),
                        default='bare',
                        help="Output format. 'wiki' is awesome!"
                            " Available formats: [%(choices)s]."
                            " [Default: %(default)s]")

    parser.add_argument(dest='entity',
                        nargs="?",
                        choices=('locations', 'qualities', 'events', 'demo', 'test'),
                        default='locations',
                        metavar="ENTITY",
                        help="Entity to work on."
                            " Available entities: [%(choices)s]."
                            " [Default: %(default)s]")

    parser.add_argument(dest='filter',
                        nargs='?',
                        metavar="FILTER",
                        help="Optional name filter to narrow results")

    args = parser.parse_args(argv)
    args.debug = args.loglevel == logging.DEBUG

    return args


def main(argv=None):
    args = parse_args(argv or [])
    logging.basicConfig(level=args.loglevel,
                        format='%(levelname)s: %(message)s')
    log.debug(args)

    ss = SunlessSea(args.datadir)

    log.debug(ss.locations)
    log.debug(ss.qualities)
    log.debug(ss.events)

    if args.entity in ('locations', 'qualities', 'events'):
        entities = getattr(ss, args.entity).find(args.filter)
        if args.format == 'wiki':
            safeprint(entities.wikitable())
        elif args.format == 'pretty':
            safeprint(entities.pretty())
        else:
            safeprint(entities.show())
        return

    elif args.entity == "demo":
        for event in ss.events.at(name="Pigmote Isle"):  # ID = 102804
            safeprint(event.pretty())
            safeprint()
        location = ss.locations.get(102004)
        safeprint(repr(location))
        safeprint(location)
        locations = ss.locations.find("pigmote")
        safeprint(locations)
        for location in ss.locations[3:6]:
            safeprint(location.pretty())
        for event in ss.events.at(name="Pigmote Isle").find("rose"):
            safeprint(repr(event))
        return

    # Testing area..

    for event in ss.events:
        for field in event.dump():
            safeprint(field)



####################################################################################
# Classes


class Entity(object):
    '''Base class for an Entity'''

    def __init__(self, data, idx=0):
        self._data = data
        self.idx   = idx
        self.id    = self._data['Id']

        self.name        = self._data.get('Name', "")
        self.description = self._data.get('Description', "")
        self.image       = (self._data.get('Image', None) or
                            self._data.get('ImageName', ""))

    def dump(self):
        return self._data

    def pretty(self):
        pretty = "{:d}".format(self.id)
        if self.name:  pretty += " - {}".format(self.name)
        if self.image: pretty += " ({})".format(self.image)
        return pretty

    def wikirow(self):
        return format_obj(
            "|-\n"
            "| {idx}\n"
            "| {id}\n"
            "| [[{name}]]\n"
            "| {{{{game icon|{image}}}}}\n"
            "| <nowiki>{description}</nowiki>\n",
            self)

    def __repr__(self):
        if self.name:
            return b"<{} {:d}: {}>".format(self.__class__.__name__,
                                           self.id,
                                           repr(self.name))
        else:
            return b"<{} {:d}>".format(self.__class__.__name__,
                                       self.id)

    def __str__(self):
        if self.name:
            return "{:d}\t{}".format(self.id, self.name)
        else:
            return str(self.id)


class Entities(object):
    '''Base class for entity containers. Subclasses SHOULD override EntityCls!'''
    EntityCls=Entity

    def __init__(self, data=None, entities=None, *eargs, **ekwargs):
        self._entities = {}
        self._order = []

        if entities is None:
            for idx, edata in enumerate(data, 1):
                entity = self.EntityCls(data=edata, idx=idx, *eargs, **ekwargs)
                self._entities[entity.id] = entity
                self._order.append(entity)
        else:
            for entity in entities:
                self._entities[entity.id] = entity
                self._order.append(entity)

    def find(self, name):
        '''Return Entities filtered by name, case-insensitive.
            If falsy, return all entities
        '''
        if not name:
            return self
        return self.__class__(entities=(_ for _ in self
                                        if re.search(name, _.name,
                                                     re.IGNORECASE)))

    def wikitable(self):
        table = ('{| class="ss-table sortable" style="width: 100%;"\n'
            '! Index\n'
            '! ID\n'
            '! Name\n'
            '! Icon\n'
            '! Description\n'
        )
        table += "".join((_.wikirow() for _ in self))
        table += '|-\n|}'
        return table

    def pretty(self):
        return "\n".join((_.pretty() for _ in self))

    def show(self):
        return "\n".join((str(_) for _ in self))

    def get(self, eid, default=None):
        '''Get entity by ID'''
        return self._entities.get(eid, default)

    def __getitem__(self, val):
        entities = self._order[val]
        if len(entities) == 1:
            return entities[0]
        else:
            return self.__class__(entities=entities)

    def __iter__(self):
        for entity in self._order:
            yield entity

    def __len__(self):
        return len(self._entities)

    def __str__(self):
        return "<{}: {:d}>".format(self.__class__.__name__,
                                   len(self._entities))


class Quality(Entity):
    _jsonattrs = {"Category",
                  "LevelDescriptionText",
                  "ChangeDescriptionText",
                  "Nature",
                  "Tag"}

    def __init__(self, data, idx=0):
        super(Quality, self).__init__(data=data, idx=idx)
        for attr in self._jsonattrs:
            setattr(self, attr.lower(), self._data.get(attr, ""))


class Qualities(Entities):
    EntityCls=Quality


class Location(Entity):
    def __init__(self, data, idx=0):
        super(Location, self).__init__(data=data, idx=idx)
        self.message     = self._data.get('MoveMessage', "")

    def pretty(self):
        pretty = super(Location, self).pretty()
        for attr in ('message', 'description'):
            pretty += "\n\t{}".format(getattr(self, attr))
        return pretty


class Locations(Entities):
    EntityCls=Location


class Action(Entity):
    pass


class Event(Entity):

    _REQ_DONT_IMPORT = ('AssociatedQuality', 'Id')

    def __init__(self, data, idx=0, qualities=None, locations=None):
        super(Event, self).__init__(data=data, idx=idx)

        self.location = None
        if 'LimitedToArea' in self._data:
            iid = self._data['LimitedToArea']['Id']
            if locations:
                self.location = locations.get(iid)

            if not self.location:
                log.warning("Could not find Location for %r: %d", self, iid)
                self.location = Location(self._data['LimitedToArea'])

        self.requirements = []
        for item in self._data['QualitiesRequired']:
            iid = item['AssociatedQuality']['Id']
            if qualities:
                quality = qualities.get(iid)

            if not quality:
                log.warning("Could not find Quality for %r: %d", self, iid)
                quality = Quality(item['AssociatedQuality'])

            self.requirements.append((quality,
                                      {_:item[_] for _ in item
                                       if _ not in self._REQ_DONT_IMPORT}))
        self.actions = []

    def pretty(self):
        pretty = super(Event, self).pretty()

        if self.location:
            pretty += "\n\tLocation: {}".format(self.location)

        pretty += "\n\tRequirements: {:d}".format(len(self.requirements))
        for req in self.requirements:
            pretty += "\n\t\t{}: {}".format(req[0].pretty(), req[1])

        return pretty


class Events(Entities):
    EntityCls=Event

    def at(self, lid=0, name=""):
        '''Return Events by location ID or name'''
        return Events(entities=(_ for _
                                in self
                                if (_.location and
                                    ((lid  and _.location.id == lid) or
                                     (name and re.search(name, _.location.name,
                                                         re.IGNORECASE))))))


class SunlessSea(object):
    '''
        Manager class, the one that loads the JSON files
        and call each entity container's constructor
    '''
    def __init__(self, datadir=None):
        self.qualities = Qualities(data=self._load('qualities', datadir))
        self.locations = Locations(data=self._load('areas', datadir))
        self.events    = Events(data=self._load('events', datadir),
                                qualities=self.qualities,
                                locations=self.locations)

    def _load(self, entity, datadir=None):
        path = os.path.join(datadir or DATADIR,
                            'entities',
                            "{}_import.json".format(entity))
        log.debug("Opening data file for '%s': %s", entity, path)
        try:
            with open(path) as fd:
                # strict=False to allow tabs inside strings
                return json.load(fd, strict=False)
        except IOError as e:
            log.error("Could not load data file for '%s': %s", entity, e)
            return []




####################################################################################
# Import guard

if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:
        log.critical(e, exc_info=True)
        sys.exit(1)
    except KeyboardInterrupt:
        pass
