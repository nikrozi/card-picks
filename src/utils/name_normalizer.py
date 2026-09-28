"""
Team Name Normalizer
Maps all known team name variants across data sources to a single canonical name.
Uses a dictionary for known names and fuzzy matching as a fallback.
"""

from thefuzz import fuzz, process

_CANONICAL_MAP = {
    # --- Premier League ---
    "Arsenal": ["Arsenal", "Arsenal FC"],
    "Aston Villa": ["Aston Villa", "Aston Villa FC"],
    "Bournemouth": ["Bournemouth", "AFC Bournemouth", "A.F.C. Bournemouth"],
    "Brentford": ["Brentford", "Brentford FC"],
    "Brighton": ["Brighton", "Brighton & Hove Albion", "Brighton and Hove Albion", "Brighton & Hove", "Brighton Hove Albion"],
    "Burnley": ["Burnley", "Burnley FC"],
    "Chelsea": ["Chelsea", "Chelsea FC"],
    "Crystal Palace": ["Crystal Palace", "Crystal Palace FC", "C Palace"],
    "Everton": ["Everton", "Everton FC"],
    "Fulham": ["Fulham", "Fulham FC"],
    "Leeds": ["Leeds", "Leeds United", "Leeds Utd"],
    "Leicester": ["Leicester", "Leicester City", "Leicester City FC"],
    "Liverpool": ["Liverpool", "Liverpool FC"],
    "Man City": ["Man City", "Manchester City", "Manchester City FC", "Man. City"],
    "Man Utd": ["Man Utd", "Manchester United", "Manchester United FC", "Man. United", "Man United"],
    "Newcastle": ["Newcastle", "Newcastle United", "Newcastle Utd", "Newcastle United FC"],
    "Nottm Forest": ["Nottm Forest", "Nottingham Forest", "Nott'm Forest", "Notts Forest", "Nottingham Forest FC"],
    "Southampton": ["Southampton", "Southampton FC"],
    "Sunderland": ["Sunderland", "Sunderland AFC"],
    "Tottenham": ["Tottenham", "Tottenham Hotspur", "Tottenham Hotspur FC", "Spurs"],
    "West Ham": ["West Ham", "West Ham United", "West Ham Utd", "West Ham United FC"],
    "Wolverhampton": ["Wolverhampton", "Wolverhampton Wanderers", "Wolves", "Wolverhampton Wanderers FC"],
    "Ipswich": ["Ipswich", "Ipswich Town", "Ipswich Town FC"],
    "Luton": ["Luton", "Luton Town", "Luton Town FC"],
    "Sheffield Utd": ["Sheffield Utd", "Sheffield United", "Sheff Utd", "Sheffield United FC"],

    # --- Championship ---
    "Birmingham": ["Birmingham", "Birmingham City", "Birmingham City FC"],
    "Blackburn": ["Blackburn", "Blackburn Rovers", "Blackburn Rovers FC"],
    "Bristol City": ["Bristol City", "Bristol City FC"],
    "Cardiff": ["Cardiff", "Cardiff City", "Cardiff City FC"],
    "Charlton": ["Charlton", "Charlton Athletic", "Charlton Athletic FC"],
    "Coventry": ["Coventry", "Coventry City", "Coventry City FC"],
    "Derby": ["Derby", "Derby County", "Derby County FC"],
    "Hull": ["Hull", "Hull City", "Hull City FC"],
    "Middlesbrough": ["Middlesbrough", "Middlesbrough FC", "Boro"],
    "Millwall": ["Millwall", "Millwall FC"],
    "Norwich": ["Norwich", "Norwich City", "Norwich City FC"],
    "Oxford United": ["Oxford United", "Oxford Utd", "Oxford United FC"],
    "Plymouth": ["Plymouth", "Plymouth Argyle", "Plymouth Argyle FC"],
    "Portsmouth": ["Portsmouth", "Portsmouth FC", "Pompey"],
    "Preston": ["Preston", "Preston North End", "Preston North End FC"],
    "QPR": ["QPR", "Queens Park Rangers", "Queens Park Rangers FC"],
    "Sheffield Wed": ["Sheffield Wed", "Sheffield Wednesday", "Sheff Wed", "Sheffield Wednesday FC"],
    "Stoke": ["Stoke", "Stoke City", "Stoke City FC"],
    "Swansea": ["Swansea", "Swansea City", "Swansea City FC"],
    "Watford": ["Watford", "Watford FC"],
    "West Brom": ["West Brom", "West Bromwich Albion", "West Bromwich", "WBA", "West Bromwich Albion FC"],
    "Wrexham": ["Wrexham", "Wrexham AFC", "Wrexham FC"],

    # --- La Liga ---
    "Atletico Madrid": ["Atletico Madrid", "Atl. Madrid", "Atlético Madrid", "Atletico de Madrid", "Atlético de Madrid", "Atl Madrid"],
    "Athletic Bilbao": ["Athletic Bilbao", "Athletic Club", "Ath Bilbao", "Ath. Bilbao"],
    "Barcelona": ["Barcelona", "FC Barcelona", "Barca", "Barça"],
    "CD Alaves": ["CD Alaves", "Alaves", "Alavés", "Deportivo Alaves", "Deportivo Alavés"],
    "Celta Vigo": ["Celta Vigo", "Celta", "RC Celta", "RC Celta de Vigo"],
    "Elche": ["Elche", "Elche CF"],
    "Espanyol": ["Espanyol", "RCD Espanyol"],
    "Getafe": ["Getafe", "Getafe CF"],
    "Girona": ["Girona", "Girona FC"],
    "Levante": ["Levante", "Levante UD"],
    "Mallorca": ["Mallorca", "RCD Mallorca", "Real Mallorca"],
    "Osasuna": ["Osasuna", "CA Osasuna"],
    "Oviedo": ["Oviedo", "Real Oviedo"],
    "Rayo Vallecano": ["Rayo Vallecano", "Rayo"],
    "Real Betis": ["Real Betis", "Betis", "Real Betis Balompie"],
    "Real Madrid": ["Real Madrid", "Real Madrid CF", "R. Madrid"],
    "Real Sociedad": ["Real Sociedad", "Real Sociedad FC", "R. Sociedad"],
    "Sevilla": ["Sevilla", "Sevilla FC"],
    "Valencia": ["Valencia", "Valencia CF"],
    "Villarreal": ["Villarreal", "Villarreal CF"],
    "Las Palmas": ["Las Palmas", "UD Las Palmas"],
    "Real Valladolid": ["Real Valladolid", "Valladolid", "R. Valladolid"],
    "Leganes": ["Leganes", "Leganés", "CD Leganés", "CD Leganes"],
    "Racing Santander": ["Racing Santander", "Racing"],

    # --- Bundesliga ---
    "Augsburg": ["Augsburg", "FC Augsburg"],
    "Bayer Leverkusen": ["Bayer Leverkusen", "Leverkusen", "B. Leverkusen", "Bayer 04 Leverkusen"],
    "Bayern Munich": ["Bayern Munich", "Bayern München", "FC Bayern Munich", "FC Bayern München", "Bayern"],
    "Borussia Dortmund": ["Borussia Dortmund", "BVB", "Dortmund", "B. Dortmund"],
    "Borussia M'gladbach": ["Borussia M'gladbach", "Borussia Monchengladbach", "Borussia Mönchengladbach", "B. Monchengladbach", "Gladbach", "M'gladbach"],
    "Cologne": ["Cologne", "FC Cologne", "FC Köln", "1. FC Köln", "Koln"],
    "Eintracht Frankfurt": ["Eintracht Frankfurt", "Ein Frankfurt", "E. Frankfurt", "Frankfurt"],
    "SC Freiburg": ["SC Freiburg", "Freiburg", "Sport-Club Freiburg"],
    "Hamburg": ["Hamburg", "Hamburger SV", "HSV"],
    "Heidenheim": ["Heidenheim", "1. FC Heidenheim", "FC Heidenheim"],
    "TSG Hoffenheim": ["TSG Hoffenheim", "Hoffenheim", "1899 Hoffenheim", "TSG 1899 Hoffenheim"],
    "Mainz": ["Mainz", "Mainz 05", "1. FSV Mainz 05", "FSV Mainz"],
    "RB Leipzig": ["RB Leipzig", "Leipzig", "RasenBallsport Leipzig"],
    "St Pauli": ["St Pauli", "St. Pauli", "FC St. Pauli", "FC St Pauli"],
    "Union Berlin": ["Union Berlin", "1. FC Union Berlin", "FC Union Berlin"],
    "VfB Stuttgart": ["VfB Stuttgart", "Stuttgart", "VfB Stuttgart 1893"],
    "Werder Bremen": ["Werder Bremen", "Bremen", "SV Werder Bremen"],
    "Wolfsburg": ["Wolfsburg", "VfL Wolfsburg"],
    "Holstein Kiel": ["Holstein Kiel", "Kiel"],

    # --- Serie A ---
    "AC Milan": ["AC Milan", "Milan", "A.C. Milan"],
    "Atalanta": ["Atalanta", "Atalanta BC", "Atalanta Bergamo"],
    "Bologna": ["Bologna", "Bologna FC", "Bologna FC 1909"],
    "Cagliari": ["Cagliari", "Cagliari Calcio"],
    "Como": ["Como", "Como 1907"],
    "Cremonese": ["Cremonese", "US Cremonese"],
    "Fiorentina": ["Fiorentina", "ACF Fiorentina"],
    "Genoa": ["Genoa", "Genoa CFC"],
    "Inter Milan": ["Inter Milan", "Inter", "Internazionale", "FC Internazionale", "FC Inter"],
    "Juventus": ["Juventus", "Juventus FC", "Juve"],
    "Lazio": ["Lazio", "SS Lazio", "S.S. Lazio"],
    "Lecce": ["Lecce", "US Lecce"],
    "Napoli": ["Napoli", "SSC Napoli", "S.S.C. Napoli"],
    "Parma": ["Parma", "Parma Calcio", "Parma Calcio 1913"],
    "Pisa": ["Pisa", "AC Pisa"],
    "Roma": ["Roma", "AS Roma", "A.S. Roma"],
    "Sassuolo": ["Sassuolo", "US Sassuolo"],
    "Torino": ["Torino", "Torino FC"],
    "Udinese": ["Udinese", "Udinese Calcio"],
    "Verona": ["Verona", "Hellas Verona", "Hellas Verona FC"],
    "Monza": ["Monza", "AC Monza"],
    "Venezia": ["Venezia", "Venezia FC"],
    "Empoli": ["Empoli", "Empoli FC"],
    "Salernitana": ["Salernitana", "US Salernitana"],

    # --- Ligue 1 ---
    "Angers": ["Angers", "Angers SCO"],
    "Auxerre": ["Auxerre", "AJ Auxerre"],
    "Brest": ["Brest", "Stade Brestois", "Stade Brestois 29"],
    "Le Havre": ["Le Havre", "Le Havre AC"],
    "Lens": ["Lens", "RC Lens"],
    "Lille": ["Lille", "LOSC Lille", "LOSC"],
    "Lorient": ["Lorient", "FC Lorient"],
    "Lyon": ["Lyon", "Olympique Lyonnais", "Olympique Lyon", "OL"],
    "Marseille": ["Marseille", "Olympique de Marseille", "Olympique Marseille", "OM"],
    "Metz": ["Metz", "FC Metz"],
    "Monaco": ["Monaco", "AS Monaco", "AS Monaco FC"],
    "Montpellier": ["Montpellier", "Montpellier HSC"],
    "Nantes": ["Nantes", "FC Nantes"],
    "Nice": ["Nice", "OGC Nice"],
    "Paris FC": ["Paris FC"],
    "PSG": ["PSG", "Paris Saint-Germain", "Paris Saint Germain", "Paris SG"],
    "Reims": ["Reims", "Stade de Reims"],
    "Rennes": ["Rennes", "Stade Rennais", "Stade Rennais FC"],
    "Saint-Etienne": ["Saint-Etienne", "St Etienne", "AS Saint-Etienne", "AS Saint-Étienne", "St-Etienne"],
    "Strasbourg": ["Strasbourg", "RC Strasbourg", "RC Strasbourg Alsace"],
    "Toulouse": ["Toulouse", "Toulouse FC"],

    # --- Eredivisie ---
    "Ajax": ["Ajax", "AFC Ajax"],
    "AZ Alkmaar": ["AZ Alkmaar", "AZ", "AZ Alkmaar FC"],
    "Excelsior": ["Excelsior", "SBV Excelsior"],
    "Feyenoord": ["Feyenoord", "Feyenoord Rotterdam"],
    "Fortuna Sittard": ["Fortuna Sittard", "Fortuna"],
    "Go Ahead Eagles": ["Go Ahead Eagles"],
    "Heerenveen": ["Heerenveen", "SC Heerenveen"],
    "Heracles": ["Heracles", "Heracles Almelo"],
    "NAC Breda": ["NAC Breda", "NAC"],
    "NEC Nijmegen": ["NEC Nijmegen", "NEC", "N.E.C."],
    "PSV": ["PSV", "PSV Eindhoven"],
    "RKC Waalwijk": ["RKC Waalwijk", "RKC"],
    "Sparta Rotterdam": ["Sparta Rotterdam", "Sparta"],
    "Twente": ["Twente", "FC Twente"],
    "Utrecht": ["Utrecht", "FC Utrecht"],
    "Vitesse": ["Vitesse", "Vitesse Arnhem"],
    "Volendam": ["Volendam", "FC Volendam"],
    "Willem II": ["Willem II", "Willem II Tilburg"],
    "PEC Zwolle": ["PEC Zwolle", "Zwolle"],

    # --- Portuguese Liga ---
    "Benfica": ["Benfica", "SL Benfica", "Sport Lisboa e Benfica"],
    "Porto": ["Porto", "FC Porto"],
    "Sporting Lisbon": ["Sporting Lisbon", "Sporting CP", "Sporting", "Sporting Clube de Portugal"],
    "Braga": ["Braga", "SC Braga", "Sporting Braga"],
    "Vitoria Guimaraes": ["Vitoria Guimaraes", "Vitória Guimarães", "Vitoria SC", "Vitória SC"],
    "Gil Vicente": ["Gil Vicente", "Gil Vicente FC"],
    "Santa Clara": ["Santa Clara", "CD Santa Clara"],
    "Moreirense": ["Moreirense", "Moreirense FC"],
    "Casa Pia": ["Casa Pia", "Casa Pia AC"],
    "Estoril": ["Estoril", "Estoril Praia", "GD Estoril Praia"],
    "Estrela": ["Estrela", "Estrela Amadora", "CF Estrela da Amadora"],
    "Tondela": ["Tondela", "CD Tondela"],
    "AVS": ["AVS", "AVS Futebol SAD"],
    "Famalicao": ["Famalicao", "Famalicão", "FC Famalicão", "FC Famalicao"],
    "Boavista": ["Boavista", "Boavista FC"],
    "Rio Ave": ["Rio Ave", "Rio Ave FC"],
    "Arouca": ["Arouca", "FC Arouca"],
    "Nacional": ["Nacional", "CD Nacional"],

    # --- Belgian Pro League ---
    "Anderlecht": ["Anderlecht", "RSC Anderlecht"],
    "Club Brugge": ["Club Brugge", "Club Bruges", "Club Brugge KV"],
    "Antwerp": ["Antwerp", "Royal Antwerp", "Royal Antwerp FC"],
    "Genk": ["Genk", "KRC Genk", "Racing Genk"],
    "Standard Liege": ["Standard Liege", "Standard Liège", "Standard de Liège", "Standard"],
    "Union SG": ["Union SG", "Union Saint-Gilloise", "Royale Union Saint-Gilloise", "Union"],
    "Gent": ["Gent", "KAA Gent", "AA Gent"],
    "Leuven": ["Leuven", "OH Leuven", "OHL"],
    "Westerlo": ["Westerlo", "KVC Westerlo"],
    "Waregem": ["Waregem", "Zulte Waregem", "SV Zulte Waregem"],
    "Cercle Brugge": ["Cercle Brugge", "Cercle Bruges"],
    "Charleroi": ["Charleroi", "Sporting Charleroi", "R. Charleroi SC"],
    "Mechelen": ["Mechelen", "KV Mechelen"],
    "Kortrijk": ["Kortrijk", "KV Kortrijk"],
    "STVV": ["STVV", "Sint-Truiden", "Sint-Truidense VV", "St. Truiden"],

    # --- Turkish Super Lig ---
    "Galatasaray": ["Galatasaray", "Galatasaray SK"],
    "Fenerbahce": ["Fenerbahce", "Fenerbahçe", "Fenerbahçe SK"],
    "Besiktas": ["Besiktas", "Beşiktaş", "Beşiktaş JK"],
    "Trabzonspor": ["Trabzonspor"],
    "Basaksehir": ["Basaksehir", "Başakşehir", "Istanbul Basaksehir", "İstanbul Başakşehir"],
    "Alanyaspor": ["Alanyaspor", "Corendon Alanyaspor"],
    "Antalyaspor": ["Antalyaspor"],
    "Karagumruk": ["Karagumruk", "Karagümrük", "Fatih Karagümrük"],
    "Gaziantep": ["Gaziantep", "Gaziantep FK"],
    "Samsunspor": ["Samsunspor"],
    "Goztepe": ["Goztepe", "Göztepe"],
    "Eyupspor": ["Eyupspor", "Eyüpspor"],
    "Sivasspor": ["Sivasspor"],
    "Kasimpasa": ["Kasimpasa", "Kasımpaşa"],
    "Hatayspor": ["Hatayspor"],
    "Kayserispor": ["Kayserispor"],
    "Konyaspor": ["Konyaspor"],
    "Rizespor": ["Rizespor", "Çaykur Rizespor"],
    "Adana Demirspor": ["Adana Demirspor"],
    "Pendikspor": ["Pendikspor"],
    "Bodrumspor": ["Bodrumspor"],

    # --- Scottish Premiership ---
    "Celtic": ["Celtic", "Celtic FC", "Celtic Glasgow"],
    "Rangers": ["Rangers", "Rangers FC", "Glasgow Rangers"],
    "Aberdeen": ["Aberdeen", "Aberdeen FC"],
    "Hearts": ["Hearts", "Heart of Midlothian", "Hearts FC"],
    "Hibernian": ["Hibernian", "Hibs", "Hibernian FC"],
    "Dundee": ["Dundee", "Dundee FC"],
    "Dundee United": ["Dundee United", "Dundee Utd", "Dundee United FC"],
    "Kilmarnock": ["Kilmarnock", "Kilmarnock FC"],
    "Motherwell": ["Motherwell", "Motherwell FC"],
    "St Mirren": ["St Mirren", "St. Mirren", "Saint Mirren", "St Mirren FC"],
    "Ross County": ["Ross County"],
    "Livingston": ["Livingston", "Livingston FC"],
    "St Johnstone": ["St Johnstone", "St. Johnstone", "Saint Johnstone"],
    "Falkirk": ["Falkirk", "Falkirk FC"],
}

_VARIANT_TO_CANONICAL = {}
_ALL_CANONICAL_NAMES = set()

for canonical, variants in _CANONICAL_MAP.items():
    _ALL_CANONICAL_NAMES.add(canonical)
    for variant in variants:
        _VARIANT_TO_CANONICAL[variant.lower()] = canonical


def normalize(name: str) -> str:
    """
    Normalize a team name to its canonical form.
    1. Exact dictionary lookup (case-insensitive)
    2. Fuzzy matching fallback (threshold 80)
    3. Returns original name if no match found
    """
    if not name or not isinstance(name, str):
        return name

    cleaned = name.strip()
    key = cleaned.lower()

    if key in _VARIANT_TO_CANONICAL:
        return _VARIANT_TO_CANONICAL[key]

    best_match, score = process.extractOne(
        cleaned, list(_VARIANT_TO_CANONICAL.keys()), scorer=fuzz.token_sort_ratio
    )
    if score >= 80:
        return _VARIANT_TO_CANONICAL[best_match]

    return cleaned


def normalize_dataframe(df, columns):
    """Normalize team name columns in a DataFrame in-place."""
    for col in columns:
        if col in df.columns:
            df[col] = df[col].apply(normalize)
    return df


def get_canonical_name(name: str) -> str:
    """Alias for normalize()."""
    return normalize(name)


if __name__ == "__main__":
    test_names = [
        "Manchester United", "Man Utd", "Man United",
        "Brighton & Hove Albion", "Brighton",
        "Wolverhampton Wanderers", "Wolves", "Wolverhampton",
        "Nottingham Forest", "Nottm Forest",
        "AFC Bournemouth", "Bournemouth",
        "Tottenham Hotspur", "Spurs",
    ]
    print("Team Name Normalization Test:")
    print("-" * 50)
    for name in test_names:
        print(f"  {name:35s} -> {normalize(name)}")
