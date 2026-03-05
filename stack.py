from __future__ import annotations
from actions import Action, PlayCardAction, AttackAction, PassAction, MulliganAction, HeroPowerAction
from models import GameState, CardType
from config import BOARD_SIZE


def merge_stacks(p1: list[Action], p2: list[Action], first_player: int = 0) -> list[Action]:
    """Interleave two action stacks. first_player (0 or 1) goes first in each pair."""
    if first_player == 1:
        p1, p2 = p2, p1
    merged: list[Action] = []
    for a, b in zip(p1, p2):
        merged.append(a)
        merged.append(b)
    longer = p1 if len(p1) > len(p2) else p2
    shorter_len = min(len(p1), len(p2))
    merged.extend(longer[shorter_len:])
    return merged


def validate_action(action: Action, state: GameState) -> tuple[bool, str]:
    """Check if an action is still legal given current game state. Returns (valid, reason)."""
    if isinstance(action, (PassAction, MulliganAction)):
        return True, ""

    if isinstance(action, HeroPowerAction):
        used = getattr(state, 'hero_power_used', (False, False))
        if used[action.player_id]:
            return False, "Hero power already used this turn"
        return True, ""

    hero = state.heroes[action.player_id]
    enemy = state.heroes[1 - action.player_id]

    if isinstance(action, PlayCardAction):
        # Check card is still in hand
        card = next((c for c in hero.hand if c.id == action.card_id), None)
        if card is None:
            return False, f"Card '{action.card_id}' not in hand"
        # Check mana
        if card.cost > hero.current_mana:
            return False, f"Not enough mana ({hero.current_mana} < {card.cost})"
        # Check target slot for creatures/buffs
        if card.card_type == CardType.CREATURE:
            if action.target_slot is None:
                return False, "Creature requires a target_slot"
            slot = hero.board[action.target_slot]
            if slot.is_occupied:
                return False, f"SLOT_OCCUPIED:{action.target_slot}"
        if card.card_type == CardType.BUFF:
            if action.target_slot is None:
                return False, "Buff requires a target_slot"
            # Determine whose board based on target_player
            target_board = hero.board if (action.target_player == 0 or action.target_player is None) else enemy.board
            slot = target_board[action.target_slot]
            if not slot.is_occupied:
                return False, f"Buff target slot {action.target_slot} is empty"
        return True, ""

    if isinstance(action, AttackAction):
        slot = hero.board[action.attacker_slot]
        if not slot.is_occupied:
            return False, f"Attacker slot {action.attacker_slot} is empty"
        # Summoning sickness check
        if slot.summoned_on_turn == state.turn:
            return False, f"Summoning sickness (played this turn)"
        # Positional combat: attacker at slot i can reach enemy slots [i-1, i, i+1]
        i = action.attacker_slot
        reachable_range = range(max(0, i - 1), min(BOARD_SIZE, i + 2))
        reachable_creatures = [s for s in reachable_range if enemy.board[s].is_occupied]
        if action.target_slot == -1:
            # Face attack only valid when no enemy creatures in positional range
            if reachable_creatures:
                return False, "Must attack a creature in range before targeting the hero"
        else:
            # Creature attack: must be within positional range
            if abs(action.target_slot - i) > 1:
                return False, f"Target slot {action.target_slot} is out of positional range"
            # If target slot is empty it will redirect to hero damage — still valid
        return True, ""

    return True, ""
