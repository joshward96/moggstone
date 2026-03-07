import argparse
import csv
import os
import re
import time
import requests
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
CSV_FILE   = os.getenv("CSV_FILE", "Cards and Mechanics - Nuetrals.csv")
CSV_V2     = os.getenv("CSV_V2",   "Cards and Mechanics - Nuetrals V2.csv")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "card_images")

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# Suffix appended to every prompt to prevent DALL-E adding card text/stats
NO_TEXT = (
    "Pure illustration only. "
    "Absolutely no text, letters, numbers, words, or symbols anywhere in the image. "
    "No card frame, no card border, no mana cost, no attack stat, no health stat, "
    "no UI elements of any kind. Just the artwork."
)


# ── CSV readers ───────────────────────────────────────────────────────────────
def _parse_rows(reader) -> list[dict]:
    cards = []
    for row in reader:
        if not any(v.strip() for v in row.values()):
            continue
        if not row.get("Name", "").strip():
            continue
        cards.append(row)
    return cards


def get_card_data() -> list[dict]:
    """Load from V2 CSV if it exists (has user-edited descriptions), else original."""
    v2_path = Path(CSV_V2)
    if v2_path.exists():
        print(f"Using V2 descriptions from: {CSV_V2}")
        with open(v2_path, newline="", encoding="utf-8") as f:
            return _parse_rows(csv.DictReader(f))

    print(f"Reading cards from: {CSV_FILE}")
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        return _parse_rows(csv.DictReader(f))


# ── Subject detection (animal vs person) ─────────────────────────────────────
ANIMAL_KEYWORDS = {
    "fish": "fish", "frog": "frog", "bear": "bear", "turtle": "turtle",
    "tiger": "tiger", "rhino": "rhinoceros", "porcupine": "porcupine",
    "dragon": "dragon", "gecko": "gecko", "ghecko": "gecko",
    "cow": "cow", "snake": "snake", "wolf": "wolf", "hawk": "hawk",
    "eagle": "eagle", "elf": "elf", "dwarf": "dwarf",
}

def get_subject(card: dict) -> tuple[str, str]:
    """
    Returns (type, subject_phrase) where type is 'animal' or 'person'.
    Uses thumbs column: 0 = animal, 2+ = person.
    """
    thumbs = card.get("thumbs", card.get("Thumbs", "2")).strip()
    name   = card.get("Name", "").lower()
    gender = card.get("Gender", "").strip().upper()

    try:
        is_animal = int(thumbs) == 0
    except ValueError:
        is_animal = False

    if is_animal:
        # Try to identify creature type from card name
        creature = "creature"
        for keyword, animal_name in ANIMAL_KEYWORDS.items():
            if keyword in name:
                creature = animal_name
                break
        return "Animal", f"a fantasy {creature} creature,"
    else:
        # Person — use gender
        gender_phrase = (
            "female" if gender == "F"
            else "male" if gender == "M"
            else "mysterious"
        )
        return "Person", f"a {gender_phrase} humanoid character,"


# ── Prompt helpers ─────────────────────────────────────────────────────────────
def describe_looks(looks_str: str) -> str:
    try:
        score = int(looks_str.strip().split("/")[0])
    except (ValueError, IndexError):
        return "average looking"
    if score <= 2:   return "extremely ugly and homely"
    elif score <= 4: return "plain and unremarkable looking"
    elif score <= 6: return "average looking"
    elif score <= 8: return "attractive"
    else:            return "strikingly beautiful"


def describe_height(height_str: str) -> str:
    s = height_str.lower().strip()
    total_inches: float | None = None

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

    if total_inches is None:         return "average sized"
    if total_inches < 12:            return "tiny, barely a foot tall"
    elif total_inches < 36:          return "small, under three feet tall"
    elif total_inches < 60:          return "average height"
    elif total_inches < 84:          return "tall"
    elif total_inches < 120:         return "towering, giant in stature"
    else:                            return "colossal, impossibly huge"


def describe_fico(fico_str: str) -> str:
    try:
        score = int(fico_str.strip())
    except ValueError:
        return ""
    if score < 580:   return "visually destitute, wearing torn ragged clothes, desperate look"
    elif score < 670: return "working-class, modest slightly-worn clothing"
    elif score < 740: return "middle-class, clean decent appearance"
    elif score < 800: return "well-off, prosperous, fine clothing"
    else:             return "extremely wealthy, opulent, adorned with jewels and luxurious garments"


def describe_pasta(pasta_str: str) -> str:
    try:
        servings = float(pasta_str.strip())
    except ValueError:
        return ""
    if servings <= 1:   return "dainty, barely eats"
    elif servings <= 3: return "modest eater"
    elif servings <= 6: return "hearty appetite"
    elif servings <= 10: return "voracious, almost gluttonous"
    else:               return "legendary glutton, unstoppable eating machine"


def describe_reading_level(level_str: str) -> str:
    s = level_str.lower().strip()
    if any(x in s for x in ["pre", "kindergarten"]):   return "dim vacant expression, barely conscious"
    elif any(x in s for x in ["1st", "2nd", "3rd"]):   return "simple vacant expression"
    elif any(x in s for x in ["4th", "5th", "6th"]):   return "ordinary unremarkable expression"
    elif any(x in s for x in ["7th", "8th", "9th"]):   return "sharp alert expression"
    elif any(x in s for x in ["10th", "11th", "12th"]): return "clever knowing expression"
    elif any(x in s for x in ["college", "university"]): return "intellectual refined expression"
    elif any(x in s for x in ["grad", "phd", "doctor", "master"]): return "brilliant scholarly expression"
    else:                                               return ""


def describe_rarity(rarity: str) -> str:
    r = rarity.lower().strip()
    if "legendary" in r: return "golden radiant aura, legendary presence"
    if "secret" in r:    return "mysterious shimmering energy, rare and enigmatic"
    if "epic" in r:      return "swirling purple arcane energy"
    if "rare" in r:      return "soft blue magical glow"
    return "natural earthy lighting, common folk"


def ability_visual(abilities: str) -> str:
    a = abilities.lower()
    if "deathrattle" in a:                      return "ghostly spectral death-magic aura,"
    if "battle cry" in a or "battlecry" in a:   return "radiating a powerful energy burst,"
    if "flash" in a:                             return "surrounded by crackling lightning energy,"
    if "charge" in a:                            return "lunging forward in a fierce charging stance,"
    if "shield wall" in a or "armored" in a:    return "clad in heavy defensive armor,"
    if "frenzy" in a or "wild" in a:            return "in a wild frenzied state,"
    if "enrage" in a:                            return "in a furious raging state,"
    if "counterstrike" in a:                     return "poised in a sharp counter-attack stance,"
    if "stealth" in a:                           return "partially cloaked in shadows,"
    if "freeze" in a:                            return "emanating icy frost magic,"
    if "poison" in a:                            return "dripping with toxic venom,"
    if "survivor" in a:                          return "bearing battle scars, standing resilient,"
    if "zoo" in a:                               return "surrounded by exotic wild animals,"
    if "shadow realm" in a:                      return "wreathed in dark shadow energy,"
    return ""


# ── Prompt builders ───────────────────────────────────────────────────────────
def build_description_v1(card: dict) -> str:
    """Base art — subject type, looks, height, ability, rarity. No fico."""
    _, subject   = get_subject(card)
    abilities    = card.get("Abilities", "")
    looks        = card.get("Looks", "5/10")
    height       = card.get("Height", "")
    rarity       = card.get("Rarity", "Common")

    parts = [
        f"Hearthstone-style fantasy card illustration, painterly digital art,",
        subject,
        f"{describe_height(height)},",
        f"{describe_looks(looks)} appearance,",
        ability_visual(abilities),
        describe_rarity(rarity) + ",",
        "dramatic fantasy lighting.",
        NO_TEXT,
    ]
    return " ".join(p for p in parts if p.strip())


def build_description_v2(card: dict) -> str:
    """Base art + Fico wealth cues."""
    _, subject   = get_subject(card)
    abilities    = card.get("Abilities", "")
    looks        = card.get("Looks", "5/10")
    height       = card.get("Height", "")
    rarity       = card.get("Rarity", "Common")
    fico_desc    = describe_fico(card.get("Fico", ""))

    parts = [
        "Hearthstone-style fantasy card illustration, painterly digital art,",
        subject,
        f"{describe_height(height)},",
        f"{describe_looks(looks)} appearance,",
        ability_visual(abilities),
        f"{fico_desc}," if fico_desc else "",
        describe_rarity(rarity) + ",",
        "dramatic fantasy lighting.",
        NO_TEXT,
    ]
    return " ".join(p for p in parts if p.strip())


def build_description_v3(card: dict) -> str:
    """Full personality — Fico + pasta + reading level, cinematic upgraded style."""
    _, subject   = get_subject(card)
    abilities    = card.get("Abilities", "")
    looks        = card.get("Looks", "5/10")
    height       = card.get("Height", "")
    rarity       = card.get("Rarity", "Common")
    fico_desc    = describe_fico(card.get("Fico", ""))
    pasta_desc   = describe_pasta(card.get("Pasta", ""))
    reading_desc = describe_reading_level(card.get("Reading Level", ""))

    parts = [
        "Hearthstone-style fantasy card illustration, ultra-detailed painterly digital art,",
        "cinematic lighting, rich saturated colors,",
        subject,
        f"{describe_height(height)},",
        f"{describe_looks(looks)} appearance,",
        ability_visual(abilities),
        f"{fico_desc}," if fico_desc else "",
        f"{pasta_desc}," if pasta_desc else "",
        f"{reading_desc}," if reading_desc else "",
        describe_rarity(rarity) + ",",
        "dynamic pose.",
        NO_TEXT,
    ]
    return " ".join(p for p in parts if p.strip())


def get_prompts(card: dict) -> tuple[str, str, str]:
    """Return (v1, v2, v3) prompts — from V2 CSV descriptions if present, else built fresh."""
    v1 = card.get("v1_description", "").strip() or build_description_v1(card)
    v2 = card.get("v2_description", "").strip() or build_description_v2(card)
    v3 = card.get("v3_description", "").strip() or build_description_v3(card)
    return v1, v2, v3


# ── Image generation ──────────────────────────────────────────────────────────
def generate_and_save(prompt: str, output_path: Path, card_name: str = "") -> None:
    """Generate image, retrying with a sanitized prompt if content policy blocks."""
    prompts_to_try = [prompt]
    # Fallback: strip the card name if present
    if card_name:
        sanitized = re.sub(rf"\bnamed\s+['\"]?{re.escape(card_name)}['\"]?,?", "", prompt)
        if sanitized != prompt:
            prompts_to_try.append(sanitized)

    last_error = None
    for attempt, p in enumerate(prompts_to_try):
        try:
            response = client.images.generate(
                model="dall-e-3",
                prompt=p,
                size="1024x1024",
                quality="standard",
                n=1,
            )
            url = response.data[0].url
            output_path.write_bytes(requests.get(url, timeout=60).content)
            print(f"    Saved  : {output_path}")
            print(f"    Revised: {response.data[0].revised_prompt[:120]}...")
            return True
        except Exception as e:
            last_error = e
            if "content_policy_violation" in str(e) and attempt < len(prompts_to_try) - 1:
                print(f"    Content filter hit — retrying with sanitized prompt...")
                time.sleep(2)
            else:
                break

    if "content_policy_violation" in str(last_error):
        print(f"    Skipped — content filter blocked this card.")
        return False
    raise last_error


# ── Helpers ───────────────────────────────────────────────────────────────────
def safe_name(name: str) -> str:
    return re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Hearthstone-style card art")
    parser.add_argument(
        "-n", "--limit", type=int, default=None,
        help="Number of cards to process (default: all)"
    )
    parser.add_argument(
        "-v", "--versions", type=str, default="1,2,3",
        help="Comma-separated versions to generate: 1=base, 2=fico, 3=personality (default: 1,2,3)"
    )
    parser.add_argument(
        "-o", "--output", type=str, default=OUTPUT_DIR,
        help=f"Output folder for images (default: {OUTPUT_DIR})"
    )
    parser.add_argument(
        "--csv-v3", action="store_true",
        help="Use V3 CSV (single description column, one image per card)"
    )
    args = parser.parse_args()

    versions = sorted(int(v.strip()) for v in args.versions.split(",") if v.strip().isdigit())

    # ── V3 mode: single description column, one image per card ──────────────
    if args.csv_v3:
        v3_csv = "Cards and Mechanics - Nuetrals V3.csv"
        if not Path(v3_csv).exists():
            print(f"ERROR: {v3_csv} not found. Run generate_v3_descriptions.py first.")
            return

        with open(v3_csv, newline="", encoding="utf-8") as f:
            cards = [
                row for row in csv.DictReader(f)
                if row.get("Name", "").strip()
            ]

        if args.limit:
            cards = cards[:args.limit]

        out = Path(args.output)
        out.mkdir(exist_ok=True)
        total = len(cards)
        skipped = []
        print(f"V3 mode — generating {total} card(s) into ./{args.output}/\n")

        for i, card in enumerate(cards, 1):
            name    = card.get("Name", "Unknown").strip()
            prompt  = card.get("description", "").strip()
            card_type = card.get("Type", "")
            folder  = out / safe_name(name)
            folder.mkdir(exist_ok=True)
            path    = folder / f"{safe_name(name)}.png"

            print(f"Card [{i}/{total}]: {name} ({card_type})")
            if path.exists():
                print(f"  Already exists, skipping")
                continue
            result = generate_and_save(prompt, path, card_name=name)
            if result is False:
                skipped.append(name)
            time.sleep(3)
            print()

        print(f"Done! Images saved to ./{args.output}/")
        if skipped:
            print(f"Skipped (content filter): {', '.join(skipped)}")
        return

    # ── Standard mode ────────────────────────────────────────────────────────
    cards = get_card_data()
    if args.limit:
        cards = cards[:args.limit]

    total = len(cards)
    print(f"Generating {total} card(s), versions: {versions}\n")

    out = Path(args.output)
    out.mkdir(exist_ok=True)

    VERSION_DEFS = {
        1: ("v1 - base",        "_v1.png"),
        2: ("v2 - fico",        "_v2_fico.png"),
        3: ("v3 - personality", "_v3_personality.png"),
    }

    for i, card in enumerate(cards, 1):
        name = card.get("Name", "Unknown").strip()
        folder = out / safe_name(name)
        folder.mkdir(exist_ok=True)

        card_type, _ = get_subject(card)
        print(f"Card [{i}/{total}]: {name} ({card_type})")

        p1, p2, p3 = get_prompts(card)
        prompts = {1: p1, 2: p2, 3: p3}

        for ver in versions:
            label, suffix = VERSION_DEFS[ver]
            path = folder / f"{safe_name(name)}{suffix}"
            if path.exists():
                print(f"  [{label}] already exists, skipping")
                continue
            print(f"  [{label}]")
            generate_and_save(prompts[ver], path, card_name=name)
            time.sleep(3)

        print()

    print(f"Done! Images saved to ./{args.output}/")


if __name__ == "__main__":
    main()
