"""Country and region logic for eligibility checks. Pure Python, no Django.

Design rule: never wrongly disqualify someone. Anything we cannot resolve
(a misspelled country, a region we have no list for) returns UNKNOWN.

The Africa and Commonwealth lists are membership lists. A provider may use a
narrower list (for example only low and middle income Commonwealth countries),
so ELIGIBLE here means "inside the stated region", not "confirmed eligible".
"""
import unicodedata

ELIGIBLE = "eligible"
INELIGIBLE = "ineligible"
UNKNOWN = "unknown"

WORLDWIDE = "worldwide"

AFRICA = (
    "Algeria", "Angola", "Benin", "Botswana", "Burkina Faso", "Burundi",
    "Cabo Verde", "Cameroon", "Central African Republic", "Chad", "Comoros",
    "Democratic Republic of the Congo", "Congo", "Côte d'Ivoire", "Djibouti",
    "Egypt", "Equatorial Guinea", "Eritrea", "Eswatini", "Ethiopia", "Gabon",
    "Gambia", "Ghana", "Guinea", "Guinea-Bissau", "Kenya", "Lesotho", "Liberia",
    "Libya", "Madagascar", "Malawi", "Mali", "Mauritania", "Mauritius",
    "Morocco", "Mozambique", "Namibia", "Niger", "Nigeria", "Rwanda",
    "São Tomé and Príncipe", "Senegal", "Seychelles", "Sierra Leone", "Somalia",
    "South Africa", "South Sudan", "Sudan", "Tanzania", "Togo", "Tunisia",
    "Uganda", "Zambia", "Zimbabwe",
)

COMMONWEALTH = (
    "Antigua and Barbuda", "Australia", "Bahamas", "Bangladesh", "Barbados",
    "Belize", "Botswana", "Brunei", "Cameroon", "Canada", "Cyprus", "Dominica",
    "Eswatini", "Fiji", "Gabon", "Gambia", "Ghana", "Grenada", "Guyana", "India",
    "Jamaica", "Kenya", "Kiribati", "Lesotho", "Malawi", "Malaysia", "Maldives",
    "Malta", "Mauritius", "Mozambique", "Namibia", "Nauru", "New Zealand",
    "Nigeria", "Pakistan", "Papua New Guinea", "Rwanda", "Saint Kitts and Nevis",
    "Saint Lucia", "Saint Vincent and the Grenadines", "Samoa", "Seychelles",
    "Sierra Leone", "Singapore", "Solomon Islands", "South Africa", "Sri Lanka",
    "Tanzania", "Togo", "Tonga", "Trinidad and Tobago", "Tuvalu", "Uganda",
    "United Kingdom", "Vanuatu", "Zambia",
)

# Common destinations and origins, so the profile form can suggest them and
# region lists that name them can be evaluated.
OTHER_COUNTRIES = (
    "Argentina", "Austria", "Belarus", "Belgium", "Brazil", "China", "Denmark",
    "Finland", "France", "Germany", "Ireland", "Italy", "Japan", "Mexico",
    "Netherlands", "Norway", "Poland", "Portugal", "Russia", "Saudi Arabia",
    "Spain", "Sweden", "Switzerland", "Turkey", "United Arab Emirates",
    "United States",
)

_RAW_ALIASES = {
    "uk": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
    "scotland": "United Kingdom",
    "wales": "United Kingdom",
    "northern ireland": "United Kingdom",
    "usa": "United States",
    "us": "United States",
    "america": "United States",
    "united states of america": "United States",
    "ivory coast": "Côte d'Ivoire",
    "drc": "Democratic Republic of the Congo",
    "dr congo": "Democratic Republic of the Congo",
    "congo (kinshasa)": "Democratic Republic of the Congo",
    "republic of the congo": "Congo",
    "congo (brazzaville)": "Congo",
    "the gambia": "Gambia",
    "swaziland": "Eswatini",
    "cape verde": "Cabo Verde",
    "united republic of tanzania": "Tanzania",
    "turkiye": "Turkey",
    "russian federation": "Russia",
    "the bahamas": "Bahamas",
    "global": "Worldwide",
    "all countries": "Worldwide",
    "any country": "Worldwide",
}


def _clean(name):
    text = (name or "").replace("’", "'").replace("‘", "'")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.casefold().replace("&", " and ").replace(".", "")
    return " ".join(text.split())


ALIASES = {_clean(k): _clean(v) for k, v in _RAW_ALIASES.items()}

AFRICA_SET = frozenset(_clean(c) for c in AFRICA)
COMMONWEALTH_SET = frozenset(_clean(c) for c in COMMONWEALTH)
GROUPS = {"africa": AFRICA_SET, "commonwealth": COMMONWEALTH_SET}
KNOWN_GROUPS = frozenset(GROUPS) | {WORLDWIDE}
KNOWN_COUNTRIES = (
    AFRICA_SET | COMMONWEALTH_SET | frozenset(_clean(c) for c in OTHER_COUNTRIES)
)

COUNTRY_NAMES = tuple(sorted(set(AFRICA) | set(COMMONWEALTH) | set(OTHER_COUNTRIES)))


def canonical(name):
    """Lower-case, accent-free, alias-resolved form used for comparisons."""
    text = _clean(name)
    return ALIASES.get(text, text)


def is_known_country(name):
    return canonical(name) in KNOWN_COUNTRIES


def groups_for(country):
    name = canonical(country)
    return frozenset(g for g, members in GROUPS.items() if name in members)


def in_group(country, group):
    return canonical(country) in GROUPS.get(canonical(group), frozenset())


def region_status(eligible_regions, excluded_regions, country):
    """Compare a listing's stated regions with the user's country.

    Returns ELIGIBLE, INELIGIBLE or UNKNOWN. An empty eligible list means the
    provider did not say, which is UNKNOWN and never INELIGIBLE.
    """
    user = canonical(country)
    if not user:
        return UNKNOWN
    tokens = {user} | set(groups_for(user))

    for name in excluded_regions or ():
        if canonical(name) in tokens:
            return INELIGIBLE

    eligible = [c for c in (canonical(n) for n in (eligible_regions or ())) if c]
    if not eligible:
        return UNKNOWN
    if WORLDWIDE in eligible:
        return ELIGIBLE
    if any(token in tokens for token in eligible):
        return ELIGIBLE

    # No match. Only call it ineligible when we can resolve both sides.
    if user not in KNOWN_COUNTRIES:
        return UNKNOWN
    if all(t in KNOWN_GROUPS or t in KNOWN_COUNTRIES for t in eligible):
        return INELIGIBLE
    return UNKNOWN
