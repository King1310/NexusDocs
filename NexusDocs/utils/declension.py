from __future__ import annotations

from dataclasses import dataclass

from domain.value_objects.fullname import FullName


@dataclass(frozen=True, slots=True)
class DeclinedName:
    last_name_genitive: str
    first_name_genitive: str
    middle_name_genitive: str
    last_name_instrumental: str


def _replace_ending(value: str, ending: str, replacement: str) -> str:
    return value[: -len(ending)] + replacement


def _genitive(value: str, *, female: bool = False) -> str:
    lower = value.lower()
    specials = {"павел": "Павла", "лев": "Льва", "илья": "Ильи"}
    if lower in specials:
        result = specials[lower]
        return result if value[:1].isupper() else result.lower()
    if female and lower.endswith(("ова", "ева", "ина", "ына")):
        return value[:-1] + "ой"
    if lower.endswith(("ая",)):
        return value[:-2] + "ой"
    if lower.endswith(("яя",)):
        return value[:-2] + "ей"
    if lower.endswith(("ский", "цкий")):
        return value[:-2] + "ого"
    if lower.endswith("ой"):
        return value[:-2] + "ого"
    if lower.endswith("ий"):
        return value[:-2] + "его"
    if lower.endswith("й"):
        return value[:-1] + "я"
    if lower.endswith("ь"):
        return value[:-1] + "я"
    if lower.endswith("я"):
        return value[:-1] + "и"
    if lower.endswith("а"):
        return value[:-1] + ("и" if lower[-2:-1] in "гкхжчшщ" else "ы")
    if female:
        return value
    if lower[-1:] in "бвгджзклмнпрстфхцчшщ":
        return value + "а"
    return value


def _instrumental(value: str, *, female: bool = False) -> str:
    lower = value.lower()
    specials = {"павел": "Павлом", "лев": "Львом", "илья": "Ильёй"}
    if lower in specials:
        result = specials[lower]
        return result if value[:1].isupper() else result.lower()
    if female and lower.endswith(("ова", "ева", "ина", "ына", "ая")):
        return value[:-1] + "ой"
    if lower.endswith("яя"):
        return value[:-2] + "ей"
    if lower.endswith(("ский", "цкий")):
        return value[:-2] + "им"
    if lower.endswith("ой"):
        return value[:-2] + "ым"
    if lower.endswith("ий"):
        return value[:-2] + "им"
    if lower.endswith(("й", "ь")):
        return value[:-1] + "ем"
    if lower.endswith(("а", "я")):
        return value[:-1] + ("ей" if lower.endswith("я") else "ой")
    if female:
        return value
    if lower[-1:] in "бвгджзклмнпрстфхцчшщ":
        return value + "ом"
    return value


def _surname_instrumental(value: str, *, female: bool = False) -> str:
    lower = value.lower()
    if not female and lower.endswith(("ов", "ев", "ёв", "ин", "ын")):
        return value + "ым"
    return _instrumental(value, female=female)


def decline_full_name(full_name: FullName) -> DeclinedName:
    """Return common Russian name forms; callers may override every result."""

    female = full_name.middle_name.lower().endswith(("на", "ична"))
    return DeclinedName(
        last_name_genitive=_genitive(full_name.last_name, female=female),
        first_name_genitive=_genitive(full_name.first_name, female=female),
        middle_name_genitive=_genitive(full_name.middle_name, female=female),
        last_name_instrumental=_surname_instrumental(
            full_name.last_name, female=female
        ),
    )


def rank_genitive(rank: str) -> str:
    words = rank.split()
    if not words:
        return rank
    adjectives = {
        "старший": "старшего",
        "младший": "младшего",
        "рядовой": "рядового",
        "ефрейтор": "ефрейтора",
        "сержант": "сержанта",
        "старшина": "старшины",
        "прапорщик": "прапорщика",
        "лейтенант": "лейтенанта",
        "капитан": "капитана",
        "майор": "майора",
        "подполковник": "подполковника",
        "полковник": "полковника",
    }
    return " ".join(adjectives.get(word.lower(), word) for word in words)
