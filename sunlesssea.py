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

def parse_args(argv=None, cmds=None, defaultcmd=None):
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

    group.add_argument('-d', '--datadir',
                       dest='datadir',
                       default=DATADIR,
                       help="Game data directory. [Default: %(default)s]")

    parser.add_argument(dest='cmd',
                        nargs='?',
                        #choices=cmds or [],
                        default=defaultcmd,
                        metavar="COMMAND",
                        help="Command to execute. "
                            " Available commands are: [%(choices)s]"
                            " [Default: %(default)s]")

    args = parser.parse_args(argv)
    args.debug = args.loglevel == logging.DEBUG

    return args


def main(argv=None):
    args = parse_args(argv or [], ('events','pretty','qualities', 'locations'))
    logging.basicConfig(level=args.loglevel,
                        format='%(levelname)s: %(message)s')
    log.debug(args)

    ss = SunlessSea(args.datadir)

    log.debug(ss.locations)
    log.debug(ss.qualities)
    log.debug(ss.events)

    if args.cmd == "events":
        for event in ss.events:
            if not event.name:
                log.warning("Event with no name: %d", event.id)
            safeprint(format_obj("{idx}\t{event}", event, event=event))
        return

    elif args.cmd == "pretty":
        for event in ss.events.at(name="Pigmote Isle"):  # ID = 102804
            safeprint(event.pretty())
            safeprint()
        return

    elif args.cmd == "qualitiesold":
        for i, quality in enumerate(ss.qualities.itervalues(), 1):
            quality['i'] = i
            safeprint("{i}\t{Id}\t{Name}".format(**quality))
        return

    elif args.cmd == "qualities":
        for i, quality in enumerate(ss.qualities.itervalues(), 1):
            quality['i'] = i
            safeprint("{i}\t{Id}\t{Name}".format(**quality))
        return

    elif args.cmd == "locations":
        location = ss.locations.get(102004)
        safeprint(repr(location))
        safeprint(location)
        locations = ss.locations.find("pigmote")
        safeprint(locations)
        for location in ss.locations[3:6]:
            safeprint(location.pretty())
        return

    elif args.cmd == "super":
        for event in ss.events.at(name="Pigmote Isle").find("rose"):
            safeprint(event)
        return




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

    def find(self, name=""):
        '''Return Entities filtered by name, case-insensitive.'''
        return self.__class__(entities=(_ for _ in self
                                        if re.search(name, _.name,
                                                     re.IGNORECASE)))

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


class Event(Entity):

    _REQ_DONT_IMPORT = ('AssociatedQuality', 'Id')

    def __init__(self, data, idx=0, qualities=None, locations=None):
        super(Event, self).__init__(data=data, idx=idx)

        self.location = None
        if 'LimitedToArea' in self._data:
            lid = self._data['LimitedToArea']['Id']
            if locations:
                self.location = locations.get(lid)

            if not self.location:
                log.warning("Could not find Location for %r: %d", self, lid)
                self.location = Location(self._data['LimitedToArea'])

        self.requirements = []
        for req in self._data['QualitiesRequired']:
            qid = req['AssociatedQuality']['Id']
            if qualities:
                quality = qualities.get(qid)

            if not quality:
                log.warning("Could not find Quality for %r: %d", self, qid)
                quality = Quality(req['AssociatedQuality'])

            self.requirements.append((quality,
                                      {_:req[_] for _ in req
                                       if _ not in self._REQ_DONT_IMPORT}))
        self.actions = []

    def pretty(self):
        pretty = super(Event, self).pretty()

        if self.location:
            pretty += "\n\tLocation: {}".format(self.location.pretty())

        pretty += "\n\tRequirements: {:d}".format(len(self.requirements))
        for req in self.requirements:
            pretty += "\n\t\t{}: {}".format(req[0].pretty(), req[1])

        return pretty


class Events(object):
    entity='events'

    def __init__(self, datadir=None, qualities=None, locations=None, events=None):
        self.events = {}
        self._order = []

        self.qualities = qualities or {_['Id']:_ for _ in self._load(datadir, 'qualities')}
        self.locations = locations or {_['Id']:_ for _ in self._load(datadir, 'areas')}

        if events is not None:
            for event in events:
                self.events[event.id] = event
                self._order.append(event.id)
        else:
            data = self._load(datadir)
            for i, obj in enumerate(data, 1):
                event = Event(obj, i, self.qualities, self.locations)
                self.events[event.id] = event
                self._order.append(event.id)

    def find(self, name):
        '''Return Events filtered by name, case-insensitive.'''
        return Events(qualities=self.qualities,
                      locations=self.locations,
                      events=(_ for _ in self
                              if re.search(name, _.name, re.IGNORECASE)))

    def at(self, lid=0, name=""):
        '''Return Events by location'''
        locations = self.locations.find(name) if (name and not lid) else []
        return Events(qualities=self.qualities,
                      locations=self.locations,
                      events=(_ for _ in self if
                              _.location and
                              ((lid  and _.location.id == lid) or
                               (name and _.location in locations))))

    def get(self, eid, default=None):
        '''Get event by ID. Raises ValueError if ID is not found'''
        return self.events.get(eid, default)

    def _load(self, datadir=None, entity=None):
        path = os.path.join(datadir or DATADIR,
                            'entities',
                            "{}_import.json".format(entity or self.entity))
        log.debug("Opening data file: %s", path)
        with open(path) as fd:
            # strict=False to allow tabs inside strings
            return json.load(fd, strict=False)

    def __iter__(self):
        for eid in self._order:
            yield self.events[eid]

    def __len__(self):
        return len(self.events)

    def __str__(self):
        return "<Events: {:d}>".format(len(self.events))


class SunlessSea(object):
    '''
        Manager class, the one that loads the JSON files
        and call each entity container's constructor
    '''
    def __init__(self, datadir=None):
        self.qualities = Qualities(data=self._load('qualities', datadir))
        self.locations = Locations(data=self._load('areas', datadir))
        self.events    = Events(datadir=datadir, qualities=self.qualities, locations=self.locations)

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
