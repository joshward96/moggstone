"""
Deck building rules configuration.
Adjust these values to change how decks can be constructed.
"""
from cards.definitions import CLASS_POOLS, NEUTRAL_POOL

# Total number of cards required in a valid deck
DECK_SIZE: int = 20

# Maximum copies of any single card allowed in a deck
MAX_COPIES_PER_CARD: int = 2

# Valid card IDs for each class (class-specific pool + neutrals)
# Cards not in this list cannot be added to that class's deck.
VALID_CARDS_FOR_CLASS: dict[str, list[str]] = {
    class_name: list(CLASS_POOLS[class_name]) + list(NEUTRAL_POOL)
    for class_name in CLASS_POOLS
}
