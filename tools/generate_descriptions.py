"""
Generates a V2 CSV with text descriptions for each card image prompt.
Review and edit the descriptions in the CSV, then run generate_cards.py
which will use your edited descriptions automatically.
"""

import csv
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from generate_cards import (
    get_card_data,
    get_subject,
    build_description_v1,
    build_description_v2,
    build_description_v3,
    CSV_FILE,
    CSV_V2,
)

# Original columns to carry through
ORIGINAL_COLS = [
    "Name", "Cost", "Attack", "Health", "Rarity",
    "Height", "thumbs", "Gender", "Fico", "Looks",
    "Pasta", "Reading Level", "Abilities",
]

def main() -> None:
    # Read from original CSV always (not V2) so we regenerate cleanly
    print(f"Reading from: {CSV_FILE}")
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        import csv as _csv
        raw_rows = []
        reader = _csv.DictReader(f)
        for row in reader:
            if not any(v.strip() for v in row.values()):
                continue
            if not row.get("Name", "").strip():
                continue
            raw_rows.append(row)

    print(f"Found {len(raw_rows)} cards. Building descriptions...\n")

    output_rows = []
    for card in raw_rows:
        name = card.get("Name", "Unknown").strip()
        card_type, _ = get_subject(card)

        v1 = build_description_v1(card)
        v2 = build_description_v2(card)
        v3 = build_description_v3(card)

        print(f"  {name} ({card_type})")

        row = {}
        for col in ORIGINAL_COLS:
            row[col] = card.get(col, "").strip()
        row["Type"]           = card_type
        row["v1_description"] = v1
        row["v2_description"] = v2
        row["v3_description"] = v3
        output_rows.append(row)

    out_cols = ORIGINAL_COLS + ["Type", "v1_description", "v2_description", "v3_description"]
    out_path = Path(CSV_V2)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_cols)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"\nDone! Review and edit descriptions in:\n  {out_path.resolve()}")
    print("\nOnce happy, run:  python generate_cards.py")
    print("(It will automatically use your edited descriptions from the V2 file)")

if __name__ == "__main__":
    main()
