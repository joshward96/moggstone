#!/usr/bin/env python3
"""
Deckbuilding game CLI entry point.

Usage:
    python game.py --player 1 --session abc123 --new   # Player 1 starts a new session
    python game.py --player 2 --session abc123          # Player 2 joins existing session
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
import random
import copy

from config import SESSION_DIR, POLL_INTERVAL_SECONDS, BOARD_SIZE
from models import GameState, Hero, Phase, CardType, TargetType, _card_from_dict
from actions import (
    Action, PlayCardAction, AttackAction, PassAction,
    serialize_actions, deserialize_actions,
)
from engine import GameEngine
from events import EventBus
from cards import get_starter_deck
from cards.definitions import build_player_deck, get_card
from deck_utils import decode_deck, validate_deck


# ---------------------------------------------------------------------------
# Session I/O helpers
# ---------------------------------------------------------------------------

def session_path(session_id: str, filename: str) -> str:
    return os.path.join(SESSION_DIR, session_id, filename)


def ensure_session_dir(session_id: str) -> None:
    os.makedirs(os.path.join(SESSION_DIR, session_id), exist_ok=True)


def write_json(path: str, data: dict | list) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def read_json(path: str) -> dict | list | None:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def load_state(session_id: str) -> GameState:
    data = read_json(session_path(session_id, "state.json"))
    if data is None:
        raise FileNotFoundError("No state.json found")
    state = GameState.from_dict(data)
    state.event_bus = EventBus()
    return state


def save_state(session_id: str, state: GameState) -> None:
    data = state.to_dict()
    write_json(session_path(session_id, "state.json"), data)


def load_hand(session_id: str, player_id: int) -> list:
    data = read_json(session_path(session_id, f"p{player_id + 1}_visible.json"))
    if data is None:
        return []
    return [_card_from_dict(c) for c in data]


def save_hand(session_id: str, player_id: int, hand: list) -> None:
    write_json(
        session_path(session_id, f"p{player_id + 1}_visible.json"),
        [c.to_dict() for c in hand],
    )


# ---------------------------------------------------------------------------
# New session initialization
# ---------------------------------------------------------------------------

def _build_deck_from_hash(hash_str: str) -> tuple[str, list]:
    """Decode a deck hash and return (class_name, list[Card]). Raises ValueError on invalid hash."""
    class_name, card_ids = decode_deck(hash_str)
    ok, msg = validate_deck(class_name, card_ids)
    if not ok:
        raise ValueError(msg)
    return class_name, [get_card(cid) for cid in card_ids]


def init_new_session(
    session_id: str,
    deck_hash_p1: str | None = None,
    deck_hash_p2: str | None = None,
) -> GameState:
    """Create a new session in LOBBY phase. Hands are not dealt until P2 joins."""
    ensure_session_dir(session_id)
    state = GameState()
    state.event_bus = EventBus()

    if deck_hash_p1:
        p1_class, deck1 = _build_deck_from_hash(deck_hash_p1)
    else:
        p1_class = "ice_witch"
        deck1 = build_player_deck(p1_class)

    if deck_hash_p2:
        p2_class, deck2 = _build_deck_from_hash(deck_hash_p2)
    else:
        p2_class = random.choice(["drum_wizard", "blood_witch"])
        deck2 = build_player_deck(p2_class)

    state.heroes = (
        Hero(name="Player 1", deck=deck1, hero_class=p1_class),
        Hero(name="Player 2", deck=deck2, hero_class=p2_class),
    )

    state.phase = Phase.LOBBY

    save_state(session_id, state)
    print(f"Session '{session_id}' created (waiting for Player 2).")
    return state


def finalize_session(session_id: str, state: GameState) -> None:
    """Deal opening hands and advance from LOBBY → MULLIGAN. Call when P2 joins."""
    state.event_bus = EventBus()
    engine = GameEngine(state)
    log = engine.deal_opening_hands()  # sets phase to MULLIGAN

    for i in range(2):
        save_hand(session_id, i, state.heroes[i].hand)

    save_state(session_id, state)
    print(f"Session '{session_id}' finalized. Mulligan begins.")
    for line in log:
        print(line)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def display_board(state: GameState, player_id: int, hand: list) -> None:
    hero = state.heroes[player_id]
    enemy = state.heroes[1 - player_id]

    print(f"\n{'=' * 50}")
    print(f"Turn {state.turn} | {hero.name} ({hero.hp} HP) | Mana: {hero.current_mana}/{hero.max_mana}")
    print(f"{'=' * 50}")

    print(f"\n-- Enemy: {enemy.name} ({enemy.hp} HP) --")
    print("Enemy board:")
    for i, slot in enumerate(enemy.board):
        if slot.is_occupied:
            buffs = f" [buffs: {len(slot.buffs)}]" if slot.buffs else ""
            print(f"  Slot {i}: {slot.creature.name} {slot.attack}/{slot.current_health}{buffs}")
        else:
            print(f"  Slot {i}: (empty)")

    print(f"\n-- Your board --")
    for i, slot in enumerate(hero.board):
        if slot.is_occupied:
            buffs = f" [buffs: {len(slot.buffs)}]" if slot.buffs else ""
            print(f"  Slot {i}: {slot.creature.name} {slot.attack}/{slot.current_health}{buffs}")
        else:
            print(f"  Slot {i}: (empty)")

    print(f"\n-- Your hand ({len(hand)} cards, {hero.current_mana} mana) --")
    for i, card in enumerate(hand):
        timing_tag = " [Prep]" if getattr(card, 'timing', 'stack') == 'prep' else ""
        if card.card_type == CardType.CREATURE:
            kws = []
            if card.riposte: kws.append("Riposte")
            if card.charge: kws.append("Charge")
            if card.enrage: kws.append(f"Enrage+{card.enrage}")
            if card.shield_wall: kws.append(f"ShieldWall {card.shield_wall}")
            kw_str = f" [{', '.join(kws)}]" if kws else ""
            print(f"  [{i}] {card.name} (cost {card.cost}){timing_tag} - {card.attack}/{card.max_health} creature{kw_str}")
        elif card.card_type == CardType.BUFF:
            bonuses = []
            if card.attack_bonus:
                bonuses.append(f"+{card.attack_bonus} ATK")
            if card.health_bonus:
                bonuses.append(f"+{card.health_bonus} HP")
            print(f"  [{i}] {card.name} (cost {card.cost}){timing_tag} - Buff: {', '.join(bonuses)}")
        else:
            desc = f" - {card.description}" if card.description else ""
            print(f"  [{i}] {card.name} (cost {card.cost}){timing_tag} - Spell{desc}")


# ---------------------------------------------------------------------------
# Prep phase input
# ---------------------------------------------------------------------------

def collect_prep_actions(state: GameState, player_id: int, hand: list) -> list[Action]:
    """Interactive loop to collect player's queued actions."""
    engine = GameEngine(state)
    hero = state.heroes[player_id]
    enemy = state.heroes[1 - player_id]

    actions: list[Action] = []
    simulated_mana = hero.current_mana

    print("\n-- Queue your actions (type 'done' when finished) --")
    print("Commands: play <hand_idx> [slot] [target_player(0=self,1=enemy)] [target_slot]")
    print("          attack <your_slot> <enemy_slot|-1_for_hero>")
    print("          done")

    while True:
        display_board(state, player_id, hand)
        print(f"\n[Queued {len(actions)} actions | Remaining mana: {simulated_mana}]")
        for i, a in enumerate(actions):
            print(f"  {i + 1}. {_describe_action(a, hand)}")

        try:
            raw = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not raw:
            continue

        parts = raw.lower().split()
        cmd = parts[0]

        if cmd in ("done", "pass", "end", "submit"):
            break

        elif cmd == "play":
            if len(parts) < 2:
                print("Usage: play <hand_idx> [slot] [target_player] [target_slot]")
                continue
            try:
                hand_idx = int(parts[1])
            except ValueError:
                print("Invalid index")
                continue
            if hand_idx < 0 or hand_idx >= len(hand):
                print(f"Invalid hand index (0-{len(hand) - 1})")
                continue

            card = hand[hand_idx]
            if card.cost > simulated_mana:
                print(f"Not enough mana (need {card.cost}, have {simulated_mana})")
                continue

            target_slot = None
            target_player = None

            if card.card_type == CardType.CREATURE:
                # Need a target slot
                free_slots = [i for i, s in enumerate(hero.board) if not s.is_occupied]
                if not free_slots:
                    print("No free board slots!")
                    continue
                if len(parts) >= 3:
                    try:
                        target_slot = int(parts[2])
                    except ValueError:
                        print("Invalid slot")
                        continue
                else:
                    print(f"Free slots: {free_slots}")
                    try:
                        target_slot = int(input("Choose slot: ").strip())
                    except (ValueError, EOFError):
                        continue
                if target_slot not in free_slots:
                    print(f"Slot {target_slot} not free")
                    continue

            elif card.card_type == CardType.BUFF:
                if len(parts) >= 3:
                    try:
                        target_slot = int(parts[2])
                    except ValueError:
                        print("Invalid slot")
                        continue
                else:
                    # Default: friendly creature
                    occ = [i for i, s in enumerate(hero.board) if s.is_occupied]
                    if not occ:
                        print("No friendly creatures to buff")
                        continue
                    print(f"Friendly occupied slots: {occ}")
                    try:
                        target_slot = int(input("Choose slot: ").strip())
                    except (ValueError, EOFError):
                        continue
                target_player = 0  # friendly by default

            elif card.card_type == CardType.SPELL:
                # Gather targeting info
                from models import TargetType
                tt = card.target_type
                if tt == TargetType.ENEMY_HERO:
                    target_player = 1
                    target_slot = None
                elif tt == TargetType.FRIENDLY_HERO:
                    target_player = 0
                    target_slot = None
                elif tt == TargetType.FRIENDLY_CREATURE:
                    occ = [i for i, s in enumerate(hero.board) if s.is_occupied]
                    if not occ:
                        print("No friendly creatures to target")
                        continue
                    print(f"Friendly occupied slots: {occ}")
                    try:
                        target_slot = int(input("Choose slot: ").strip())
                        target_player = 0
                    except (ValueError, EOFError):
                        continue
                elif tt == TargetType.ENEMY_CREATURE:
                    occ = [i for i, s in enumerate(enemy.board) if s.is_occupied]
                    if not occ:
                        print("No enemy creatures to target")
                        continue
                    print(f"Enemy occupied slots: {occ}")
                    try:
                        target_slot = int(input("Choose slot: ").strip())
                        target_player = 1
                    except (ValueError, EOFError):
                        continue
                else:  # ANY_TARGET
                    if len(parts) >= 3:
                        try:
                            target_player = int(parts[2])
                        except ValueError:
                            print("Invalid target_player (0=self, 1=enemy)")
                            continue
                    else:
                        try:
                            target_player = int(input("Target player (0=self, 1=enemy): ").strip())
                        except (ValueError, EOFError):
                            continue
                    if target_player not in (0, 1):
                        print("target_player must be 0 or 1")
                        continue
                    target_board = hero.board if target_player == 0 else enemy.board
                    occ = [i for i, s in enumerate(target_board) if s.is_occupied]
                    print(f"Occupied slots: {occ} (leave empty for hero)")
                    raw_slot = input("Choose slot (or Enter for hero): ").strip()
                    if raw_slot:
                        try:
                            target_slot = int(raw_slot)
                        except ValueError:
                            target_slot = None
                    else:
                        target_slot = None

            act = PlayCardAction(
                player_id=player_id,
                card_id=card.id,
                target_slot=target_slot,
                target_player=target_player,
            )
            actions.append(act)
            simulated_mana -= card.cost
            print(f"Queued: play {card.name}")

        elif cmd == "attack":
            if len(parts) < 3:
                print("Usage: attack <your_slot> <enemy_slot|-1>")
                continue
            try:
                att_slot = int(parts[1])
                tgt_slot = int(parts[2])
            except ValueError:
                print("Invalid slot numbers")
                continue

            if att_slot < 0 or att_slot >= BOARD_SIZE:
                print(f"Invalid attacker slot (0-{BOARD_SIZE - 1})")
                continue
            if not hero.board[att_slot].is_occupied:
                print(f"Slot {att_slot} has no creature")
                continue

            act = AttackAction(player_id=player_id, attacker_slot=att_slot, target_slot=tgt_slot)
            actions.append(act)
            print(f"Queued: attack with slot {att_slot}")

        else:
            print(f"Unknown command: {cmd}")

    actions.append(PassAction(player_id=player_id))
    return actions


def _describe_action(action: Action, hand: list) -> str:
    if isinstance(action, PlayCardAction):
        card_name = action.card_id
        for c in hand:
            if c.id == action.card_id:
                card_name = c.name
                break
        return f"Play {card_name}"
    elif isinstance(action, AttackAction):
        tgt = "hero" if action.target_slot == -1 else f"slot {action.target_slot}"
        return f"Attack {tgt} with slot {action.attacker_slot}"
    elif isinstance(action, PassAction):
        return "Pass"
    return str(action)


# ---------------------------------------------------------------------------
# Resolution and polling
# ---------------------------------------------------------------------------

def run_resolution(session_id: str, state: GameState) -> None:
    """Attempt to acquire the resolution lock, then resolve and print results."""
    lock_path = session_path(session_id, "resolving.lock")

    # Atomic lock acquire
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        # Other process is already resolving
        print("Other player is resolving... waiting for results.")
        _wait_for_next_turn(session_id, state.turn)
        return

    try:
        p1_data = read_json(session_path(session_id, "p1_actions.json"))
        p2_data = read_json(session_path(session_id, "p2_actions.json"))

        if p1_data is None or p2_data is None:
            print("Error: missing action files")
            return

        p1_actions = deserialize_actions(json.dumps(p1_data))
        p2_actions = deserialize_actions(json.dumps(p2_data))

        # Reload fresh state (may have been updated)
        state = load_state(session_id)
        # Restore hands into state for engine use
        for i in range(2):
            state.heroes[i].hand = load_hand(session_id, i)

        engine = GameEngine(state)

        log = engine.resolution_phase(p1_actions, p2_actions)
        game_over = any(h.hp <= 0 for h in state.heroes)
        if not game_over:
            log += engine.end_phase()
            log += engine.start_phase()

        print("\n" + "\n".join(log))

        # Save hands
        for i in range(2):
            save_hand(session_id, i, state.heroes[i].hand)

        save_state(session_id, state)

        # Save resolution log for the waiting player
        write_json(session_path(session_id, "resolution_log.json"), log)

        # Clean up action files
        for fname in ("p1_actions.json", "p2_actions.json"):
            try:
                os.remove(session_path(session_id, fname))
            except FileNotFoundError:
                pass

    finally:
        try:
            os.remove(lock_path)
        except FileNotFoundError:
            pass


def _wait_for_next_turn(session_id: str, current_turn: int) -> None:
    """Poll until state.json advances to the next turn, then print log."""
    print("Waiting for resolution...", end="", flush=True)
    timeout = 120
    elapsed = 0
    while elapsed < timeout:
        time.sleep(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS
        print(".", end="", flush=True)
        data = read_json(session_path(session_id, "state.json"))
        if data and data.get("turn", current_turn) > current_turn:
            print()
            log = read_json(session_path(session_id, "resolution_log.json"))
            if log:
                print("\n".join(log))
            return
    print("\nTimeout waiting for other player.")


def poll_for_opponent(session_id: str, player_id: int, my_actions_file: str) -> None:
    """Poll until the opponent has also submitted their actions."""
    opponent_id = 1 - player_id
    opp_file = session_path(session_id, f"p{opponent_id + 1}_actions.json")
    print(f"Waiting for Player {opponent_id + 1} to submit...", end="", flush=True)
    timeout = 300
    elapsed = 0
    while elapsed < timeout:
        time.sleep(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS
        print(".", end="", flush=True)
        if os.path.exists(opp_file):
            print(" ready!")
            return
    print("\nTimeout waiting for opponent.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Main game loop
# ---------------------------------------------------------------------------

def do_mulligan_cli(session_id: str, player_id: int) -> None:
    """Interactive mulligan: show opening hand, let player swap cards."""
    state = load_state(session_id)
    hand = load_hand(session_id, player_id)

    print(f"\n=== Mulligan — Player {player_id + 1} ===")
    print("Your opening hand:")
    for i, card in enumerate(hand):
        if card.card_type == CardType.CREATURE:
            print(f"  [{i}] {card.name} (cost {card.cost}) - {card.attack}/{card.max_health}")
        elif card.card_type == CardType.BUFF:
            print(f"  [{i}] {card.name} (cost {card.cost}) - Buff")
        else:
            desc = f": {card.description}" if card.description else ""
            print(f"  [{i}] {card.name} (cost {card.cost}) - Spell{desc}")

    print("\nEnter card indices to KEEP (space-separated), or press Enter to keep all:")
    try:
        raw = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        raw = ""

    if raw:
        try:
            keep_indices = [int(x) for x in raw.split()]
        except ValueError:
            keep_indices = list(range(len(hand)))
    else:
        keep_indices = list(range(len(hand)))

    state.heroes[player_id].hand = hand
    engine = GameEngine(state)
    log = engine.mulligan(player_id, keep_indices)
    for line in log:
        print(line)

    for i in range(2):
        save_hand(session_id, i, state.heroes[i].hand)
    save_state(session_id, state)

    if not all(state.mulligan_done):
        # Wait for opponent to mulligan
        print("Waiting for opponent to mulligan...", end="", flush=True)
        timeout = 300
        elapsed = 0
        while elapsed < timeout:
            time.sleep(POLL_INTERVAL_SECONDS)
            elapsed += POLL_INTERVAL_SECONDS
            print(".", end="", flush=True)
            current = load_state(session_id)
            if current.phase != Phase.MULLIGAN:
                print(" done!")
                log2 = read_json(session_path(session_id, "resolution_log.json"))
                if log2:
                    print("\n".join(log2))
                return
        print("\nTimeout.")


def play_turn(session_id: str, player_id: int) -> None:
    state = load_state(session_id)
    hand = load_hand(session_id, player_id)

    print(f"\n=== Turn {state.turn} — Player {player_id + 1} ===")
    display_board(state, player_id, hand)

    actions = collect_prep_actions(state, player_id, hand)

    # Write my actions
    my_file = session_path(session_id, f"p{player_id + 1}_actions.json")
    write_json(my_file, json.loads(serialize_actions(actions)))
    print(f"\nActions submitted ({len(actions)} total, including pass).")

    # Wait for opponent then resolve
    poll_for_opponent(session_id, player_id, my_file)
    run_resolution(session_id, state)


def main() -> None:
    parser = argparse.ArgumentParser(description="Deckbuilding game CLI")
    parser.add_argument("--player", type=int, required=True, choices=[1, 2], help="Player number (1 or 2)")
    parser.add_argument("--session", type=str, required=True, help="Session ID (shared between players)")
    parser.add_argument("--new", action="store_true", help="Start a new session (Player 1 only)")
    args = parser.parse_args()

    player_id = args.player - 1  # 0-indexed internally
    session_id = args.session

    ensure_session_dir(session_id)

    if args.new:
        if player_id != 0:
            print("Only Player 1 can start a new session with --new")
            sys.exit(1)
        state = init_new_session(session_id)
    else:
        state_path = session_path(session_id, "state.json")
        if not os.path.exists(state_path):
            print(f"No session '{session_id}' found. Player 1 must start with --new")
            sys.exit(1)

    print(f"\nWelcome, Player {args.player}! Session: {session_id}")

    # Handle mulligan phase before entering main loop
    state = load_state(session_id)
    if state.phase == Phase.MULLIGAN:
        do_mulligan_cli(session_id, player_id)

    while True:
        state = load_state(session_id)
        if state.phase == Phase.END:
            print("Game over!")
            break

        play_turn(session_id, player_id)

        # Check if game ended
        state = load_state(session_id)
        if state.phase == Phase.END:
            print("Game over! Check the resolution log for the winner.")
            break

        again = input("\nContinue to next turn? [Y/n]: ").strip().lower()
        if again in ("n", "no"):
            break


if __name__ == "__main__":
    main()
