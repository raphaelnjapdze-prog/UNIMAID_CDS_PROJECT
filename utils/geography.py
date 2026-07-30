"""Administrative geography for the survey area.

Stdlib only, no Streamlit — the DHIS2 UID script and any offline tooling import this
without starting an app runtime, the same reason logging_config keeps its imports bare.
"""

# The 27 Local Government Areas of Borno State, where this survey operates.
#
# A fixed list rather than free text: the LGA is the DHIS2 export's grouping key, so
# "Maiduguri", "maiduguri " and "Maiduguri MC" typed on three different days would silently
# become three org units. Names are the standard spellings used by the Nigerian NHMIS
# registry, including the two with slashes — do not "clean" those; they are the real names,
# and the mapping to a DHIS2 UID is by exact string.
BORNO_LGAS = [
    "Abadam", "Askira/Uba", "Bama", "Bayo", "Biu", "Chibok", "Damboa", "Dikwa",
    "Gubio", "Guzamala", "Gwoza", "Hawul", "Jere", "Kaga", "Kala/Balge", "Konduga",
    "Kukawa", "Kwaya Kusar", "Mafa", "Magumeri", "Maiduguri", "Marte", "Mobbar",
    "Monguno", "Ngala", "Nganzai", "Shani",
]

# Selected by default in the Site Log: a field worker logging from Maiduguri should not
# have to scroll 27 options to pick the one they are standing in.
DEFAULT_LGA = "Maiduguri"
