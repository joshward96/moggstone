from __future__ import annotations
import json
import random
from typing import Any

from config import MAX_MANA, STARTING_HAND_SIZE, CARDS_DRAWN_PER_TURN
from models import GameState, Hero, BoardSlot, Phase, CardType, CreatureCard, BuffCard, SpellCard
from actions import Action, PlayCardAction, AttackAction, PassAction, MulliganAction, HeroPowerAction
from stack import merge_stacks, validate_action
from events import EventBus, EventType
from effects import EFFECT_REGISTRY, get_effect


class GameEngine:
    def __init__(self, state: GameState):
        self.state = state
        # Attach event bus to state so effects can dispatch events
        if not hasattr(state, "event_bus"):
            state.event_bus = EventBus()

    # ------------------------------------------------------------------
    # Turn phases
    # ------------------------------------------------------------------

    def start_phase(self) -> list[str]:
        """Increment mana, draw cards, fire ON_TURN_START."""
        log: list[str] = []
        state = self.state
        turn = state.turn

        # Reset hero power usage each turn
        state.hero_power_used = (False, False)

        for i, hero in enumerate(state.heroes):
            new_mana = min(turn, MAX_MANA)
            hero.max_mana = new_mana
            hero.current_mana = new_mana
            log.append(f"{hero.name} mana set to {new_mana}")

        for i, hero in enumerate(state.heroes):
            self._draw_cards(i, CARDS_DRAWN_PER_TURN, log)

        state.event_bus.dispatch(EventType.ON_TURN_START, state, log)
        state.phase = Phase.PREP
        return log

    def resolution_phase(self, p1_actions: list[Action], p2_actions: list[Action]) -> list[str]:
        """Merge stacks and resolve all actions. Prep cards run before stack cards."""
        log: list[str] = []
        state = self.state
        fp = state.first_player

        log.append(f"=== Resolution Phase (turn {state.turn}, P{fp+1} goes first) ===")
        log.append(self._board_snapshot())

        # Split each player's actions into prep and stack queues
        def split_by_timing(actions: list[Action]) -> tuple[list[Action], list[Action]]:
            prep, stack = [], []
            for a in actions:
                if isinstance(a, HeroPowerAction):
                    prep.append(a)
                    continue
                if isinstance(a, PlayCardAction):
                    hero = state.heroes[a.player_id]
                    card = next((c for c in hero.hand if c.id == a.card_id), None)
                    if card and getattr(card, 'timing', 'stack') == 'prep':
                        prep.append(a)
                        continue
                stack.append(a)
            return prep, stack

        p1_prep, p1_stack = split_by_timing(p1_actions)
        p2_prep, p2_stack = split_by_timing(p2_actions)

        prep_merged = merge_stacks(p1_prep, p2_prep, first_player=fp)
        stack_merged = merge_stacks(p1_stack, p2_stack, first_player=fp)

        action_queue: list[Action] = prep_merged + stack_merged
        state.current_stack = action_queue  # expose to effects

        log.append(f"Prep: {len(prep_merged)} actions, Stack: {len(stack_merged)} actions")

        idx = 0
        while idx < len(action_queue):
            action = action_queue[idx]
            idx += 1

            valid, reason = validate_action(action, state)
            if not valid:
                if reason.startswith("SLOT_OCCUPIED:"):
                    # Mana is burned but card returns to hand
                    self._handle_slot_occupied_fail(action, reason, log)
                else:
                    log.append(f"[SKIP] {_action_desc(action)}: {reason}")
                continue

            log.append(f"\n[ACTION] {_action_desc(action)}")
            self._execute_action(action, log)
            self._resolve_deaths(log)
            log.append(self._board_snapshot())

            # Check win condition after each action
            winner = self._check_win()
            if winner is not None:
                log.append(f"\n=== {state.heroes[winner].name} WINS! ===")
                state.phase = Phase.END
                log.append(self._board_snapshot())
                return log

        state.phase = Phase.END
        return log

    def _handle_slot_occupied_fail(self, action: PlayCardAction, reason: str, log: list[str]) -> None:
        """Card was played into an occupied slot — burn mana but return card to hand."""
        state = self.state
        hero = state.heroes[action.player_id]
        card = next((c for c in hero.hand if c.id == action.card_id), None)
        if card:
            cost = card.cost
            if cost <= hero.current_mana:
                hero.current_mana -= cost
                log.append(f"[FAIL] {hero.name}'s {card.name} fizzled — slot occupied! ({cost} mana burned, card returned)")
            else:
                log.append(f"[FAIL] {hero.name}'s {card.name} fizzled — slot occupied! (insufficient mana to burn)")

    def end_phase(self) -> list[str]:
        """Fire ON_TURN_END, strip temporary buffs, advance turn, flip first player."""
        log: list[str] = []
        state = self.state

        state.event_bus.dispatch(EventType.ON_TURN_END, state, log)

        # Strip temporary buffs from all slots
        for player_id in range(2):
            for slot in state.heroes[player_id].board:
                if slot.is_occupied:
                    to_remove = [b for b in slot.buffs if getattr(b, 'temporary', False)]
                    for buff in to_remove:
                        slot.buffs.remove(buff)
                        # Reverse health bonus (floor at 1)
                        if buff.health_bonus > 0:
                            slot.current_health = max(1, slot.current_health - buff.health_bonus)
                    if to_remove:
                        log.append(f"  Temporary buffs expired on {slot.creature.name}")

        # Alternate who goes first
        state.first_player = 1 - state.first_player
        state.turn += 1
        state.phase = Phase.START
        log.append(f"Turn {state.turn - 1} complete. Starting turn {state.turn}. P{state.first_player+1} goes first next.")
        return log

    # ------------------------------------------------------------------
    # Action execution
    # ------------------------------------------------------------------

    def _execute_action(self, action: Action, log: list[str]) -> None:
        if isinstance(action, PlayCardAction):
            self._execute_play_card(action, log)
        elif isinstance(action, AttackAction):
            self._execute_attack(action, log)
        elif isinstance(action, HeroPowerAction):
            self._execute_hero_power(action, log)
        elif isinstance(action, PassAction):
            log.append(f"  {self.state.heroes[action.player_id].name} passes")

    def _execute_play_card(self, action: PlayCardAction, log: list[str]) -> None:
        state = self.state
        hero = state.heroes[action.player_id]
        enemy = state.heroes[1 - action.player_id]

        card = next((c for c in hero.hand if c.id == action.card_id), None)
        if card is None:
            log.append(f"  Card {action.card_id} not found in hand")
            return

        # Deduct mana and remove from hand
        hero.current_mana -= card.cost
        hero.hand.remove(card)
        log.append(f"  {hero.name} plays {card.name} (cost {card.cost})")

        if card.card_type == CardType.CREATURE:
            slot_idx = action.target_slot
            if slot_idx is None:
                slot_idx = next((i for i, s in enumerate(hero.board) if not s.is_occupied), None)
            if slot_idx is None:
                log.append(f"  No empty board slot available!")
                return
            slot = hero.board[slot_idx]
            slot.place_creature(card)  # type: ignore

            # Summoning sickness — charge creatures bypass it
            if not card.charge:  # type: ignore
                slot.summoned_on_turn = state.turn
            else:
                slot.summoned_on_turn = None  # Charge: no sickness

            log.append(f"  {card.name} ({card.attack}/{slot.current_health}) placed in slot {slot_idx}")

            # Shield Wall: buff adjacent friendly creatures
            if card.shield_wall > 0:  # type: ignore
                self._apply_shield_wall(action.player_id, slot_idx, card.shield_wall, log)  # type: ignore

            # Register event handlers for this creature
            self._register_creature_events(action.player_id, slot_idx, card)  # type: ignore

            # Fire on-play effect
            if card.on_play_effect:  # type: ignore
                effect = get_effect(card.on_play_effect)  # type: ignore
                if effect:
                    effect(state, action.player_id, log, target_slot=slot_idx)

            state.event_bus.dispatch(EventType.ON_PLAY, state, action.player_id, slot_idx, log)

            # Charge: insert attack action immediately after current position in stack
            if card.charge and action.charge_target is not None:  # type: ignore
                from actions import AttackAction as AA
                charge_attack = AA(
                    player_id=action.player_id,
                    attacker_slot=slot_idx,
                    target_slot=action.charge_target,
                )
                # Insert right after current idx in current_stack
                stack = state.current_stack
                try:
                    cur_pos = stack.index(action) + 1
                except ValueError:
                    cur_pos = 0
                stack.insert(cur_pos, charge_attack)
                log.append(f"  {card.name} charges slot {action.charge_target}!")

        elif card.card_type == CardType.BUFF:
            buff_card: BuffCard = card  # type: ignore
            target_player_id = action.target_player if action.target_player is not None else action.player_id
            target_board = state.heroes[target_player_id].board
            slot_idx = action.target_slot
            if slot_idx is None:
                log.append("  Buff requires a target slot")
                return
            slot = target_board[slot_idx]
            if not slot.is_occupied:
                log.append(f"  Slot {slot_idx} is empty, buff wasted")
                return
            slot.apply_buff(buff_card)
            log.append(f"  {buff_card.name} applied to {slot.creature.name}: now {slot.attack}/{slot.current_health}")

            if buff_card.on_play_effect:
                effect = get_effect(buff_card.on_play_effect)
                if effect:
                    effect(state, action.player_id, target_player_id, slot_idx, log)

        elif card.card_type == CardType.SPELL:
            spell_card: SpellCard = card  # type: ignore
            target_player_id = action.target_player if action.target_player is not None else (1 - action.player_id)
            target_slot = action.target_slot

            if spell_card.on_play_effect:
                effect = get_effect(spell_card.on_play_effect)
                if effect:
                    effect(state, action.player_id, target_player_id, target_slot, log)

            state.event_bus.dispatch(EventType.ON_PLAY, state, action.player_id, None, log)

    def _execute_hero_power(self, action: HeroPowerAction, log: list[str]) -> None:
        state = self.state
        hero = state.heroes[action.player_id]

        # Mark used
        used = list(state.hero_power_used)
        used[action.player_id] = True
        state.hero_power_used = tuple(used)  # type: ignore

        hero_class = getattr(hero, 'hero_class', '')
        log.append(f"  {hero.name} uses hero power!")

        if hero_class == "ice_witch":
            effect = get_effect("hero_power_ice_witch")
            if effect:
                effect(state, action.player_id, action.target_player, action.target_slot, log)
        elif hero_class == "drum_wizard":
            effect = get_effect("hero_power_drum_wizard")
            if effect:
                effect(state, action.player_id, action.target_player, action.target_slot, log)
        elif hero_class == "blood_witch":
            effect = get_effect("hero_power_blood_witch")
            if effect:
                effect(state, action.player_id, action.target_player, action.target_slot, log)
        else:
            log.append(f"  (no hero power defined for class '{hero_class}')")

    def _execute_attack(self, action: AttackAction, log: list[str]) -> None:
        state = self.state
        attacker_hero = state.heroes[action.player_id]
        defender_hero = state.heroes[1 - action.player_id]

        attacker_slot = attacker_hero.board[action.attacker_slot]
        if not attacker_slot.is_occupied:
            log.append(f"  Attacker slot {action.attacker_slot} is empty")
            return

        atk_name = attacker_slot.creature.name
        atk_power = attacker_slot.attack

        # Check on-attack effect (e.g. DJ lone wolf check)
        if attacker_slot.creature.on_attack_effect:
            effect = get_effect(attacker_slot.creature.on_attack_effect)
            if effect:
                result = effect(state, action.player_id, log,
                                attacker_slot=action.attacker_slot,
                                target_slot=action.target_slot)
                if result is False:
                    return  # cancelled by on-attack effect

        state.event_bus.dispatch(EventType.ON_ATTACK, state, action.player_id, action.attacker_slot, log)

        # Track last killer for on-kill effects
        state._last_attacker = (action.player_id, action.attacker_slot)

        if action.target_slot == -1 or not defender_hero.board[action.target_slot].is_occupied:
            # Attack goes to enemy hero directly
            defender_hero.hp -= atk_power
            log.append(f"  {atk_name} attacks {defender_hero.name} for {atk_power} ({defender_hero.hp} HP remaining)")
            state._last_attacker = None
        else:
            # Creature vs creature — defender does NOT deal damage back (per rules)
            target_slot_idx = action.target_slot
            target_slot = defender_hero.board[target_slot_idx]
            def_name = target_slot.creature.name
            target_slot.current_health -= atk_power
            log.append(f"  {atk_name} attacks {def_name} ({target_slot.current_health} HP remaining)")

            # Riposte: defender deals its attack back to the attacker
            if target_slot.creature.riposte:
                riposte_dmg = target_slot.attack
                attacker_slot.current_health -= riposte_dmg
                log.append(f"  Riposte! {def_name} deals {riposte_dmg} back to {atk_name} ({attacker_slot.current_health} HP)")
                state.event_bus.dispatch(
                    EventType.ON_DAMAGE, state,
                    action.player_id, action.attacker_slot, riposte_dmg, log
                )

            # Dispatch on-damage for the defender
            state.event_bus.dispatch(
                EventType.ON_DAMAGE, state,
                1 - action.player_id, target_slot_idx, atk_power, log
            )

            # Post-attack effect (fires after damage, only on creature vs creature hits)
            if attacker_slot.is_occupied and attacker_slot.creature.post_attack_effect:
                pa_effect = get_effect(attacker_slot.creature.post_attack_effect)
                if pa_effect:
                    pa_effect(state, action.player_id, 1 - action.player_id, target_slot_idx, log)

        # Trigger on-attack double-attack (Tempo-Penguins) — after attack resolution
        if attacker_slot.is_occupied and attacker_slot.creature.on_attack_effect == "double_attack":
            effect = get_effect("double_attack")
            if effect:
                effect(state, action.player_id, log,
                       attacker_slot=action.attacker_slot,
                       target_slot=action.target_slot)

    def _apply_shield_wall(self, player_id: int, slot_idx: int, bonus: int, log: list[str]) -> None:
        """Apply Shield Wall +bonus/+bonus to adjacent friendly creatures."""
        board = self.state.heroes[player_id].board
        for adj in [slot_idx - 1, slot_idx + 1]:
            if 0 <= adj < len(board) and board[adj].is_occupied:
                sw_buff = BuffCard(
                    id="shield_wall_buff", name="Shield Wall", cost=0, card_type=CardType.BUFF,
                    attack_bonus=bonus, health_bonus=bonus,
                )
                board[adj].apply_buff(sw_buff)
                log.append(f"  Shield Wall: {board[adj].creature.name} gets +{bonus}/+{bonus}")

    # ------------------------------------------------------------------
    # Death resolution
    # ------------------------------------------------------------------

    def _resolve_deaths(self, log: list[str]) -> None:
        state = self.state
        attacker_info = getattr(state, '_last_attacker', None)
        for player_id in range(2):
            hero = state.heroes[player_id]
            for slot_idx, slot in enumerate(hero.board):
                if slot.is_dead():
                    creature_name = slot.creature.name
                    on_death = slot.creature.on_death_effect
                    on_kill = slot.creature.on_kill_effect if slot.is_occupied else None
                    log.append(f"  {creature_name} dies!")
                    owner_key = f"p{player_id}_slot{slot_idx}"
                    state.event_bus.unsubscribe_owner(owner_key)
                    slot.clear()
                    # Fire on-death effect
                    if on_death:
                        effect = get_effect(on_death)
                        if effect:
                            effect(state, player_id, log)
                    state.event_bus.dispatch(EventType.ON_DEATH, state, player_id, slot_idx, log)
                    # Fire killer's on-kill effect
                    if attacker_info:
                        killer_pid, killer_slot_idx = attacker_info
                        killer_slot = state.heroes[killer_pid].board[killer_slot_idx]
                        if killer_slot.is_occupied and killer_slot.creature.on_kill_effect:
                            kill_effect = get_effect(killer_slot.creature.on_kill_effect)
                            if kill_effect:
                                kill_effect(state, killer_pid, log,
                                            target_player_id=player_id,
                                            target_slot=slot_idx)
        state._last_attacker = None

    # ------------------------------------------------------------------
    # Creature event registration
    # ------------------------------------------------------------------

    def _register_creature_events(self, player_id: int, slot_idx: int, card: CreatureCard) -> None:
        """Subscribe a creature's event handlers to the event bus."""
        owner_key = f"p{player_id}_slot{slot_idx}"
        state = self.state

        if card.on_damage_effect:
            effect_name = card.on_damage_effect

            def on_damage_handler(gs, dmg_player_id, dmg_slot_idx, amount, log,
                                  _pid=player_id, _sidx=slot_idx, _eff=effect_name):
                if dmg_player_id == _pid and dmg_slot_idx == _sidx:
                    effect = get_effect(_eff)
                    if effect:
                        attacker_pid = 1 - _pid
                        effect(gs, _pid, _sidx, attacker_pid, None, log)

            state.event_bus.subscribe(EventType.ON_DAMAGE, owner_key, on_damage_handler)

        if card.enrage > 0:
            def enrage_handler(gs, dmg_player_id, dmg_slot_idx, amount, log,
                               _pid=player_id, _sidx=slot_idx):
                if dmg_player_id == _pid and dmg_slot_idx == _sidx:
                    slot = gs.heroes[_pid].board[_sidx]
                    if slot.is_occupied and slot.creature.enrage > 0:
                        slot.enrage_bonus += slot.creature.enrage
                        log.append(f"  {slot.creature.name} enrages! (+{slot.creature.enrage} attack)")

            state.event_bus.subscribe(EventType.ON_DAMAGE, owner_key, enrage_handler)

    # ------------------------------------------------------------------
    # Drawing and setup
    # ------------------------------------------------------------------

    def _draw_cards(self, player_id: int, count: int, log: list[str]) -> list:
        hero = self.state.heroes[player_id]
        drawn = []
        for _ in range(count):
            if hero.deck:
                card = hero.deck.pop(0)
                hero.hand.append(card)
                drawn.append(card)
                log.append(f"  {hero.name} draws {card.name}")
        return drawn

    def deal_opening_hands(self) -> list[str]:
        log: list[str] = []
        for i in range(2):
            self._draw_cards(i, STARTING_HAND_SIZE, log)
        self.state.phase = Phase.MULLIGAN
        self.state.mulligan_done = (False, False)
        return log

    def mulligan(self, player_id: int, keep_indices: list[int]) -> list[str]:
        """Swap cards NOT in keep_indices back to deck and draw replacements."""
        log: list[str] = []
        hero = self.state.heroes[player_id]
        hand = list(hero.hand)
        to_swap = [card for i, card in enumerate(hand) if i not in keep_indices]
        to_keep = [card for i, card in enumerate(hand) if i in keep_indices]

        # Return swapped cards to deck and shuffle
        hero.deck.extend(to_swap)
        random.shuffle(hero.deck)

        # Draw replacements
        hero.hand = to_keep
        self._draw_cards(player_id, len(to_swap), log)
        log.append(f"  {hero.name} mulliganed {len(to_swap)} card(s)")

        # Mark mulligan done
        done = list(self.state.mulligan_done)
        done[player_id] = True
        self.state.mulligan_done = tuple(done)  # type: ignore

        if all(self.state.mulligan_done):
            self.state.phase = Phase.START
            log.append("  Both players mulligan complete — game starts!")

        return log

    # ------------------------------------------------------------------
    # Board snapshot (for animated resolution log)
    # ------------------------------------------------------------------

    def _board_snapshot(self) -> str:
        """Serialize minimal board state for frontend step-by-step animation."""
        state = self.state
        data = {
            "heroes": [
                {
                    "hp": hero.hp,
                    "current_mana": hero.current_mana,
                    "board": [
                        {
                            "name": slot.creature.name,
                            "attack": slot.attack,
                            "health": slot.current_health,
                            "frozen": slot.frozen,
                            "keywords": {
                                "riposte": bool(slot.creature.riposte),
                                "enrage": bool(slot.creature.enrage),
                                "shield_wall": bool(slot.creature.shield_wall),
                            },
                        } if slot.is_occupied else None
                        for slot in hero.board
                    ],
                }
                for hero in state.heroes
            ]
        }
        return "__SNAPSHOT__:" + json.dumps(data)

    # ------------------------------------------------------------------
    # Win condition
    # ------------------------------------------------------------------

    def _check_win(self) -> int | None:
        h0, h1 = self.state.heroes
        if h0.hp <= 0 and h1.hp <= 0:
            return 0
        if h0.hp <= 0:
            return 1
        if h1.hp <= 0:
            return 0
        return None

    # ------------------------------------------------------------------
    # Mana validation for prep phase
    # ------------------------------------------------------------------

    def validate_prep_actions(self, player_id: int, actions: list[Action]) -> tuple[bool, str]:
        hero = self.state.heroes[player_id]
        simulated_mana = hero.current_mana
        simulated_hand = list(hero.hand)

        for action in actions:
            if isinstance(action, PassAction):
                break
            if isinstance(action, PlayCardAction):
                card = next((c for c in simulated_hand if c.id == action.card_id), None)
                if card is None:
                    return False, f"Card '{action.card_id}' not in hand"
                if card.cost > simulated_mana:
                    return False, f"Not enough mana for {card.name} (need {card.cost}, have {simulated_mana})"
                simulated_mana -= card.cost
                simulated_hand.remove(card)
        return True, ""


def _action_desc(action: Action) -> str:
    if isinstance(action, PlayCardAction):
        return f"P{action.player_id + 1} plays {action.card_id}"
    elif isinstance(action, AttackAction):
        tgt = "hero" if action.target_slot == -1 else f"slot {action.target_slot}"
        return f"P{action.player_id + 1} attacks {tgt} with slot {action.attacker_slot}"
    elif isinstance(action, HeroPowerAction):
        return f"P{action.player_id + 1} hero power"
    elif isinstance(action, PassAction):
        return f"P{action.player_id + 1} passes"
    elif isinstance(action, MulliganAction):
        return f"P{action.player_id + 1} mulligans"
    return str(action)
