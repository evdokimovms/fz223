import re

from config import CFG

LATIN_STOP = {
    "ISO", "GSM", "HVAC", "LED", "USB", "LAN", "IP", "PDF", "DOC", "DOCX", "XLS", "XLSX",
    "SMS", "VAT", "UPS", "CAD", "BIM", "RAL", "DIN", "EN", "IEC", "UTP", "FTP", "PVC",
    "HDPE", "PPR", "PE", "PP", "AC", "DC", "TV", "PC", "CPU", "RAM", "SSD", "HDD",
    "IT", "GOST", "DN", "VRF", "VRV", "CFR", "FDA", "RFC", "IEEE", "ANSI", "ASTM",
    "API", "WHO", "EU", "EEC", "CE", "UL", "ETL", "GMP", "GLP", "GCP", "HIPAA",
    "SOC", "PCI", "DSS", "NIST", "FIPS", "OWASP", "ITIL", "COBIT",
}

STANDARD_RX = re.compile(
    r"\bFDA\b|"
    r"\b\d+\s*CFR\b|"
    r"CFR\s*Part\s*\d+|"
    r"\bISO\s*\d[\d\-.:]*|"
    r"\bIEC\s*\d[\d\-.:]*|"
    r"\bIEEE\s*\d[\d\-.:]*|"
    r"\bRFC\s*\d+|"
    r"\bANSI\s*[A-Z]?\d[\d\-.:]*|"
    r"\bASTM\s*[A-Z]?\d[\d\-.:]*|"
    r"\bГОСТ(?:\s*Р)?(?:\s*[А-ЯA-Z]?\s*[\d.\-]+)?|"
    r"\bСНиП\b|\bСП\s*\d|"
    r"\bТР\s*ТС\b|\bТР\s*ЕАЭС\b|"
    r"\bEN\s*\d[\d\-.:]*|"
    r"\bDIN\s*\d[\d\-.:]*|"
    r"\bNIST\b|\bFIPS\s*\d+|"
    r"\bPCI[\s\-]?DSS\b|\bHIPAA\b|\bSOX\b|"
    r"21\s*CFR|"
    r"Part\s*11\b",
    re.I,
)

LAW_RX = re.compile(
    r"\b\d{2,3}[\-\s]?ФЗ\b|"
    r"Федеральн\w+\s+закон|"
    r"постановлен\w+\s+Правительств|"
    r"\bN\s*\d{2,3}\-ФЗ",
    re.I,
)

TM_STRONG_RX = re.compile(r"товарн\w*\s+знак|торгов\w*\s+марк", re.I)
BAN_RX = re.compile(
    r"(?:аналог\w*|эквивалент\w*|иных\s+марок)[^.;\n]{0,60}(?:не\s+допуска\w+|запрещ\w+|не\s+принима\w+)"
    r"|(?:не\s+допуска\w+|запрещ\w+)[^.;\n]{0,60}(?:аналог\w*|эквивалент\w*)"
    r"|использовани\w*\s+иных\s+марок\s+не\s+допуска", re.I)
OR_EQUIV_RX = re.compile(
    r"(?:или|либо)\s+(?:эквивалент|аналог)\w*|(?:эквивалент|аналог)\w*\s+(?:допуска\w+|допустим\w+)", re.I)
FALSE_EQUIV_RX = re.compile(
    r"(?:или|либо)\s+(?:эквивалент|аналог)\w*[^.;\n]{0,120}?"
    r"(?:абсолютно\s+идентичн|полностью\s+соответств|до\s+миллиметр|точь[- ]в[- ]точь|тех\s+же\s+габарит)"
    r"|(?:абсолютно\s+идентичн|до\s+миллиметр)[^.;\n]{0,80}?(?:или|либо)\s+(?:эквивалент|аналог)", re.I)
EXISTING_RX = re.compile(
    r"существующ\w+|установленн\w+|эксплуатируем\w+|совместим\w+|ремонт\w*|запасн\w+\s+част\w+", re.I)
TU_RX = re.compile(r"\bТУ\b")
TU_NUM_RX = re.compile(r"\bТУ\s*(?:№\s*)?\d[\d\-\./]{4,}")
PLANT_RX = re.compile(r"завод\w*|изготовител\w+", re.I)
CHARS_RX = re.compile(
    r"характеристик|параметр\w*|мощност\w+|\d+[,.]?\d*\s*(?:мм|см|кг|кВт|Вт)(?!\w)|не\s+менее|не\s+более", re.I)
ORIGIN_BAN_RX = re.compile(
    r"только\s+(?:из|от|произвед|изготов)|исключительно\s+(?:из|произвед)|не\s+допуска\w+|иных?\s+стран", re.I)
ORIGIN_TABLE_RX = re.compile(
    r"(?:поз\.?|наименован\w*|ед\.?\s*изм|кол-?во).{0,60}?стран\w*\s+происхождени", re.I)
EXCL_STRONG_RX = re.compile(
    r"единственн\w+\s+(?:поставщик|производител|исполнител)\w*"
    r"|только\s+(?:от|у)\s+(?:производител|официальн|авторизован)\w*", re.I)
TERRITORY_EXP_RX = re.compile(
    r"(?i:опыт\w*)[^.;\n]{0,60}(?i:в\s+(?:г\.\s*)?(?:Москв|Санкт|регион|област|город|субъект)\w*)")
DEALER_RX = re.compile(r"(?i:официальн\w+|авторизованн\w+)\s+(?i:дилер\w*|дистрибьютор\w*|партн[её]р\w*)")
CERT_BRAND_RX = re.compile(
    r"(?i:сертификат\w*|авторизаци\w+|авторизованн\w*)[^.;\n]{0,80}?\b[A-Z][A-Za-z]{2,}\b")

REQUISITES_RX = re.compile(
    r"фирменн\w*\s+наименован|"
    r"организационно[- ]правов\w*\s+форм|"
    r"участник\w*\s+размещени\w*\s+заказ|"
    r"сведения\s+об\s+участник|"
    r"\bИНН\b|\bОГРН\b|\bКПП\b|\bОКОПФ\b|\bОКПО\b|\bОКВЭД\b|"
    r"свидетельство\s+о\s+регистрац|"
    r"юридическ\w*\s+адрес|почтовый\s+адрес|"
    r"место\s+нахождени\w*|адрес\s+местонахождени|"
    r"заполняется\s+участник|"
    r"руководитель\s+организац|подпись\s*м\.?\s*п",
    re.I,
)
TABLE_HEADER_TM_RX = re.compile(
    r"(?:товарный\s+знак|производитель|фирменн\w*\s+наименован).{0,40}?"
    r"(?:ед\.?\s*изм|кол-?во|цена|сумма|характеристик|наименован\w*\s+товар)"
    r"|(?:характеристик|наименован\w*\s+товар|функцион).{0,60}?"
    r"(?:товарный\s+знак|производитель)"
    r"|\|\s*(?:товарный\s+знак|производитель)\s*\|",
    re.I,
)
FORM_RX = re.compile(
    r"заполняется\s+участник|сведения\s+об\s+участник|"
    r"форма\s+\d|приложение\s*[№nN]?\s*\d|образец\s+заявк|анкета\s+участник",
    re.I,
)

PATTERNS = [
    ("brand",
     r"товарн\w*\s+знак|торгов\w*\s+марк|\bпатент\w*|\bмодел[ьи]\b|\bмарк[аи]\b"
     r"|\bпроизводител(?:ь|я|ю|ем|е|и|ей)\b",
     re.I),
    ("origin",
     r"(?i:стран\w*\s+(?:происхождени\w+|изготовлени\w+|производств\w+))"
     r"|(?i:произведен\w*|изготовлен\w*)\s+(?i:в|на)\s+[А-ЯЁ][а-яё]+",
     0),
    ("standards", r"\bГОСТ(?:\s*Р)?\b|\bТУ\b|\bISO\b|\bСП\s*\d|\bFDA\b|\bCFR\b|\bIEC\b", 0),
    ("exclusive",
     r"единственн\w+|исключительн\w+\s+(?:право|поставщик\w*)"
     r"|только\s+(?:от|у|производител\w+|поставщик\w+)",
     re.I),
    ("participants",
     r"опыт\w*\s+(?:работ\w+|выполнени\w+|поставк\w+)"
     r"|не\s+менее\s+\d+\s+(?:лет|год\w*|специалист\w*)"
     r"|лиценз\w+|\bСРО\b|в\s+штате|сертификат\w*|авторизаци\w*|\bдилер\w*",
     re.I),
]

REQUIRED_SECTIONS = {
    "предмет закупки": r"предмет\w*\s+(?:закупк|договор|контракт)",
    "характеристики предмета": r"характеристик",
    "срок поставки/выполнения": r"срок\w*|в\s+течени\w+|не\s+позднее",
    "место поставки/выполнения": r"мест\w+\s+(?:поставк|выполнени)|адрес\w*|по\s+адресу",
    "качество/гарантии": r"гаранти|качеств",
    "приёмка": r"прием?к|приёмк",
}

CATEGORY_LEGAL_QUERY = {
    "brand": "описание предмета закупки товарные знаки или эквивалент ограничение участников",
    "origin": "требования к стране происхождения товара ограничение участников",
    "standards": "документация о закупке стандарты ГОСТ ТУ ISO описание предмета",
    "exclusive": "необоснованное ограничение конкуренции равноправие",
    "participants": "требования к участникам закупки необоснованное ограничение конкуренции",
    "competition": "принципы закупки равноправие необоснованное ограничение конкуренции",
    "completeness": "документация о закупке характеристики предмета закупки",
}

TYPE_NAME = {
    "brand": "Товарный знак / производитель",
    "origin": "Страна происхождения",
    "standards": "ТУ / стандарты",
    "exclusive": "Единственный поставщик",
    "participants": "Требования к участникам",
    "competition": "Ограничение конкуренции",
    "completeness": "Полнота комплекта документации",
}

BLOCK_SKIP_FOR_BRAND = {"REQUISITES", "TABLE_HEADER", "FORM", "SIGNATURE"}


def find_brands(frag: str, limit: int = 4) -> list[str]:
    out = []
    cleaned = STANDARD_RX.sub(" ", frag)
    cleaned = LAW_RX.sub(" ", cleaned)
    for m in re.finditer(r"\b[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)?\b", cleaned):
        w = m.group(0)
        base = re.sub(r"[\d\-].*$", "", w).upper()
        if len(base) < 2 or base in LATIN_STOP or w in out:
            continue
        out.append(w)
    return out[:limit]


def classify_entities(frag: str) -> dict:
    standards = [m.group(0).strip() for m in STANDARD_RX.finditer(frag)]
    laws = [m.group(0).strip() for m in LAW_RX.finditer(frag)]
    brands = find_brands(frag)
    std_u, seen = [], set()
    for s in standards:
        k = s.lower()
        if k not in seen:
            seen.add(k)
            std_u.append(s)
    return {
        "standards": std_u[:5],
        "laws": laws[:3],
        "brands": brands,
        "has_standard": bool(std_u),
        "has_law": bool(laws),
        "has_brand": bool(brands),
    }


def classify_block(frag: str) -> str:
    if FORM_RX.search(frag) or REQUISITES_RX.search(frag):
        if find_brands(frag):
            return "TECHNICAL_REQUIREMENT"
        if REQUISITES_RX.search(frag) and not TM_STRONG_RX.search(frag):
            return "REQUISITES"
        if FORM_RX.search(frag):
            return "FORM"
    if TABLE_HEADER_TM_RX.search(frag) and not find_brands(frag) and not BAN_RX.search(frag):
        return "TABLE_HEADER"
    if re.search(r"руководитель\s+организац|подпись|м\.?\s*п\.?", frag, re.I) and len(frag) < 400:
        return "SIGNATURE"
    return "TEXT"


def extract_signals(frag: str, category: str) -> dict:
    block_type = classify_block(frag)
    ents = classify_entities(frag)
    brands = ents["brands"]
    ban = bool(BAN_RX.search(frag))
    eq = bool(OR_EQUIV_RX.search(frag))
    false_eq = bool(FALSE_EQUIV_RX.search(frag))
    tm_hit = bool(TM_STRONG_RX.search(frag))

    if block_type in BLOCK_SKIP_FOR_BRAND:
        brand_detected = bool(brands)
    else:
        brand_detected = bool(brands) or (tm_hit and not ents["has_standard"])

    if ents["has_standard"] and not brands and not ban:
        brand_detected = False

    skip_brand = (
        block_type in BLOCK_SKIP_FOR_BRAND
        or (ents["has_standard"] and not brands and category == "brand")
        or (ents["has_law"] and not brands and category == "brand")
    )

    return {
        "block_type": block_type,
        "entity_types": {
            "brands": brands,
            "standards": ents["standards"],
            "laws": ents["laws"],
        },
        "brand_detected": brand_detected,
        "brands": brands,
        "standard_detected": ents["has_standard"],
        "standards_found": ents["standards"],
        "law_detected": ents["has_law"],
        "declare_trademark_only": False,
        "analogs_banned": ban,
        "equivalent_allowed": eq and not ban and not false_eq,
        "false_equivalent": false_eq,
        "existing_context": bool(EXISTING_RX.search(frag)),
        "tu_plant": bool(TU_NUM_RX.search(frag) or (TU_RX.search(frag) and PLANT_RX.search(frag))),
        "no_characteristics": not bool(CHARS_RX.search(frag)),
        "no_equivalent": not eq,
        "origin_requirement": category == "origin" or bool(re.search(r"стран\w*\s+происхождени", frag, re.I)),
        "origin_ban": bool(ORIGIN_BAN_RX.search(frag)),
        "origin_table_only": bool(ORIGIN_TABLE_RX.search(frag)) and not bool(ORIGIN_BAN_RX.search(frag)),
        "exclusive_phrase": bool(EXCL_STRONG_RX.search(frag)),
        "territorial_experience": bool(TERRITORY_EXP_RX.search(frag)),
        "manufacturer_cert": bool(CERT_BRAND_RX.search(frag)) and bool(brands),
        "official_dealer": bool(DEALER_RX.search(frag)),
        "needs_internal_check": category in ("brand", "exclusive", "participants") and not skip_brand,
        "skip_rules": skip_brand and category == "brand",
    }


def find_candidates(text: str, ctx: int = 280) -> list[dict]:
    cands = []
    for cat, rx, flags in PATTERNS:
        last_end, n = -1, 0
        for m in re.finditer(rx, text, flags):
            if m.start() < last_end:
                continue
            s, e = max(0, m.start() - ctx), min(len(text), m.end() + ctx)
            frag = text[s:e].strip()
            signals = extract_signals(frag, cat)
            if signals.get("skip_rules"):
                last_end = e
                continue
            cands.append({
                "category": cat,
                "match": m.group(0),
                "fragment": frag,
                "signals": signals,
            })
            last_end = e
            n += 1
            if n >= CFG.max_candidates_per_category:
                break
    return cands


def missing_sections(text: str) -> list[str]:
    return [name for name, rx in REQUIRED_SECTIONS.items() if not re.search(rx, text, re.I)]
