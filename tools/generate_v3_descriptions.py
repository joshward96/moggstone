"""
Generates V3 CSV with one simplified description per card.
- Old cartoon fantasy style, no Hearthstone reference
- Names included
- Simple plain-english: tall/short, wealthy/broke, attractive/ugly
- Skips rarity
- Animal vs person from thumbs column

Review the CSV, then run:  python generate_cards.py --csv-v3
"""

import csv
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

CSV_FILE = "Cards and Mechanics - Nuetrals.csv"
CSV_V3   = "Cards and Mechanics - Nuetrals V3.csv"

NO_TEXT = "A single character portrait painting with a plain background."

ANIMAL_KEYWORDS = {
    "fish": "fish", "frog": "frog", "bear": "bear", "turtle": "turtle",
    "tiger": "tiger", "rhino": "rhinoceros", "porcupine": "porcupine",
    "dragon": "dragon", "gecko": "gecko", "ghecko": "gecko",
    "cow": "cow", "snake": "snake", "wolf": "wolf", "panda": "panda",
}


def get_subject(card: dict) -> tuple[str, str]:
    thumbs = card.get("thumbs", card.get("Thumbs", "2")).strip()
    gender = card.get("Gender", "").strip().upper()
    name   = card.get("Name", "").lower()

    try:
        is_animal = int(thumbs) == 0
    except ValueError:
        is_animal = False

    if is_animal:
        creature = "creature"
        for keyword, animal in ANIMAL_KEYWORDS.items():
            if keyword in name:
                creature = animal
                break
        return "Animal", creature
    else:
        gender_word = "female" if gender == "F" else "male" if gender == "M" else "mysterious"
        return "Person", gender_word


def simple_height(height_str: str) -> str:
    s = height_str.lower().strip()
    total_inches = None

    m = re.match(r"(\d+)\s*ft\s*(\d+)", s)
    if m:
        total_inches = float(m.group(1)) * 12 + float(m.group(2))
    if total_inches is None:
        m = re.match(r"(\d+(?:\.\d+)?)\s*fo(?:ot|et)", s)
        if m: total_inches = float(m.group(1)) * 12
    if total_inches is None:
        m = re.match(r"(\d+(?:\.\d+)?)\s*ft", s)
        if m: total_inches = float(m.group(1)) * 12
    if total_inches is None:
        m = re.match(r"(\d+(?:\.\d+)?)\s*in", s)
        if m: total_inches = float(m.group(1))

    if total_inches is None:
        return ""
    if total_inches >= 72:   return "tall"
    if total_inches < 54:    return "short"
    return ""  # average — skip


def simple_looks(looks_str: str) -> str:
    try:
        score = int(looks_str.strip().split("/")[0])
    except (ValueError, IndexError):
        return ""
    if score >= 8:  return "attractive"
    if score <= 3:  return "ugly"
    return ""  # average — skip


def simple_fico(fico_str: str) -> str:
    try:
        score = int(fico_str.strip())
    except ValueError:
        return ""
    if score >= 750:  return "wealthy"
    if score < 580:   return "broke"
    return ""  # middle — skip


def ability_visual(abilities: str) -> str:
    a = abilities.lower()
    if "deathrattle" in a:                    return "ghostly aura"
    if "battle cry" in a or "battlecry" in a: return "glowing with energy"
    if "flash" in a:                           return "crackling with lightning"
    if "charge" in a:                          return "charging forward"
    if "shield wall" in a or "armored" in a:  return "heavily armored"
    if "frenzy" in a or "enrage" in a:        return "in a furious rage"
    if "counterstrike" in a:                   return "in a counter-attack stance"
    if "stealth" in a:                         return "cloaked in shadows"
    if "survivor" in a:                        return "battle-scarred but standing"
    if "zoo" in a:                             return "surrounded by wild animals"
    if "shadow realm" in a:                    return "wreathed in dark energy"
    if "blood" in a:                           return "in a wild frenzy"
    return ""


def build_descriptions(card: dict) -> tuple[str, str]:
    """Returns two distinct prompts (A and B) for the same card."""
    name         = card.get("Name", "Unknown").strip()
    card_type, subject = get_subject(card)
    abilities    = card.get("Abilities", "")

    height_desc  = simple_height(card.get("Height", ""))
    looks_desc   = simple_looks(card.get("Looks", ""))
    fico_desc    = simple_fico(card.get("Fico", ""))
    ability_desc = ability_visual(abilities)

    traits = [t for t in [height_desc, looks_desc, fico_desc, ability_desc] if t]
    traits_str = (", " + ", ".join(traits)) if traits else ""

    if card_type == "Animal":
        subject_phrase = f"a {subject}{traits_str}"
    else:
        subject_phrase = f"a {subject}{traits_str}"

    # A: close-up face/bust, flat solid color background, 90s Saturday morning cartoon style
    # Completely avoid card-game language — frame it as a cartoon show character sheet
    prompt_a = (
        f"1990s Saturday morning cartoon character. "
        f"Close-up bust portrait of {subject_phrase}, named {name}. "
        f"Flat solid color background. Thick outlines, bright colors, expressive face. "
        f"Character design sheet style. No text."
    )

    # B: full body, outdoors environment, children's fairy tale book illustration style
    prompt_b = (
        f"Children's fairy tale book illustration. "
        f"Full body painting of {subject_phrase}, named {name}, "
        f"standing in a dramatic outdoor scene with a detailed painted background. "
        f"Watercolor and ink style, loose brushwork, storybook lighting. No text."
    )

    return prompt_a, prompt_b


def main() -> None:
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        raw_rows = [
            row for row in reader
            if any(v.strip() for v in row.values()) and row.get("Name", "").strip()
        ]

    print(f"Found {len(raw_rows)} cards. Building V3 descriptions...\n")

    ORIGINAL_COLS = [
        "Name", "Cost", "Attack", "Health", "Rarity",
        "Height", "thumbs", "Gender", "Fico", "Looks",
        "Pasta", "Reading Level", "Abilities",
    ]
    out_rows = []
    for card in raw_rows:
        name = card.get("Name", "").strip()
        card_type, _ = get_subject(card)
        desc_a, desc_b = build_descriptions(card)
        print(f"  {name} ({card_type})")

        row = {col: card.get(col, "").strip() for col in ORIGINAL_COLS}
        row["Type"]          = card_type
        row["description_a"] = desc_a
        row["description_b"] = desc_b
        out_rows.append(row)

    out_cols = ORIGINAL_COLS + ["Type", "description_a", "description_b"]
    with open(CSV_V3, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_cols)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"\nDone! Review descriptions in:\n  {Path(CSV_V3).resolve()}")
    print("\nThen run:  python pick_cards.py -n 5 -o card_images_pick")


if __name__ == "__main__":
    main()
