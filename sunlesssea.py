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

# Ideas
# - pretty(short=True), so they can use each other
#    Ex: Location.pretty(short=True) does not print description
# - just the caller indents the result, using indent() - no more _level madness!
# - make pretty uniform across indent, \n, etc
# - Outcomes are a dict: only Default, Success, Rare.
#    4 keys: DefaultEvent, RareDefaultEvent, SuccessEvent, RareSuccessEvent
#    Possible combinations:
#        Def+RarDef
#        Def(Fail)+RarDef(SuperFail)+Suc
#        Def(Fail)+Suc
#        Def(Fail)+Suc+RarSuc(SuperSuc)


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


def indent(text, level=1, pad='\t'):
    '''Indent a text. As a side-effect it also rstrips (right-trim) whitespaces'''
    if not level:
        return text
    indent = level * pad
    return "{}{}".format(indent, ('\n'+indent).join(text.rstrip().split('\n')))


def iif(cond, trueval, falseval=""):
    if cond:
        return trueval
    else:
        return falseval


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
                        choices=('bare', 'dump', 'pretty', 'wiki', 'wikipage'),
                        default='pretty',
                        help="Output format. 'wiki' is awesome!"
                            " Available formats: [%(choices)s]."
                            " [Default: %(default)s]")

    parser.add_argument(dest='entity',
                        nargs="?",
                        choices=('locations', 'qualities', 'events', 'demo', 'test'),
                        default='test',
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
        elif args.format == 'wikipage':
            safeprint(entities.wikipage())
        elif args.format == 'pretty':
            safeprint(entities.pretty())
        elif args.format == 'dump':
            safeprint(entities.dump())
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
    event = ss.events.get(208079)
    safeprint(event.pretty())
    #safeprint(event.wikipage())



####################################################################################
# Classes


class Entity(object):
    '''Base class for an Entity
        Subclasses SHOULD override _REQUIRED_FIELDS, _OPTIONAL_FIELDS, _IGNORED_FIELDS
    '''

    _ENTITY_FIELDS    = set(("Id", "Name", "Description", "Image"))
    _ENTITY_REQUIRED  = set(("Id",))

    _REQUIRED_FIELDS  = set(_ENTITY_FIELDS)
    _OPTIONAL_FIELDS  = set()  # Converted to attributes using default values
    _IGNORED_FIELDS   = set()  # No attributes created

    def __init__(self, data, idx=0, ss=None):
        self._data = data
        self.idx   = idx
        self.ss    = ss
        self.id    = self._data['Id']

        self.name        = self._data.get('Name', "")
        self.description = self._data.get('Description', "")
        self.image       = (self._data.get('Image', None) or
                            self._data.get('ImageName', ""))  # Locations

        self._test_integrity()

    def _test_integrity(self):
        fields = set(self._data)

        f = ((self._ENTITY_REQUIRED |
              self._REQUIRED_FIELDS) -
             fields)
        if f:
            log.error("%r is missing REQUIRED fields: %s",
                      self, ", ".join(sorted(f)))

        f = fields - (self._ENTITY_REQUIRED |
                      self._REQUIRED_FIELDS |
                      self._OPTIONAL_FIELDS |
                      self._IGNORED_FIELDS)
        if f:
            log.warn("%r contains UNKNOWN fields: %s",
                      self, ", ".join(sorted(f)))

    def dump(self):
        return self._data

    def pretty(self):
        pretty = "{:d}".format(self.id)
        if self.name:  pretty += " - {}".format(self.name)
        if self.image: pretty += " ({})".format(self.image)
        pretty += "\n"
        return pretty

    def wiki(self):
        return self.name or str(self.id)

    def wikirow(self):
        return format_obj(
            "|-\n"
            "| {idx}\n"
            "| {id}\n"
            "| [[{name}]]\n"
            "| {{{{game icon|{image}}}}}\n"
            "| <nowiki>{description}</nowiki>\n",
            self)

    def wikipage(self):
        return format_obj(
            "=={name}==\n"
            "* <nowiki>{repr}</nowiki>\n"
            "* {wiki}\n",
            self, entity=self, wiki=self.wiki(), repr=repr(self))

    def _desc(self, text, cut=80, elipsis="(...)"):
        '''Quotes and limits a description, and replace control characters'''
        if len(text) > cut:
            text = text[:cut-len(elipsis)] + "(...)"
        # repr() quotes and fixes \n, \r, but must get rid of 'u' prefix
        return repr(text)[1:]

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


class Quality(Entity):
    _REQUIRED_FIELDS = {'Name'}
    _OPTIONAL_FIELDS = set((
        "Description",
        "Image",

        "ChangeDescriptionText",
        "LevelDescriptionText",
        'LevelImageText',

        "AvailableAt",
        "Cap",
        "Category",
        "IsSlot",
        "Nature",
        "Persistent",
        "Tag",
        'Visible',
    ))
    _IGNORED_FIELDS  = set((
        'AllowedOn',
        'AssignToSlot',
        'CssClasses',
        'DifficultyScaler',
        "DifficultyTestType",
        'Enhancements',
        'Notes',
        "Ordering",
        'OwnerName',
        'PyramidNumberIncreaseLimit',
        'QEffectPriority',
        'QualitiesPossessedList',
        'UseEvent',
        'UsePyramidNumbers',
    ))

    _status_fields = (
        ('level_status',  'LevelDescriptionText', 'Journal Descriptions'),
        ('change_status', 'ChangeDescriptionText', 'Change Descriptions'),
        ('image_status',  'LevelImageText', 'Images'),
    )

    def __init__(self, data, idx=0, ss=None):
        super(Quality, self).__init__(data=data, idx=idx, ss=ss)
        for attr, atype, default in (
            ("AvailableAt", str,  ""),
            ("Cap",         int,  0),
            ("Category",    int,  0),
            ("IsSlot",      bool, False),
            ("Nature",      int,  0),
            ("Persistent",  bool, False),
            ("Tag",         str,  ""),
            ("Visible",     bool, False),
        ):
            setattr(self, attr.lower(), atype(self._data.get(attr, default)))

        for attr, key, _ in self._status_fields:
            setattr(self, attr, self._parse_status(self._data.get(key, "")))

    def _parse_status(self, value):
        if not value:
            return {}
        return {int(k):v for k,v in (row.split("|") for row in value.split("~"))}

    def pretty(self):
        pretty = super(Quality, self).pretty()

        if self.description:
            pretty += "\t{}\n".format(self._desc(self.description))

        for attr, _, caption in self._status_fields:
            statuses = getattr(self, attr)
            if statuses:
                pretty += "\n\t{}: {:d}\n".format(caption, len(statuses))
                for status in sorted(statuses.iteritems()):
                    pretty += "\t\t[{}] - {}\n".format(*status)

        return pretty


class Location(Entity):
    _REQUIRED_FIELDS = set(('Name',))
    _OPTIONAL_FIELDS = set(('Description', 'ImageName', 'MoveMessage'))

    def __init__(self, data, idx=0, ss=None):
        super(Location, self).__init__(data=data, idx=idx, ss=ss)
        self.message     = self._data.get('MoveMessage', "")

    def pretty(self):
        pretty = super(Location, self).pretty()
        for attr in ('message', 'description'):
            pretty += "\t{}\n".format(self._desc(getattr(self, attr)))
        return pretty


class BaseEvent(Entity):
    '''Base class for Event, Action and Effect, as they have a very similar format'''

    _OUTCOME_TYPES = ('DefaultEvent',
                     'RareDefaultEvent',
                     'SuccessEvent',
                     'RareSuccessEvent')

    _OPTIONAL_FIELDS = set((
        "Name",
        "Description",
        "Image",
    ))

    def __init__(self, data, idx=0, parent=None, qualities=None, ss=None):
        super(BaseEvent, self).__init__(data=data, idx=idx, ss=ss)

        # Requirements and Effects
        for key, attr, cls in (
            ('QualitiesRequired', 'requirements', Requirement),  # Only Events and Actions
            ('QualitiesAffected', 'effects',      Effect),       # Only Events and Outcomes
        ):
            if key in self._data:
                setattr(self, attr, [])
                for item in self._data[key]:
                    getattr(self, attr).append(cls(data=item,
                                                   parent=self,
                                                   ss=self.ss))

        # Only Actions and Outcomes
        if parent:
            self.parent = parent

        # Sanity checks

        if 'ParentEvent' in self._data:
            iid = self._data['ParentEvent']['Id']
            if not parent:
                log.warn("%r should have parent with ID %d", self, iid)
            elif parent.id != iid:
                log.warn("Parent ID in object and data don't match for %r: %d vs %d",
                         parent.id, iid)

    def pretty(self):
        pretty = "{}\n".format(super(BaseEvent, self).pretty().strip())

        if self.description:
            pretty += "\t{}\n".format(self._desc(self.description))

        if getattr(self, 'requirements', None):
            pretty += "\tRequirements: {:d}\n".format(len(self.requirements))
            for item in self.requirements:
                pretty += "{}\n".format(indent(item.pretty(), 2))

        if getattr(self, 'effects', None):
            pretty += "\tEffects: {:d}\n".format(len(self.effects))
            for item in self.effects:
                pretty += "{}\n".format(indent(item.pretty(), 2))

        return pretty


class Event(BaseEvent):
    '''"Root" events, such as Port Interactions'''

    _REQUIRED_FIELDS = set((
        "ChildBranches",
        'QualitiesRequired'
    ))
    _OPTIONAL_FIELDS = BaseEvent._OPTIONAL_FIELDS | set((
        "Autofire",
        'Category',
        'LimitedToArea',
        'QualitiesAffected'
    ))
    _IGNORED_FIELDS  = set((
        'CanGoBack',
        'ChallengeLevel',
        "Deck",
        "Distribution",
        'ExoticEffects',
        "Ordering",
        "Setting",
        "Stickiness",
        'Transient',
        "Urgency",
    ))

    def __init__(self, data, idx=0, qualities=None, locations=None, ss=None):
        super(Event, self).__init__(data=data, idx=idx, qualities=qualities, ss=ss)

        self.autofire = self._data.get("Autofire", False)
        self.category = self._data.get("Category", 0)

        self.location = None
        if 'LimitedToArea' in self._data:
            iid = self._data['LimitedToArea']['Id']
            if locations:
                self.location = locations.get(iid)

            if not self.location:
                log.warning("Could not find Location for %r: %d", self, iid)
                self.location = Location(self._data['LimitedToArea'])

        self.actions = []
        for i, item in enumerate(self._data.get('ChildBranches', []), 1):
            self.actions.append(Action(data=item, idx=i,
                                       qualities=qualities,
                                       parent=self,
                                       ss=self.ss))

    def pretty(self):
        pretty = super(Event, self).pretty()

        if self.location:
            pretty += "\tLocation: {}\n".format(self.location)

        if self.actions:
            pretty += "\n\tActions: {:d}".format(len(self.actions))
            for item in self.actions:
                pretty += "\n{}\n".format(indent(item.pretty(), 2))

        return pretty

    def wikipage(self):
        page = format_obj(
            '=={name}==\n'
            '{{{{Infobox story\n'
            '|name         = {name}\n'
            '|image        = {{{{PAGEIMAGE|{name}}}}}\n'
            '|id           = {id}\n'
            '|px           = 260px\n'
#            '|category     = [[Story Event]]'
#            '|type         = [[Story Event#Pigmote Isle|Pigmote Isle]]'
            '|linked       = {{{{link icon|{location}}}}}\n'
            '}}}}\n'
            "'''{name}''' is a [[Sunless Sea]] [[Story Event]] in [[{location}]]\n"
            '\n\n'
            '----\n'
            '===Description===\n'
            "''\"{description}\"''\n"
            '\n\n'
            '----\n'
            '===Trigger Conditions===\n'
            "'''{name}''' is triggered under the following conditions:\n"
            , self,
            location=self.location.name if self.location else "",
        )
        for item in self.requirements:
            page += '* {}\n'.format(item.wiki())

        page += (
            '\n\n'
            '----\n'
            '===Interactions===\n'
            '{| class="ss-table sortable" style="width: 100%;"\n'
            '! style="width:10%;" | Interaction\n'
            '! style="width:20%;" | Unlocked by\n'
            '! style="width:20%;" | Effects\n'
            '! style="width:10%;" | Notes\n'
            '\n'
        )
        page += "\n".join((_.wikirow() for _ in self.actions))
        page += '\n|-\n|}'

        return page


class Action(BaseEvent):
    _REQUIRED_FIELDS = set((
        "QualitiesRequired",
        'ParentEvent'
    ))
    _OPTIONAL_FIELDS = (
        set(BaseEvent._OPTIONAL_FIELDS) |
        set(BaseEvent._OUTCOME_TYPES)   |
        set(_+"Chance" for _ in BaseEvent._OUTCOME_TYPES)
    )
    _IGNORED_FIELDS = set((
        'ActionCost',
        'ButtonText',
        "Ordering",
    ))

    _outcome_label_replaces = (("Event", ""),
                               ("Rare", "Rare "),
                               ("Success", "Successful"))
    _outcome_label_failed   = (("Default", "Failed"),)

    def __init__(self, data, idx=0, qualities=None, parent=None, ss=None):
        super(Action, self).__init__(data=data, idx=idx, qualities=qualities, parent=parent, ss=ss)

        self.outcomes = []
        failed = 'SuccessEvent' in self._data
        for item in self._OUTCOME_TYPES:
            if item in self._data:
                self.outcomes.append(Outcome(
                     data      = self._data[item],
                     qualities = qualities,
                     parent    = self,
                     ss        = self.ss,
                     otype     = item,
                     chance    = self._data.get(item + 'Chance', None),
                     label     = self._outcome_label(item, failed)))

        # Integrity checks
        if not self.outcomes:
            log.warn("%r has no outcomes!", self)
        elif self.outcomes[0].type != self._OUTCOME_TYPES[0]:
            log.warn("%r first outcome is not '%s': '%s'",
                     self, self._OUTCOME_TYPES[0], self.outcomes[0].type)

    @property
    def gamenote(self):
        note = re.search(r'\[([^\]]*)\]', self.description)
        if note:
            return note.group(1)
        return ""

    def pretty(self):
        pretty = super(Action, self).pretty().strip()

        for item in self.outcomes:
            pretty += "\n\n{}".format(indent(item.pretty(), 1))

        return pretty

    def wikirow(self):
        note = self.gamenote
        return '''|-
            | {name}
            |
            <ul>
            {reqs}
            </ul>
            | {outs}
            |{note}
        '''.replace(4 * " ", "").format(
            name=self.name,
            reqs="<p></p>\n".join(_.wiki() for _ in self.requirements) or "-",
            outs="\n<br>\n".join(_.wiki() for _ in self.outcomes) or "-",
            note=iif(note, " {{{{game note|{}}}}}".format(note))
        )

    def _outcome_label(self, otype, failed):
        label = otype
        for sfrom, sto in (self._outcome_label_replaces +
                           (self._outcome_label_failed if failed else ())):
            label = label.replace(sfrom, sto)
        return label


class Outcome(BaseEvent):
    _REQUIRED_FIELDS = set()
    _OPTIONAL_FIELDS = BaseEvent._OPTIONAL_FIELDS - {'Image'} | set((
        "QualitiesAffected",
        "LinkToEvent",
    ))
    _IGNORED_FIELDS  = set((
        'Category',
        'ExoticEffects',
        'MoveToArea',
        "Urgency",
        "SwitchToSetting",
        "SwitchToSettingId",
    ))

    def __init__(self, data, idx=0, qualities=None, parent=None, ss=None,
                 otype=None, chance=None, label=None):
        super(Outcome, self).__init__(data=data, idx=idx,
                                      qualities=qualities, parent=parent, ss=ss)

        self.type    = otype
        self.chance  = chance
        self.label   = label
        self.trigger = self._data.get('LinkToEvent', {}).get('Id', None)

    def pretty(self):
        pretty = "{} Outcome{}:\n{}\n".format(self.label,
                                      " {}%".format(self.chance)
                                            if self.chance else "",
                                      indent(super(Outcome, self).pretty(), 1))

        if self.trigger:
            pretty += "\t\tTrigger event: {}\n".format(self.trigger)

        return pretty

    def wiki(self):
        return '''
            {label} event{chance}<br>{name}
            <ul>
            {effects}{sep}{trigger}
            </ul>
            '''.replace(4 * " ", "").format(
            chance  = iif(self.chance, " ({}%)".format(self.chance)),
            label   = self.label,
            name    = iif(self.name, "{{{{effect title|{}}}}}".format(self.name)),
            effects = "<p></p>\n".join(_.wiki() for _ in self.effects),
            sep     = iif(self.effects and self.trigger, "<br>\n"),
            trigger = iif(self.trigger and self.trigger != self.parent.parent.id,
                          "{{{{trigger event|{}}}}}".format(self.trigger)),
        ).strip()


class Entities(object):
    '''Base class for entity containers. Subclasses SHOULD override EntityCls!'''
    EntityCls=Entity

    def __init__(self, data=None, entities=None, ss=None, *eargs, **ekwargs):
        self._entities = {}
        self._order = []
        self.ss = ss

        if entities is None:
            for idx, edata in enumerate(data, 1):
                entity = self.EntityCls(data=edata, idx=idx, ss=self.ss,
                                        *eargs, **ekwargs)
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

    def wikipage(self):
        page = ('')
        page += "\n\n".join((_.wikipage() for _ in self))
        page += ''
        return page

    def dump(self):
        return "\n".join((_.dump() for _ in self))

    def pretty(self):
        return "\n".join((_.pretty() for _ in self))

    def show(self):
        return "\n".join((unicode(_) for _ in self))

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


class Qualities(Entities):
    EntityCls=Quality


class Locations(Entities):
    EntityCls=Location


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


class QualityOperator(object):
    '''Base Class for Effects and Requirements'''

    _NOT_OP  = ('AssociatedQuality', 'Id')
    _HIDE_OP = ('VisibleWhenRequirementFailed',
                'BranchVisibleWhenRequirementFailed',
                'Priority',
                'ForceEquip')

    _STR_OP  = dict(
        # Requirements
        MinLevel             = '≥',
        MinAdvanced          = '≥',
        MaxLevel             = '≤',
        MaxAdvanced          = '≤',
        DifficultyLevel      = 'challenge',
        DifficultyAdvanced   = 'challenge',

        # Effects
        Level                = '+=',
        ChangeByAdvanced     = '+=',
        SetToExactly         = '=',
        SetToExactlyAdvanced = '=',
        OnlyIfAtLeast        = 'if ≥',
        OnlyIfNoMoreThan     = 'if ≤',
    )

    _reverse = ('Terror', 'Hunger', 'Menaces: Wounds')

    def __init__(self, data, parent=None, ss=None):
        self.id       = data['Id']
        self.parent   = parent
        self.ss       = ss
        self.quality  = None
        self.operator = {_:data[_] for _ in data
                         if _ not in self._NOT_OP}

        qid = data['AssociatedQuality']['Id']
        if self.ss and self.ss.qualities:
            self.quality = self.ss.qualities.get(qid)

        if not self.quality:
            # Create a dummy one
            self.quality = Quality(data=data['AssociatedQuality'], ss=self.ss)
            log.warning("Could not find Quality for %r: %d",
                        parent, qid)

    def pretty(self, _level=0):
        return indent(format_obj("{id} - {name} {ops}",
                                 self.quality,
                                 ops = self._format_ops(self.operator)),
                      _level)

    def wiki(self):
        if 'Level' in self.operator:
            return '{{{{link qty|{level:+d}|{name}{rev}}}}}{sep}{ops}'.format(
                name=self.quality.name,
                rev="||-" if self.quality.name in self._reverse else "",
                level=self.operator['Level'],
                sep=", " if len(self.operator) > 1 else "",
                ops=self._format_ops(self.operator, hidelist=['Level']),
            )
        else:
            return '{{{{link icon|{name}}}}} {ops}'.format(
                name=self.quality.name,
                ops=self._format_ops(self.operator)
            )

    def _format_ops(self, ops, sep_op=" and ", sep_pair=" ", hidelist=None, raw=False):
        '''Basic operator formatting:
            {'MaxLevel': 2, 'MinLevel': 1} => "MaxLevel: 2, MinLevel: 1"
        '''
        return sep_op.join(sep_pair.join(
            (k if raw
                else self._STR_OP.get(k, k),
             self._parse_advanced(str(v))))
            for k,v in ops.iteritems()
            if k not in (() if raw else self._HIDE_OP)+tuple(hidelist or ()))

    def _format_str(self):
        _OPS = (
            # Requirements
            'MinLevel',
            'MinAdvanced',
            'MaxLevel',
            'MaxAdvanced',
            'DifficultyLevel',
            'DifficultyAdvanced',
            # Effects
            'Level',
            'ChangeByAdvanced',
            'SetToExactly',
            'SetToExactlyAdvanced',
            'OnlyIfAtLeast',
            'OnlyIfNoMoreThan',
        )

    def _parse_advanced(self, opstr, fmt="[{name}]", *args, **kwargs):
        result = opstr
        for match in re.finditer(r'\[(?P<key>[^:]+):(?P<value>[^\]]+)\]', opstr):
            try:
                mstr, (key, value) = match.group(), match.group('key', 'value')
            except Exception:
                print((repr(self), opstr, match))
                sys.exit()

            if   key == 'q':
                if self.ss and self.ss.qualities:
                    quality = self.ss.qualities.get(int(value))
                else:
                    quality = None
                if not quality:
                    # Create a dummy one
                    quality = Quality(data={'Id': int(value)}, ss=self.ss)
                    log.warning("Could not find Quality for %r.%r: %s",
                                self.parent, self, mstr)

                subst = format_obj(fmt, quality, *args, **kwargs)

            elif key == 'd':
                subst = "[1 to {}]".format(value)
            else:
                subst = None

            if subst:
                result = result.replace(mstr, subst, 1)

        return result

    def __str__(self):
        return "{qname} {operator}".format(
            qname    = self.quality.name,
            operator = self._format_ops(self.operator))

    def __repr__(self):
        return b"<{cls} {id}: {qid} - {qname} {ops}>".format(
            cls   = self.__class__.__name__,
            id    = self.id,
            qid   = self.quality.id,
            qname = repr(self.quality.name),
            ops   = repr(self.operator))


class Effect(QualityOperator):
    pass


class Requirement(QualityOperator):
    pass


class SunlessSea(object):
    '''
        Manager class, the one that loads the JSON files
        and call each entity container's constructor
    '''
    def __init__(self, datadir=None):
        self.qualities = Qualities(data=self._load('qualities', datadir), ss=self)
        self.locations = Locations(data=self._load('areas',     datadir), ss=self)
        self.events    = Events(   data=self._load('events',    datadir), ss=self,
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
