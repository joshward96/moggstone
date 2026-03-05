#!/usr/bin/env python3
"""
Flask web server for the deckbuilding game.
Serves the single-page UI and provides a JSON API.
"""
from __future__ import annotations
import json
import os
import random
import string
import sys

# Ensure the deckgame directory is in the path when run directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, request, render_template, abort

from game import (
    session_path, ensure_session_dir, write_json, read_json,
    load_state, save_state, load_hand, save_hand, init_new_session,
    finalize_session, _build_deck_from_hash,
)
from actions import PassAction, MulliganAction, HeroPowerAction, deserialize_actions
from cards.definitions import HERO_POWERS, CARD_CATALOG, CLASS_POOLS, NEUTRAL_POOL
from deck_utils import decode_deck, validate_deck
from deckbuilding_config import DECK_SIZE, MAX_COPIES_PER_CARD
from events import EventBus
from engine import GameEngine
from models import Phase

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _random_session_id(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


_HIDDEN_CREATURE_ATTRS = ("looks", "fico", "height_cm", "reading_level", "social_credit", "noodles", "thumbs")


def _strip_hidden(d: dict) -> dict:
    """Remove server-only creature attributes before sending to client."""
    for attr in _HIDDEN_CREATURE_ATTRS:
        d.pop(attr, None)
    return d


def _strip_slot(slot_dict: dict) -> dict:
    """Strip hidden attrs from a board slot dict."""
    if slot_dict.get("creature"):
        _strip_hidden(slot_dict["creature"])
    return slot_dict


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/session", methods=["POST"])
def create_or_join_session():
    data = request.get_json(force=True)
    player_id = int(data.get("player_id", 1))  # 1-indexed from client
    session_id = data.get("session_id") or _random_session_id()
    deck_hash = data.get("deck_hash") or None

    if player_id == 1:
        # Player 1 creates a fresh session in LOBBY phase
        try:
            init_new_session(session_id, deck_hash_p1=deck_hash)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
    else:
        # Player 2 joins — verify session exists
        state_file = session_path(session_id, "state.json")
        if not os.path.exists(state_file):
            return jsonify({"ok": False, "error": f"Session '{session_id}' not found"}), 404

        try:
            state = load_state(session_id)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

        # If still in LOBBY, finalize: optionally update P2 deck then deal hands
        if state.phase == Phase.LOBBY:
            if deck_hash:
                try:
                    p2_class, deck2 = _build_deck_from_hash(deck_hash)
                    state.heroes[1].hero_class = p2_class
                    state.heroes[1].deck = deck2
                except ValueError as e:
                    return jsonify({"ok": False, "error": str(e)}), 400
            finalize_session(session_id, state)

    return jsonify({"ok": True, "session_id": session_id})


@app.route("/api/state/<session_id>/<int:player_id>")
def get_state(session_id: str, player_id: int):
    """player_id is 0-indexed."""
    state_file = session_path(session_id, "state.json")
    if not os.path.exists(state_file):
        abort(404)

    try:
        state = load_state(session_id)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    hand = load_hand(session_id, player_id)

    submitted = os.path.exists(session_path(session_id, f"p{player_id + 1}_actions.json"))
    opponent_submitted = os.path.exists(session_path(session_id, f"p{2 - player_id}_actions.json"))
    both_submitted = submitted and opponent_submitted

    resolution_log = read_json(session_path(session_id, "resolution_log.json"))

    # Build hero dicts with board info — hide opponent hand, strip hidden creature attrs
    heroes = []
    for i, hero in enumerate(state.heroes):
        hero_dict = {
            "name": hero.name,
            "hp": hero.hp,
            "max_mana": hero.max_mana,
            "current_mana": hero.current_mana,
            "deck_count": len(hero.deck),
            "hand_count": len(hero.hand),
            "board": [_strip_slot(slot.to_dict()) for slot in hero.board],
            "hero_class": getattr(hero, "hero_class", ""),
        }
        heroes.append(hero_dict)

    mulligan_done = list(getattr(state, 'mulligan_done', (False, False)))
    hero_power_used = list(getattr(state, 'hero_power_used', (False, False)))

    return jsonify({
        "turn": state.turn,
        "phase": state.phase.value,
        "heroes": heroes,
        "hand": [_strip_hidden(c.to_dict()) for c in hand],
        "submitted": submitted,
        "both_submitted": both_submitted,
        "resolution_log": resolution_log,
        "mulligan_done": mulligan_done,
        "first_player": getattr(state, 'first_player', 0),
        "hero_power_used": hero_power_used,
        "hero_powers": HERO_POWERS,
    })


@app.route("/api/actions/<session_id>/<int:player_id>", methods=["POST"])
def submit_actions(session_id: str, player_id: int):
    """player_id is 0-indexed."""
    state_file = session_path(session_id, "state.json")
    if not os.path.exists(state_file):
        abort(404)

    try:
        state = load_state(session_id)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    if state.phase != Phase.PREP:
        return jsonify({"ok": False, "error": f"Not in PREP phase (current: {state.phase.value})"}), 400

    action_dicts = request.get_json(force=True)
    if not isinstance(action_dicts, list):
        return jsonify({"ok": False, "error": "Expected a JSON array of actions"}), 400

    # Append PassAction so the engine always terminates
    action_dicts.append({"action_type": "pass", "player_id": player_id})

    # Clear any existing resolution log when new actions arrive for next turn
    log_path = session_path(session_id, "resolution_log.json")
    if os.path.exists(log_path):
        # Only clear if we're starting a fresh submission round (no opponent file yet)
        opp_file = session_path(session_id, f"p{2 - player_id}_actions.json")
        if not os.path.exists(opp_file):
            try:
                os.remove(log_path)
            except FileNotFoundError:
                pass

    my_file = session_path(session_id, f"p{player_id + 1}_actions.json")
    write_json(my_file, action_dicts)

    # Check if opponent has also submitted
    opp_file = session_path(session_id, f"p{2 - player_id}_actions.json")
    triggered = False
    if os.path.exists(opp_file):
        triggered = True
        _run_resolution(session_id)

    return jsonify({"ok": True, "triggered_resolution": triggered})


@app.route("/api/mulligan/<session_id>/<int:player_id>", methods=["POST"])
def submit_mulligan(session_id: str, player_id: int):
    """player_id is 0-indexed. Body: {keep_indices: [0, 2, ...]}"""
    state_file = session_path(session_id, "state.json")
    if not os.path.exists(state_file):
        abort(404)

    try:
        state = load_state(session_id)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    if state.phase != Phase.MULLIGAN:
        return jsonify({"ok": False, "error": f"Not in MULLIGAN phase (current: {state.phase.value})"}), 400

    data = request.get_json(force=True)
    keep_indices = data.get("keep_indices", [])

    state.event_bus = EventBus()
    for i in range(2):
        state.heroes[i].hand = load_hand(session_id, i)

    engine = GameEngine(state)
    log = engine.mulligan(player_id, keep_indices)

    for i in range(2):
        save_hand(session_id, i, state.heroes[i].hand)

    # If both done, run start phase
    if state.phase == Phase.START:
        log += engine.start_phase()

    save_state(session_id, state)
    write_json(session_path(session_id, "resolution_log.json"), log)

    return jsonify({"ok": True, "phase": state.phase.value})


# ---------------------------------------------------------------------------
# Deck builder endpoints
# ---------------------------------------------------------------------------

@app.route("/api/cards")
def get_all_cards():
    """Return all cards organized by class for the deck builder UI."""
    result = {}
    for class_name, pool in CLASS_POOLS.items():
        class_cards = []
        for cid in pool:
            if cid in CARD_CATALOG:
                class_cards.append(_strip_hidden(CARD_CATALOG[cid].to_dict()))
        neutral_cards = []
        for cid in NEUTRAL_POOL:
            if cid in CARD_CATALOG:
                neutral_cards.append(_strip_hidden(CARD_CATALOG[cid].to_dict()))
        result[class_name] = {
            "class_cards": class_cards,
            "neutral_cards": neutral_cards,
        }
    return jsonify({
        "cards": result,
        "deck_size": DECK_SIZE,
        "max_copies": MAX_COPIES_PER_CARD,
    })


@app.route("/api/deck/validate", methods=["POST"])
def validate_deck_hash():
    """Validate a deck hash. Body: {hash: "..."}"""
    data = request.get_json(force=True)
    hash_str = data.get("hash", "").strip()
    if not hash_str:
        return jsonify({"ok": False, "error": "No hash provided"}), 400
    try:
        class_name, card_ids = decode_deck(hash_str)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    ok, msg = validate_deck(class_name, card_ids)
    if not ok:
        return jsonify({"ok": False, "error": msg}), 400

    cards = [_strip_hidden(CARD_CATALOG[cid].to_dict()) for cid in card_ids if cid in CARD_CATALOG]
    return jsonify({"ok": True, "class_name": class_name, "cards": cards})


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def _run_resolution(session_id: str) -> None:
    """Resolve the current turn: execute actions, advance to next PREP phase."""
    lock_path = session_path(session_id, "resolving.lock")
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        return  # Another request is already resolving

    try:
        p1_data = read_json(session_path(session_id, "p1_actions.json"))
        p2_data = read_json(session_path(session_id, "p2_actions.json"))

        if p1_data is None or p2_data is None:
            return

        p1_actions = deserialize_actions(json.dumps(p1_data))
        p2_actions = deserialize_actions(json.dumps(p2_data))

        # Reload fresh state and attach hands
        state = load_state(session_id)
        state.event_bus = EventBus()
        for i in range(2):
            state.heroes[i].hand = load_hand(session_id, i)

        engine = GameEngine(state)
        log = engine.resolution_phase(p1_actions, p2_actions)

        game_over = any(h.hp <= 0 for h in state.heroes)
        if not game_over:
            log += engine.end_phase()
            log += engine.start_phase()

        # Persist updated hands and state
        for i in range(2):
            save_hand(session_id, i, state.heroes[i].hand)
        save_state(session_id, state)

        # Write resolution log for clients to read
        write_json(session_path(session_id, "resolution_log.json"), log)

        # Clean up submitted action files
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000)
