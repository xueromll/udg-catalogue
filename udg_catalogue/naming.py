from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from typing import Any

import pandas as pd
from sci_etl_core.processors import DefaultKeyNormalizer, KeyNormalizer, Processor

DEFAULT_PREFIX_ALIASES: dict[str, str] = {"dragonfly": "df"}
_NAME_TOKEN = re.compile(r"[^\W\d_]+|\d+")
_NUMBER_SEPARATOR = "."
_CLASS_LABEL = "udg"
_PARENTHESES = re.compile(r"\(([^()]*)\)")
_ALIAS_SEPARATOR = re.compile(r"[,;]")


class GalaxyNameNormalizer(KeyNormalizer):
    """Match spellings of one designation: ``DF 44``, ``Dragonfly 044`` and ``UDG-DF44`` share the key ``df44``.

    A leading ``UDG`` label is dropped when a designation with letters
    follows it, as in ``UDG-DF44``; ``UDG 7`` keeps it, since the number alone
    is no designation.
    """

    def __init__(self, prefix_aliases: Mapping[str, str] | None = None) -> None:
        self._prefix_aliases = dict(DEFAULT_PREFIX_ALIASES if prefix_aliases is None else prefix_aliases)
        self._missing_value_guard = DefaultKeyNormalizer()

    def normalize(self, raw_value: Any) -> str:
        if not self._missing_value_guard.normalize(raw_value):
            return ""
        tokens = _NAME_TOKEN.findall(unicodedata.normalize("NFKC", str(raw_value)).casefold())
        if not tokens:
            return ""
        if tokens[0] == _CLASS_LABEL and len(tokens) > 1 and not tokens[1].isdecimal():
            tokens = tokens[1:]
        tokens[0] = self._prefix_aliases.get(tokens[0], tokens[0])
        key: list[str] = []
        previous_is_number = False
        for token in tokens:
            is_number = token.isdecimal()
            if is_number and previous_is_number:
                key.append(_NUMBER_SEPARATOR)
            key.append(str(int(token)) if is_number else token)
            previous_is_number = is_number
        return "".join(key)


def designations(name: Any) -> list[str]:
    """The designations a name with parentheses gives: the part outside them, then each alias inside.

    ``Yagi093 (DF26, GMP 2748)`` gives ``Yagi093``, ``DF26`` and ``GMP 2748``.
    A name without parentheses gives none. A part without a digit, such as the
    ``KiDS UDG candidate`` of a name that only describes the object, or with an
    ``=``, such as ``RA=0.6277``, is no designation and is left out.
    """
    if not isinstance(name, str) or not _PARENTHESES.search(name):
        return []
    parts = [_PARENTHESES.sub(" ", name)]
    for inside in _PARENTHESES.findall(name):
        parts.extend(_ALIAS_SEPARATOR.split(inside))
    return [part.strip() for part in parts if any(c.isdigit() for c in part) and "=" not in part]


class AliasKeyStep(Processor):
    """Give rows the same key when one row's name lists another row's name as a designation.

    ``NGVS1593 (VCC1052)`` and ``VCC1052`` get one key, and so do
    ``Yagi276 (DF28)`` and ``DF28``. Only designations that are some row's own
    key join anything. A designation shared by different galaxies, such as the
    ``DF2`` of ``DF2 (RCP 29)`` and of the Coma galaxy DF2, joins their keys
    too, so a sky-position split must follow (see
    :class:`~udg_catalogue.astrometry.NamesakeSplitStep`).
    """

    def __init__(self, name_column: str, key_column: str, normalizer: KeyNormalizer) -> None:
        self._name_column = name_column
        self._key_column = key_column
        self._normalizer = normalizer

    def process(self, frame: pd.DataFrame) -> pd.DataFrame:
        keys = frame[self._key_column]
        present = set(keys[keys != ""])
        links: dict[str, set[str]] = {}
        for name, key in zip(frame[self._name_column], keys, strict=True):
            for part in designations(name) if key else []:
                alias = self._normalizer.normalize(part)
                if alias != key and alias in present:
                    links.setdefault(key, set()).add(alias)
                    links.setdefault(alias, set()).add(key)
        if not links:
            return frame
        shared = _shared_keys(links)
        frame = frame.copy()
        frame[self._key_column] = keys.map(lambda key: shared.get(key, key))
        return frame


def _shared_keys(links: Mapping[str, set[str]]) -> dict[str, str]:
    """Map every linked key to the smallest key of its connected group."""
    shared: dict[str, str] = {}
    for start in sorted(links):
        if start in shared:
            continue
        group, frontier = {start}, [start]
        while frontier:
            for neighbour in links[frontier.pop()]:
                if neighbour not in group:
                    group.add(neighbour)
                    frontier.append(neighbour)
        for key in group:
            shared[key] = min(group)
    return shared
