"""Wielojęzyczne etykiety z faktur Amazon VCS (PL/IT/FR/DE/ES/NL/SV/EN).

Wszystkie etykiety są małymi literami. Dopasowanie: linia (albo prawa kolumna
nagłówka) zaczyna się od etykiety; wybierana jest najdłuższa pasująca etykieta,
a wartość to reszta linii (lub następna linia, gdy reszta jest pusta).
"""
from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# miesiące (pełne nazwy + skróty angielskie z CSV)
# ---------------------------------------------------------------------------
MONTHS: dict[str, int] = {
    # pl
    "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4, "maja": 5, "czerwca": 6,
    "lipca": 7, "sierpnia": 8, "września": 9, "wrzesnia": 9, "października": 10,
    "pazdziernika": 10, "listopada": 11, "grudnia": 12,
    "styczeń": 1, "luty": 2, "marzec": 3, "kwiecień": 4, "maj": 5, "czerwiec": 6,
    "lipiec": 7, "sierpień": 8, "wrzesień": 9, "październik": 10, "listopad": 11, "grudzień": 12,
    # it
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
    # fr
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "décembre": 12, "decembre": 12,
    # de
    "januar": 1, "jänner": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "juni": 6,
    "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12,
    # es
    "enero": 1, "febrero": 2, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    # nl
    "januari": 1, "februari": 2, "maart": 3, "mei": 5, "augustus": 8, "december": 12,
    # sv
    "maj": 5, "augusti": 8,
    # en
    "january": 1, "february": 2, "march": 3, "may": 5, "june": 6, "july": 7,
    "october": 10,
    # skróty (CSV: 12-Aug-2026)
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
    "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    # skróty pl/de/it/fr
    "sty": 1, "lut": 2, "kwi": 4, "cze": 6, "lip": 7, "sie": 8, "wrz": 9, "paź": 10,
    "lis": 11, "gru": 12, "mrz": 3, "okt": 10, "dez": 12, "gen": 1, "mag": 5, "giu": 6,
    "lug": 7, "ago": 8, "set": 9, "ott": 10, "dic": 12, "janv": 1, "févr": 2, "avr": 4,
    "juil": 7, "déc": 12, "ene": 1, "abr": 4, "ago.": 8,
}

# ---------------------------------------------------------------------------
# etykiety pól (prawa kolumna nagłówka / sekcja zamówienia)
# ---------------------------------------------------------------------------
LABELS: dict[str, list[str]] = {
    "invoice_number": [
        "nr faktury", "numer faktury", "nr noty kredytowej", "numer noty kredytowej",
        "numer ricevuta", "numero ricevuta", "numero fattura", "numero della fattura",
        "numero nota di credito", "numero della nota di credito",
        "numéro de la facture", "numéro de facture", "n° de facture", "no de facture",
        "numéro de l'avoir", "numéro d'avoir",
        "rechnungsnummer", "rechnungs-nr", "rechnungs-nr.", "gutschriftsnummer", "gutschrift-nr",
        "número de factura", "número de la factura", "nº de factura", "n.º de factura",
        "número de nota de crédito", "número de la nota de crédito",
        "factuurnummer", "creditnotanummer", "creditfactuurnummer",
        "fakturanummer", "kreditnotanummer", "kreditfakturanummer", "kvittonummer",
        "invoice number", "invoice no", "invoice no.", "credit note number", "credit note no",
        "receipt number",
    ],
    "invoice_date": [
        "data faktury/data dostawy", "data faktury", "data wystawienia", "data noty kredytowej",
        "data ricevuta", "data fattura/data di consegna", "data fattura", "data della fattura",
        "data nota di credito", "data della nota di credito",
        "date de la facture/date de la livraison", "date de la facture", "date de facture",
        "date de l'avoir", "date d'avoir",
        "rechnungsdatum/lieferdatum", "rechnungsdatum", "gutschriftsdatum", "datum der gutschrift",
        "fecha de la factura/fecha de entrega", "fecha de la factura", "fecha de factura",
        "fecha de la nota de crédito", "fecha de nota de crédito",
        "factuurdatum/leverdatum", "factuurdatum", "creditnotadatum",
        "fakturadatum/leveransdatum", "fakturadatum", "kreditnotadatum", "kvittodatum",
        "invoice date/delivery date", "invoice date", "credit note date", "receipt date",
    ],
    "order_date": [
        "data zamówienia", "data ordine", "data dell'ordine", "date de la commande",
        "date de commande", "bestelldatum", "fecha del pedido", "fecha de pedido",
        "besteldatum", "orderdatum", "beställningsdatum", "order date",
    ],
    "order_number": [
        "nr zamówienia", "numer zamówienia", "numero ordine", "numero d'ordine",
        "numero dell'ordine", "contratto", "numéro de la commande", "numéro de commande",
        "n° de commande", "bestellnummer", "bestell-nr", "bestell-nr.", "número de pedido",
        "número del pedido", "nº de pedido", "bestelnummer", "ordernummer",
        "beställningsnummer", "order number", "order no", "order no.", "order id",
    ],
    "payment_reference": [
        "numer referencyjny płatności", "numero di riferimento del pagamento",
        "riferimento pagamento", "référence de paiement", "zahlungsreferenz",
        "referencia de pago", "referencia del pago", "betalingsreferentie",
        "betalningsreferens", "payment reference",
    ],
    "seller": [
        "sprzedawca", "venduto da", "vendu par", "verkauft von", "vendido por",
        "verkocht door", "säljs av", "såld av", "sold by",
    ],
    "vat_id": [
        "nip", "p. iva", "p.iva", "partita iva", "tva", "n° tva", "numéro de tva",
        "ust-idnr", "ust-idnr.", "ust-id", "ust-id-nr", "ust-id-nr.", "umsatzsteuer-id",
        "umsatzsteuer-identifikationsnummer", "steuernummer",
        "nif", "cif", "nif/cif", "nif-iva", "n.º de iva", "número de iva",
        "btw-nummer", "btw nummer", "btw-id", "btw-identificatienummer", "btw",
        "momsregistreringsnummer", "momsreg.nr", "momsreg. nr", "moms nr", "momsnummer",
        "vat number", "vat no", "vat no.", "vat reg. no", "vat registration number", "vat id",
        "dič", "dic", "ic dph",
    ],
    "total_to_pay": [
        "razem do zapłaty", "do zapłaty", "totale da pagare", "total à payer",
        "gesamtbetrag", "zu zahlender betrag", "zahlbetrag", "fälliger betrag",
        "total a pagar", "importe a pagar", "totaal te betalen", "te betalen",
        "totalt att betala", "att betala", "total to pay", "amount due", "total payable",
        "total due",
    ],
    "invoice_total": [
        "suma faktury", "razem faktura", "totale fattura", "totale ricevuta", "facture total",
        "total facture", "total de la facture", "rechnungsbetrag", "rechnungssumme",
        "gesamtsumme rechnung", "total factura", "total de la factura", "factuurtotaal",
        "totaal factuur", "fakturatotal", "fakturasumma", "totalt faktura", "invoice total",
        "receipt total",
    ],
    "shipping": [
        "koszty wysyłki", "koszt wysyłki", "koszty dostawy", "costi di spedizione",
        "spese di spedizione", "frais d'expédition", "frais de livraison", "frais de port",
        "versandkosten", "gastos de envío", "gastos de envio", "costes de envío",
        "verzendkosten", "fraktkostnad", "fraktkostnader", "frakt", "shipping charges",
        "shipping costs", "shipping cost", "delivery charges", "postage",
    ],
    "billing_address": [
        "adres rozliczeniowy", "adres do faktury", "indirizzo di fatturazione",
        "adresse de facturation", "rechnungsadresse", "rechnungsanschrift",
        "dirección de facturación", "factuuradres", "faktureringsadress", "fakturaadress",
        "billing address",
    ],
    "shipping_address": [
        "adres dostawy", "adres wysyłki", "indirizzo di spedizione", "indirizzo di consegna",
        "adresse de livraison", "adresse d'expédition", "lieferadresse", "versandadresse",
        "dirección de envío", "dirección de entrega", "verzendadres", "afleveradres",
        "leveransadress", "shipping address", "delivery address",
    ],
    "order_details": [
        "szczegóły zamówienia", "informazioni sull'ordine", "dettagli dell'ordine",
        "dettagli ordine", "informations de la commande", "détails de la commande",
        "bestelldetails", "bestellinformationen", "bestellangaben", "detalles del pedido",
        "información del pedido", "informacion del pedido", "bestelgegevens",
        "bestelinformatie", "orderinformation", "orderdetaljer", "order details",
        "order information",
    ],
    "items_header": [
        "szczegóły faktury", "dettagli ricevuta", "dettagli fattura", "dettagli della fattura",
        "détails de la facture", "rechnungsdetails", "rechnungspositionen",
        "detalles de la factura", "factuurgegevens", "factuurdetails", "fakturainformation",
        "fakturadetaljer", "fakturaspecifikation", "invoice details", "receipt details",
    ],
    "qty": [
        "ilość", "ilosc", "quant.", "quantità", "quantita", "qtà", "qté", "qte", "quantité",
        "menge", "anzahl", "cant.", "cantidad", "aantal", "antal", "qty", "quantity",
    ],
    "description": [
        "opis", "descrizione", "description", "beschreibung", "artikel", "descripción",
        "descripcion", "omschrijving", "beskrivning",
    ],
    "paid": [
        "zapłacono", "opłacono", "pagato", "payé", "paye", "bezahlt", "pagado", "betaald",
        "betald", "betalt", "paid",
    ],
    "vat_summary_header": [
        "stawka podatku", "aliquota iva", "aliquota", "taux tva", "taux de tva", "steuersatz",
        "mwst.-satz", "mwst-satz", "ust.-satz", "tipo de iva", "tipo iva", "btw-tarief",
        "btw tarief", "momssats", "vat rate", "tax rate",
    ],
    "summary_total": [
        "suma", "razem", "totale", "total", "gesamt", "gesamtsumme", "summe", "totaal",
        "summa", "totalt",
    ],
    "shipped_from": [
        "towary wysłane z", "merci spedite da", "marchandises expédiées depuis",
        "marchandises expédiées de", "waren versandt aus", "waren versendet aus",
        "versand aus", "mercancías enviadas desde", "productos enviados desde",
        "goederen verzonden vanuit", "goederen verzonden uit", "varor skickade från",
        "varor levererade från", "goods shipped from", "items shipped from",
    ],
    "exchange_rate": [
        "kurs wymiany", "kurs", "tasso di cambio", "taux de change", "wechselkurs",
        "umrechnungskurs", "tipo de cambio", "wisselkoers", "växelkurs", "exchange rate",
    ],
}

# tytuły dokumentów (prawy górny róg)
DOC_TITLES_INVOICE = [
    "faktura", "faktura vat", "fattura", "ricevuta d'acquisto", "ricevuta", "facture",
    "rechnung", "factura", "factuur", "invoice", "kvitto", "reçu", "recibo", "quittung",
    "tax invoice", "paragon",
]
DOC_TITLES_CREDIT = [
    "nota kredytowa", "faktura korygująca", "korekta faktury", "nota di credito",
    "avoir", "gutschrift", "stornorechnung", "nota de crédito", "factura rectificativa",
    "creditnota", "creditfactuur", "kreditnota", "kreditfaktura", "credit note",
    "credit memo", "kreditnote",
]

# język na podstawie tytułu / etykiet
LANG_HINTS = {
    "pl": ["faktura", "sprzedawca", "nr faktury", "zapłacono", "szczegóły"],
    "it": ["ricevuta", "fattura", "venduto da", "pagato", "dettagli"],
    "fr": ["facture", "vendu par", "payé", "détails", "commande"],
    "de": ["rechnung", "verkauft von", "bezahlt", "bestell"],
    "es": ["factura", "vendido por", "pagado", "pedido"],
    "nl": ["factuur", "verkocht door", "betaald", "bestel"],
    "sv": ["faktura", "säljs av", "betald", "beställning", "kvitto"],
    "en": ["invoice", "sold by", "paid", "order details"],
}

# nazwy krajów po polsku (na tytuł zakładki)
COUNTRY_PL = {
    "AT": "Austria", "BE": "Belgia", "BG": "Bułgaria", "HR": "Chorwacja", "CY": "Cypr",
    "CZ": "Czechy", "DK": "Dania", "EE": "Estonia", "FI": "Finlandia", "FR": "Francja",
    "DE": "Niemcy", "GR": "Grecja", "HU": "Węgry", "IE": "Irlandia", "IT": "Włochy",
    "LV": "Łotwa", "LT": "Litwa", "LU": "Luksemburg", "MT": "Malta", "NL": "Holandia",
    "PL": "Polska", "PT": "Portugalia", "RO": "Rumunia", "SK": "Słowacja", "SI": "Słowenia",
    "ES": "Hiszpania", "SE": "Szwecja", "GB": "Wielka Brytania", "UK": "Wielka Brytania",
    "CH": "Szwajcaria", "NO": "Norwegia", "US": "USA", "TR": "Turcja", "MC": "Monako",
    "LI": "Liechtenstein", "IS": "Islandia",
}

# nazwy jurysdykcji z CSV (Jurisdiction Name) -> kod ISO
JURISDICTION_TO_ISO = {
    "AUSTRIA": "AT", "BELGIUM": "BE", "BULGARIA": "BG", "CROATIA": "HR", "CYPRUS": "CY",
    "CZECH REPUBLIC": "CZ", "CZECHIA": "CZ", "DENMARK": "DK", "ESTONIA": "EE",
    "FINLAND": "FI", "FRANCE": "FR", "GERMANY": "DE", "GREECE": "GR", "HUNGARY": "HU",
    "IRELAND": "IE", "ITALY": "IT", "LATVIA": "LV", "LITHUANIA": "LT", "LUXEMBOURG": "LU",
    "MALTA": "MT", "NETHERLANDS": "NL", "POLAND": "PL", "PORTUGAL": "PT", "ROMANIA": "RO",
    "SLOVAKIA": "SK", "SLOVENIA": "SI", "SPAIN": "ES", "SWEDEN": "SE",
    "UNITED KINGDOM": "GB", "GREAT BRITAIN": "GB", "SWITZERLAND": "CH", "NORWAY": "NO",
    "MONACO": "MC", "TURKEY": "TR",
}

EU_COUNTRIES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE",
    "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE", "MC",
}

CURRENCY_SYMBOLS = {
    "zł": "PLN", "zl": "PLN", "pln": "PLN", "€": "EUR", "eur": "EUR", "£": "GBP",
    "gbp": "GBP", "kr": "SEK", "sek": "SEK", "kč": "CZK", "czk": "CZK", "chf": "CHF",
    "dkk": "DKK", "nok": "NOK", "$": "USD", "usd": "USD", "ft": "HUF", "huf": "HUF",
    "lei": "RON", "ron": "RON",
}

# boilerplate w opisie pozycji, do usunięcia
DESCRIPTION_NOISE = [
    "information indisponible sur les pièces détachées",
    "informations indisponibles sur les pièces détachées",
]

_BOILERPLATE_RE = re.compile(
    r"(www\.amazon\.[a-z.]+/contact-us|amazon\.[a-z.]+/kontakt|customer service|"
    r"service client|servizio clienti|kundenservice|atención al cliente|klantenservice|"
    r"kundtjänst|jeśli masz pytania|per domande|veuillez contacter|bei fragen|"
    r"si tiene preguntas|si tienes preguntas|als u vragen|om du har frågor|if you have questions|"
    r"strona \d+ z \d+|pagina \d+ di \d+|page \d+ de \d+|page \d+ of \d+|seite \d+ von \d+|"
    r"página \d+ de \d+|pagina \d+ van \d+|sida \d+ av \d+)",
    re.IGNORECASE,
)


def strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def norm(text: str) -> str:
    """Normalizacja do porównań etykiet: małe litery, bez akcentów, pojedyncze spacje."""
    text = strip_accents(text or "").lower().replace(" ", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


# etykiety znormalizowane, posortowane od najdłuższej (żeby 'data faktury/data dostawy'
# wygrało z 'data faktury')
NORM_LABELS: dict[str, list[str]] = {
    key: sorted({norm(v) for v in values}, key=len, reverse=True)
    for key, values in LABELS.items()
}


def match_label(text: str, key: str) -> str | None:
    """Jeśli `text` zaczyna się od którejś etykiety `key`, zwraca resztę (wartość).

    Zwraca None gdy brak dopasowania. Pusta reszta -> ''.
    """
    t = norm(text)
    for label in NORM_LABELS[key]:
        if t == label:
            return ""
        if t.startswith(label):
            rest = t[len(label):]
            # następny znak musi być separatorem (spacja, ':', '/', nawias) – żeby
            # 'nip' nie łapało 'nipx', ale 'nr faktury CZ...' tak
            if rest[0] in " :/-(.)":
                # zwracamy oryginalny (nieznormalizowany) fragment, żeby zachować
                # wielkość liter numerów/nazwisk
                orig_rest = _original_rest(text, len(label))
                return orig_rest.lstrip(" :/-").strip()
    return None


def _original_rest(text: str, norm_prefix_len: int) -> str:
    """Odcina prefix o długości `norm_prefix_len` liczonej na tekście znormalizowanym.

    Normalizacja nie zmienia liczby znaków poza zwijaniem białych znaków i
    usunięciem akcentów (1:1), więc wystarczy zliczyć znaki po zwinięciu spacji.
    """
    collapsed = re.sub(r"\s+", " ", (text or "").replace(" ", " ")).strip()
    return collapsed[norm_prefix_len:]


def is_boilerplate(text: str) -> bool:
    return bool(_BOILERPLATE_RE.search(text or ""))


def detect_language(full_text: str) -> str:
    t = norm(full_text)
    best, best_score = "unknown", 0
    for lang, hints in LANG_HINTS.items():
        score = sum(1 for h in hints if norm(h) in t)
        if score > best_score:
            best, best_score = lang, score
    return best
