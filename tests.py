"""
Unit tests for the deckbuilding game MVP.
Run with: python tests.py
"""
from __future__ import annotations
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from models import GameState, Hero, BoardSlot, Phase, CardType
from actions import PlayCardAction, AttackAction, PassAction
from stack import merge_stacks, validate_action
from events import EventBus
from engine import GameEngine
from cards.definitions import get_card, STONE_GUARD, EMBER_WOLF, PLAGUE_RAT, SHOCK, SHIELD_AURA, WAR_EDGE, SHADOW_STEP


def make_state() -> GameState:
    state = GameState()
    state.event_bus = EventBus()
    state.heroes = (
        Hero(name="P1"),
        Hero(name="P2"),
    )
    for hero in state.heroes:
        hero.max_mana = 10
        hero.current_mana = 10
    return state


# ---------------------------------------------------------------------------
# 1. Stack merging
# ---------------------------------------------------------------------------

def test_merge_equal():
    p1 = [PassAction(0), PassAction(0)]
    p2 = [PassAction(1), PassAction(1)]
    merged = merge_stacks(p1, p2)
    assert len(merged) == 4
    assert merged[0].player_id == 0
    assert merged[1].player_id == 1
    assert merged[2].player_id == 0
    assert merged[3].player_id == 1
    print("PASS test_merge_equal")


def test_merge_p1_longer():
    p1 = [PassAction(0), PassAction(0), PassAction(0)]
    p2 = [PassAction(1)]
    merged = merge_stacks(p1, p2)
    assert len(merged) == 4
    assert merged[0].player_id == 0
    assert merged[1].player_id == 1
    assert merged[2].player_id == 0  # leftover
    assert merged[3].player_id == 0  # leftover
    print("PASS test_merge_p1_longer")


def test_merge_empty():
    merged = merge_stacks([], [])
    assert merged == []
    print("PASS test_merge_empty")


def test_merge_one_empty():
    p1 = [PassAction(0), PassAction(0)]
    merged = merge_stacks(p1, [])
    assert len(merged) == 2
    assert all(a.player_id == 0 for a in merged)
    print("PASS test_merge_one_empty")


# ---------------------------------------------------------------------------
# 2. Damage resolution
# ---------------------------------------------------------------------------

def test_attack_empty_slot_hits_hero():
    state = make_state()
    engine = GameEngine(state)

    stone_guard = get_card("stone_guard")
    state.heroes[0].board[0].place_creature(stone_guard)

    initial_hp = state.heroes[1].hp
    action = AttackAction(player_id=0, attacker_slot=0, target_slot=0)  # enemy slot 0 is empty
    log = []
    engine._execute_attack(action, log)

    assert state.heroes[1].hp == initial_hp - stone_guard.attack, f"Expected {initial_hp - stone_guard.attack}, got {state.heroes[1].hp}"
    print("PASS test_attack_empty_slot_hits_hero")


def test_attack_creature_vs_creature():
    state = make_state()
    engine = GameEngine(state)

    sg = get_card("stone_guard")   # 2/3
    ew = get_card("ember_wolf")    # 3/2
    state.heroes[0].board[0].place_creature(sg)
    state.heroes[1].board[0].place_creature(ew)

    log = []
    action = AttackAction(player_id=0, attacker_slot=0, target_slot=0)
    engine._execute_attack(action, log)

    # stone_guard (2 atk, 3 hp) vs ember_wolf (3 atk, 2 hp)
    # stone_guard takes 3 dmg → 3 - 3 = 0 HP
    # ember_wolf takes 2 dmg → 2 - 2 = 0 HP
    assert state.heroes[0].board[0].current_health == 0
    assert state.heroes[1].board[0].current_health == 0
    print("PASS test_attack_creature_vs_creature")


def test_creature_death_fires_on_death():
    state = make_state()
    engine = GameEngine(state)

    ew = get_card("ember_wolf")  # on_death: deal 1 to all enemies
    state.heroes[0].board[0].place_creature(ew)
    state.heroes[0].board[0].current_health = 0  # mark as dead

    initial_hp = state.heroes[1].hp
    log = []
    engine._resolve_deaths(log)

    # Ember Wolf deals 1 to enemy hero
    assert state.heroes[1].hp == initial_hp - 1, f"Expected {initial_hp - 1}, got {state.heroes[1].hp}"
    assert not state.heroes[0].board[0].is_occupied
    print("PASS test_creature_death_fires_on_death")


# ---------------------------------------------------------------------------
# 3. Buff lifecycle
# ---------------------------------------------------------------------------

def test_buff_applied_to_creature():
    state = make_state()
    engine = GameEngine(state)

    sg = get_card("stone_guard")  # 2/3
    state.heroes[0].board[1].place_creature(sg)
    state.heroes[0].hand.append(get_card("shield_aura"))  # +0/+3

    action = PlayCardAction(player_id=0, card_id="shield_aura", target_slot=1, target_player=0)
    log = []
    engine._execute_play_card(action, log)

    slot = state.heroes[0].board[1]
    assert slot.attack == 2         # no atk bonus
    assert slot.current_health == 6  # 3 base + 3 buff
    assert len(slot.buffs) == 1
    print("PASS test_buff_applied_to_creature")


def test_buff_cleared_on_creature_death():
    state = make_state()
    engine = GameEngine(state)

    sg = get_card("stone_guard")
    state.heroes[0].board[0].place_creature(sg)
    state.heroes[0].hand.append(get_card("war_edge"))  # +2/+0

    action = PlayCardAction(player_id=0, card_id="war_edge", target_slot=0, target_player=0)
    log = []
    engine._execute_play_card(action, log)

    assert len(state.heroes[0].board[0].buffs) == 1

    # Kill the creature
    state.heroes[0].board[0].current_health = 0
    engine._resolve_deaths(log)

    slot = state.heroes[0].board[0]
    assert not slot.is_occupied
    assert len(slot.buffs) == 0
    print("PASS test_buff_cleared_on_creature_death")


# ---------------------------------------------------------------------------
# 4. Mana validation
# ---------------------------------------------------------------------------

def test_mana_validation_sufficient():
    state = make_state()
    state.heroes[0].current_mana = 2
    state.heroes[0].hand = [get_card("stone_guard")]  # costs 2

    engine = GameEngine(state)
    actions = [PlayCardAction(player_id=0, card_id="stone_guard", target_slot=0)]
    ok, err = engine.validate_prep_actions(0, actions)
    assert ok, f"Expected OK, got: {err}"
    print("PASS test_mana_validation_sufficient")


def test_mana_validation_insufficient():
    state = make_state()
    state.heroes[0].current_mana = 1
    state.heroes[0].hand = [get_card("stone_guard")]  # costs 2

    engine = GameEngine(state)
    actions = [PlayCardAction(player_id=0, card_id="stone_guard", target_slot=0)]
    ok, err = engine.validate_prep_actions(0, actions)
    assert not ok, "Expected failure due to insufficient mana"
    print("PASS test_mana_validation_insufficient")


def test_mana_cumulative_spend():
    """Two cards that together exceed mana should fail."""
    state = make_state()
    state.heroes[0].current_mana = 3
    state.heroes[0].hand = [get_card("stone_guard"), get_card("stone_guard")]

    engine = GameEngine(state)
    # Each stone_guard costs 2, total 4 > 3
    actions = [
        PlayCardAction(player_id=0, card_id="stone_guard", target_slot=0),
        PlayCardAction(player_id=0, card_id="stone_guard", target_slot=1),
    ]
    ok, err = engine.validate_prep_actions(0, actions)
    assert not ok, "Expected failure: total cost 4 > 3"
    print("PASS test_mana_cumulative_spend")


# ---------------------------------------------------------------------------
# 5. Stack manipulation (Shadow Step)
# ---------------------------------------------------------------------------

def test_shadow_step_reorders_stack():
    from effects import shadow_step
    state = make_state()
    state.action_stacks = (
        [],
        [PassAction(1), AttackAction(player_id=1, attacker_slot=0, target_slot=-1)],
    )

    log = []
    # source_player_id=0 uses shadow step on enemy (player 1)
    shadow_step(state, 0, 1, None, log)

    # The top of enemy stack (PassAction) should move to the bottom
    stack = state.action_stacks[1]
    assert isinstance(stack[0], AttackAction), f"Expected AttackAction at top, got {type(stack[0])}"
    assert isinstance(stack[1], PassAction), f"Expected PassAction at bottom, got {type(stack[1])}"
    print("PASS test_shadow_step_reorders_stack")


# ---------------------------------------------------------------------------
# 6. Full resolution integration
# ---------------------------------------------------------------------------

def test_full_resolution_smoke():
    """Two players each play a creature and attack. Verify state is consistent."""
    state = make_state()
    engine = GameEngine(state)

    # Give each player a creature in hand
    sg1 = get_card("stone_guard")
    sg2 = get_card("stone_guard")
    state.heroes[0].hand = [sg1]
    state.heroes[1].hand = [sg2]

    p1_actions = [
        PlayCardAction(player_id=0, card_id="stone_guard", target_slot=0),
        AttackAction(player_id=0, attacker_slot=0, target_slot=0),
        PassAction(player_id=0),
    ]
    p2_actions = [
        PlayCardAction(player_id=1, card_id="stone_guard", target_slot=0),
        PassAction(player_id=1),
    ]

    log = engine.resolution_phase(p1_actions, p2_actions)
    print("Resolution log:")
    for line in log:
        print(" ", line)
    print("PASS test_full_resolution_smoke")


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_merge_equal,
        test_merge_p1_longer,
        test_merge_empty,
        test_merge_one_empty,
        test_attack_empty_slot_hits_hero,
        test_attack_creature_vs_creature,
        test_creature_death_fires_on_death,
        test_buff_applied_to_creature,
        test_buff_cleared_on_creature_death,
        test_mana_validation_sufficient,
        test_mana_validation_insufficient,
        test_mana_cumulative_spend,
        test_shadow_step_reorders_stack,
        test_full_resolution_smoke,
    ]

    failures = []
    for test in tests:
        try:
            test()
        except Exception as e:
            import traceback
            failures.append((test.__name__, traceback.format_exc()))
            print(f"FAIL {test.__name__}: {e}")

    print(f"\n{'=' * 40}")
    print(f"{len(tests) - len(failures)}/{len(tests)} tests passed")
    if failures:
        print("\nFailures:")
        for name, tb in failures:
            print(f"\n-- {name} --\n{tb}")
        sys.exit(1)
    else:
        print("All tests passed!")
