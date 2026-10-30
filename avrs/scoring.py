"""Conservative, split-independent answer scoring; no hidden answer is used at inference."""
import re
from decimal import Decimal, InvalidOperation


def _normalize(s):
    return " ".join(str(s).strip().lower().split()).rstrip(". ")


def _option_index(s):
    s = str(s).strip()
    # Only a standalone option marker, not an arbitrary digit from an explanation.
    m = re.fullmatch(r"(?:option\s*|choice\s*|answer\s*(?:is\s*)?)?([1-9])\.?", s, re.I)
    if m: return int(m.group(1))
    m = re.fullmatch(r"(?:option\s*|choice\s*|answer\s*(?:is\s*)?)?([A-I])\.?", s, re.I)
    if m: return ord(m.group(1).upper()) - ord("A") + 1
    return None


def _number(s):
    text = str(s).strip().replace(",", "")
    text = re.sub(r"^\s*(?:\$|₹)\s*", "", text)
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
        try: return Decimal(text)
        except InvalidOperation: return None
    if re.fullmatch(r"[+-]?\d+/[1-9]\d*", text):
        a, b = text.split("/")
        return Decimal(a) / Decimal(b)
    return None


def score(prediction, label, mode):
    if prediction is None or not str(prediction).strip():
        return {"correct": False, "scorable": True, "method": "missing_answer"}
    if label is None or str(label).strip() == "":
        return {"correct": None, "scorable": False, "method": "missing_label"}
    a, b = _normalize(prediction), _normalize(label)
    if mode == "hybrid":
        ai, bi = _option_index(a), _option_index(b)
        if bi is not None:
            if ai is None:
                return {"correct": False, "scorable": True, "method": "invalid_option"}
            return {"correct": ai == bi, "scorable": True, "method": "option_1_based"}
        # Refuse to assign a guessed index convention for non-option labels.
        return {"correct": a == b, "scorable": True, "method": "exact_hybrid_text"}
    if a == b:
        return {"correct": True, "scorable": True, "method": "exact"}
    an, bn = _number(a), _number(b)
    if an is not None and bn is not None:
        return {"correct": an == bn, "scorable": True, "method": "numeric"}
    return {"correct": False, "scorable": True, "method": "exact_text"}
