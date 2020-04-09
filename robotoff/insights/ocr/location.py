from contextlib import ExitStack
import dataclasses
import gzip
import json
from pathlib import Path
import re
from typing import Union, List, Dict, Optional, Tuple, Sequence, BinaryIO
import unicodedata

try:
    # Python >= 3.7
    from importlib.resources import open_binary
except ImportError:
    # Python < 3.7 with backported importlib_resources installed
    from importlib_resources import open_binary

from flashtext import KeywordProcessor

from robotoff.insights.ocr.dataclass import OCRResult
from robotoff.utils import get_logger


logger = get_logger(__name__)
CITIES_FR_RESOURCE = (f"{__package__}.resources", "laposte_hexasmal.json.gz")


@dataclasses.dataclass(frozen=True)
class City:
    """A city, storing its name, postal code and GPS coordinates."""

    name: str
    postal_code: str
    coordinates: Optional[Tuple[float, float]]


# TODO (alexandre.marty, 20200401): Is there a current practice for storing data in
#  the repo?
def load_cities_fr(source: Union[Path, BinaryIO, None] = None) -> List[City]:
    """Load French cities dataset.

    French cities are taken from the La Poste hexasmal dataset:
    https://datanova.legroupe.laposte.fr/explore/dataset/laposte_hexasmal/. The
    source file must be a gzipped-JSON.

    The returned list of cities can contain multiple items with the same name: multiple
    cities can exist with the same name but a different postal code.

    Also, the original dataset may contain multiple items with are not unique with
    regard to the :class:`City` class' attributes: there are additional fields in the
    original dataset which are ignored here. These duplicates are removed.

    Args:
        source (Path or BinaryIO or None, optional, default None): Path to the dataset
            file or open binary stream. If None, the dataset file contained in the
            repo will be used.

    Returns:
        list of City: List of all French cities as `City` objects.
    """
    # JSON file contains a lot of repeated data. An alternative could be to use the
    # CSV file.

    # Load JSON content
    with ExitStack() as cm_stack:
        if source is None:
            source = cm_stack.enter_context(open_binary(*CITIES_FR_RESOURCE))
        cities_file = cm_stack.enter_context(gzip.open(source, "rb"))
        json_data = json.load(cities_file)

    # Create City objects
    cities = []
    for item in json_data:
        city_data = item["fields"]
        coords = city_data.get("coordonnees_gps")
        if coords is not None:
            coords = tuple(coords)
        cities.append(
            City(
                city_data["nom_de_la_commune"].lower(), city_data["code_postal"], coords
            )
        )

    # Remove duplicates
    return list(set(cities))


def remove_accents(text: str) -> str:
    """Replace accented characters with non-accented ones in unicode string.

    Args:
        text (str): String to remove accents from.

    Returns:
        str: The input string with accents removed.

    Examples:
        >>> remove_accents("àéèïç")
        'aeeic'
    """
    nfkd_form = unicodedata.normalize("NFKD", text)
    return u"".join(c for c in nfkd_form if not unicodedata.combining(c))


# TODO (alexandre.marty, 20200401): Is this the right way to extract the locale?
def get_locale(ocr_result: OCRResult) -> Optional[str]:
    """Extract the most likely locale from the result of an OCR request.

    Args:
        ocr_result (OCRResult): An OCR request result.

    Returns:
        str or None: The most likely locale of the OCR result's text as a two-character
        string if found, otherwise None.
    """
    if len(ocr_result.text_annotations) > 0:
        return ocr_result.text_annotations[0].locale
    else:
        return None


class AddressExtractor:
    # TODO:
    #   * use city name and postal code distance
    #   * handle stop word in city names? (l, la...)
    def __init__(self, cities: Sequence[City]):
        self.cities = cities
        self.cities_processor = KeywordProcessor()
        for city in self.cities:
            self.cities_processor.add_keyword(city.name, city)

    def extract_location(self, ocr_result: OCRResult):
        locale = get_locale(ocr_result)
        if locale != "fr":
            return {"cities": [], "full_cities": [], "addresses": []}

        text = self.prepare_text(ocr_result.text_annotations_str_lower)
        cities = self.find_city_names(text)

        surround_distance = 30
        full_cities = []
        addresses = []
        for city, *span in cities:
            nearby_code = self.find_nearby_postal_code(text, city, span)
            if nearby_code is not None:
                full_cities.append((nearby_code, (city.name, *span)))
                address_start = min(span[0], nearby_code[1]) - surround_distance
                address_end = max(span[1], nearby_code[2]) + surround_distance
                addresses.append(
                    text[max(0, address_start):min(len(text), address_end)]
                )

        return {"cities": [(c[0].name, *c[1:]) for c in cities],
                "full_cities": full_cities,
                "addresses": addresses
                }

    def prepare_text(self, text_annotations_str_lower: str) -> str:
        text = text_annotations_str_lower
        text = text[:text.find("||")]  # Keep only full description
        text = remove_accents(text)
        text = text.replace("'", " ").replace("-", " ")
        return text

    def find_city_names(self, text: str) -> List[Tuple[City, int, int]]:
        return self.cities_processor.extract_keywords(text, span_info=True)

    def find_nearby_postal_code(self, text: str, city: City, span: Tuple[int, int]):
        max_distance = 10
        pattern = r"(?:[^0-9]|^)({})(?:[^0-9]|$)".format(city.postal_code)
        sub_start = max(0, span[0] - max_distance)
        sub_end = min(len(text), span[1] + max_distance)
        sub_text = text[sub_start:sub_end]
        match = re.search(pattern, sub_text)
        if match is None:
            return None
        else:
            return match.group(), sub_start + match.start(), sub_start + match.end()


def find_locations(content: Union[OCRResult, str]) -> List[Dict]:
    # TODO (alexandre.marty, 20200401): Is there an existing way to properly cache
    #  resources expensive to load?
    cities = load_cities_fr()
    location_extractor = AddressExtractor(cities)
    return [location_extractor.extract_location(content)]
