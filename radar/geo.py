"""Country, city and region lookup for location strings."""
import re

EUROPE = {
    "AL": ["albania", "tirana"], "AD": ["andorra"], "AT": ["austria", "österreich", "vienna", "wien", "graz", "linz", "salzburg", "innsbruck"],
    "BY": ["belarus", "minsk"], "BE": ["belgium", "belgië", "belgique", "brussels", "bruxelles", "brussel", "antwerp", "antwerpen", "ghent", "gent", "leuven", "liège"],
    "BA": ["bosnia", "sarajevo"], "BG": ["bulgaria", "sofia", "plovdiv", "varna"], "HR": ["croatia", "hrvatska", "zagreb", "split", "rijeka"],
    "CY": ["cyprus", "nicosia", "limassol"], "CZ": ["czechia", "czech republic", "česko", "prague", "praha", "brno", "ostrava"],
    "DK": ["denmark", "danmark", "copenhagen", "københavn", "aarhus", "odense"], "EE": ["estonia", "tallinn", "tartu"],
    "FI": ["finland", "suomi", "helsinki", "espoo", "tampere", "oulu", "turku"],
    "FR": ["france", "paris", "lyon", "marseille", "toulouse", "bordeaux", "lille", "nantes", "nice", "montpellier", "rennes", "strasbourg", "grenoble", "sophia antipolis"],
    "DE": ["germany", "deutschland", "berlin", "munich", "münchen", "muenchen", "hamburg", "frankfurt", "cologne", "köln", "koeln", "düsseldorf", "duesseldorf", "dusseldorf",
           "stuttgart", "leipzig", "dresden", "hannover", "hanover", "nuremberg", "nürnberg", "bonn", "karlsruhe", "freiburg", "mannheim", "heidelberg", "potsdam", "essen", "dortmund", "bremen", "münster", "aachen"],
    "GR": ["greece", "athens", "thessaloniki"], "HU": ["hungary", "magyarország", "magyarorszag", "budapest", "debrecen", "szeged", "pécs", "pecs", "győr", "gyor", "miskolc", "kecskemét", "székesfehérvár"],
    "IS": ["iceland", "reykjavik", "reykjavík"], "IE": ["ireland", "dublin", "cork", "galway", "limerick"],
    "IT": ["italy", "italia", "rome", "roma", "milan", "milano", "turin", "torino", "bologna", "florence", "firenze", "naples", "napoli", "genoa", "padua", "verona"],
    "XK": ["kosovo", "pristina", "prishtina"], "LV": ["latvia", "riga"], "LI": ["liechtenstein"], "LT": ["lithuania", "vilnius", "kaunas"],
    "LU": ["luxembourg"], "MT": ["malta", "valletta"], "MD": ["moldova", "chisinau", "chișinău"], "MC": ["monaco"], "ME": ["montenegro", "podgorica"],
    "NL": ["netherlands", "nederland", "holland", "amsterdam", "rotterdam", "utrecht", "the hague", "den haag", "eindhoven", "groningen", "delft", "leiden", "haarlem", "arnhem", "nijmegen"],
    "MK": ["north macedonia", "macedonia", "skopje"], "NO": ["norway", "norge", "oslo", "bergen", "trondheim", "stavanger"],
    "PL": ["poland", "polska", "warsaw", "warszawa", "krakow", "kraków", "cracow", "wroclaw", "wrocław", "gdansk", "gdańsk", "poznan", "poznań", "lodz", "łódź", "katowice", "gdynia", "lublin", "szczecin"],
    "PT": ["portugal", "lisbon", "lisboa", "porto", "braga", "coimbra", "aveiro"],
    "RO": ["romania", "românia", "bucharest", "bucurești", "bucuresti", "cluj", "iasi", "iași", "timisoara", "timișoara", "brasov", "brașov"],
    "RS": ["serbia", "belgrade", "beograd", "novi sad"], "SK": ["slovakia", "bratislava", "košice", "kosice"], "SI": ["slovenia", "ljubljana", "maribor"],
    "ES": ["spain", "españa", "espana", "madrid", "barcelona", "valencia", "seville", "sevilla", "malaga", "málaga", "bilbao", "palma", "zaragoza", "alicante"],
    "SE": ["sweden", "sverige", "stockholm", "gothenburg", "göteborg", "goteborg", "malmö", "malmo", "uppsala", "lund", "linköping"],
    "CH": ["switzerland", "schweiz", "suisse", "svizzera", "zurich", "zürich", "geneva", "genève", "basel", "bern", "lausanne", "zug", "lucerne", "luzern"],
    "UA": ["ukraine", "kyiv", "kiev", "lviv", "kharkiv", "odesa", "odessa", "dnipro"],
    "GB": ["united kingdom", "uk", "u.k.", "england", "scotland", "wales", "northern ireland", "great britain", "london", "manchester", "edinburgh", "glasgow",
           "bristol", "birmingham", "leeds", "cambridge", "oxford", "belfast", "brighton", "liverpool", "newcastle", "sheffield", "nottingham", "reading", "cardiff", "bath"],
    "TR": ["turkey", "türkiye", "turkiye", "istanbul", "ankara", "izmir"],
}
EU_MEMBERS = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}
COUNTRY_NAMES = {
    "AL": "Albania", "AD": "Andorra", "AT": "Austria", "BY": "Belarus", "BE": "Belgium", "BA": "Bosnia", "BG": "Bulgaria", "HR": "Croatia", "CY": "Cyprus",
    "CZ": "Czechia", "DK": "Denmark", "EE": "Estonia", "FI": "Finland", "FR": "France", "DE": "Germany", "GR": "Greece", "HU": "Hungary", "IS": "Iceland",
    "IE": "Ireland", "IT": "Italy", "XK": "Kosovo", "LV": "Latvia", "LI": "Liechtenstein", "LT": "Lithuania", "LU": "Luxembourg", "MT": "Malta", "MD": "Moldova",
    "MC": "Monaco", "ME": "Montenegro", "NL": "Netherlands", "MK": "North Macedonia", "NO": "Norway", "PL": "Poland", "PT": "Portugal", "RO": "Romania",
    "RS": "Serbia", "SK": "Slovakia", "SI": "Slovenia", "ES": "Spain", "SE": "Sweden", "CH": "Switzerland", "UA": "Ukraine", "GB": "United Kingdom", "TR": "Türkiye",
    "US": "United States", "CA": "Canada", "IN": "India", "IL": "Israel", "SG": "Singapore", "AU": "Australia", "NZ": "New Zealand", "JP": "Japan",
    "AE": "UAE", "BR": "Brazil", "MX": "Mexico", "AR": "Argentina", "CO": "Colombia", "CL": "Chile", "ZA": "South Africa", "NG": "Nigeria", "KE": "Kenya",
    "EG": "Egypt", "PH": "Philippines", "KR": "South Korea", "CN": "China", "HK": "Hong Kong", "TW": "Taiwan", "GE": "Georgia", "AM": "Armenia",
}
OTHER = {
    "US": ["united states", "usa", "u.s.", "u.s.a", "new york", "nyc", "san francisco", "sf bay", "bay area", "los angeles", "seattle", "austin", "boston",
           "chicago", "denver", "atlanta", "miami", "washington, dc", "washington dc", "portland, or", "san diego", "san jose", "palo alto", "mountain view",
           "menlo park", "brooklyn", "philadelphia", "dallas", "houston", "salt lake", "minneapolis", "pittsburgh", "raleigh", "nashville", "phoenix"],
    "CA": ["canada", "toronto", "vancouver", "montreal", "montréal", "ottawa", "calgary", "waterloo"],
    "IN": ["india", "bangalore", "bengaluru", "mumbai", "delhi", "gurgaon", "gurugram", "noida", "hyderabad", "pune", "chennai"],
    "IL": ["israel", "tel aviv", "tel-aviv"], "SG": ["singapore"], "AU": ["australia", "sydney", "melbourne", "brisbane", "perth"],
    "NZ": ["new zealand", "auckland", "wellington"], "JP": ["japan", "tokyo"], "AE": ["uae", "united arab emirates", "dubai", "abu dhabi"],
    "BR": ["brazil", "brasil", "são paulo", "sao paulo"], "MX": ["mexico", "méxico", "mexico city"], "AR": ["argentina", "buenos aires"],
    "CO": ["colombia", "bogota", "bogotá", "medellin"], "CL": ["chile", "santiago"], "ZA": ["south africa", "cape town", "johannesburg"],
    "NG": ["nigeria", "lagos"], "KE": ["kenya", "nairobi"], "EG": ["egypt", "cairo"], "PH": ["philippines", "manila"], "KR": ["korea", "seoul"],
    "CN": ["china", "shanghai", "beijing", "shenzhen"], "HK": ["hong kong"], "TW": ["taiwan", "taipei"], "GE": ["tbilisi"], "AM": ["armenia", "yerevan"],
}
US_STATES = {"AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
             "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"}
US_STATE_NAMES = ["california", "texas", "florida", "massachusetts", "illinois", "colorado", "washington state", "oregon", "north carolina", "virginia",
                  "pennsylvania", "new jersey", "michigan", "minnesota", "utah", "arizona", "ohio", "tennessee", "maryland", "connecticut"]

WORLDWIDE = ["worldwide", "anywhere", "global", "remote - global", "location independent", "work from anywhere", "earth", "all countries", "international"]
EUROPE_WORDS = ["europe", "european", "emea", "eu ", " eu", "(eu)", "eu-", "eu,", "eea", "cet", "cest", "eet", "cee", "dach", "nordics", "baltics", "benelux",
                "european union", "central europe", "eastern europe", "western europe", "european timezone", "european time zone"]
AMERICAS_WORDS = ["americas", "north america", "latam", "latin america", "us only", "usa only", "us-only", "united states only", "canada only", "us timezone",
                  "us time zone", "est timezone", "pst timezone"]
APAC_WORDS = ["apac", "asia pacific", "asia-pacific", "oceania", "anz"]

_PAT = []
for code, words in list(EUROPE.items()) + list(OTHER.items()):
    for w in words:
        _PAT.append((re.compile(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])"), code))
_STATE_PAT = re.compile(r",\s*(" + "|".join(sorted(US_STATES)) + r")\b(?!\s*[a-z])")


def countries_in(text):
    """Return ordered unique ISO2 codes found in a location string."""
    if not text:
        return []
    low = text.lower()
    found = []
    for pat, code in _PAT:
        if code in found:
            continue
        if pat.search(low):
            # 'georgia' and 'ca' style ambiguity is avoided by not listing them as words
            found.append(code)
    if _STATE_PAT.search(text) and "US" not in found:
        # "Austin, TX" style; skip ', CA' when Canada words present
        m = _STATE_PAT.search(text).group(1)
        if not (m == "CA" and "CA" in found):
            found.append("US")
    if any(s in low for s in US_STATE_NAMES) and "US" not in found:
        found.append("US")
    if "GB" in found and "IE" in found and "northern ireland" in low and "dublin" not in low and "republic" not in low:
        found.remove("IE")
    return found


def has_any(low, words):
    return any(w in low for w in words)


def is_europe(code):
    return code in EUROPE


def label(code):
    return COUNTRY_NAMES.get(code, code)
