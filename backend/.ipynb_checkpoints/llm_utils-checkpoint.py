import json
import logging
import re

log = logging.getLogger("llm")


def ask_json(llm, prompt: str, retries: int = 2):
    if llm is None:
        return None
    for _ in range(retries + 1):
        try:
            raw = llm.invoke(prompt).content
        except Exception as e:  # Ollama недоступна → работаем без LLM
            log.warning("LLM call failed: %r", e)
            return None
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", raw, re.S)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
    return None


def is_grounded(text: str, fragment: str, extra: str = "") -> bool:
    allowed_tokens = set(re.findall(r"[a-zа-яё0-9]+", f"{fragment} {extra}".lower()))
    allowed = {"223", "135", "фз"}
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9\-]*|\d+", text):
        if tok.lower() not in allowed_tokens and tok.lower() not in allowed:
            return False
    return True
