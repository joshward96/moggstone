from __future__ import annotations
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from models import GameState, Card, BoardSlot, CreatureCard
    from actions import Action, AttackAction

EFFECT_REGISTRY: dict[str, Callable] = {}


def register_effect(name: str):
    """Decorator to register a named effect in the global registry."""
    def decorator(fn: Callable) -> Callable:
        EFFECT_REGISTRY[name] = fn
        return fn
    return decorator


def get_effect(name: str) -> Callable | None:
    return EFFECT_REGISTRY.get(name)


# ---------------------------------------------------------------------------
# Helper utilities used by effects
# ---------------------------------------------------------------------------

def _deal_damage_to_hero(state: GameState, target_player_id: int, amount: int, log: list[str]) -> None:
    from events import EventType
    hero = state.heroes[target_player_id]
    hero.hp -= amount
    log.append(f"  {hero.name} takes {amount} damage ({hero.hp} HP remaining)")
    state.event_bus.dispatch(EventType.ON_DAMAGE, state, None, target_player_id, log)


def _deal_damage_to_slot(state: GameState, owner_id: int, slot_idx: int, amount: int, log: list[str]) -> None:
    from events import EventType
    slot = state.heroes[owner_id].board[slot_idx]
    if not slot.is_occupied:
        return
    slot.current_health -= amount
    log.append(f"  {slot.creature.name} (slot {slot_idx}) takes {amount} damage ({slot.current_health} HP remaining)")
    owner_key = f"p{owner_id}_slot{slot_idx}"
    state.event_bus.dispatch(EventType.ON_DAMAGE, state, owner_id, slot_idx, amount, log)


def freeze_slot(state: GameState, owner_id: int, slot_idx: int, log: list[str]) -> None:
    """Freeze a creature: move its next pending attack to bottom of current_stack."""
    from actions import AttackAction
    slot = state.heroes[owner_id].board[slot_idx]
    if not slot.is_occupied:
        return
    slot.frozen = True
    # Find and move any pending attack from this slot to bottom of stack
    stack = state.current_stack
    for i, action in enumerate(stack):
        if isinstance(action, AttackAction) and action.player_id == owner_id and action.attacker_slot == slot_idx:
            stack.append(stack.pop(i))
            log.append(f"  {slot.creature.name} frozen — attack moved to bottom of stack")
            return
    log.append(f"  {slot.creature.name} frozen")


def _consecutive_actions(state: GameState, player_id: int, count: int, log: list[str]) -> None:
    """Extract the next `count` actions belonging to player_id from current_stack and re-insert them consecutively."""
    stack = state.current_stack
    # Collect indices of this player's upcoming actions (after current position, which is being executed)
    player_actions = [(i, a) for i, a in enumerate(stack) if hasattr(a, 'player_id') and a.player_id == player_id]
    to_move = player_actions[:count]
    if not to_move:
        log.append("  No pending actions to reorder")
        return
    # Remove them from stack (in reverse order to preserve indices)
    for i, _ in reversed(to_move):
        stack.pop(i)
    # Re-insert at the front
    for _, action in reversed(to_move):
        stack.insert(0, action)
    log.append(f"  Next {len(to_move)} actions queued consecutively")


# ---------------------------------------------------------------------------
# Creature on-play effects
# ---------------------------------------------------------------------------

@register_effect("draw_a_card")
def draw_a_card(state: GameState, source_player_id: int, log: list[str], **kwargs) -> None:
    """Iron Colossus: on-play draw a card."""
    from events import EventType
    hero = state.heroes[source_player_id]
    if hero.deck:
        card = hero.deck.pop(0)
        hero.hand.append(card)
        log.append(f"  {hero.name} draws {card.name}")
        state.event_bus.dispatch(EventType.ON_DRAW, state, source_player_id, card, log)
    else:
        log.append(f"  {hero.name}'s deck is empty, no card drawn")


@register_effect("capibarra_register")
def capibarra_register(state: GameState, source_player_id: int, log: list[str],
                       target_slot: int | None = None, **kwargs) -> None:
    """Coconut Capibarra: subscribe ON_TURN_END — draw a card if still alive."""
    from events import EventType
    if target_slot is None:
        return
    owner_key = f"p{source_player_id}_slot{target_slot}"

    def on_turn_end(s, lg, **kw):
        slot = s.heroes[source_player_id].board[target_slot]
        if slot.is_occupied and slot.creature.id == "coconut_capibarra":
            hero = s.heroes[source_player_id]
            if hero.deck:
                card = hero.deck.pop(0)
                hero.hand.append(card)
                lg.append(f"  Coconut Capibarra vibe check — {hero.name} draws {card.name}")

    state.event_bus.subscribe(EventType.ON_TURN_END, owner_key, on_turn_end)
    log.append(f"  Coconut Capibarra registered end-of-turn draw")


# ---------------------------------------------------------------------------
# Creature on-death effects
# ---------------------------------------------------------------------------

@register_effect("ember_wolf_death")
def ember_wolf_death(state: GameState, dead_player_id: int, log: list[str], **kwargs) -> None:
    """Ember Wolf: on-death deal 1 damage to all enemy creatures and hero."""
    enemy_id = 1 - dead_player_id
    enemy = state.heroes[enemy_id]
    log.append(f"  Ember Wolf's death: deal 1 to all enemies")
    _deal_damage_to_hero(state, enemy_id, 1, log)
    for i, slot in enumerate(enemy.board):
        if slot.is_occupied:
            _deal_damage_to_slot(state, enemy_id, i, 1, log)


# ---------------------------------------------------------------------------
# Creature on-damage effects
# ---------------------------------------------------------------------------

@register_effect("plague_rat_counter")
def plague_rat_counter(state: GameState, victim_player_id: int, slot_idx: int,
                       attacker_player_id: int, attacker_slot_idx: int | None,
                       log: list[str], **kwargs) -> None:
    """Plague Rat: when damaged, deal 1 to the attacker."""
    if attacker_slot_idx is None:
        return
    attacker_slot = state.heroes[attacker_player_id].board[attacker_slot_idx]
    if attacker_slot.is_occupied:
        attacker_slot.current_health -= 1
        log.append(f"  Plague Rat retaliates! {attacker_slot.creature.name} takes 1 damage ({attacker_slot.current_health} HP remaining)")


@register_effect("enrage_trigger")
def enrage_trigger(state: GameState, victim_player_id: int, slot_idx: int,
                   amount: int = 1, log: list[str] = None, **kwargs) -> None:
    """Generic enrage: add creature's enrage value to its attack bonus."""
    if log is None:
        log = []
    slot = state.heroes[victim_player_id].board[slot_idx]
    if slot.is_occupied and slot.creature.enrage > 0:
        slot.enrage_bonus += slot.creature.enrage
        log.append(f"  {slot.creature.name} enrages! (+{slot.creature.enrage} attack)")


# ---------------------------------------------------------------------------
# Creature on-attack effects
# ---------------------------------------------------------------------------

@register_effect("double_attack")
def double_attack(state: GameState, source_player_id: int, log: list[str],
                  attacker_slot: int | None = None, target_slot: int | None = None, **kwargs) -> None:
    """Tempo-Penguins: insert a duplicate attack action right after current position in stack."""
    from actions import AttackAction
    if attacker_slot is None or target_slot is None:
        return
    stack = state.current_stack
    duplicate = AttackAction(player_id=source_player_id, attacker_slot=attacker_slot, target_slot=target_slot)
    stack.insert(0, duplicate)
    log.append(f"  Tempo-Penguins queues a second attack!")


@register_effect("dj_lone_wolf")
def dj_lone_wolf(state: GameState, source_player_id: int, log: list[str],
                 attacker_slot: int | None = None, **kwargs) -> bool:
    """DJ Tightpants: can only attack if no adjacent friendly minions."""
    if attacker_slot is None:
        return True
    board = state.heroes[source_player_id].board
    left = attacker_slot - 1
    right = attacker_slot + 1
    if (0 <= left < len(board) and board[left].is_occupied) or \
       (0 <= right < len(board) and board[right].is_occupied):
        log.append(f"  DJ Tightpants can't attack — adjacent minions present")
        return False  # signals engine to cancel the attack
    return True


# ---------------------------------------------------------------------------
# On-kill effects
# ---------------------------------------------------------------------------

@register_effect("rhino_splash")
def rhino_splash(state: GameState, source_player_id: int, log: list[str],
                 target_player_id: int | None = None, target_slot: int | None = None, **kwargs) -> None:
    """Raging Rhino: deal 1 damage to minions adjacent to the killed creature."""
    if target_player_id is None or target_slot is None:
        return
    for adj in [target_slot - 1, target_slot + 1]:
        if 0 <= adj < len(state.heroes[target_player_id].board):
            _deal_damage_to_slot(state, target_player_id, adj, 1, log)
    log.append(f"  Raging Rhino splashes 1 damage to adjacent slots")


# ---------------------------------------------------------------------------
# Spell effects
# ---------------------------------------------------------------------------

@register_effect("deal_2_to_target")
def deal_2_to_target(state: GameState, source_player_id: int, target_player: int,
                     target_slot: int | None, log: list[str], **kwargs) -> None:
    """Shock: deal 2 damage to any target."""
    _apply_spell_damage(state, source_player_id, target_player, target_slot, 2, "Shock", log)


@register_effect("deal_5_to_target")
def deal_5_to_target(state: GameState, source_player_id: int, target_player: int,
                     target_slot: int | None, log: list[str], **kwargs) -> None:
    """Fireball: deal 5 damage to any target."""
    _apply_spell_damage(state, source_player_id, target_player, target_slot, 5, "Fireball", log)


def _apply_spell_damage(state: GameState, source_player_id: int, target_player: int,
                        target_slot: int | None, amount: int, spell_name: str, log: list[str]) -> None:
    if target_slot is None:
        _deal_damage_to_hero(state, target_player, amount, log)
        log[-1] = f"  {spell_name}: " + log[-1].strip()
    else:
        slot = state.heroes[target_player].board[target_slot]
        if slot.is_occupied:
            _deal_damage_to_slot(state, target_player, target_slot, amount, log)
            log[-1] = f"  {spell_name}: " + log[-1].strip()
        else:
            log.append(f"  {spell_name}: target slot {target_slot} is empty, no effect")


@register_effect("restore_4_hp")
def restore_4_hp(state: GameState, source_player_id: int, target_player: int,
                 target_slot: int | None, log: list[str], **kwargs) -> None:
    """Mend: restore 4 HP to friendly hero."""
    from config import STARTING_HP
    hero = state.heroes[source_player_id]
    healed = min(4, STARTING_HP - hero.hp)
    hero.hp += healed
    log.append(f"  Mend: {hero.name} heals {healed} HP ({hero.hp} HP)")


@register_effect("buff_health_3")
def buff_health_3(state: GameState, source_player_id: int, target_player: int,
                  target_slot: int | None, log: list[str], **kwargs) -> None:
    log.append(f"  Shield Aura applied to slot {target_slot}")


@register_effect("buff_attack_2")
def buff_attack_2(state: GameState, source_player_id: int, target_player: int,
                  target_slot: int | None, log: list[str], **kwargs) -> None:
    log.append(f"  War Edge applied to slot {target_slot}")


@register_effect("shadow_step")
def shadow_step(state: GameState, source_player_id: int, target_player: int,
                target_slot: int | None, log: list[str], **kwargs) -> None:
    """Shadow Step: move the enemy's next action to the bottom of the current stack."""
    enemy_id = 1 - source_player_id
    stack = state.current_stack
    # Find first action belonging to the enemy and move it to the end
    for i, action in enumerate(stack):
        if hasattr(action, 'player_id') and action.player_id == enemy_id:
            stack.append(stack.pop(i))
            log.append(f"  Shadow Step: enemy's next action moved to bottom of stack")
            return
    log.append(f"  Shadow Step: no enemy actions remaining in stack")


# ---------------------------------------------------------------------------
# Ice Witch spell effects
# ---------------------------------------------------------------------------

@register_effect("deal_6_to_creature")
def deal_6_to_creature(state: GameState, source_player_id: int, target_player: int,
                       target_slot: int | None, log: list[str], **kwargs) -> None:
    """Ice Beam: deal 6 damage to an enemy creature."""
    enemy_id = 1 - source_player_id
    if target_slot is None:
        log.append("  Ice Beam: no target")
        return
    slot = state.heroes[enemy_id].board[target_slot]
    if slot.is_occupied:
        _deal_damage_to_slot(state, enemy_id, target_slot, 6, log)
        log[-1] = "  Ice Beam: " + log[-1].strip()
    else:
        log.append(f"  Ice Beam: target slot {target_slot} is empty")


@register_effect("hot_girl_winter")
def hot_girl_winter(state: GameState, source_player_id: int, target_player: int,
                    target_slot: int | None, log: list[str], **kwargs) -> None:
    """Hot Girl Winter: freeze all male minions on the board and shrink them to 1 attack."""
    from models import BuffCard, CardType, TargetType
    log.append("  Hot Girl Winter activates!")
    for owner_id in range(2):
        for slot_idx, slot in enumerate(state.heroes[owner_id].board):
            if slot.is_occupied and slot.creature.gender == "male":
                # Shrunk: reduce attack to 1 via negative buff
                shrink_amount = slot.attack - 1
                if shrink_amount > 0:
                    shrunk_buff = BuffCard(
                        id="shrunk", name="Shrunk", cost=0, card_type=CardType.BUFF,
                        attack_bonus=-shrink_amount, health_bonus=0,
                    )
                    slot.apply_buff(shrunk_buff)
                freeze_slot(state, owner_id, slot_idx, log)
                log.append(f"  {slot.creature.name} (slot {slot_idx}) shrunken and frozen")


@register_effect("blizzard")
def blizzard(state: GameState, source_player_id: int, target_player: int,
             target_slot: int | None, log: list[str], **kwargs) -> None:
    """Blizzard: deal 2 damage to all minions and freeze them."""
    log.append("  Blizzard sweeps the board!")
    for owner_id in range(2):
        for slot_idx, slot in enumerate(state.heroes[owner_id].board):
            if slot.is_occupied:
                _deal_damage_to_slot(state, owner_id, slot_idx, 2, log)
                freeze_slot(state, owner_id, slot_idx, log)


# ---------------------------------------------------------------------------
# Drum Wizard spell effects
# ---------------------------------------------------------------------------

@register_effect("guitar_solo")
def guitar_solo(state: GameState, source_player_id: int, target_player: int,
                target_slot: int | None, log: list[str], **kwargs) -> None:
    """Guitar Solo: your next 5 stack actions happen consecutively."""
    _consecutive_actions(state, source_player_id, 5, log)
    log.append("  Guitar Solo! Next 5 actions shred in a row.")


@register_effect("double_time")
def double_time(state: GameState, source_player_id: int, target_player: int,
                target_slot: int | None, log: list[str], **kwargs) -> None:
    """Double Time: your next 2 stack actions happen consecutively."""
    _consecutive_actions(state, source_player_id, 2, log)
    log.append("  Double Time! Next 2 actions go back-to-back.")


@register_effect("horns_of_power")
def horns_of_power(state: GameState, source_player_id: int, target_player: int,
                   target_slot: int | None, log: list[str], **kwargs) -> None:
    """Horns of Power: double all friendly creatures' attack until end of turn."""
    from models import BuffCard, CardType, TargetType
    hero = state.heroes[source_player_id]
    count = 0
    for slot in hero.board:
        if slot.is_occupied:
            bonus = slot.attack  # current effective attack — adding it again doubles it
            if bonus > 0:
                temp_buff = BuffCard(
                    id="horns_temp", name="Horns of Power", cost=0, card_type=CardType.BUFF,
                    attack_bonus=bonus, health_bonus=0, temporary=True,
                )
                slot.apply_buff(temp_buff)
                count += 1
    log.append(f"  Horns of Power! {count} minion(s) attack doubled this turn.")


@register_effect("horn_of_terror")
def horn_of_terror(state: GameState, source_player_id: int, target_player: int,
                   target_slot: int | None, log: list[str], **kwargs) -> None:
    """Horn of Terror: return an enemy minion to their hand."""
    enemy_id = 1 - source_player_id
    if target_slot is None:
        log.append("  Horn of Terror: no target")
        return
    slot = state.heroes[enemy_id].board[target_slot]
    if not slot.is_occupied:
        log.append(f"  Horn of Terror: slot {target_slot} is empty")
        return
    from events import EventType
    owner_key = f"p{enemy_id}_slot{target_slot}"
    state.event_bus.unsubscribe_owner(owner_key)
    card = slot.creature
    name = card.name
    slot.clear()
    state.heroes[enemy_id].hand.append(card)
    log.append(f"  Horn of Terror: {name} returned to enemy's hand")


@register_effect("grapeshot")
def grapeshot(state: GameState, source_player_id: int, target_player: int,
              target_slot: int | None, log: list[str], **kwargs) -> None:
    """Grapeshot: 6 damage to target enemy slot, 2 to adjacent."""
    enemy_id = 1 - source_player_id
    if target_slot is None:
        log.append("  Grapeshot: no target")
        return
    log.append("  Grapeshot!")
    _deal_damage_to_slot(state, enemy_id, target_slot, 6, log)
    for adj in [target_slot - 1, target_slot + 1]:
        if 0 <= adj < len(state.heroes[enemy_id].board):
            _deal_damage_to_slot(state, enemy_id, adj, 2, log)


@register_effect("mariachi_march")
def mariachi_march(state: GameState, source_player_id: int, target_player: int,
                   target_slot: int | None, log: list[str], **kwargs) -> None:
    """Mariachi March: fill each empty friendly slot with a 2/3 Mariachi Band."""
    import copy
    from cards.definitions import MARIACHI_BAND
    hero = state.heroes[source_player_id]
    spawned = 0
    for slot_idx, slot in enumerate(hero.board):
        if not slot.is_occupied:
            slot.place_creature(copy.deepcopy(MARIACHI_BAND))
            slot.summoned_on_turn = state.turn
            spawned += 1
    log.append(f"  Mariachi March! Summoned {spawned} Mariachi Band(s).")


@register_effect("framemogg")
def framemogg(state: GameState, source_player_id: int, target_player: int,
              target_slot: int | None, log: list[str], **kwargs) -> None:
    """FrameMogg: destroy all board minions with hp < your highest-hp friendly creature."""
    friendly_board = state.heroes[source_player_id].board
    max_hp = max((s.current_health for s in friendly_board if s.is_occupied), default=0)
    if max_hp == 0:
        log.append("  FrameMogg: no friendly creatures, no effect")
        return
    log.append(f"  FrameMogg! Destroying all minions with < {max_hp} HP")
    from events import EventType
    for owner_id in range(2):
        for slot_idx, slot in enumerate(state.heroes[owner_id].board):
            if slot.is_occupied and slot.current_health < max_hp:
                name = slot.creature.name
                owner_key = f"p{owner_id}_slot{slot_idx}"
                state.event_bus.unsubscribe_owner(owner_key)
                on_death = slot.creature.on_death_effect
                slot.clear()
                log.append(f"  {name} destroyed by FrameMogg!")
                if on_death:
                    effect = get_effect(on_death)
                    if effect:
                        effect(state, owner_id, log)


@register_effect("march_of_the_titans")
def march_of_the_titans(state: GameState, source_player_id: int, target_player: int,
                        target_slot: int | None, log: list[str], **kwargs) -> None:
    """March of the Titans: give all friendly creatures +2/+2."""
    from models import BuffCard, CardType, TargetType
    hero = state.heroes[source_player_id]
    count = 0
    for slot in hero.board:
        if slot.is_occupied:
            buff = BuffCard(
                id="march_buff", name="March of the Titans", cost=0, card_type=CardType.BUFF,
                attack_bonus=2, health_bonus=2,
            )
            slot.apply_buff(buff)
            count += 1
    log.append(f"  March of the Titans! {count} minion(s) get +2/+2.")


@register_effect("love_song")
def love_song(state: GameState, source_player_id: int, target_player: int,
              target_slot: int | None, log: list[str], **kwargs) -> None:
    """Love Song: steal an enemy minion — it goes to your hand."""
    enemy_id = 1 - source_player_id
    if target_slot is None:
        log.append("  Love Song: no target")
        return
    slot = state.heroes[enemy_id].board[target_slot]
    if not slot.is_occupied:
        log.append(f"  Love Song: slot {target_slot} is empty")
        return
    from events import EventType
    owner_key = f"p{enemy_id}_slot{target_slot}"
    state.event_bus.unsubscribe_owner(owner_key)
    card = slot.creature
    name = card.name
    slot.clear()
    state.heroes[source_player_id].hand.append(card)
    log.append(f"  Love Song: {name} is yours now")


# ---------------------------------------------------------------------------
# Hidden-attribute targeting effects
# ---------------------------------------------------------------------------

@register_effect("bookmogg")
def bookmogg(state: GameState, source_player_id: int, target_player: int,
             target_slot: int | None, log: list[str], **kwargs) -> None:
    """BookMogg: destroy all minions (both boards) with reading_level <= 6."""
    from events import EventType
    log.append("  BookMogg! Destroying all minions that read at 6th grade or below...")
    destroyed = 0
    for owner_id in range(2):
        for slot_idx, slot in enumerate(state.heroes[owner_id].board):
            if slot.is_occupied and slot.creature.reading_level <= 6:
                name = slot.creature.name
                on_death = slot.creature.on_death_effect
                owner_key = f"p{owner_id}_slot{slot_idx}"
                state.event_bus.unsubscribe_owner(owner_key)
                slot.clear()
                log.append(f"  {name} (reading level {slot.creature.reading_level if slot.creature else '?'}) is destroyed!")
                # Re-fetch name since we just cleared
                log[-1] = f"  {name} is destroyed by BookMogg!"
                destroyed += 1
                if on_death:
                    effect = get_effect(on_death)
                    if effect:
                        effect(state, owner_id, log)
    log.append(f"  BookMogg claimed {destroyed} illiterate minion(s).")


@register_effect("pastamax")
def pastamax(state: GameState, source_player_id: int, target_player: int,
             target_slot: int | None, log: list[str], **kwargs) -> None:
    """PastaMax: give each friendly creature +X/+X equal to its noodle score."""
    from models import BuffCard, CardType
    hero = state.heroes[source_player_id]
    count = 0
    for slot in hero.board:
        if slot.is_occupied:
            n = slot.creature.noodles
            if n > 0:
                buff = BuffCard(
                    id="pasta_buff", name="PastaMax", cost=0, card_type=CardType.BUFF,
                    attack_bonus=n, health_bonus=n,
                )
                slot.apply_buff(buff)
                log.append(f"  PastaMax: {slot.creature.name} gets +{n}/+{n} (noodle score {n})")
                count += 1
    log.append(f"  PastaMax pumped {count} minion(s)!")


@register_effect("ficomax")
def ficomax(state: GameState, source_player_id: int, target_player: int,
            target_slot: int | None, log: list[str], **kwargs) -> None:
    """FicoMax: each friendly creature gains attack equal to fico/50 - 12."""
    from models import BuffCard, CardType
    hero = state.heroes[source_player_id]
    count = 0
    for slot in hero.board:
        if slot.is_occupied:
            bonus = int(slot.creature.fico / 50) - 12
            if bonus == 0:
                log.append(f"  FicoMax: {slot.creature.name} (FICO {slot.creature.fico}) — no change")
                continue
            # Allow negative bonus (bad credit hurts), but clamp so attack can't go below 0
            bonus = max(-slot.creature.attack, bonus)
            buff = BuffCard(
                id="fico_buff", name="FicoMax", cost=0, card_type=CardType.BUFF,
                attack_bonus=bonus, health_bonus=0,
            )
            slot.apply_buff(buff)
            sign = "+" if bonus >= 0 else ""
            log.append(f"  FicoMax: {slot.creature.name} (FICO {slot.creature.fico}) gets {sign}{bonus} attack")
            count += 1
    log.append(f"  FicoMax affected {count} minion(s)!")


# ---------------------------------------------------------------------------
# Blood Witch card effects
# ---------------------------------------------------------------------------

@register_effect("black_cat_register")
def black_cat_register(state: GameState, source_player_id: int, log: list[str],
                       target_slot: int | None = None, **kwargs) -> None:
    """Black Cat: subscribe ON_TURN_END — draw an extra card while alive."""
    from events import EventType
    if target_slot is None:
        return
    owner_key = f"p{source_player_id}_slot{target_slot}"

    def on_turn_end(s, lg, **kw):
        slot = s.heroes[source_player_id].board[target_slot]
        if slot.is_occupied and slot.creature.id == "black_cat":
            hero = s.heroes[source_player_id]
            if hero.deck:
                card = hero.deck.pop(0)
                hero.hand.append(card)
                lg.append(f"  Black Cat draws {hero.name} an extra card: {card.name}")

    state.event_bus.subscribe(EventType.ON_TURN_END, owner_key, on_turn_end)
    log.append(f"  Black Cat registered end-of-turn draw")


@register_effect("bat_ninja_return")
def bat_ninja_return(state: GameState, source_player_id: int, target_player: int,
                     target_slot: int | None, log: list[str], **kwargs) -> None:
    """Bat Ninja: after dealing damage to a creature, return it to its owner's hand."""
    if target_player is None or target_slot is None:
        return
    slot = state.heroes[target_player].board[target_slot]
    if not slot.is_occupied:
        return
    from events import EventType
    owner_key = f"p{target_player}_slot{target_slot}"
    state.event_bus.unsubscribe_owner(owner_key)
    card = slot.creature
    name = card.name
    slot.clear()
    state.heroes[target_player].hand.append(card)
    log.append(f"  Bat Ninja: {name} is returned to hand!")


@register_effect("reverse_stack")
def reverse_stack(state: GameState, source_player_id: int, log: list[str],
                  target_slot: int | None = None, **kwargs) -> None:
    """Hone of Tinderlost: reverse the remaining action stack."""
    stack = state.current_stack
    if stack:
        stack.reverse()
        log.append(f"  Hone of Tinderlost: the stack has been reversed! ({len(stack)} actions)")
    else:
        log.append(f"  Hone of Tinderlost: stack is empty, nothing to reverse")


@register_effect("vampire_buff_females")
def vampire_buff_females(state: GameState, source_player_id: int, log: list[str],
                         target_slot: int | None = None, **kwargs) -> None:
    """Hot Vampire Dude: give all female creatures on the board +2 health."""
    from models import BuffCard, CardType
    count = 0
    for owner_id in range(2):
        for slot in state.heroes[owner_id].board:
            if slot.is_occupied and slot.creature.gender == "female":
                buff = BuffCard(
                    id="vampire_buff", name="Vampire Aura", cost=0, card_type=CardType.BUFF,
                    attack_bonus=0, health_bonus=2,
                )
                slot.apply_buff(buff)
                log.append(f"  Hot Vampire Dude: {slot.creature.name} gets +2 health")
                count += 1
    log.append(f"  Hot Vampire Dude: {count} female creature(s) buffed!")


@register_effect("voodoo_doll_register")
def voodoo_doll_register(state: GameState, source_player_id: int, target_player_id: int,
                          target_slot: int | None, log: list[str], **kwargs) -> None:
    """Voodoo Doll: when the enchanted minion takes X damage, deal 2X to the enemy hero."""
    from events import EventType
    if target_slot is None:
        return
    owner_key = f"voodoo_{source_player_id}_p{target_player_id}_slot{target_slot}"
    enemy_id = 1 - source_player_id

    def on_damage_handler(gs, dmg_player_id, dmg_slot_idx, amount, lg, **kw):
        if dmg_player_id == target_player_id and dmg_slot_idx == target_slot:
            slot = gs.heroes[target_player_id].board[target_slot]
            # Check voodoo doll still active on this slot
            if slot.is_occupied and any(b.id == "voodoo_doll" for b in slot.buffs):
                enemy = gs.heroes[enemy_id]
                voodoo_dmg = amount * 2
                enemy.hp -= voodoo_dmg
                lg.append(f"  Voodoo Doll: {enemy.name} takes {voodoo_dmg} voodoo damage!")

    state.event_bus.subscribe(EventType.ON_DAMAGE, owner_key, on_damage_handler)
    log.append(f"  Voodoo Doll attached! Damage to minion → 2x damage to enemy hero.")


# ---------------------------------------------------------------------------
# Hero power effects
# ---------------------------------------------------------------------------

@register_effect("hero_power_ice_witch")
def hero_power_ice_witch(state: GameState, source_player_id: int, target_player: int,
                         target_slot: int | None, log: list[str], **kwargs) -> None:
    """Ice Witch — Frost Shard: deal 2 damage to any target."""
    if target_player is None:
        target_player = 1 - source_player_id
    _apply_spell_damage(state, source_player_id, target_player, target_slot, 2, "Frost Shard", log)


@register_effect("hero_power_drum_wizard")
def hero_power_drum_wizard(state: GameState, source_player_id: int, target_player: int,
                            target_slot: int | None, log: list[str], **kwargs) -> None:
    """Drum Wizard — Tempo Freeze: freeze a target creature."""
    if target_player is None or target_slot is None:
        log.append("  Tempo Freeze: no target")
        return
    slot = state.heroes[target_player].board[target_slot]
    if not slot.is_occupied:
        log.append(f"  Tempo Freeze: slot {target_slot} is empty")
        return
    freeze_slot(state, target_player, target_slot, log)


@register_effect("hero_power_blood_witch")
def hero_power_blood_witch(state: GameState, source_player_id: int, target_player: int,
                            target_slot: int | None, log: list[str], **kwargs) -> None:
    """Blood Witch — Sacrifice: destroy a friendly minion, gain mana equal to its cost."""
    if target_player is None or target_slot is None:
        log.append("  Sacrifice: no target selected")
        return
    # Sacrifice must target own creature
    slot = state.heroes[source_player_id].board[target_slot]
    if not slot.is_occupied:
        log.append(f"  Sacrifice: slot {target_slot} is empty")
        return

    hero = state.heroes[source_player_id]
    card = slot.creature
    name = card.name
    cost = card.cost

    # Destroy the creature
    from events import EventType
    owner_key = f"p{source_player_id}_slot{target_slot}"
    state.event_bus.unsubscribe_owner(owner_key)
    on_death = card.on_death_effect
    slot.clear()
    log.append(f"  Sacrifice: {name} is sacrificed!")

    if on_death:
        effect = get_effect(on_death)
        if effect:
            effect(state, source_player_id, log)
    state.event_bus.dispatch(EventType.ON_DEATH, state, source_player_id, target_slot, log)

    # Gain mana equal to the creature's cost (up to max)
    gained = min(cost, hero.max_mana - hero.current_mana)
    if gained > 0:
        hero.current_mana += gained
        log.append(f"  Sacrifice: {hero.name} gained {gained} mana ({hero.current_mana}/{hero.max_mana})")
    else:
        log.append(f"  Sacrifice: mana already at max, no mana gained")


# ---------------------------------------------------------------------------
# Spellbook — draw spell (timing="prep")
# ---------------------------------------------------------------------------

@register_effect("spellbook")
def spellbook(state: GameState, source_player_id: int, target_player: int,
              target_slot: int | None, log: list[str], **kwargs) -> None:
    """Spellbook: add 3 random spells to your hand."""
    import random
    from cards.definitions import SPELL_POOL, get_card
    hero = state.heroes[source_player_id]
    choices = random.sample(SPELL_POOL, min(3, len(SPELL_POOL)))
    for cid in choices:
        card = get_card(cid)
        hero.hand.append(card)
        log.append(f"  Spellbook: {hero.name} gets {card.name}")
    log.append(f"  Spellbook: {hero.name} added 3 spells to hand!")


@register_effect("beauty_contest")
def beauty_contest(state: GameState, source_player_id: int, target_player: int,
                   target_slot: int | None, log: list[str], **kwargs) -> None:
    """Beauty Contest: at end of turn, the player with the best-looking minion draws 3 cards."""
    from events import EventType
    owner_key = f"p{source_player_id}_beauty_contest_{state.turn}"

    def on_turn_end_beauty(s, lg):
        # Find max looks for each player
        best = [-1, -1]
        for pid in range(2):
            for slot in s.heroes[pid].board:
                if slot.is_occupied:
                    if slot.creature.looks > best[pid]:
                        best[pid] = slot.creature.looks

        if best[0] == -1 and best[1] == -1:
            lg.append("  Beauty Contest: no minions on the board — no winner")
            return

        if best[0] > best[1]:
            winner_id = 0
        elif best[1] > best[0]:
            winner_id = 1
        else:
            lg.append(f"  Beauty Contest: tie at looks {best[0]} — no one draws")
            return

        winner = s.heroes[winner_id]
        drawn = 0
        for _ in range(3):
            if winner.deck:
                card = winner.deck.pop(0)
                winner.hand.append(card)
                drawn += 1
        lg.append(f"  Beauty Contest: {winner.name} wins with looks {best[winner_id]}! Draws {drawn} card(s)!")

        # Unsubscribe so it only fires once
        s.event_bus.unsubscribe_owner(owner_key)

    state.event_bus.subscribe(EventType.ON_TURN_END, owner_key, on_turn_end_beauty)
    log.append("  Beauty Contest registered — winner draws 3 at end of turn!")


# ---------------------------------------------------------------------------
# New neutral card effects
# ---------------------------------------------------------------------------

@register_effect("tasty_fish_death")
def tasty_fish_death(state: GameState, dead_player_id: int, log: list[str], **kwargs) -> None:
    """Tasty Fish deathrattle: restore 3 HP to your hero."""
    from config import STARTING_HP
    hero = state.heroes[dead_player_id]
    healed = min(3, STARTING_HP - hero.hp)
    hero.hp += healed
    log.append(f"  Tasty Fish deathrattle: {hero.name} restores {healed} HP ({hero.hp} HP)")


@register_effect("survivor_draw_card")
def survivor_draw_card(state: GameState, source_player_id: int, log: list[str],
                       target_slot: int | None = None, **kwargs) -> None:
    """Survivor: draw a card at end of turn while this creature lives."""
    from events import EventType
    if target_slot is None:
        return
    owner_key = f"p{source_player_id}_slot{target_slot}"
    creature_id = state.heroes[source_player_id].board[target_slot].creature.id

    def on_turn_end(s, lg, **kw):
        slot = s.heroes[source_player_id].board[target_slot]
        if slot.is_occupied and slot.creature.id == creature_id:
            hero = s.heroes[source_player_id]
            if hero.deck:
                card = hero.deck.pop(0)
                hero.hand.append(card)
                lg.append(f"  {slot.creature.name} Survivor: {hero.name} draws {card.name}")

    state.event_bus.subscribe(EventType.ON_TURN_END, owner_key, on_turn_end)
    creature_name = state.heroes[source_player_id].board[target_slot].creature.name
    log.append(f"  {creature_name} Survivor registered — draw a card each turn")


@register_effect("survivor_heal_3")
def survivor_heal_3(state: GameState, source_player_id: int, log: list[str],
                    target_slot: int | None = None, **kwargs) -> None:
    """Survivor: restore 3 HP to your hero at end of turn while this creature lives."""
    from events import EventType
    from config import STARTING_HP
    if target_slot is None:
        return
    owner_key = f"p{source_player_id}_slot{target_slot}"
    creature_id = state.heroes[source_player_id].board[target_slot].creature.id

    def on_turn_end(s, lg, **kw):
        slot = s.heroes[source_player_id].board[target_slot]
        if slot.is_occupied and slot.creature.id == creature_id:
            hero = s.heroes[source_player_id]
            healed = min(3, STARTING_HP - hero.hp)
            if healed > 0:
                hero.hp += healed
                lg.append(f"  {slot.creature.name} Survivor: {hero.name} heals {healed} HP ({hero.hp} HP)")

    state.event_bus.subscribe(EventType.ON_TURN_END, owner_key, on_turn_end)
    creature_name = state.heroes[source_player_id].board[target_slot].creature.name
    log.append(f"  {creature_name} Survivor registered — heal 3 HP each turn")


@register_effect("armored_1")
def armored_1(state: GameState, victim_player_id: int, slot_idx: int,
              attacker_player_id: int, attacker_slot_idx: int | None,
              log: list[str], **kwargs) -> None:
    """Armored 1: heal back 1 HP after each hit (effectively reduces all damage by 1)."""
    slot = state.heroes[victim_player_id].board[slot_idx]
    if slot.is_occupied:
        slot.current_health += 1
        log.append(f"  Armor! {slot.creature.name} shrugs off 1 damage ({slot.current_health} HP)")


@register_effect("sinister_spy_reveal")
def sinister_spy_reveal(state: GameState, source_player_id: int, log: list[str],
                        target_slot: int | None = None, **kwargs) -> None:
    """Sinister Spy: reveal the opponent's hand in the resolution log."""
    enemy_id = 1 - source_player_id
    enemy = state.heroes[enemy_id]
    hand_names = [c.name for c in enemy.hand]
    if hand_names:
        log.append(f"  Sinister Spy: {enemy.name}'s hand revealed — {', '.join(hand_names)}")
    else:
        log.append(f"  Sinister Spy: {enemy.name}'s hand is empty!")


@register_effect("weird_fish_reverse")
def weird_fish_reverse(state: GameState, source_player_id: int, log: list[str],
                       target_slot: int | None = None, **kwargs) -> None:
    """Weird Fish: reverse the remaining action stack."""
    stack = state.current_stack
    if stack:
        stack.reverse()
        log.append(f"  Weird Fish: the stack has been reversed! ({len(stack)} actions)")
    else:
        log.append(f"  Weird Fish: stack is empty, nothing to reverse")


@register_effect("barbarian_beastmaster_send")
def barbarian_beastmaster_send(state: GameState, source_player_id: int, log: list[str],
                               target_slot: int | None = None, **kwargs) -> None:
    """Barbarian Beastmaster: Battle Cry — remove a random enemy animal (thumbs=0) from the board.
    NOTE: Zoo storage not yet implemented; creature is simply banished."""
    import random
    enemy_id = 1 - source_player_id
    enemy_board = state.heroes[enemy_id].board
    candidates = [(i, s) for i, s in enumerate(enemy_board)
                  if s.is_occupied and s.creature.thumbs == 0]
    if not candidates:
        log.append(f"  Barbarian Beastmaster: no animals (0 thumbs) on enemy board")
        return
    idx, slot = random.choice(candidates)
    name = slot.creature.name
    on_death = slot.creature.on_death_effect
    owner_key = f"p{enemy_id}_slot{idx}"
    state.event_bus.unsubscribe_owner(owner_key)
    slot.clear()
    log.append(f"  Barbarian Beastmaster: {name} sent to the Zoo!")
    if on_death:
        effect = get_effect(on_death)
        if effect:
            effect(state, enemy_id, log)


@register_effect("sheriff_jail")
def sheriff_jail(state: GameState, source_player_id: int, log: list[str],
                 target_slot: int | None = None, **kwargs) -> None:
    """Sheriff of Nottingham: Battle Cry — remove a random enemy debtor (FICO < 600) from the board.
    NOTE: County Jail storage not yet implemented; creature is simply banished."""
    import random
    enemy_id = 1 - source_player_id
    enemy_board = state.heroes[enemy_id].board
    candidates = [(i, s) for i, s in enumerate(enemy_board)
                  if s.is_occupied and s.creature.fico < 600]
    if not candidates:
        log.append(f"  Sheriff of Nottingham: no debtors (FICO < 600) on enemy board")
        return
    idx, slot = random.choice(candidates)
    name = slot.creature.name
    fico = slot.creature.fico
    on_death = slot.creature.on_death_effect
    owner_key = f"p{enemy_id}_slot{idx}"
    state.event_bus.unsubscribe_owner(owner_key)
    slot.clear()
    log.append(f"  Sheriff of Nottingham: {name} (FICO {fico}) thrown in county jail!")
    if on_death:
        effect = get_effect(on_death)
        if effect:
            effect(state, enemy_id, log)


@register_effect("negligent_zookeeper_draw")
def negligent_zookeeper_draw(state: GameState, source_player_id: int, log: list[str],
                              target_slot: int | None = None, **kwargs) -> None:
    """Negligent Zookeeper: Battle Cry — draw 3 minions from the Zoo.
    STUB: Zoo mechanic not yet implemented."""
    log.append(f"  Negligent Zookeeper: the Zoo is empty... (Zoo mechanic not yet implemented)")


@register_effect("corrupted_zookeeper_purge")
def corrupted_zookeeper_purge(state: GameState, source_player_id: int, log: list[str],
                               target_slot: int | None = None, **kwargs) -> None:
    """Corrupted Zookeeper: Battle Cry — send all Zoo animals to the Shadow Realm.
    STUB: Zoo + Shadow Realm mechanics not yet implemented."""
    log.append(f"  Corrupted Zookeeper: no one was in the Zoo... (Zoo mechanic not yet implemented)")


# ---------------------------------------------------------------------------
# Bloodlust effects — fire via on_attack_effect when target_slot == -1 (hero hit)
# ---------------------------------------------------------------------------

@register_effect("snake_oil_bloodlust")
def snake_oil_bloodlust(state: GameState, source_player_id: int, log: list[str],
                        attacker_slot: int | None = None, target_slot: int | None = None,
                        **kwargs) -> bool:
    """Snake Oil Salesman Bloodlust: when hitting the enemy hero, reduce all enemy minion attacks to 1."""
    if target_slot != -1:
        return True  # only on hero hits
    from models import BuffCard, CardType
    enemy_id = 1 - source_player_id
    affected = 0
    for slot in state.heroes[enemy_id].board:
        if slot.is_occupied:
            current_attack = slot.attack
            if current_attack > 1:
                debuff = BuffCard(
                    id="snake_oil_debuff", name="Snake Oil", cost=0, card_type=CardType.BUFF,
                    attack_bonus=-(current_attack - 1), health_bonus=0,
                )
                slot.apply_buff(debuff)
                affected += 1
    if affected > 0:
        log.append(f"  Snake Oil Salesman Bloodlust! {affected} enemy minion(s) reduced to 1 attack")
    return True


@register_effect("musical_bandit_bloodlust")
def musical_bandit_bloodlust(state: GameState, source_player_id: int, log: list[str],
                              attacker_slot: int | None = None, target_slot: int | None = None,
                              **kwargs) -> bool:
    """Musical Bandit Bloodlust: when hitting the enemy hero, draw a card."""
    if target_slot != -1:
        return True  # only on hero hits
    from events import EventType
    hero = state.heroes[source_player_id]
    if hero.deck:
        card = hero.deck.pop(0)
        hero.hand.append(card)
        log.append(f"  Musical Bandit Bloodlust! {hero.name} draws {card.name}")
        state.event_bus.dispatch(EventType.ON_DRAW, state, source_player_id, card, log)
    else:
        log.append(f"  Musical Bandit Bloodlust! {hero.name}'s deck is empty")
    return True


@register_effect("skinny_blood_witch_bloodlust")
def skinny_blood_witch_bloodlust(state: GameState, source_player_id: int, log: list[str],
                                  attacker_slot: int | None = None, target_slot: int | None = None,
                                  **kwargs) -> bool:
    """Skinny Blood Witch Bloodlust: when hitting the enemy hero, summon from shadow realm.
    STUB: Shadow Realm mechanic not yet implemented."""
    if target_slot != -1:
        return True
    log.append(f"  Skinny Blood Witch Bloodlust! [Shadow Realm not yet implemented]")
    return True


# ---------------------------------------------------------------------------
# Mogg & Max spell effects (new neutral spells)
# ---------------------------------------------------------------------------

def _mogg_remove(state: GameState, owner_id: int, slot_idx: int,
                 log: list[str], flavor: str) -> bool:
    """Remove a minion from the board, fire its death effect, and log with flavor text."""
    slot = state.heroes[owner_id].board[slot_idx]
    if not slot.is_occupied:
        return False
    name = slot.creature.name
    on_death = slot.creature.on_death_effect
    state.event_bus.unsubscribe_owner(f"p{owner_id}_slot{slot_idx}")
    slot.clear()
    log.append(f"  {name} {flavor}!")
    if on_death:
        fn = get_effect(on_death)
        if fn:
            fn(state, owner_id, log)
    return True


# --- Choose-a-friendly Moggs ---

@register_effect("thumbmogg")
def thumbmogg(state: GameState, source_player_id: int, target_player: int,
              target_slot: int | None, log: list[str], **kwargs) -> None:
    """ThumbMogg: send all minions with fewer thumbs than the chosen friendly to the Zoo."""
    if target_slot is None or not state.heroes[target_player].board[target_slot].is_occupied:
        log.append("  ThumbMogg: no valid target"); return
    pivot = state.heroes[target_player].board[target_slot].creature
    threshold = pivot.thumbs
    log.append(f"  ThumbMogg! {pivot.name} ({threshold} thumbs) — purging low-thumb minions to Zoo...")
    removed = 0
    for owner_id in range(2):
        for slot_idx in range(len(state.heroes[owner_id].board)):
            if owner_id == target_player and slot_idx == target_slot:
                continue
            slot = state.heroes[owner_id].board[slot_idx]
            if slot.is_occupied and slot.creature.thumbs < threshold:
                t = slot.creature.thumbs
                if _mogg_remove(state, owner_id, slot_idx, log, f"sent to the Zoo ({t} thumbs < {threshold})"):
                    removed += 1
    log.append(f"  ThumbMogg: {removed} minion(s) banished to the Zoo!")


@register_effect("ficomogg")
def ficomogg(state: GameState, source_player_id: int, target_player: int,
             target_slot: int | None, log: list[str], **kwargs) -> None:
    """FicoMogg: destroy all minions with a lower FICO score than the chosen friendly."""
    if target_slot is None or not state.heroes[target_player].board[target_slot].is_occupied:
        log.append("  FicoMogg: no valid target"); return
    pivot = state.heroes[target_player].board[target_slot].creature
    threshold = pivot.fico
    log.append(f"  FicoMogg! {pivot.name} (FICO {threshold}) — low-credit minions beware...")
    removed = 0
    for owner_id in range(2):
        for slot_idx in range(len(state.heroes[owner_id].board)):
            if owner_id == target_player and slot_idx == target_slot:
                continue
            slot = state.heroes[owner_id].board[slot_idx]
            if slot.is_occupied and slot.creature.fico < threshold:
                f_val = slot.creature.fico
                if _mogg_remove(state, owner_id, slot_idx, log, f"destroyed (FICO {f_val} < {threshold})"):
                    removed += 1
    log.append(f"  FicoMogg: {removed} low-credit minion(s) destroyed!")


@register_effect("heighmogg")
def heighmogg(state: GameState, source_player_id: int, target_player: int,
              target_slot: int | None, log: list[str], **kwargs) -> None:
    """HeighMogg: destroy all male minions shorter than the chosen friendly."""
    if target_slot is None or not state.heroes[target_player].board[target_slot].is_occupied:
        log.append("  HeighMogg: no valid target"); return
    pivot = state.heroes[target_player].board[target_slot].creature
    threshold = pivot.height_cm
    log.append(f"  HeighMogg! {pivot.name} ({threshold}cm) — short kings eliminated...")
    removed = 0
    for owner_id in range(2):
        for slot_idx in range(len(state.heroes[owner_id].board)):
            if owner_id == target_player and slot_idx == target_slot:
                continue
            slot = state.heroes[owner_id].board[slot_idx]
            if slot.is_occupied and slot.creature.gender == "male" and slot.creature.height_cm < threshold:
                h = slot.creature.height_cm
                if _mogg_remove(state, owner_id, slot_idx, log, f"destroyed (too short: {h}cm < {threshold}cm)"):
                    removed += 1
    log.append(f"  HeighMogg: {removed} short male minion(s) destroyed!")


@register_effect("pastamogg")
def pastamogg(state: GameState, source_player_id: int, target_player: int,
              target_slot: int | None, log: list[str], **kwargs) -> None:
    """PastaMogg: send all minions that eat less pasta than the chosen friendly to the Shadow Realm."""
    if target_slot is None or not state.heroes[target_player].board[target_slot].is_occupied:
        log.append("  PastaMogg: no valid target"); return
    pivot = state.heroes[target_player].board[target_slot].creature
    threshold = pivot.noodles
    log.append(f"  PastaMogg! {pivot.name} (noodles: {threshold}) — light eaters banished...")
    removed = 0
    for owner_id in range(2):
        for slot_idx in range(len(state.heroes[owner_id].board)):
            if owner_id == target_player and slot_idx == target_slot:
                continue
            slot = state.heroes[owner_id].board[slot_idx]
            if slot.is_occupied and slot.creature.noodles < threshold:
                n = slot.creature.noodles
                if _mogg_remove(state, owner_id, slot_idx, log, f"sent to Shadow Realm (noodles: {n} < {threshold})"):
                    removed += 1
    log.append(f"  PastaMogg: {removed} picky eater(s) banished to the Shadow Realm!")


@register_effect("bookmogg_choose")
def bookmogg_choose(state: GameState, source_player_id: int, target_player: int,
                    target_slot: int | None, log: list[str], **kwargs) -> None:
    """BookMogg: destroy all minions that read at a lower level than the chosen friendly."""
    if target_slot is None or not state.heroes[target_player].board[target_slot].is_occupied:
        log.append("  BookMogg: no valid target"); return
    pivot = state.heroes[target_player].board[target_slot].creature
    threshold = pivot.reading_level
    log.append(f"  BookMogg! {pivot.name} (grade {threshold}) — illiterates beware...")
    removed = 0
    for owner_id in range(2):
        for slot_idx in range(len(state.heroes[owner_id].board)):
            if owner_id == target_player and slot_idx == target_slot:
                continue
            slot = state.heroes[owner_id].board[slot_idx]
            if slot.is_occupied and slot.creature.reading_level < threshold:
                rl = slot.creature.reading_level
                if _mogg_remove(state, owner_id, slot_idx, log, f"destroyed (grade {rl} < {threshold})"):
                    removed += 1
    log.append(f"  BookMogg: {removed} illiterate minion(s) purged!")


@register_effect("looksmogg")
def looksmogg(state: GameState, source_player_id: int, target_player: int,
              target_slot: int | None, log: list[str], **kwargs) -> None:
    """LooksMogg: destroy all minions less good-looking than the chosen friendly."""
    if target_slot is None or not state.heroes[target_player].board[target_slot].is_occupied:
        log.append("  LooksMogg: no valid target"); return
    pivot = state.heroes[target_player].board[target_slot].creature
    threshold = pivot.looks
    log.append(f"  LooksMogg! {pivot.name} (looks: {threshold}/10) — uglies beware...")
    removed = 0
    for owner_id in range(2):
        for slot_idx in range(len(state.heroes[owner_id].board)):
            if owner_id == target_player and slot_idx == target_slot:
                continue
            slot = state.heroes[owner_id].board[slot_idx]
            if slot.is_occupied and slot.creature.looks < threshold:
                lk = slot.creature.looks
                if _mogg_remove(state, owner_id, slot_idx, log, f"destroyed (looks {lk} < {threshold})"):
                    removed += 1
    log.append(f"  LooksMogg: {removed} ugly minion(s) destroyed!")


# --- Auto-targeting Moggs ---

@register_effect("legalmogg")
def legalmogg(state: GameState, source_player_id: int, target_player: int,
              target_slot: int | None, log: list[str], **kwargs) -> None:
    """LegalMogg: send all minions with reading_level <= 6 to county jail."""
    log.append("  LegalMogg! Rounding up all 6th-grade-or-below readers...")
    removed = 0
    for owner_id in range(2):
        for slot_idx in range(len(state.heroes[owner_id].board)):
            slot = state.heroes[owner_id].board[slot_idx]
            if slot.is_occupied and slot.creature.reading_level <= 6:
                rl = slot.creature.reading_level
                if _mogg_remove(state, owner_id, slot_idx, log, f"sent to county jail (grade {rl})"):
                    removed += 1
    log.append(f"  LegalMogg: {removed} minion(s) jailed!")


@register_effect("fistmogg")
def fistmogg(state: GameState, source_player_id: int, target_player: int,
             target_slot: int | None, log: list[str], **kwargs) -> None:
    """FistMogg: destroy all minions with less than 2 effective attack."""
    log.append("  FistMogg! Destroying all minions with less than 2 attack...")
    removed = 0
    for owner_id in range(2):
        for slot_idx in range(len(state.heroes[owner_id].board)):
            slot = state.heroes[owner_id].board[slot_idx]
            if slot.is_occupied and slot.attack < 2:
                atk = slot.attack
                if _mogg_remove(state, owner_id, slot_idx, log, f"destroyed (attack {atk} < 2)"):
                    removed += 1
    log.append(f"  FistMogg: {removed} weakling(s) destroyed!")


# --- Persistent Max spells ---

@register_effect("looksmax")
def looksmax(state: GameState, source_player_id: int, target_player: int,
             target_slot: int | None, log: list[str], **kwargs) -> None:
    """LooksMax: each turn end — if your minion is most beautiful, draw a card. Otherwise self-destruct."""
    from events import EventType
    owner_key = f"p{source_player_id}_looksmax_{state.turn}"

    def on_turn_end(s, lg, **kw):
        best = [
            max((slot.creature.looks for slot in s.heroes[pid].board if slot.is_occupied), default=-1)
            for pid in range(2)
        ]
        if best[source_player_id] > best[1 - source_player_id]:
            hero = s.heroes[source_player_id]
            if hero.deck:
                card = hero.deck.pop(0)
                hero.hand.append(card)
                lg.append(f"  LooksMax: {hero.name} wins the beauty check! Draws {card.name}")
            else:
                lg.append(f"  LooksMax: {hero.name} wins looks — deck is empty!")
        else:
            s.event_bus.unsubscribe_owner(owner_key)
            if best[0] == best[1]:
                lg.append(f"  LooksMax: it's a tie — LooksMax self-destructs!")
            else:
                lg.append(f"  LooksMax: {s.heroes[source_player_id].name} lost the beauty contest — LooksMax self-destructs!")

    state.event_bus.subscribe(EventType.ON_TURN_END, owner_key, on_turn_end)
    log.append(f"  LooksMax registered — draw a card each turn your minion is the most beautiful!")


@register_effect("pastamax_persistent")
def pastamax_persistent(state: GameState, source_player_id: int, target_player: int,
                        target_slot: int | None, log: list[str], **kwargs) -> None:
    """PastaMax: each turn end — if your minion eats the most, give friendlies +2 health. Otherwise self-destruct."""
    from events import EventType
    owner_key = f"p{source_player_id}_pastamax_{state.turn}"

    def on_turn_end(s, lg, **kw):
        best = [
            max((slot.creature.noodles for slot in s.heroes[pid].board if slot.is_occupied), default=-1)
            for pid in range(2)
        ]
        if best[source_player_id] > best[1 - source_player_id]:
            from models import BuffCard, CardType
            count = 0
            for slot in s.heroes[source_player_id].board:
                if slot.is_occupied:
                    buff = BuffCard(
                        id="pastamax_buff", name="PastaMax", cost=0, card_type=CardType.BUFF,
                        attack_bonus=0, health_bonus=2,
                    )
                    slot.apply_buff(buff)
                    count += 1
            lg.append(f"  PastaMax: {s.heroes[source_player_id].name} wins the pasta check! {count} minion(s) get +2 health")
        else:
            s.event_bus.unsubscribe_owner(owner_key)
            if best[0] == best[1]:
                lg.append(f"  PastaMax: it's a tie — PastaMax self-destructs!")
            else:
                lg.append(f"  PastaMax: {s.heroes[source_player_id].name} lost the pasta contest — PastaMax self-destructs!")

    state.event_bus.subscribe(EventType.ON_TURN_END, owner_key, on_turn_end)
    log.append(f"  PastaMax registered — buff friendlies +2 health each turn you have the hungriest minion!")
