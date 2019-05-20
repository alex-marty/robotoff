
import re

from robotoff.utils.text import strip_consecutive_spaces

WEIGHT_REGEX = re.compile(r"[0-9]+[,.]?[0-9]*\s?(fl oz|dl|cl|mg|ml|lbs|oz|g|kg|l)(?![a-z])")

LABELS_REGEX = {
    'fr': re.compile(r'agriculture biologique|biologique|bio|igp|aop|aoc|label rouge'),
    'en': re.compile(r'organic|pgi'),
}

EXTRAWORDS_REGEX = {
    'fr': re.compile(r'gourmand'),
    'en': re.compile(r'delicious'),
}


def preprocess_name(name: str, lang: str) -> str:
    """Preprocess category name before matching:
    - remove all weight mentions (100 g, 1l,...)
    - remove all label mentions (IGP, AOP, Label Rouge,...)

    This preprocessing step increases recall, while not decreasing
    precision."""
    name = name.lower()
    name = remove_weights(name)
    name = remove_labels(name, lang)
    name = strip_consecutive_spaces(name)
    name = name.strip()
    return name


def remove_weights(name: str) -> str:
    return WEIGHT_REGEX.sub('', name)


def remove_labels(name: str, lang: str) -> str:
    if lang in LABELS_REGEX:
        name = LABELS_REGEX[lang].sub('', name)

    return name
