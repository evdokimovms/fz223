from llm_utils import ask_json

ROLES = {
    "participant": "требования к участнику закупки, составу заявки, квалификации и опыту",
    "product_spec": "описание и характеристики предмета закупки (товара, работ, услуг), стандарты на него",
    "deliverables": "результаты работ, сдаваемые документы, приёмка, комплектность поставки",
    "schedule": "сроки, этапы, место исполнения",
    "price_payment": "цена, оплата, обеспечение, штрафы и неустойки",
    "warranty": "гарантийные обязательства и качество",
    "contract_terms": "прочие условия исполнения договора (субподряд, ответственность, взаимодействие сторон)",
    "references": "перечень нормативных документов и ссылок",
    "procedure": "порядок проведения закупки, извещение, подача заявок",
    "other": "не подходит ни одна роль, заголовок или служебный текст",
}
ROLE_KEYS = tuple(ROLES)
ROLES_HELP = "; ".join(f"{k} — {v}" for k, v in ROLES.items())

PROMPT = (
    "Определи РОЛЬ каждого пункта технического задания на закупку, то есть о чём он по смыслу.\n"
    "Роли: <<ROLES>>.\n"
    "Учитывай раздел, в котором стоит пункт: он задаёт контекст. "
    "Если ни одна роль не подходит или пункт — заголовок/служебный текст, ставь other.\n\n"
    "Пункты:\n<<ITEMS>>\n\n"
    'JSON: {"roles":[{"id":номер,"role":"одна из ролей"}]}'
)


def _item(c) -> str:
    sec = f"[раздел: {c.section[:70]}] " if getattr(c, "section", "") else ""
    hdr = f"[столбцы таблицы: {c.table_header[:100]}] " if getattr(c, "table_header", "") else ""
    return f"{c.idx}. {sec}{hdr}{c.text[:300]}"


def classify_roles(llm, clauses: list, batch: int = 20) -> dict[int, str]:
    out = {c.idx: "other" for c in clauses}
    if llm is None or not clauses:
        return out
    for i in range(0, len(clauses), batch):
        chunk = clauses[i:i + batch]
        data = ask_json(llm, PROMPT.replace("<<ROLES>>", ROLES_HELP)
                        .replace("<<ITEMS>>", "\n".join(_item(c) for c in chunk))) or {}
        for r in data.get("roles") or []:
            if not isinstance(r, dict):
                continue
            try:
                idx = int(r.get("id"))
            except (TypeError, ValueError):
                continue
            role = str(r.get("role") or "").strip().lower()
            if idx in out and role in ROLES:
                out[idx] = role
    return out


def applicable(role: str, applies_to) -> bool:
    at = {str(x).strip().lower() for x in (applies_to or [])} or {"any"}
    return "any" in at or role == "other" or role not in ROLES or role in at
