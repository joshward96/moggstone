"""
Generates two images per card (A and B), saves a side-by-side comparison,
lets user pick A or B interactively, then outputs:
  - <output>/CardName/CardName_A.png
  - <output>/CardName/CardName_B.png
  - <output>/CardName/CardName_compare.png   (A | B side by side)
  - selected/                                (copies of chosen images)
  - selected_cards.csv                       (full card data + Card Image file name)
"""

import argparse
import csv
import os
import re
import shutil
import time
import requests
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

load_dotenv()

CSV_V3     = "Cards and Mechanics - Nuetrals V3.csv"
SELECTED   = Path("selected")
OUTPUT_CSV = "selected_cards.csv"

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


# ── Helpers ───────────────────────────────────────────────────────────────────
def safe_name(name: str) -> str:
    return re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")


def load_cards(limit: int | None) -> list[dict]:
    if not Path(CSV_V3).exists():
        raise FileNotFoundError(f"{CSV_V3} not found. Run generate_v3_descriptions.py first.")
    with open(CSV_V3, newline="", encoding="utf-8") as f:
        cards = [r for r in csv.DictReader(f) if r.get("Name", "").strip()]
    return cards[:limit] if limit else cards


# ── Image generation ──────────────────────────────────────────────────────────
def generate_image(prompt: str, output_path: Path, card_name: str) -> bool:
    """Returns True on success, False if content-filtered (skips gracefully)."""
    prompts_to_try = [prompt]
    sanitized = re.sub(rf"\b{re.escape(card_name)}\b", "", prompt).strip()
    if sanitized != prompt:
        prompts_to_try.append(sanitized)

    for attempt, p in enumerate(prompts_to_try):
        try:
            response = client.images.generate(
                model="dall-e-3", prompt=p, size="1024x1024", quality="standard", n=1
            )
            output_path.write_bytes(requests.get(response.data[0].url, timeout=60).content)
            return True
        except Exception as e:
            if "content_policy_violation" in str(e) and attempt < len(prompts_to_try) - 1:
                print(f"    Content filter — retrying without name...")
                time.sleep(2)
            elif "content_policy_violation" in str(e):
                print(f"    Skipped — content filter.")
                return False
            else:
                raise
    return False


def make_comparison(path_a: Path, path_b: Path, out_path: Path) -> None:
    """Stitch A and B side by side with labels."""
    img_a = Image.open(path_a).convert("RGB")
    img_b = Image.open(path_b).convert("RGB")

    w, h = img_a.size
    combined = Image.new("RGB", (w * 2 + 20, h + 60), (30, 30, 30))
    combined.paste(img_a, (0, 60))
    combined.paste(img_b, (w + 20, 60))

    # Draw labels using a simple pixel approach (no font needed)
    from PIL import ImageDraw
    draw = ImageDraw.Draw(combined)
    draw.rectangle([0, 0, w, 59], fill=(50, 50, 50))
    draw.rectangle([w + 20, 0, w * 2 + 20, 59], fill=(50, 50, 50))
    draw.text((w // 2 - 10, 15), "A", fill=(255, 220, 50), font_size=36)
    draw.text((w + 20 + w // 2 - 10, 15), "B", fill=(255, 220, 50), font_size=36)

    combined.save(out_path)


# ── Picker UI ─────────────────────────────────────────────────────────────────
def ask_choice(name: str, path_a: Path, path_b: Path, compare_path: Path) -> str | None:
    """Returns 'A', 'B', or None (skipped)."""
    import subprocess
    try:
        subprocess.Popen(["explorer.exe", str(compare_path.resolve())])
    except Exception:
        win_path = "\\\\wsl$\\Ubuntu" + str(compare_path.resolve()).replace("/", "\\")
        print(f"  Open manually: {win_path}")

    while True:
        choice = input(f"  [{name}] Pick A, B, or S to skip: ").strip().upper()
        if choice in ("A", "B", "S"):
            return None if choice == "S" else choice
        print("  Please enter A, B, or S.")


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Generate A/B card images and pick favorites")
    parser.add_argument("-n", "--limit", type=int, default=None, help="Number of cards to process")
    parser.add_argument("-o", "--output", type=str, default="card_images_pick", help="Output folder")
    args = parser.parse_args()

    cards = load_cards(args.limit)
    total = len(cards)
    out   = Path(args.output)
    out.mkdir(exist_ok=True)
    SELECTED.mkdir(exist_ok=True)

    selections = []  # list of (card_dict, chosen_file_name)
    skipped    = []

    print(f"Generating {total} card(s) with A/B options...\n")

    for i, card in enumerate(cards, 1):
        name   = card.get("Name", "Unknown").strip()
        sname  = safe_name(name)
        folder = out / sname
        folder.mkdir(exist_ok=True)

        # Skip if already picked (either A or B exists in selected/)
        already_picked = (SELECTED / f"{sname}_A.png").exists() or \
                         (SELECTED / f"{sname}_B.png").exists()
        if already_picked:
            print(f"Card [{i}/{total}]: {name} — already picked, skipping")
            continue

        prompt_a = card.get("description_a", "").strip()
        prompt_b = card.get("description_b", "").strip()
        path_a   = folder / f"{sname}_A.png"
        path_b   = folder / f"{sname}_B.png"
        compare  = folder / f"{sname}_compare.png"

        print(f"Card [{i}/{total}]: {name}")

        # Generate A
        if not path_a.exists():
            print(f"  Generating A...")
            ok = generate_image(prompt_a, path_a, name)
            if not ok:
                skipped.append(name)
                continue
            time.sleep(3)

        # Generate B
        if not path_b.exists():
            print(f"  Generating B...")
            ok = generate_image(prompt_b, path_b, name)
            if not ok:
                skipped.append(name)
                continue
            time.sleep(3)

        # Side-by-side comparison
        if not compare.exists():
            make_comparison(path_a, path_b, compare)

        # User picks
        choice = ask_choice(name, path_a, path_b, compare)
        if choice is None:
            print(f"  Skipped.")
            skipped.append(name)
            continue

        chosen_path = path_a if choice == "A" else path_b
        chosen_filename = f"{sname}_{choice}.png"
        shutil.copy(chosen_path, SELECTED / chosen_filename)
        print(f"  Saved {choice} → selected/{chosen_filename}")
        selections.append((card, chosen_filename))

    # Write selected_cards.csv
    if selections:
        ORIGINAL_COLS = [
            "Name", "Cost", "Attack", "Health", "Rarity",
            "Height", "thumbs", "Gender", "Fico", "Looks",
            "Pasta", "Reading Level", "Abilities",
        ]
        out_cols = ORIGINAL_COLS + ["Card Image file name"]
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=out_cols)
            writer.writeheader()
            for card, filename in selections:
                row = {col: card.get(col, "").strip() for col in ORIGINAL_COLS}
                row["Card Image file name"] = filename
                writer.writerow(row)
        print(f"\nSelected cards saved to: {OUTPUT_CSV}")
        print(f"Images saved to:          selected/")

    if skipped:
        print(f"Skipped: {', '.join(skipped)}")

    print("\nDone!")


if __name__ == "__main__":
    main()
