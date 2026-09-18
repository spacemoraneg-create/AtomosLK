import re

CANONICAL_SCHOOLS = {
    "RC": "Royal College",
    "STC": "S. Thomas' College",
    "AC": "Ananda College",
    "TCK": "Trinity College Kandy",
    "LC": "Ladies' College",
    "BC": "Bishop's College",
    "VV": "Visakha Vidyalaya",
    "DS": "D. S. Senanayake College",
    "HFC": "Holy Family Convent",
    "SBC": "St. Bridget's Convent",
    "HCK": "Hillwood College Kandy",
    "SACK": "St. Anthony's College Kandy",
    "Moir": "Elizabeth Moir School",
    "EMS": "Elizabeth Moir School",
    "GCD": "Gateway College Dehiwala",
    "GCC": "Gateway College Colombo",
    "GCK": "Gateway College Kandy",
    "GCN": "Gateway College Negombo",
    "CIS": "Colombo International School",
    "AIS": "Asian International School",
    "SPC": "St. Peter's College",
    "SJC": "St. Joseph's College",
    "WC": "Wesley College",
    "TC": "Thurstan College",
    "NC": "Nalanda College",
    "MC": "Methodist College",
    "DRCK": "Dharmaraja College Kandy",
    "DBV": "Devi Balika Vidyalaya",
    "RISK": "Royal International School Kurunegala",
    "SJM": "Sujatha Vidyalaya Matara",
    "SCG": "Southlands College Galle",
    "SJCJ": "St. John's College Jaffna",
    "JLC": "Jaffna Ladies' College",
    "JHLC": "Jaffna Hindu Ladies' College",
    "Anula": "Anula Vidyalaya",
    "Hejaaz": "Hejaaz International School",
    "Daybridge": "Daybridge International School",
    "Maliyadeva": "Kurunegala Maliyadeva Balika Vidyalaya",
    "Logos": "Logos College",
    "Isipathana": "Isipathana College",
    "Hindu": "Hindu College",
}

def clean_school_name(raw_name: str) -> str:
    s = raw_name.replace('&#x27;', "'").replace('&amp;', '&').replace('’', "'").replace('`', "'").strip()
    # Normalize punctuation and extra spaces
    s = re.sub(r'\s*,\s*', ', ', s)
    s = re.sub(r'\s+', ' ', s)
    return s

def resolve_institution(code: str, full_name: str) -> tuple[str, str]:
    """
    Returns (canonical_code, canonical_name)
    """
    clean_code = code.strip()
    clean_name = clean_school_name(full_name)
    
    # Check if swing or bye
    if clean_code.upper() in ["SWING", "BYE"] or clean_name.upper() in ["SWING", "BYE"]:
        return "SWING", "Swing Team"
        
    # Check canonical code mapping
    if clean_code in CANONICAL_SCHOOLS:
        return clean_code, CANONICAL_SCHOOLS[clean_code]
        
    # Check if code without punctuation matches
    no_dot_code = clean_code.replace('.', '')
    if no_dot_code in CANONICAL_SCHOOLS:
        return no_dot_code, CANONICAL_SCHOOLS[no_dot_code]
        
    return clean_code, clean_name
