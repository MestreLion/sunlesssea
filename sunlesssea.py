#!/usr/bin/env python3
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
    Tools for Sunless Sea data dumps and autosave editing
"""

# Ideas / To-Do list
# ------------------
# - Make q/e/l/a entity cmd arg optional, by default searches all entities.
# - Create --exact|-E to match exact names (useful for 'supplies' and others)
# - Improve Entities.filter(): if attr value is str, do partial/insentive like find()
# - Custom parsing for ExocticEffets (specially Game Win/Lose, Move to Port, etc)
# - cmd-line arg for Outcomes, Effects, Requirements, Actions, including -a
# - Rename Quality.usage() to .interactions(), create .obtain() and .usage()
#   - obtain() for ways to get (positive Effects and shop buy)
#   - usage() for ways to use/spend (Requirements, negative sffects, shop sell)
#   - interactions() for both, all mentions (similar to current  usage())
#     - Improve interactions():
#       - Look for "[q:{id}]" in Advanced operators (done already?)
#       - show all Event and Action Requirements, as well as all Outcomes.
#         (as a side-effect, will dramatically simplify the code)
# - Quality need a custom wikipage() with {{quality status}} listings
# - pretty(short=True), so they can use each other [PARTIALLY DONE, need cmd-line]
#    Ex: Location.pretty(short=True) does not print description, short Event
#        does not print Quality status; short Quality does not print status list
# - make pretty uniform across indent, \n, etc. Not there yet
#    Idea: functions return with trailing '\n' if there is content
#        Callers can .strip() if they want or "".join() directly
# - format +[1 to x] so it can use {{qty}} to get non-text color
# - read text statuses on numeric quality assignments/tests
#    so "QualityX := 3" => "QualityX := 3, [3's Status Description]"
#    or even "Description" (think about SAY) [PARTIALLY DONE, can be smarter]
# - Improve (or even completely deprecate) format_obj using better .format()
#    specs and ideas from http://code.activestate.com/recipes/577227/
# - Improve SaveQualities/SaveQuality: Better pretty/bare, proper idx on .wiki()
# - Take a look on _IGNORED/OPTIONAL_FIELDS, and parse more of them.
# - Revamp QualityOperator._format() the same way done in Requirement.
#   - Also, either move to Effects (good) or unify them both (possibly not viable)
# - Create a ShipSlots hardcoded mapping table, recreating game DLL data
# - class Dummy with __bool__() returning False, each class has a dummy counterpart,
#   inheriting from both itself and Dummy, all instance attributes as class attributes,
#   falsy value, no specialized methods. To be used as return value instead of None
# - Implement challenges in Requirement.check()
# - Implement Entities._eval_adv() for Effect.apply() and Requirement.check(). ast.parse
# - Fix Outcome.label/__str__()/re.sub() madness, and create a proper __repr__()
# - Result values from Requirement.check()/Action.do() are messy.

# Knowledge
# ------------------
# Journal: sections named by Tag.
# Ship Slots: the Ship<->Slots mapping are hardcoded in game's DLL files :(
#   But can be somewhat edited by changing the Slot Quality value to 1
#   (meaning you/the ship "possess" the slot). Whenever you change ships,
#   game resets the slots values to the hardcoded ones.
#   This allows editing the slots of your *current* ship, but prevents getting
#   other ship's slots from JSON data


import argparse
import bisect
import collections
import enum
import json
import logging
import math
import os
import random
import re
import sys
import urllib.parse


log = logging.getLogger(os.path.basename(os.path.splitext(__file__)[0]))

# Changed by main() on command-line args
TEST_INTEGRITY = False

ENTITIES = {
    'autosave':  'autosave',
    'event':     'events',
    'location':  'locations',
    'quality':   'qualities',
    'shop':      'shops',
    'demo':      None,
}




################################################################################
# General helper functions

def safeprint(text=""):
    # print() chooses encoding based on stdout type, if it's a tty (terminal)
    # or file (redirect/pipe); For ttys it auto-detects the terminals's
    # preferred encoding, but for files and pipes, sys.stdout.encoding
    # defaults to None in Python 2.7, so ascii is used (ew!).
    # In this case we encode to UTF-8.
    # See https://stackoverflow.com/questions/492483
    print(text)



def format_obj(fmt, obj, *args, **kwargs):
    objdict = {_:getattr(obj, _) for _ in vars(obj) if not _.startswith('_')}
    objdict.update(dict(str=str(obj), repr=repr(obj)))
    objdict.update(kwargs)
    return fmt.format(*args, **objdict)



def indent(text, level=1, pad='\t'):
    '''Indent a text. As a side-effect it also strip trailing whitespace,
        even for level = 0
    '''
    if not level:
        return text.rstrip()
    indent = level * pad
    return "{}{}".format(indent,
                         ('\n'+indent).join(text.rstrip().split('\n')))



def iif(cond, trueval, falseval=""):
    if cond:
        return trueval
    else:
        return falseval



# FIXME: Not used yet, most likely will never be
def try_number(value):
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value



class Error(Exception):
    """Base class for custom exceptions, with errno and %-formatting for args.

    All modules in this package raise this (or a subclass) for all
    explicitely raised, business-logic, expected or handled exceptions
    """
    def __init__(self, msg:str="", *args, errno:int=0):
        super().__init__(str(msg) % args)
        self.errno = errno


class CheckResult:
    """Enum-like class, attributes used as return value of Requirement.check()

    Represents the requirement evalualion to determine the action outcome:
    LOCKED :      Requirement NOT met, action is "Locked". Value is Falsy by design.
    DEFAULT:      Requirement met, no challenge.
    RARE:         Requirement met, no challenge, rare outcome.
    FAILURE:      Requirement met but challenge failed.
    SUCCESS:      Requirement met and challenge successful.
    RARE_FAILURE: Requirement met and challenge had a rare failure.
    RARE_SUCCESS: Requirement met and challenge had a rare success.
    """
    LOCKED       = ""
    DEFAULT      = "DEFAULT"
    RARE         = "RAREDEFAULT"
    FAILURE      = "Default"  # Similar to DEFAULT by design: they're the same in game data
    SUCCESS      = "Success"
    RARE_FAILURE = "RareDefault"
    RARE_SUCCESS = "RareSuccess"


################################################################################
# Main() and helpers

def get_datadir():
    # Linux and FreeBSD
    if sys.platform.startswith("linux") or sys.platform.startswith("freebsd"):
        import xdg.BaseDirectory as xdg
        return os.path.join(xdg.xdg_config_home,
                            "unity3d/Failbetter Games/Sunless Sea")

    # Mac OSX
    elif sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/"
                                  "Unity.Failbetter Games.Sunless Sea")

    # Windows
    elif sys.platform == "win32":
        return os.path.expanduser("~\\AppData\\LocalLow\\"
                                  "Failbetter Games\\Sunless Sea")

    return "."  # and pray for the best...



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

    parser.add_argument('-c', '--check',
                        dest='check',
                        action="store_true",
                        default=False,
                        help="Perform integrity checks, takes about 20%% longer.")

    parser.add_argument('-d', '--datadir',
                        default=get_datadir(),
                        help="Game data directory. [Default: %(default)s]")

    parser.add_argument('-f', '--format',
                        choices=('bare', 'dump', 'json', 'pretty', 'wiki', 'wikipage'),
                        default='pretty',
                        help="Output format. 'wiki' is awesome!"
                            " Available formats: [%(choices)s]."
                            " [Default: %(default)s]")

    parser.add_argument('-a', '--attribute',
                        nargs=2,
                        metavar=('ATTRIBUTE','VALUE'),
                        help="Only entities where ATTRIBUTE == VALUE")

    group = parser.add_mutually_exclusive_group()
    group.add_argument('-U', '--usage', const="usage",
                       dest='method',
                       action="store_const",
                       help="Show quality usage")
    group.add_argument('-R', '--related', const="related",
                       dest='method',
                       action="store_const",
                       help="Show event related images")
    group.add_argument('-C', '--cargo', const="cargo",
                       dest='method',
                       action="store_const",
                       help="Show current cargo and total hold space in Autosave")

    parser.add_argument(dest='entity',
                        choices=sorted(set(ENTITIES) | set(_[0] for _ in ENTITIES)),
                        metavar="ENTITY",
                        default='event',
                        nargs='?',
                        help="Entity to work on."
                            " Available entities: {}."
                            " [Default: %(default)s]".format(list(ENTITIES)))

    parser.add_argument(dest='filter',
                        nargs='?',
                        metavar="MATCH",
                        help="Match entities by numerical ID or name"
                            " (partial, case-insentitive).")

    args = parser.parse_args(argv)
    args.debug = args.loglevel == logging.DEBUG
    if len(args.entity) == 1:
        args.entity = [_ for _ in ENTITIES if _[0] == args.entity][0]
    args.entity = ENTITIES.get(args.entity) or args.entity

    return args



def main(argv=None):
    global TEST_INTEGRITY
    args = parse_args(argv or [])
    logging.basicConfig(level=args.loglevel,
                        format='%(levelname)s: %(message)s')
    log.debug(args)
    TEST_INTEGRITY = args.check

    ss = SunlessSea(args.datadir)

    log.debug(ss.locations)
    log.debug(ss.qualities)
    log.debug(ss.events)
    log.debug(ss.shops)

    if args.entity == "demo":
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

    if args.method == 'cargo':
        for q in ss.autosave.qualities:
            if q.in_cargo:
                print(q)
        print("Cargo in hold: {}/{}".format(ss.autosave.cargo,
                                            ss.autosave.hold))
        return

    # General entities
    entities = (ss.autosave.qualities if args.entity == "autosave" else
                getattr(ss, args.entity)).find(args.filter)

    if args.attribute:
        entities = entities.filter(*args.attribute)

    if not entities:
        if args.attribute and args.filter:
            log.error("No %s found matching %r with %s == %r",
                      args.entity, args.filter, *args.attribute)
        elif args.attribute:
            log.error("No %s found with %s == %r", args.entity, *args.attribute)
        elif args.filter:
            log.error("No %s found matching %r", args.entity, args.filter)
        else:
            log.error("No %s found", args.entity)
        return 1

    if args.method == 'usage':
        if not args.entity == 'qualities':
            log.error("Method 'usage' only available for qualities")
            return 1
        safeprint(entities.usage(args.format))
        return
    elif args.method == 'related':
        if not args.entity == 'events':
            log.error("Method 'related' only available for events")
            return 1
        safeprint(entities.wiki_linkicons())
        return

    if args.format == 'wiki':
        safeprint(entities.wikitable())
    elif args.format == 'wikipage':
        safeprint(entities.wikipage())
    elif args.format == 'pretty':
        safeprint(entities.pretty())
    elif args.format == 'dump':
        safeprint(entities.dump())
    elif args.format == 'json':
        safeprint(entities.to_json())
    else:
        safeprint(entities.bare())
    return



################################################################################
# Classes

class Entity:
    '''Base class for an Entity
        Subclasses MAY override or extend _REQUIRED_FIELDS, and MAY override
        _OPTIONAL_FIELDS and _IGNORED_FIELDS
    '''

    _ENTITY_FIELDS    = set(("Id", "Name", "Description", "Image"))
    _ENTITY_REQUIRED  = set(("Id",))

    _REQUIRED_FIELDS  = set(_ENTITY_FIELDS)
    _OPTIONAL_FIELDS  = set()  # Converted to attributes using default values
    _IGNORED_FIELDS   = set()  # No attributes created

    _re_gamenote = re.compile('\[([^\]]+)]"?$')
    _re_adv = re.compile('\[(?P<key>[a-z]+):(?P<value>(?:[^][]+|\[[^][]+])+)]')


    def __init__(self, data, idx=0, ss=None):
        self._data = data
        self.idx   = idx
        self.ss    = ss
        self.id    = self._data['Id']

        self.name        = self._data.get('Name', "").strip()
        self.description = self._data.get('Description', "").strip()
        self.image       = (self._data.get('Image', None) or
                            self._data.get('ImageName', ""))  # Locations

        if TEST_INTEGRITY:
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

        if not self.ss:
            log.error("%r has no reference to a SunlessSea instance", self)


    @property
    def etype(self):
        # Just a convenience. Provisional name (and method)
        return self.__class__.__name__

    @property
    def name_adv(self):
        return self._parse_adv(self.name)

    @property
    def description_adv(self):
        return self._parse_adv(self.description)

    @property
    def description_pretty(self):
        return self._pretty_text(self.description_adv)

    @property
    def name_wiki(self):
        return self._parse_adv(self.name, qnamefmt="[q:[[{}]]]")

    @property
    def description_wiki(self):
        return self._parse_adv(
            "\n".join(_.strip() for _ in
                      self.description.replace("\r","").split('\n')),
            qnamefmt="{{{{quality|{}}}}}")

    @property
    def image_wiki_title(self):
        return urllib.parse.quote("File:SS {}.png".format(
            self.name.replace(":", "").replace("?", "")))

    @property
    def image_wiki_file(self):
        return "File:SS {}small.png".format(self.image or "")

    @property
    def gamenote(self):
        match = re.search(self._re_gamenote, self.description)
        if match:
            return match.group(1)
        return ""


    def dump(self):
        return self._data


    def to_json(self):
        return json.dumps(self._data, indent=4, separators=(',',':'))


    def bare(self, sep='\t'):
        if self.name:
            return "{}{}{}".format(self.id, sep, self.name)
        else:
            return str(self.id)


    def pretty(self, short=False):
        pretty = "{:d}".format(self.id)
        if self.name:        pretty += " - {}".format(self.name_adv)
        if self.image:       pretty += " ({})".format(self.image)
        if self.description and not short:
            # Trailing '\n' is intentional, blank line after Description
            pretty += "\n\t{}\n".format(self.description_pretty)
        #pretty += "\n"
        return pretty


    def wiki(self):
        return self.name_wiki or str(self.id)


    def wikirow(self):
        return format_obj(
            "|-\n"
            "| {idx}\n"
            "| {id}\n"
            "| [[{name_wiki}]]\n"
            "| {{{{game icon|{image}}}}}\n"
            "| {description_wiki}\n",
            self)


    def wikipage(self):
        return format_obj(
            "=={name_wiki}==\n"
            "* <nowiki>{repr}</nowiki>\n"
            "* {wiki}\n",
            self, wiki=self.wiki(), repr=repr(self))


    def _pretty_text(self, text, cut=120, elipsis="(...)"):
        '''Quotes and limits a text, replacing control characters'''
        if cut and len(text) > cut:
            text = text[:cut-len(elipsis)] + "(...)"
        # repr() quotes and fixes \n, \r
        return repr(text)


    def _parse_adv(self, text, qfmt="[{name}]", qbfmt="[Base {name}]", dfmt="[1 to {}]",
                   noqfmt="[Quality({})]", qnamefmt="{{{}}}"):
        '''
        Parse "Advanced" strings containing references to entities in [k:v] format

        Current references are:
        [q:ID]   - Quality by ID, return its current effective value, i.e.,
                     Level + EffectiveLevelModifier
        [qb:ID]  - Quality by ID, return its current base value, i.e., only Level
        [q:NAME] - Quality by name, return LevelDescriptionText for its current Level
        [d:NUM]  - Dice roll, 1 to NUM

        Some very basic nesting is also used, only in [d:...], as in:
        [d:[q:ID]] - Dice roll, 1 to Quality(ID).Level

        No other nestings are found, only combinations and expressions:
        "[d:[q:108665]] - [d:5] - (100 * [q:112904])"

        Altough not used, this method also supports nesting combos such as:
        "OK [d:99+[q:102898]+2*[q:112904]+10], [q:123], [q:something], [k:foo]"

        Parameters:
            opstr: String being searched for references
            qfmt:     Formatting string for Qualities looked up by ID.
                        Use Quality attribute names such as '{name}', '{id}'.
                        '{str}' for str(Quality) and '{repr}' for its repr()
            dfmt:     Formatting string for dice rolls. '{}' for the value
            noqfmt:   Formatting string for Quality ID not found in Qualities
                        '{}' for the ID
            qnamefmt: Formatting string for Quality name. No Qualities lookup
                        is actually performed. '{}' for the name content.
        '''
        if not isinstance(text, str):
            return text

        result = text
        for match in re.finditer(self._re_adv, text):
            mstr, (key, value) = match.group(), match.group('key', 'value')
            subst = None
            quality = None

            # Qualities
            if key in ('q', 'qb'):
                # By ID, used in Requirements and Effects
                if value.isdigit():
                    if self.ss and self.ss.qualities:
                        quality = self.ss.qualities.get(int(value))
                    if quality:
                        subst = format_obj(qbfmt if key == 'qb' else qfmt,
                                           quality, quality=quality)
                    else:
                        subst = noqfmt.format(value)
                        log.warning("Could not find Quality ID %s for %r in %r",
                                    value, self, text)
                # By name, used in many Descriptions and in some Names
                else:
                    # Key 'qb' is never used with names, so only qnamefmt is used
                    subst = qnamefmt.format(value)

            # Dice roll
            elif key == 'd':
                subst = dfmt.format(self._parse_adv(value, qfmt, qbfmt, dfmt,
                                                    noqfmt, qnamefmt))

            else:
                log.warn("Unknown %r key when parsing advanced string: %r",
                         key, text)

            if subst:
                result = result.replace(mstr, subst, 1)

        return result


    def __lt__(self, other):
        return self.id < other.id


    def __repr__(self):
        if self.name:
            return "<{} {:d}: {}>".format(self.__class__.__name__,
                                           self.id,
                                           repr(self.name))
        else:
            return "<{} {:d}>".format(self.__class__.__name__,
                                       self.id)


    def __str__(self):
        return self.name if self.name else repr(self)



class Quality(Entity):
    _REQUIRED_FIELDS = {'Name'}
    _OPTIONAL_FIELDS = set((
        "AvailableAt",
        "Description",
        "Image",

        "ChangeDescriptionText",
        "LevelDescriptionText",
        "LevelImageText",

        "Cap",
        "Category",
        'DifficultyScaler',
        "DifficultyTestType",
        "IsSlot",
        "Nature",
        "Persistent",
        "PluralName",
        "PyramidNumberIncreaseLimit",
        "Tag",
        "UsePyramidNumbers",
        "Visible",

        'AssignToSlot',
        'Enhancements',
        'UseEvent',
    ))
    _IGNORED_FIELDS  = set((
        'AllowedOn',
        'CssClasses',
        'Notes',
        'Ordering',
        'OwnerName',
        'QEffectPriority',
        'QualitiesPossessedList',
        'VariableDescriptionText',  # Only on ID=126669, "{}" (string)
    ))

    _status_fields = (
        # Attribute name   JSON key                 Caption for .pretty()
        ('level_status',  'LevelDescriptionText',  'Journal Descriptions'),
        ('change_status', 'ChangeDescriptionText', 'Change Descriptions'),
        ('image_status',  'LevelImageText',        'Images'),
    )


    def __init__(self, data, idx=0, ss=None):
        super(Quality, self).__init__(data=data, idx=idx, ss=ss)
        # For scalar (atomic, non-mutable) values only!
        for attr, atype, default in (
            ("AvailableAt",                str,  ""),
            ("Cap",                        int,  0),
            ("Category",                   int,  0),
            ("DifficultyScaler",           int,  0),
            ("DifficultyTestType",         int,  0),
            ("IsSlot",                     bool, False),
            ("Nature",                     int,  0),
            ("Persistent",                 bool, False),
            ("PluralName",                 str,  ""),
            ("PyramidNumberIncreaseLimit", int,  0),
            ("Tag",                        str,  ""),
            ("UsePyramidNumbers",          bool, False),
            ("Visible",                    bool, False),
        ):
            setattr(self, attr.lower(), atype(self._data.get(attr, default)))

        def _parse_status(value):
            if not value:
                return {}
            return {int(k):v for k,v in sorted(row.split("|")
                                               for row in value.split("~"))}

        for attr, key, _ in self._status_fields:
            setattr(self, attr, _parse_status(self._data.get(key, "")))

        # Both assign and enhancements referece other qualities that might not
        # have been loaded yet, as well as UseEvent.
        # Post-processing for them is performed by SunlessSea()
        self.assign = self._data.get('AssignToSlot', {}).get('Id', None)
        self.enhancements = self._data.get('Enhancements', [])
        self.event = self._data.get('UseEvent', {}).get('Id', None)

        if TEST_INTEGRITY:
            if self.assign and self.category not in (
                  106,  # Officers, with a couple exceptions
                  150,  # Curiosities (Zong of Zee and mis-categorized officers)
                  200,  # Cargo (assignable items are Equipments)
                10000,  # Ships
            ):
                log.error("Category mismatch for %r: %d, assigns to %s",
                          self, self.category, self.assign)

            if self.is_officer and not self.assign:
                log.error("Officer with no slot assignment: %r", self)

            if (
                (self.category == 10000 and not self.tag == "Ship"    ) or
                (self.tag == "Ship"     and not self.category == 10000)
            ):
                log.error("Category and tag mismatch for %r: %d, '%s'",
                          self, self.category, self.tag)


    @property
    def is_luck(self):
        return self.category == 2000  # A Single member, 'Luck', ID=432

    @property
    def is_officer(self):
        # Most are 106, except Urbane Magician and Keeper-Moth, both 150
        # Monkey Foundling, Eyeless Skull, Your Father: 106 but not Tag Officer
        return self.category == 106 or self.tag == "Officer"

    @property
    def is_cargo(self):
        return self.category == 200

    @property
    def difficulty_factor(self):
        if not self.difficultyscaler:
            return 0
        return 100.0 / self.difficultyscaler


    def challenge_cap(self, difficulty):
        if not(difficulty or self.difficultyscaler):
            return difficulty

        if self.is_luck:
            return 50 - difficulty * self.difficultyscaler

        return (int(math.ceil(difficulty * self.difficulty_factor)))


    def status_for(self, value):
        #FIXME: add an option for bisect_right(), for tests on Min value (<=)
        # See https://docs.python.org/3/library/bisect.html and
        #     https://code.activestate.com/recipes/577197-sortedcollection/
        def largest_lesser(d, v):
            if not d:
                return
            keys = sorted(d.keys())
            i = bisect.bisect_left(keys, v)
            if i:
                return d[keys[i-1]]
        return (self.change_status.get(value) or
                self.level_status.get(value) or
                largest_lesser(self.change_status, value) or
                largest_lesser(self.level_status, value)
                or "").rstrip('.') or ""


    def pretty(self):
        pretty = super(Quality, self).pretty()

        if self.availableat:
            pretty += "{}\t{}\n".format(iif(self.description, "", '\n'),
                                        self.availableat)

        pretty += "\n\tCategory: {}".format(self.category)
        if self.tag:
            pretty += "\n\tTag: {}".format(self.tag)

        if self.event:
            pretty += "\n\tUse event: {}".format(self.event.bare(sep=" - "))

        if self.assign:
            pretty += "\n\tAssignable to {} slot".format(self.assign)

        if self.enhancements:
            pretty += "\n\tEnhancements: {:d}\n\t\t{}".format(
                len(self.enhancements),
                "\n\t\t".join(_.pretty().strip() for _ in self.enhancements))

        if self.isslot:
            pretty += "\n\tIs a slot"

        for attr, _, caption in self._status_fields:
            statuses = getattr(self, attr)
            if statuses:
                pretty += "\n\n\t{}: {:d}".format(caption, len(statuses))
                for status in sorted(statuses.items()):
                    pretty += "\n\t\t[{}] - {}".format(*status)

        return pretty


    def usage(self, formatting='pretty'):
        '''
        Shows all usages, that is: all events, actions, outcomes and shops
        this appears as either a requirement, effect or tradable item

        Highly experimental! Ugly output! Cryptic coding! Use at your own risk!
            OTOH, this is awesome!
        '''

        if not formatting == 'pretty':
            log.info("You don't want pretty, but that's what you'll get")

        qid = self.id
        results = {}
        output = []
        for e in self.ss.events:
            for r in e.requirements:
                if r.quality.id == qid:
                    results.setdefault(e,
                        dict(req=None, eff=None, act={}))['req'] = r
                    break

            for f in e.effects:
                if r.quality.id == qid:
                    results.setdefault(e,
                        dict(req=None, eff=None, act={}))['eff'] = f
                    break

            for a in e.actions:
                for r in a.requirements:
                    if r.quality.id == qid:
                        results.setdefault(e,
                            dict(req=None, eff=None, act={}))['act'].setdefault(a,
                                dict(req=None, out=[]))['req'] = r
                        break

                for o in a.outcomes:
                    for f in o.effects:
                        if f.quality.id == qid:
                            results.setdefault(e,
                                dict(req=None, eff=None, act={}))['act'].setdefault(a,
                                    dict(req=None, out=[]))['out'].append(o)
                            break

        for s in self.ss.shops:
            for i in s.items:
                if qid in (i.item.id, i.currency.id):
                    results.setdefault(s, []).append(i)

        def _print(e, i=0):
            if not e:  # No object (None) or blank line ("")
                if not i:
                    output.append("")
                return

            if e.etype == "Outcome":
                out = e.pretty(short=True)
            elif e.etype == "Event":
                out = "{} {}{}".format(
                        e.etype.upper(), e,
                        " [{}]".format(e.location)
                            if e.location else "",
                )
            elif e.etype == "Shop":
                out = "{} {}{}".format(
                        e.etype.upper(), e,
                        " [{}]".format(", ".join(str(_) for _ in e.locations))
                            if e.locations else "",
                )
            else:
                out = "{} {}".format(e.etype.upper(), e)

            output.append(indent(out, i))


        for e, r in sorted(results.items()):
            _print(e)

            if e.etype == "Shop":
                for i in r:
                    _print(i, 1)
                _print("")
                continue

            _print(r['req'], 1)
            _print(r['eff'], 1)
            for a in r['act']:
                _print(a, 1)
                _print(r['act'][a]['req'], 2)
                for o in r['act'][a]['out']:
                    _print(o, 2)
                _print("")
            #_print("")

        return "\n".join(output).strip()


    def trade(self):
        pass



class Location(Entity):
    _REQUIRED_FIELDS = set(('Name',))
    _OPTIONAL_FIELDS = set(('Description', 'ImageName', 'MoveMessage'))


    def __init__(self, data, idx=0, ss=None):
        super(Location, self).__init__(data=data, idx=idx, ss=ss)
        self.message = self._data.get('MoveMessage', "")
        self.setting = 0


    def pretty(self):
        pretty = super(Location, self).pretty().strip()  # No '\n' after Description
        if self.message:
            pretty += "\n\tMessage: {}".format(self._pretty_text(self.message))
        return pretty



class ShopItem(Entity):
    _REQUIRED_FIELDS = set(("Quality", "PurchaseQuality"))
    _OPTIONAL_FIELDS = set(("Cost", "SellPrice"))
    _IGNORED_FIELDS  = set(("BuyMessage", "SellMessage"))  # only dummies


    def __init__(self, data, idx=0, ss=None, shop=None):
        super(ShopItem, self).__init__(data=data, idx=idx, ss=ss)
        self.shop     = shop
        self.item     = ss.qualities.get(self._data['Quality']['Id'])
        self.currency = ss.qualities.get(self._data['PurchaseQuality']['Id'])
        self.buy      = self._data.get('Cost', 0)
        self.sell     = self._data.get('SellPrice', 0)


    def pretty(self):
        sell = ", sell for {}".format(self.sell) if self.sell else ""
        return "{0.item}: {0.buy} x {0.currency}{sell}".format(self, sell=sell)


    def __repr__(self):
        try:
            return ("<{0.__class__.__name__} {0.id}:"
                     " {0.item!r} ({0.buy}, {0.sell})"
                     " x {0.currency!r}>".format(self))
        except AttributeError:
            # repr() requested by base class before __init__() finishes
            return "<{0.__class__.__name__} {0.id}>".format(self)


    def __str__(self):
        return self.pretty()



class Shop(Entity):
    _REQUIRED_FIELDS = Entity._REQUIRED_FIELDS | set(('Availabilities',))
    _IGNORED_FIELDS  = {
        'Ordering',
        'QualitiesRequired',
    }


    def __init__(self, data, idx=0, ss=None, locations=None):
        super(Shop, self).__init__(data=data, idx=idx, ss=ss)
        self.locations = locations
        self.items = [ShopItem(data=_d, idx=_i, ss=self.ss, shop=self)
                      for _i, _d in
                      enumerate(self._data['Availabilities'], 1)]

        # Integrity checks
        if not TEST_INTEGRITY:
            return

        if self._data.get('QualitiesRequired'):
            log.warn("%r have non-empty 'QualitiesRequired' list: %s", self,
                     self._data['QualitiesRequired'])


    def pretty(self):
        pretty = super(Shop, self).pretty()
        locations = (
            "\n\tLocation: {}".format(", ".join(str(_) for _ in self.locations))
        ) if self.locations else ""
        items = "\n\t\t".join(_.pretty() for _ in self.items)
        return "{}{}\n\tItems: {}\n\t\t{}".format(pretty, locations, len(self.items), items)



class QualityOperator(Entity):
    '''Base Class for Effects and Requirements
        Subclasses MUST override _OPS and _OPTIONAL_FIELDS
    '''

    # Order IS relevant, hence a tuple
    _OPS = ()

    # To satisfy Entity base class
    _REQUIRED_FIELDS = {'AssociatedQuality'}
    _OPTIONAL_FIELDS = {'Id'}
    _IGNORED_FIELDS  = {
        'VisibleWhenRequirementFailed',
        'BranchVisibleWhenRequirementFailed',
        'Priority',
        'ForceEquip',
    }

    _reverse = (r'Terror$', r'Hunger$', r'Menaces:')


    def __init__(self, data, idx=0, parent=None, ss=None):
        super(QualityOperator, self).__init__(data=data, idx=idx, ss=ss)

        self.parent   = parent
        self.quality  = None
        self.operator = {_:data[_] for _ in data
                         if _ in self._OPS}

        qid = self._data['AssociatedQuality']['Id']
        if self.ss and self.ss.qualities:
            self.quality = self.ss.qualities.get(qid)

        if not self.quality:
            # Create a dummy one
            self.quality = Quality(data={'Id': qid, 'Name':''},
                                   ss=self.ss)
            log.warning("Could not find Quality for %r: %d",
                        parent, qid)

        # Integrity check
        if TEST_INTEGRITY:
            if not self.operator:
                log.error("No relevant operators in %r.%r",
                         self.parent, self)


    def pretty(self, short=False):  # @UnusedVariable
        return self._format()  # (showstatus=not short), changed for Quality.usage()


    def wiki(self):
        return self._format(
            "{{{{link icon|{name}}}}}{sep}{ops}{ifsep}{ifs}",
            "{{{{link qty|{qtyops}|{name}}}}}{ifsep}{ifs}",
            "{{{{link qty|{qtyops}|{name}||*}}}}{ifsep}{ifs}",
            lvlfmt="{:+d}",
            lvladvfmt="+{}",
            advfmt='([[{name}]])',
            statusfmt='{} {{{{status|{status}}}}}',
        )


    def _format(self,
            # Defaults are suitable for __str__() and pretty()
            qfmt="{name}{sep}{ops}{ifsep}{ifs}",
            qfmtqty="{name} += {qtyops}{ifsep}{ifs}",
            qfmtrev="{name} += ({qtyops}){ifsep}{ifs}",
            dfmt="[1 to {}]",
            advfmt="[{name}]",
            advbfmt="[Base {name}]",
            lvlfmt="{:d}",
            lvladvfmt="{}",
            setfmt="= {}",  # ":= {}"
            ifminfmt="≥ {}",  # "if ≥ {}"
            ifmaxfmt="≤ {}",  # "if ≤ {}"
            ifeqfmt="= {}",  # "if == {}"
            ifadjfmt="= {v1} to {v2}",  # "if == {v1} to {v2}"
            elsefmt="{op}: {}",
            opsep=" and ",
            qtyopsep=" + ",
            ifsep=", only if ",
            statusfmt="{} [{status}]",
            sep=" ",
            showstatus=True,
    ):
        def add(fmt, value, adv=False, *args, **kwargs):
            posopstrs.append(fmt.format((self._parse_adv(str(value),
                                                         advfmt, advbfmt, dfmt)
                                         if adv else value),
                                        *args, **kwargs))

        ops = self.operator.copy()
        posopstrs = []
        qtyopstrs = []
        ifopstrs  = []
        useqty = False  # ('Level' in ops or 'ChangeByAdvanced' in ops)

        def add_status(val):
            if not showstatus:
                return val
            s = self.quality.status_for(val)
            if not s:
                return val
            return statusfmt.format(val, status=s)

        # Loop in _OPS to preserve order
        for op in self._OPS:
            if op not in ops:
                continue

            value = ops[op]

            if op == 'OnlyIfAtLeast':
                # Look-ahead, equal values
                val = ops.get('OnlyIfNoMoreThan', None)
                if val == value:
                    ifopstrs.append(ifeqfmt.format(add_status(value)))
                    ops.pop('OnlyIfNoMoreThan')

                # Look-ahead for range values
                elif val:
                    ifopstrs.append(ifadjfmt.format(v1=value, v2=val))
                    ops.pop('OnlyIfNoMoreThan')

                else:
                    # Add the string snippet
                    ifopstrs.append(ifminfmt.format(add_status(value)))

            elif op == 'OnlyIfNoMoreThan':
                ifopstrs.append(ifmaxfmt.format(add_status(value)))

            elif op == 'Level':
                useqty = True
                qtyopstrs.append(lvlfmt.format(value))

            elif op == 'ChangeByAdvanced':
                useqty = True
                val = re.sub(r"^[+-]?0+([+-])", "\g<1>", value)
                if val[:1] not in "+-":
                    val = lvladvfmt.format(val)

                qtyopstrs.append(self._parse_adv(val, advfmt, advbfmt, dfmt))

            elif op == 'SetToExactly':         add(setfmt, add_status(value))
            elif op == 'SetToExactlyAdvanced': add(setfmt, value, True)

            else:
                add(elsefmt, value, adv='Advanced' in op, op=op)

        if useqty:
            if any(re.match(_, self.quality.name) for _ in self._reverse):
                qfmt = qfmtrev
            else:
                qfmt = qfmtqty

        return format_obj(qfmt,
                          self.quality,
                          sep=iif(posopstrs, sep),
                          ifsep=iif(ifopstrs, ifsep),
                          ifs=opsep.join(ifopstrs),
                          ops=opsep.join(posopstrs),
                          qtyops=qtyopsep.join(qtyopstrs),
        )


    def __str__(self):
        return self._format()


    def __repr__(self):
        try:
            return "<{cls} {id}: {qid} - {qname} {ops}>".format(
                cls   = self.__class__.__name__,
                id    = self.id,
                qid   = self.quality.id,
                qname = repr(self.quality.name),
                ops   = repr(self.operator))
        except AttributeError:
            # repr() requested by base class before __init__() finishes
            return "<{cls} {id}>".format(
                cls   = self.__class__.__name__,
                id    = self.id)



class Effect(QualityOperator):
    # Order is important for both ._format() and .apply()!
    _OPS = (
        'Level',
        'ChangeByAdvanced',
        'SetToExactly',
        'SetToExactlyAdvanced',
        'OnlyIfAtLeast',
        'OnlyIfNoMoreThan',
    )
    _OPTIONAL_FIELDS = QualityOperator._OPTIONAL_FIELDS | set(_OPS)


    def __init__(self, data, idx=0, parent=None, ss=None):
        super(Effect, self).__init__(data=data, idx=idx, parent=parent, ss=ss)

        # Integrity check
        if TEST_INTEGRITY:
            ops = set(self.operator) - set(('OnlyIfAtLeast',
                                            'OnlyIfNoMoreThan'))
            if len(ops) > 1:
                log.error("Mutually exclusive operators in %r.%r: %s",
                          self.parent, self, ops)


    def apply(self, save=None):
        if save is None:
            save = self.ss.autosave
        squality = save.qualities.get(self.quality.id)
        if not squality:
            squality = save.add_quality(self.quality)
        for op in reversed(self._OPS):
            if op not in self.operator:
                continue
            value = self.operator[op]
            if   op == 'OnlyIfAtLeast':
                if squality.value < value: return
            elif op == 'OnlyIfNoMoreThan':
                if squality.value > value: return
            elif op == 'SetToExactly': squality.set_to(value)
            elif op == 'Level':        squality.increase_by(value)
            else:
                log.warning("Can not apply effect, operation not implemented: %s", self)



class Requirement(QualityOperator):
    # Order is important for ._format()!
    _OPS = (
        'DifficultyLevel',
        'DifficultyAdvanced',
        'MinLevel',
        'MinAdvanced',
        'MaxLevel',
        'MaxAdvanced',
    )
    _OPTIONAL_FIELDS = QualityOperator._OPTIONAL_FIELDS | set(_OPS)

    _Op = enum.Enum('Operator', (
        'EQUAL',
        'MIN',
        'MAX',
        'RANGE',
        'LUCK',
        'CHALLENGE',
        'CHALLENGEADV',
        'INVALID',
    ))


    def check(self, save=None):
        if save is None:
            save = self.ss.autosave
        squality = save.qualities.get(self.quality.id) or SaveQuality.new(self.quality.id)
        for op, value in self.operator.items():
            if op not in self._OPS:
                continue
            if   op == 'MinLevel':
                if squality.value < value: return CheckResult.LOCKED
            elif op == 'MaxLevel':
                if squality.value > value: return CheckResult.LOCKED
            else:
                log.warning("Can not check requirement, operation not implemented: %s", self)
                return CheckResult.LOCKED
        return CheckResult.DEFAULT


    def _tokenize(self):
        # Create a copy of operators, filtering out irrelevant ones
        ops = self.operator.copy()
        tokens = []

        def tokenize(optype, *args, **kwargs):
            tokens.append((optype, value, op,
                           op.startswith('Difficulty'),
                           op.endswith('Advanced'),
                           args, kwargs))

        # Unusual dict looping idiom to make sure that:
        # - operations are looped in self._OPS order
        # - operations can be removed/popped without affecting loop
        for op in self._OPS:
            if op not in ops:
                continue
            value = ops[op]

            if op.startswith('Min'):  # MinLevel, MinAdvanced
                # Look-ahead for Max op, to combine '>= x and =< x' into '== x'
                maxop = 'Max{}'.format(op[3:])
                valmax = ops.get(maxop, None)
                if valmax == value:
                    tokenize(self._Op.EQUAL)
                    ops.pop(maxop)

                # Look-ahead for ranges, combine into '== x to y'
                elif valmax is not None:
                    tokenize(self._Op.RANGE, v1=value, v2=valmax)
                    ops.pop(maxop)

                else:
                    # Regular Min
                    tokenize(self._Op.MIN)

            elif op.startswith('Max'):
                tokenize(self._Op.MAX)

            elif op == 'DifficultyLevel':
                value = self.quality.challenge_cap(value)
                tokenize(self._Op.LUCK if self.quality.is_luck else
                         self._Op.CHALLENGE)

            elif op == 'DifficultyAdvanced':
                tokenize(self._Op.CHALLENGEADV,
                         scaler=self.quality.difficultyscaler,
                         factor=self.quality.difficulty_factor)

            else:
                tokenize(self._Op.INVALID, op=op)
                log.error("Unknown operation in %r.%r.%r: %s = %r",
                          self.parent.parent, self.parent, self, op, value)

        return tokens


    def _format(self, formats=None, showstatus=True, forceprefix=True):
        fmts = {
            'prefix':              "{quality}",
            'sep':                 " ",
            self._Op.EQUAL:        "= {}",
            self._Op.MIN:          "≥ {}",
            self._Op.MAX:          "≤ {}",
            self._Op.RANGE:        "= {v1} to {v2}",
            self._Op.CHALLENGE:    "challenge ({} for 100%)",
            self._Op.CHALLENGEADV: "challenge ((100/{scaler}) * ({}) for 100%)",
            self._Op.LUCK:         "challenge ({}% chance)",
            self._Op.INVALID:      "{op} = {}",
            'opsep':               " and ",
            'status':              "{} [{status}]",
            'advanced:q':          "[{quality}]",
            'advanced:qb':         "[Base {quality}]",
            'advanced:d':          "[1 to {}]",
        }
        fmts.update(formats or {})
        tokens = self._tokenize()
        prefix = forceprefix or not any(_[3] for _ in tokens)  # 3 = challenge
        statusops = (
            self._Op.EQUAL,
            self._Op.MIN,
            self._Op.MAX,
            self._Op.INVALID,
        )

        def parse_adv(val):
            return self._parse_adv(val,
                fmts['advanced:q'], fmts['advanced:qb'], fmts['advanced:d'])

        def add_status(val):
            s = self.quality.status_for(val)
            if not s:
                return val
            return fmts['status'].format(val, status=s)

        opstrs = []
        for optype, value, op, _, advanced, args, kwargs in tokens:
            if advanced:
                value = parse_adv(value)
                args = tuple(parse_adv(_) for _ in args)
                kwargs = {_:parse_adv(kwargs[_]) for _ in kwargs}

            elif showstatus and optype in statusops:
                value = add_status(value)
                args = tuple(add_status(_) for _ in args)
                kwargs = {_:add_status(kwargs[_]) for _ in kwargs}

            kwargs.update({'op': op, 'quality': self.quality})
            opstrs.append(fmts[optype].format(value, *args, **kwargs))

        return "{prefix}{sep}{ops}".format(
            prefix = iif(prefix, fmts['prefix'].format(quality=self.quality)),
            sep    = iif(prefix and opstrs, fmts['sep']),
            ops    = fmts['opsep'].join(opstrs),
        )


    def wiki(self):
        return self._format(formats={
            'prefix':              "{{{{link icon|{quality.name}}}}}",
            self._Op.CHALLENGE:    "{{{{challenge|{quality.name}|{}}}}}",
            self._Op.CHALLENGEADV: "{{{{challenge|{quality.name}|(100/{scaler}) * ({})}}}}",
            self._Op.LUCK:         "{{{{link icon|{quality.name}}}}} challenge"
                                   " ({{{{action|{}%}}}} chance to win)",
            'status':              "{} {{{{status|{status}}}}}",
            'advanced:q':          "([[{quality.name}]])",
            'advanced:qb':         "(Base [[{quality.name}]])",
            }, forceprefix = False,
        )



class BaseEvent(Entity):
    '''
    Base class for Event, Action and Outcome, as they have a very similar format
        Subclasses SHOULD override or extend _OPTIONAL_FIELDS
    '''

    _OPTIONAL_FIELDS = set((
        "Name",
        "Description",
        "Image",
    ))

    _qualop_types = dict(
        requirements=('QualitiesRequired', Requirement),  # Events and Actions
        effects=     ('QualitiesAffected', Effect),       # Events and Outcomes
    )


    def __init__(self, data, idx=0, parent=None, ss=None):
        super(BaseEvent, self).__init__(data=data, idx=idx, ss=ss)

        # Only Actions and Outcomes
        self.parent = parent

        # Integrity checks
        if not TEST_INTEGRITY:
            return

        if 'ParentEvent' in self._data:
            iid = self._data['ParentEvent']['Id']
            if not parent:
                log.warn("%r should have parent with ID %d", self, iid)
            elif parent.id != iid:
                log.warn("Parent ID in object and data don't match for %r: %d vs %d",
                         parent.id, iid)


    def _apply(self, save=None):
        """Apply all effects to the save file qualities.

        Triggered Events, Exotic Effects and Move to Area are currently ignored.
        """
        if save is None:
            save = self.ss.autosave
        if not hasattr(self, 'effects'):
            raise NotImplementedError("{} has no effects to apply".format(
                                      self.__class__.__name__))
        for effect in self.effects:
            effect.apply(save=save)
        for attr in ('trigger', 'exoticeffects', 'movetoarea'):
            attrval = getattr(self, attr, None)
            if attrval:
                continue  # Temporarily disable the warning below, too chatty
                log.warning("Can not apply %r, not implemented: %r",
                            attr.title(), attrval)

    def _check(self, save=None):
        """Check all requirements against the save file qualities."""
        if save is None:
            save = self.ss.autosave
        if not hasattr(self, 'requirements'):
            raise NotImplementedError("{} has no requirements to check".format(
                                      self.__class__.__name__))
        # A single LOCKED: bail out
        # A single challenge fail: FAILURE
        # All challenges successful: SUCCESS
        # No challenge: DEFAULT
        output = CheckResult.DEFAULT
        for requirement in self.requirements:
            result = requirement.check(save=save)
            if not result:
                return CheckResult.LOCKED
            elif result == CheckResult.FAILURE:
                output = CheckResult.FAILURE
            elif result == CheckResult.SUCCESS and not output == CheckResult.FAILURE:
                output = CheckResult.SUCCESS
        return output


    def pretty(self, location=None, short=False):
        pretty = super(BaseEvent, self).pretty(short=short)

        if location:
            pretty += "\n\tLocation: {}".format(self.location)

        if getattr(self, 'requirements', None):
            pretty += "\n\tRequirements: {:d}\n".format(len(self.requirements))
            for item in self.requirements:
                pretty += "{}\n".format(indent(item.pretty(), 2))

        return pretty


    def _pretty_qualops(self, attr, short=False):
        '''Pretty-format lists of Requirements and Effects
            - Does NOT add leading '\n'
            - DOES add trailing '\n' IF there is content
            - Does NOT indent the optional header
            - Indent list IF there is a header
        '''
        out = []
        qualops = getattr(self, attr, None)
        if qualops:
            if not short:
                out.append("{}: {:d}".format(attr.title(), len(qualops)))
            # rely on indent() to rtrip each line
            out.extend(indent(_.pretty(short=short), 0 if short else 1)
                       for _ in qualops)
            out.append("")  # add trailing '\n' only if here IS content
        return "\n".join(out)


    def _create_qualops(self, attr):
        key, cls = self._qualop_types[attr]
        iids = []  # needed just for the integrity check
        for i, item in enumerate(self._data[key], 1):
            if TEST_INTEGRITY:
                iid = item['AssociatedQuality']['Id']
                if iid in iids:
                    log.error('Duplicate quality %d in %s for %r',
                              iid, attr, self)
                else:
                    iids.append(iid)
            yield cls(data=item, idx=i, parent=self, ss=self.ss)



class Event(BaseEvent):
    '''"Root" events, such as Port Interactions'''

    _REQUIRED_FIELDS = set((
        'ChildBranches',
        'QualitiesRequired',
        'QualitiesAffected',
    ))
    _OPTIONAL_FIELDS = BaseEvent._OPTIONAL_FIELDS | set((
        'Autofire',
        'Category',
        'LimitedToArea',
    ))
    _IGNORED_FIELDS  = set((
        'CanGoBack',
        'ChallengeLevel',
        'Deck',
        'Distribution',
        'ExoticEffects',
        'Ordering',
        'Setting',
        'Stickiness',
        'Transient',
        'Urgency',
    ))


    def __init__(self, data, idx=0, ss=None):
        super(Event, self).__init__(data=data, idx=idx, ss=ss)

        self.autofire = self._data.get("Autofire", False)
        self.category = self._data.get("Category", 0)

        self.location = None
        if 'LimitedToArea' in self._data:
            iid = self._data['LimitedToArea']['Id']
            if self.ss and self.ss.locations:
                self.location = ss.locations.get(iid)

            if not self.location:
                log.warning("Could not find Location for %r: %d", self, iid)
                self.location = Location(self._data['LimitedToArea'])

        self.requirements = list(self._create_qualops('requirements'))
        self.effects      = list(self._create_qualops('effects'))

        self.actions = []
        for i, item in enumerate(self._data.get('ChildBranches', []), 1):
            self.actions.append(Action(data=item, idx=i, parent=self, ss=self.ss))


    @property
    def image_wiki_file(self):
        return "File:SS {}gaz.png".format(self.image or "")


    apply = BaseEvent._apply
    check = BaseEvent._check


    def pretty(self, short=False):
        out = [super(Event, self).pretty(location=self.location,
                                         short=short).strip()]

        out.append(indent(self._pretty_qualops('effects', short=short)))

        if self.actions:
            out.append("\tActions: {:d}".format(len(self.actions)))
            out.append("\n\n".join(indent(_.pretty(), 2) for _ in self.actions))

        return "\n".join(filter(None, out)) + '\n'


    def wikipage(self):
        linked, inloc = (
            '|linked       = {{{{link icon|{.location}}}}}\n'.format(self),
            " in [[{.location}]]".format(self),
        ) if self.location else ("", "")

        header=(
            '=={self.name_wiki}==\n'
            '{{{{Infobox story\n'
            '|name         = {self.name_wiki}\n'
            '|image        = SS {self.image}gaz.png\n'
            '|id           = {self.id}\n'
            '|px           = 260px\n'
            '|category     = {self.category}\n'
#            '|type         = [[Story Event#Pigmote Isle|Pigmote Isle]]'
            '{linked}'
            '}}}}\n'
            "'''{self.name_wiki}''' is a [[Sunless Sea]] [[Story Event]]{inloc}"
        ).format(**locals())

        description=(
            '===Description===\n'
            "''\"{.description_wiki}\"''"
        ).format(self) if self.description else ""

        requirements=(
            '===Trigger Conditions===\n'
            "'''{}''' requires all the following conditions:"
            ).format(self) + "".join(
            '\n* {}'
            .format(_.wiki()) for _ in self.requirements
        ) if self.requirements else ""

        effects=(
            '===Effects===\n'
            "'''{}''' automatically causes the following effects:"
            ).format(self) + "".join(
            '\n* {}'
            .format(_.wiki()) for _ in self.requirements
        ) if self.effects else ""

        # Percentages don't add up to 100%, but consistent rest of the with wiki
        actions = (
            '===Interactions===\n'
            '{{| class="ss-table" style="width: 100%;"\n'
            '! style="width:10%;" | Interaction\n'
            '! style="width:15%;" | Unlocked by\n'
            '! style="width:15%;" | Effects\n'
            '! style="width:10%;" | Notes\n'
            '\n'
            '{}\n'
            '|-\n|}}'
            .format("\n".join(_.wikirow() for _ in self.actions))
        ) if self.actions else ""

        return "\n\n\n----\n".join(filter(None, (
            header,
            description,
            requirements,
            effects,
            actions,
        )))


    def wiki_linkicons(self):
        for entity in sorted(self._related(), key=lambda _: _.name):
            yield '\n'.join(
                ("{e.name}",
                 "https://sunlesssea.gamepedia.com/{e.image_wiki_title}?action=edit",
                 "#REDIRECT [[{e.image_wiki_file}]]")).format(e=entity)


    def _related(self):
        """Set of all entities related to the Event

        Qualitites in all effects and requirements,
        including actions and its outcomes,
        and also Events and Locations from such outcomes
        """
        entities = set([self])
        qualityiters = [self.requirements, self.effects]
        for action in self.actions:
            qualityiters.append(action.requirements)
            for outcome in action.outcomes:
                qualityiters.append(outcome.effects)
                entities.update(_ for _ in (outcome.trigger, outcome.movetoarea) if _)
        entities.update(__.quality for _ in qualityiters for __ in _)
        return entities



class Action(BaseEvent):
    # Order is VERY important, hence tuple
    _OUTCOME_TYPES = ('DefaultEvent',
                      'RareDefaultEvent',
                      'SuccessEvent',
                      'RareSuccessEvent')

    _REQUIRED_FIELDS = set((
        'QualitiesRequired',
        'ParentEvent',
        'DefaultEvent',
    ))
    _OPTIONAL_FIELDS = (
        set(BaseEvent._OPTIONAL_FIELDS) |
        set(_OUTCOME_TYPES[1:])         |
        set(_+"Chance" for _ in _OUTCOME_TYPES)
    )
    _IGNORED_FIELDS = set((
        'ActionCost',
        'ButtonText',
        'Ordering',
    ))

    _outcome_label_replaces = (("Event", ""),
                               ("Rare", "Rare "),
                               ("Success", "Successful"))
    _outcome_label_failed   = (("Default", "Failed"),)


    def __init__(self, data, idx=0, parent=None, ss=None):
        super(Action, self).__init__(data=data, idx=idx, parent=parent, ss=ss)

        self.requirements = list(self._create_qualops('requirements'))
        self.canfail      = 'SuccessEvent' in self._data

        self.outcomes = []
        self._outdict = {}
        for i, item in enumerate((_ for _ in self._OUTCOME_TYPES
                                  if _ in self._data), 1):
            outcome = Outcome(
                 data      = self._data[item],
                 idx       = i,
                 parent    = self,
                 ss        = self.ss,
                 otype     = item,
                 chance    = self._data.get(item + 'Chance', None),
                 label     = self._outcome_label(item))
            self.outcomes.append(outcome)
            self._outdict[item] = outcome

        # Integrity checks
        if not TEST_INTEGRITY:
            return

        if self._data.get('QualitiesAffected'):
            log.warn("%r have non-null effects: %s", self,
                     self._data['QualitiesAffected'])


    @property
    def description_wiki(self):
        return re.sub(self._re_gamenote, "", super().description_wiki).strip()

    @property
    def quality_bought(self):
        """Return the quality you buy through this action, if any, or None.

        A buying action is defined by having all of:
        - A single outcome containing 2 effects, 'quality += 1' and 'echo -= X'
        - Additional effects, if any, must be to Terror or Fragment
        - A requirement in the strict form of 'echo >= X'.
          (it may contain additional requirements)
        """
        if not self.ss:
            raise Error("Missing SunlessSea reference required for .quality_sold(): %r",
                        self)
        # Structure check: at least 1 requirement, 1 outcome with at least 2 effects
        if not (    self.requirements
                and len(self.outcomes) == 1
                and len(self.outcomes[0].effects) >= 2
        ):
            return
        price = 0
        quality = None
        echo = self.ss.qualities.fetch('Echo')
        # Effects check:
        # Both quality and echo must have a single 'Level' operator
        # Quality effect is increment by 1, Echo effect is decrement by price
        for effect in self.outcomes[0].effects:
            if not (len(effect.operator) == 1 and 'Level' in effect.operator): break
            value = effect.operator['Level']
            if   (effect.quality != echo and value == +1): quality = effect.quality
            elif (effect.quality == echo and value <   0): price   = -value
            elif (effect.quality.name not in ('Terror', 'Fragment')): break
        if not (quality and price):
            return
        # Requirements check: find one 'Echo >= price'
        for requirement in self.requirements:
            if (    requirement.quality == echo
                and len(requirement.operator) == 1
                and requirement.operator.get('MinLevel') == price
            ):
                break
        else:
            return
        return quality  #, price, amount

    @property
    def quality_sold(self):
        """Return the quality you sell through this action, if any, or None.

        A selling action is defined by having all of:
        - A single requirement, in the strict form of 'quality >= 1', and quality not Echo
        - All outcomes contain one effect 'echo += X' and one 'quality -= 1'
         (it may contain additional effects)
        """
        if not self.ss:
            raise Error("Missing SunlessSea reference required for .quality_sold(): %r",
                        self)
        # Structure check
        if not len(self.requirements) == 1:
            return
        echo = self.ss.qualities.fetch('Echo')
        requirement = self.requirements[0]
        quality = requirement.quality
        # Requirement check
        if not (    quality != echo
                and len(requirement.operator) == 1
                and requirement.operator.get('MinLevel') == 1  # amount = 1
        ):
            return
        # Outcomes and effects check
        for outcome in self.outcomes:
            qok = eok = False
            for effect in outcome.effects:
                if not (len(effect.operator) == 1 and 'Level' in effect.operator): continue
                value = effect.operator['Level']
                if   (effect.quality == quality and value == -1): qok = True  # == -amount
                elif (effect.quality == echo    and value >   0): eok = True  # price = value
            if not (qok and eok):
                return
        return quality  #, price, amount


    check = BaseEvent._check


    def do(self, repeats=1, save=None, output=len):
        if save is None:
            save = self.ss.autosave
        results = []
        for _ in range(repeats):
            # Check Requirements
            result = self.check(save=save)
            if not result:
                break  # Requirements not met
            # Do adjustments based on whether a challenge happened
            if result == CheckResult.DEFAULT:
                # No challenge
                showlog = False
                resfunc = str.upper
            else:
                showlog = True
                resfunc = lambda _: _  # No-op
            # Get default outcome
            otype = "{}Event".format(result.title())
            outcome = self._outdict[otype]
            # Check for rare outcome, if any
            rare = self._outdict.get('Rare{}'.format(otype))
            # Choose outcome
            if rare:
                if random.randrange(100) < rare.chance:
                    # Rare
                    outcome = rare
                    result = rare.type.replace("Event", "")
                    showlog = True
                else:
                    # Normal
                    pass
            else:
                # Default
                pass
            result = resfunc(result)
            if showlog:
                log.debug("%r: %s", self, re.sub(" [Dd]efault", "", str(outcome)))
                #log.debug("%s outcome in %r: %r", loglabel.title(), self, outcome)
            # Apply outcome effects
            outcome.apply(save=save)
            results.append(result)
        return output(results)


    def pretty(self):
        pretty = super(Action, self).pretty().strip()

        for item in self.outcomes:
            pretty += "\n\n{}".format(indent(item.pretty(), 1))

        return pretty


    def wikirow(self):
        outcomes = len(self.outcomes)
        rows = 2 * outcomes - (0 if self.canfail else 1)
        rowspan = iif(rows > 1, '| rowspan="{}"{}'.format(rows, ' ' * 14))
        note = self.gamenote  # save to avoid multiple calls to property

        def innerheader(outcome):
            return ("| {{{{style inner header{rare} "
                    "| {label} event{chance}\n"
            ).format(
                label  = re.sub(" [Dd]efault", "", outcome.label),
                rare   = iif("Rare" in outcome.label, "|*}}", "}}  "),  # lame
                chance = iif(outcome.chance, " ({}% chance)".format(outcome.chance)),
            )

        def innercell(outcome):
            return "|{}{}{}\n".format(
                iif(outcome.idx < outcomes, " {{style inner cell}}     |"),
                iif(outcome.name, " ", "\n"),
                outcome.wiki(),
            )

        outcome = self.outcomes[0]
        if self.canfail:
            firstrow  = innerheader(self.outcomes[0])
            secondrow = "|-\n{}".format(innercell(outcome))
        else:
            firstrow = innercell(self.outcomes[0])
            secondrow = ""

        page = (
            "|-\n"
            "{rowspan}| {{{{action title|{name}}}}}\n{description}"
            "{rowspan}|\n"
            "<ul>\n"
            "{reqs}<br>\n"
            "</ul>\n"
            "{firstrow}"  # firstrow always contains leading '|' and trailing '\n'
            "{rowspan}|{note}\n"
        ).format(
            name=self.name_wiki,
            description=iif(self.description, "{}\n".format(self.description_wiki)),
            reqs="<br>\n".join(_.wiki() for _ in self.requirements) or "-",
            note=iif(note, " {{{{game note|{}}}}}".format(note)),
            rowspan=rowspan,
            firstrow=firstrow,
        )

        page += secondrow

        for outcome in self.outcomes[1:]:
            page += "|-\n{}|-\n{}".format(innerheader(outcome),
                                            innercell(outcome))

        return page


    def _outcome_label(self, otype):
        label = otype
        for sfrom, sto in (self._outcome_label_replaces +
                           (self._outcome_label_failed
                            if self.canfail
                            else ())):
            label = label.replace(sfrom, sto)
        return label.capitalize()



class Outcome(BaseEvent):
    _REQUIRED_FIELDS = set(('QualitiesAffected',))
    _OPTIONAL_FIELDS = BaseEvent._OPTIONAL_FIELDS - {'Image'} | set((
        'ExoticEffects',
        'LinkToEvent',
        'MoveToArea',
    ))
    _IGNORED_FIELDS  = set((
        'Category',
        'ChildBranches',
        'SwitchToSetting',
        'SwitchToSettingId',
        'Urgency',
    ))


    def __init__(self, data, idx=0, parent=None, ss=None,
                 otype=None, chance=None, label=None):
        super(Outcome, self).__init__(data=data, idx=idx, parent=parent, ss=ss)

        self.type    = otype
        self.chance  = chance
        self.label   = label
        self.trigger = self._data.get('LinkToEvent', {}).get('Id', None)
        self.effects = list(self._create_qualops('effects'))

        self.exoticeffects = self._data.get('ExoticEffects', "")

        self.movetoarea = None
        if 'MoveToArea' in self._data:
            eid = self._data['MoveToArea']['Id']
            if self.ss and self.ss.locations:
                self.movetoarea = ss.locations.get(eid)

            if not self.movetoarea:
                log.warning("Could not find Location referenced in %r: %d", self, eid)
                self.movetoarea = Location(self._data['MoveToArea'])
                if self.ss:
                    self.ss.locations.add(self.movetoarea)

        # Integrity checks
        if not TEST_INTEGRITY:
            return

        if self._data.get('ChildBranches'):
            log.warn("%r have non-null 'ChildBranches': %s", self,
                     self._data['ChildBranches'])

        if self._data.get('QualitiesRequired'):
            log.warn("%r have non-null requirements: %s", self,
                     self._data['QualitiesRequired'])


    @property
    def description_wiki(self):
        note = self.gamenote
        if note:
            return "{}\n\n{{{{game note|{}}}}}".format(
                re.sub(self._re_gamenote, "", super().description_wiki).strip(),
                note)
        return super().description_wiki


    apply = BaseEvent._apply


    def pretty(self, short=False):
        out = ["{} outcome{}:".format(self.label,
            iif(self.chance, " ({}% chance)".format(self.chance)))
        ]

        if not short:
            out.append(indent(super(Outcome, self).pretty(short=False)))

        out.append(indent(self._pretty_qualops('effects', short=short)))

        if self.trigger:
            out.append("\tTrigger event: {} - {}".format(self.trigger.id,
                                                         self.trigger.name))

        if self.movetoarea:
            out.append("\tMove to: {} - {}".format(self.movetoarea.id,
                                                  self.movetoarea.name))

        if self.exoticeffects:
            out.append("\t{}".format(self.exoticeffects))

        return "\n".join(filter(None, out)) + '\n'


    def wiki(self):
        page  = iif(self.name, "{{{{effect title|{}}}}}\n".format(self.name_wiki))
        page += iif(self.description, "{}\n".format(self.description_wiki))
        pg = ""

        for effect in self.effects:
            pg += "* {}\n".format(effect.wiki())

        if self.trigger and self.trigger is not self.parent.parent:
            pg += "* {{{{trigger event|{}}}}}\n".format(self.trigger.name)

        if self.movetoarea:
            pg += "* {{{{trigger location|{}}}}}\n".format(self.movetoarea.name)

        if self.exoticeffects:
            pg += "* {{{{action|{}}}}}\n".format(self.exoticeffects)

        page += pg if pg else "<ul>-</ul>\n"

        return page.strip()


    def __str__(self):
        return "{} Outcome{}{}".format(
            self.label,
            iif(self.chance, " ({}% chance)".format(self.chance)),
            iif(self.name, " '{}'".format(self.name)))



class Entities:
    '''Base class for entity containers. Subclasses SHOULD override EntityCls!'''
    EntityCls=Entity


    def __init__(self, data=None, entities=None, path=None, ss=None,
                 *eargs, **ekwargs):
        self._entities = {}
        self._order = []
        self.path = path
        self.ss = ss

        if data is not None:
            for idx, edata in enumerate(data, 1):
                entity = self.EntityCls(data=edata, idx=idx, ss=self.ss,
                                        *eargs, **ekwargs)
                self.add(entity, check=False)
        if entities is not None:
            for entity in entities:
                self.add(entity, check=TEST_INTEGRITY)


    def filter(self, attr, value):
        """Select entities where entity.attr = value"""
        entities=(_ for _ in self if str(getattr(_, attr, "")) == str(value))
        return self.__class__(path=self.path, ss=self.ss, entities=entities)


    def fetch(self, query, partial=False):
        """Find a single entity, raise Error if none or multiple found"""
        entities = self.find(query, partial=partial)
        found = len(entities)
        if not found:
            raise Error("No %s matching %r", self.EntityCls.__name__, query)
        if found > 1:
            raise Error("%s match '%s':\n\t%s",
                        entities, query, "\n\t".join(str(_) for _ in entities))
        return entities[0]


    def find(self, query, partial=True):
        """Return entities matching by ID or name"""
        try:
            entities = self.find_by_id(int(query or ""))
            if not entities:
                raise ValueError
        except ValueError:
            entities = self.find_by_name(query, partial=partial)
        return entities


    def find_by_name(self, name, partial=True):
        """Return Entities matching name, case-insensitive.

        If name is falsy, return all entities.
        """
        if not name:
            return self
        if partial:
            def search(x, s): return x.lower() in s.lower()
        else:
            def search(x, s): return x.lower() == s.lower()
        # An idea: elif regex: def search(x, s): return re.search(x, s, re.IGNORECASE)
        entities=(_ for _ in self if search(name, _.name))
        return self.__class__(path=self.path, ss=self.ss, entities=entities)


    def find_by_id(self, eid):
        '''Like .find(), but matching entity ID instead of name.
            Unlike .get() it always returns a container, either with a single
            entity or empty if none was found.
            Unlike .find(), a falsy ID will also return an empty container.
        '''
        return self.__class__(path=self.path,
                              ss=self.ss,
                              entities=(_ for _ in self if _.id == eid))


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
        return "\n\n\n".join(_.wikipage().strip() for _ in self)


    def dump(self):
        return [_.dump() for _ in self]


    def to_json(self):
        return "[\n{}\n]".format(',\n'.join(_.to_json() for _ in self))


    def pretty(self):
        return "\n\n".join((_.pretty().strip() for _ in self))


    def bare(self):
        return "\n".join(_.bare() for _ in self)


    def get(self, eid, default=None):
        '''Get entity by ID'''
        return self._entities.get(eid, default)


    def add(self, entity, check=True):
        '''Add an Entity to the container.
            Use with caution, as Entities should remain as immutable as possible
            It does NOT, for example, update any parent._data JSON
        '''
        if check and not isinstance(entity, self.EntityCls):
            raise ValueError("Must be instance of {} to add to {}, type {} found: {}"
                             .format(self.EntityCls.__name__,
                                     self.__class__.__name__,
                                     type(entity),
                                     repr(entity)))
        self._entities[entity.id] = entity
        self._order.append(entity)


    def __getitem__(self, val):
        if isinstance(val, int):
            return self._order[val]
        else:
            return self.__class__(path=self.path,
                                  ss=self.ss,
                                  entities=self._order[val])


    def __iter__(self):
        for entity in self._order:
            yield entity


    def __len__(self):
        return len(self._entities)


    def __str__(self):
        length = len(self)
        name = (self.EntityCls if length == 1 else self.__class__).__name__.lower()
        return "{} {}".format(length, name)


    def __repr__(self):
        return "<{}: {:d}>".format(self.__class__.__name__,
                                   len(self._entities))



class Qualities(Entities):
    EntityCls=Quality

    def usage(self, formatting='pretty'):
        if formatting == 'wikipage':
            func = 'wikipage'
        else:
            func = 'pretty'

        return "\n\n\n\n".join(
            "\n\n".join((indent(getattr(_, func)(),0), indent(_.usage())))
            for _ in self)



class Locations(Entities):
    EntityCls=Location



class Shops(Entities):
    EntityCls=Shop



class Events(Entities):
    EntityCls=Event


    def at(self, lid=0, name=""):
        '''Return Events by location ID or name'''
        return Events(ss=self.ss,
                      entities=(_ for _
                                in self
                                if (_.location and
                                    ((lid  and _.location.id == lid) or
                                     (name and re.search(name, _.location.name,
                                                         re.IGNORECASE))))))


    def wiki_linkicons(self):
        return "\n\n---\n\n".join("\n\n".join(_.wiki_linkicons()) for _ in self)



class SaveQuality:
    TEMPLATE = {
        "Name": None,
        "EquippedPossession": None,
        "Relationships": [],
        "XP": 0,
        "EffectiveLevelModifier": 0,
        "TargetQuality": None,
        "TargetLevel": None,
        "CompletionMessage": None,
        "Level": 0,
        "AssociatedQuality": None,
        "AssociatedQualityId": 0,
        "QualityName": None,
        "QualityDescription": None,
        "QualityImage": None,
        "QualityNature": None,
        "QualityCategory": None,
        "QualityAllowedOn": None,
        "Id": 0
    }

    def __init__(self, data=None, idx=0, save=None, ss=None):
        self._data = data
        self.idx   = idx
        self.ss    = ss
        self.save  = save

        # Find and assign the associated Quality
        qid  = self._data['AssociatedQualityId']
        self.quality  = None
        if self.ss and self.ss.qualities:
            self.quality = self.ss.qualities.get(qid)
            if not self.quality:
                # Create a dummy one
                self.quality = Quality(data={'Id': qid, 'Name':''},
                                       ss=self.ss)
                log.warning("Could not find Quality for %r[%d]: %d",
                            save, idx, qid)

        # Modifier is a value added to (base) value
        # For example Engine Power and Stats enhancements
        self.modifier =  self._data['EffectiveLevelModifier']

        # Equipped is the quality currently assigned to a slot
        # For Officers, Ship Equipment and Current Ship
        # FIXME: this should actually be a SaveQuality, not a Quality!
        # No need to post-process: data is fully dumped in the JSON,
        # and there's no need to associate with the one from autosave.qualities
        # But fix requires all code using .equipped to be (potentially) adapted
        # as SaveQuality is NOT a Quality.
        self.equipped = None
        qid = (self._data['EquippedPossession'] or {}).get('AssociatedQualityId', 0)
        if qid and self.ss and self.ss.qualities:
            self.equipped = self.ss.qualities.get(qid)

            if not self.equipped:
                # Create a dummy one
                self.equipped = Quality(data={'Id': qid, 'Name':''},
                                        ss=self.ss)
                log.warning("Could not find Quality equipped to %s slot: %d",
                            self.name, qid)

        if TEST_INTEGRITY:
            # Test if fixed keys match template
            for k, v in self._data.items():
                if k in ('AssociatedQualityId', 'Level', 'EquippedPossession',
                         'EffectiveLevelModifier', 'XP', 'Name'):
                    continue
                if v != self.TEMPLATE[k]:
                    log.warning("%r[%s] does not match template, expected %r: %r",
                                self, k, self.TEMPLATE[k], v)

            if self.equipped and not self.quality.isslot:
                log.error("%r is not a slot but has a quality equipped: %r",
                          self, self.equipped)

            e = self._data['EquippedPossession']
            if e:  # e is None for non-slots or slots with nothing equipped on.
                qid1 =  e['AssociatedQualityId']
                qid2 = (e['AssociatedQuality'] or {'Id':None})['Id']
                if not (qid1 or qid2):
                    log.error("No quality assigned to equipped slot %r", self)

                if qid2 and not qid2 == qid1:
                    log.error("Equipped quality and ID mismatch in %r: %s, %s",
                              self, qid1, qid2)


    @property
    def id(self):
        # To make SaveQualities.get() work
        return self.quality.id

    @property
    def name(self):
        # To make SaveQualities.find() work
        # Combines the Quality name with the SaveQuality name itself, if any
        # Used to store the custom Ship Name
        return ("{} ({})".format(self._data['Name'], self.quality.name)
                if self._data['Name']
                else self.quality.name)

    @property
    def status(self):
        return self.quality.status_for(self.value)

    @property
    def in_cargo(self):
        if not self.quality.is_cargo or not self.save or not self.value:
            return False
        for quality in self.save.qualities:
            if quality.equipped == self.quality:
                return False
        return True

    @property
    def pyramid_limit(self):
        value = self.value
        limit = self.quality.pyramidnumberincreaselimit or value
        return min(value, limit)

    @property
    def value(self):
        return self._data['Level']
    @value.setter
    def value(self, value):
        value = int(value)
        if self.quality.cap and value > self.quality.cap:
            value = self.quality.cap
        if value < 0:
            # Silently ignore, like the games does with, for example, Terror
            # log.warning("Setting %r to a negative value, ignoring: %r", self, value)
            return
        log.debug("%+5d x %r => %r ", value - self.value, self, value)
        self._data['Level'] = value

    @property
    def xp(self):
        return self._data.get('XP', 0)
    @xp.setter
    def xp(self, value):
        self._data['XP'] = int(value)


    @classmethod
    def new(cls, qid, idx=0, save=None, ss=None, level=0, modifier=0, name=None):
        # XP and EquippedPossession are is intentionally left out, for now.
        data = cls.TEMPLATE.copy()
        data.update({
            "Name": name,
            "EffectiveLevelModifier": modifier,
            "Level": level,
            "AssociatedQualityId": qid.id if isinstance(qid, Quality) else int(qid)
        })
        # It's tempting to add data to save._data here, but as this is a private
        # attribute, let this to Save
        return SaveQuality(data=data, idx=idx, save=save, ss=ss)


    def increase_by(self, value=1):
        # Basic increment
        if not self.quality.usepyramidnumbers:
            self.value += value
            return

        # In practice, only used in 'Favours: Antiquarian' (Alarming Scholar)
        for _ in range(value):
            self.xp += 1
            if self.xp > self.pyramid_limit:
                self.value += 1
                self.xp = 0

    def set_to(self, value=1, xp=0):
        self.value = value
        self.xp = xp

        if xp:
            if not self.quality.usepyramidnumbers:
                log.warning("XP has no effect as %r does not use pyramid numbers",
                            self.quality)
            elif xp > self.pyramid_limit:
                log.warning("XP set higher than current pyramid limit (%d) in %r: %d",
                            self.pyramid_limit, self, xp)


    def dump(self):
        return self._data

    def to_json(self):
        return json.dumps(self._data, indent=4, separators=(',',':'))

    def bare(self, sep='\t'):  # @UnusedVariable
        return str(self)

    def pretty(self, short=False):  # @UnusedVariable
        return str(self)

    def wiki(self):
        return self.name or str(self.id)

    def wikirow(self):
        return format_obj(
            "|-\n"
            "| {idx}\n"
            "| {id}\n"
            "| [[{name_wiki}]]\n"
            "| {{{{game icon|{image}}}}}\n"
            "| {description_wiki}\n",
            self.quality, idx=self.idx)

    def wikipage(self):
        return format_obj(
            "=={name}==\n"
            "* <nowiki>{repr}</nowiki>\n"
            "* {wiki}\n",
            self, name=self.name, wiki=self.wiki(), repr=repr(self))

    def __str__(self):
        capstr = iif(self.quality.cap, "/{}".format(self.quality.cap))
        xpstr = iif(self.quality.usepyramidnumbers, " ({} more to increase)".format(
            self.pyramid_limit - self.xp + 1))
        statusstr = iif(self.status, " [{}]".format(self.status))
        modstr = iif(self.modifier, " + {} = {}".format(self.modifier,
                                                        self.value + self.modifier))
        equipstr = iif(self.quality.isslot, " [{}]".format(self.equipped or ""))

        return ("{self.id}\t{self.name} = {self.value}{capstr}{xpstr}"
                "{statusstr}{modstr}{equipstr}".format(**locals()))


    def __repr__(self):
        if self.quality.name:
            return "<{cls} {qid}: {qname!r} = {value!r}>".format(
                cls   = self.__class__.__name__,
                qid   = self.quality.id,
                qname = self.quality.name,
                value = self.value)
        else:
            return "<{cls} {qid} = {value!r}>".format(
                cls   = self.__class__.__name__,
                qid   = self.quality.id,
                qname = self.quality.name,
                value = self.value)



class SaveQualities(Entities):
    EntityCls = SaveQuality

    def pretty(self):
        return "\n".join((_.pretty().strip() for _ in self))



class Save:
    def __init__(self, data=None, ss=None, path=None):
        self._data = data
        self.path  = path
        self.ss    = ss

        self.qualities = SaveQualities(
           data=self._data['QualitiesPossessedList'],
           ss=self.ss,
           save=self,
        )


    @property
    def cargo(self):
        return sum(_.value if _.in_cargo else 0 for _ in self.qualities)

    @property
    def hold(self):
        hold = self.qualities.find('hold') or 0
        if hold:
            hold = hold[0].value + hold[0].modifier
        else:
            log.warning("No 'Hold' quality found in Autosave, maybe it is corrupt?")
        return hold


    def add_quality(self, qid, level=0, modifier=0, name=None):
        quality = SaveQuality.new(
            qid      = qid,
            idx      = len(self.qualities) + 1,
            save     = self,
            ss       = self.ss,
            level    = level,
            modifier = modifier,
            name     = name
        )
        self._data['QualitiesPossessedList'].append(quality.dump())
        self.qualities.add(quality)
        log.debug("Created new Quality in Save: %r", quality)
        return quality


    def dump(self):
        return self._data


    def save(self):
        try:
            with open(self.path, "w") as fd:
                json.dump(self._data, fd, separators=(',',':'))
        except IOError as e:
            log.error("Could not save: %s", e)



class SunlessSea:
    '''
        Manager class, the one that loads the JSON files
        and call each entity container's constructor
    '''


    def __init__(self, datadir=None):
        self.datadir = datadir or get_datadir()
        self.qualities = Qualities(ss=self, **self._load('qualities'))
        self.locations = Locations(ss=self, **self._load('areas'))
        self.events    = Events(   ss=self, **self._load('events'))
        self.autosave  = Save(     ss=self, **self._load('Autosave', 'saves',
                                                         '', ordered=True))

        # Not yet a first-class citizen
        self.settings = self._create_settings()

        # First class, requires self.settings, constructor still messy
        self.shops = Shops(entities=(_ for _ in self._create_shop()), ss=self)
        self.ports = None  # soon!

        # Add references to other Qualities in 'Enhancements' and 'AssignToSlot',
        # and to Events in UseEvent
        for quality in self.qualities:
            # Enhancements
            quality.enhancements = [
                Effect(data=_d, idx=_i, ss=self, parent=quality)
                for _i, _d in enumerate(quality.enhancements, 1)
            ]

            # UseEvent
            if quality.event:
                event = self.events.get(quality.event)
                if not event:
                    # Create a dummy one
                    event = Event(ss=self, data=dict(Id=quality.event,
                                                     ChildBranches=[],
                                                     QualitiesRequired=[]))
                    log.error("%r uses non-existing event: %r", quality, event)
                quality.event = event

            # AssingTo
            slot = quality.assign
            if slot is None:
                continue

            quality.assign = self.qualities.get(slot)
            if quality.assign is not None:
                continue

            # Create a dummy one
            quality.assign = Quality(ss=self, data=dict(Id=slot, Name=""))
            log.error("%r assigns to a non-existant slot: %d",
                      quality, slot)

        # Add 'LinkToEvent' references
        for event in self.events:
            for action in event.actions:
                for outcome in action.outcomes:
                    trigger = outcome.trigger
                    if trigger is None:
                        continue

                    outcome.trigger = self.events.get(trigger)
                    if outcome.trigger is not None:
                        continue

                    # Create a dummy one
                    outcome.trigger = Event(ss=self,
                                            data=dict(Id=trigger,
                                                      ChildBranches=[],
                                                      QualitiesRequired=[]))
                    log.error("%r.%r.%r links to a non-existant event: %d",
                              event, action, outcome, trigger)

        if TEST_INTEGRITY:
            for item in self.autosave.qualities:
                if item.equipped and item.equipped.assign is not item.quality:
                    log.error("Autosave slot %r has %r equipped, but that is"
                              " assignable to slot %r",
                              item, item.equipped, item.equipped.assign)


    def _create_shop(self):
        i = 0  # lame
        exchanges = self._load('exchanges')['data']
        for exchange in exchanges:
            locations = set(_l
                            for _ in exchange['SettingIds'] if _ in self.settings
                            for _l in self.settings[_]['locations'])

            for shop in exchange['Shops']:
                i+=1
                yield Shop(data=shop, idx=i, ss=self, locations=locations)


    def _create_settings(self):
        # Deal with the tiles, settings, areas, locations and ports mess
        settings = {}
        areas={}  # Integrity check only
        tiles = self._load('Tiles', subdir='geography')['data']
        for item, aid, sid in (((_['Name'], _t['Name'], _p['Name']),
                                _p['Area']['Id'],
                                _p['Setting']['Id'])
                                for _ in tiles
                                for _t in  _['Tiles']
                                for _p in _t['PortData']):
                if TEST_INTEGRITY:
                    if not areas.get(aid, sid) == sid:
                        log.error("Area %s is not 1:1 with Settings: %s, %s",
                                  aid, areas[aid], sid)
                    areas[aid] = sid

                location = self.locations.get(aid, None)
                if location:
                    location.setting = sid
                else:
                    # Dummy
                    location = Location(data={'Id': aid}, ss=self)
                    log.error("Location not found for port (%s): %s",
                              ", ".join(item), aid)

                settings.setdefault(
                    sid, {'locations': set()})['locations'].add(location)

        # Requires check AND debug flags... can't possibly hide this better :)
        if TEST_INTEGRITY:
            for sid, setting in settings.items():
                log.debug("Locations in setting %s: %s", sid,
                          ", ".join("{0.id} - {0!s}".format(_)
                                    for _ in setting['locations']))

        return settings


    def _load(self, entity, subdir='entities', suffix="_import", ordered=False):
        path = os.path.join(self.datadir,
                            subdir,
                            "{}{}.json".format(entity, suffix))
        log.debug("Opening data file for '%-9s': %s", entity, path)
        try:
            with open(path) as fd:
                # strict=False to allow tabs inside strings
                return dict(path=path, data=json.load(fd, strict=False,
                        object_pairs_hook=(collections.OrderedDict
                                           if ordered else None)))
        except IOError as e:
            log.error("Could not load data file for '%s': %s", entity, e)
            return dict(path=path, data={})




################################################################################
# Import guard

if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except BrokenPipeError:
        # https://docs.python.org/3/library/signal.html#note-on-sigpipe
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except Exception as e:
        log.critical(e, exc_info=True)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(2)  # signal.SIGINT.value
