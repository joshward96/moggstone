"""
Deck hash encoding/decoding and validation utilities.
"""
import base64
import json
from collections import Counter

from cards.definitions import CARD_CATALOG
from deckbuilding_config import DECK_SIZE, MAX_COPIES_PER_CARD, VALID_CARDS_FOR_CLASS


def encode_deck(class_name: str, card_ids: list[str]) -> str:
    """Encode a deck as a URL-safe base64 string."""
    data = {"c": class_name, "d": sorted(card_ids)}
    raw = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_deck(hash_str: str) -> tuple[str, list[str]]:
    """Decode a hash back to (class_name, card_ids). Raises ValueError on bad input."""
    # Restore base64 padding
    padding = (4 - len(hash_str) % 4) % 4
    padded = hash_str + "=" * padding
    try:
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        data = json.loads(raw)
        return data["c"], data["d"]
    except Exception as exc:
        raise ValueError(f"Invalid deck hash: {exc}") from exc


def validate_deck(class_name: str, card_ids: list[str]) -> tuple[bool, str]:
    """
    Validate a deck against deckbuilding_config rules.
    Returns (ok, error_message).
    """
    if class_name not in VALID_CARDS_FOR_CLASS:
        return False, f"Unknown class: '{class_name}'"

    if len(card_ids) != DECK_SIZE:
        return False, f"Deck must have exactly {DECK_SIZE} cards (has {len(card_ids)})"

    valid_pool = set(VALID_CARDS_FOR_CLASS[class_name])
    counts = Counter(card_ids)

    for cid, count in counts.items():
        if cid not in CARD_CATALOG:
            return False, f"Unknown card: '{cid}'"
        if cid not in valid_pool:
            return False, f"Card '{cid}' is not valid for {class_name}"
        if count > MAX_COPIES_PER_CARD:
            return False, (
                f"Max {MAX_COPIES_PER_CARD} copies of each card "
                f"('{cid}' has {count})"
            )

    return True, "ok"
