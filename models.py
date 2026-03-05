from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from config import STARTING_HP, MAX_MANA, BOARD_SIZE


class CardType(str, Enum):
    CREATURE = "creature"
    SPELL = "spell"
    BUFF = "buff"


class TargetType(str, Enum):
    ANY_TARGET = "any_target"
    ENEMY_HERO = "enemy_hero"
    FRIENDLY_HERO = "friendly_hero"
    FRIENDLY_CREATURE = "friendly_creature"
    ENEMY_CREATURE = "enemy_creature"


class Phase(str, Enum):
    LOBBY = "lobby"
    START = "start"
    MULLIGAN = "mulligan"
    PREP = "prep"
    RESOLUTION = "resolution"
    END = "end"


@dataclass
class Card:
    id: str
    name: str
    cost: int
    card_type: CardType
    timing: str = "stack"   # "prep" or "stack"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "cost": self.cost,
            "card_type": self.card_type.value,
            "timing": self.timing,
        }


@dataclass
class CreatureCard(Card):
    attack: int = 0
    max_health: int = 1
    on_play_effect: str | None = None
    on_death_effect: str | None = None
    on_damage_effect: str | None = None
    on_attack_effect: str | None = None
    on_kill_effect: str | None = None
    post_attack_effect: str | None = None   # fires after attack damage is dealt to a creature
    gender: str = "neutral"   # "male" / "female" / "neutral"
    riposte: bool = False
    charge: bool = False
    enrage: int = 0           # attack bonus added each time this creature takes damage
    shield_wall: int = 0      # on-play: give adjacent friendly creatures +X/+X
    # Hidden server-side attributes (never sent to client)
    looks: int = 5            # 1-10 appearance score
    fico: int = 650           # 300-800 credit score
    height_cm: int = 170      # height in centimeters
    reading_level: int = 8    # US grade level (1-12+)
    social_credit: int = 750  # Chinese social credit score
    noodles: int = 5          # 1-10 bowls of noodles capacity
    thumbs: int = 2           # 0 = no thumbs (animal), 2 = normal hands, 4 = extra arms

    def __post_init__(self):
        self.card_type = CardType.CREATURE

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "attack": self.attack,
            "max_health": self.max_health,
            "on_play_effect": self.on_play_effect,
            "on_death_effect": self.on_death_effect,
            "on_damage_effect": self.on_damage_effect,
            "on_attack_effect": self.on_attack_effect,
            "on_kill_effect": self.on_kill_effect,
            "post_attack_effect": self.post_attack_effect,
            "gender": self.gender,
            "riposte": self.riposte,
            "charge": self.charge,
            "enrage": self.enrage,
            "shield_wall": self.shield_wall,
            # Hidden attrs — included for server-side storage; stripped before sending to client
            "looks": self.looks,
            "fico": self.fico,
            "height_cm": self.height_cm,
            "reading_level": self.reading_level,
            "social_credit": self.social_credit,
            "noodles": self.noodles,
            "thumbs": self.thumbs,
        })
        return d


@dataclass
class SpellCard(Card):
    on_play_effect: str = ""
    target_type: TargetType = TargetType.ANY_TARGET
    description: str = ""

    def __post_init__(self):
        if self.card_type not in (CardType.SPELL, CardType.BUFF):
            self.card_type = CardType.SPELL

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "on_play_effect": self.on_play_effect,
            "target_type": self.target_type.value,
            "description": self.description,
        })
        return d


@dataclass
class BuffCard(SpellCard):
    attack_bonus: int = 0
    health_bonus: int = 0
    temporary: bool = False   # if True, removed at end of turn

    def __post_init__(self):
        self.card_type = CardType.BUFF

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "attack_bonus": self.attack_bonus,
            "health_bonus": self.health_bonus,
            "temporary": self.temporary,
        })
        return d


@dataclass
class BoardSlot:
    creature: CreatureCard | None = None
    current_health: int = 0
    buffs: list[BuffCard] = field(default_factory=list)
    summoned_on_turn: int | None = None  # set when placed; prevents attacking same turn
    frozen: bool = False                  # next attack from this slot moves to stack bottom
    enrage_bonus: int = 0                 # accumulated from Enrage triggers

    @property
    def is_occupied(self) -> bool:
        return self.creature is not None

    @property
    def attack(self) -> int:
        if self.creature is None:
            return 0
        return max(0, self.creature.attack + sum(b.attack_bonus for b in self.buffs) + self.enrage_bonus)

    @property
    def max_health(self) -> int:
        if self.creature is None:
            return 0
        return self.creature.max_health + sum(b.health_bonus for b in self.buffs)

    def place_creature(self, card: CreatureCard) -> None:
        self.creature = card
        self.current_health = card.max_health
        self.buffs = []
        self.summoned_on_turn = None  # engine sets this after placement
        self.frozen = False
        self.enrage_bonus = 0

    def apply_buff(self, buff: BuffCard) -> None:
        self.buffs.append(buff)
        self.current_health += buff.health_bonus

    def is_dead(self) -> bool:
        return self.creature is not None and self.current_health <= 0

    def clear(self) -> None:
        self.creature = None
        self.current_health = 0
        self.buffs = []
        self.summoned_on_turn = None
        self.frozen = False
        self.enrage_bonus = 0

    def to_dict(self) -> dict:
        return {
            "creature": self.creature.to_dict() if self.creature else None,
            "current_health": self.current_health,
            "attack": self.attack,
            "buffs": [b.to_dict() for b in self.buffs],
            "summoned_on_turn": self.summoned_on_turn,
            "frozen": self.frozen,
            "enrage_bonus": self.enrage_bonus,
        }

    @staticmethod
    def from_dict(d: dict) -> BoardSlot:
        slot = BoardSlot()
        if d["creature"]:
            slot.creature = _card_from_dict(d["creature"])  # type: ignore
        slot.current_health = d["current_health"]
        slot.buffs = [_card_from_dict(b) for b in d["buffs"]]  # type: ignore
        slot.summoned_on_turn = d.get("summoned_on_turn")
        slot.frozen = d.get("frozen", False)
        slot.enrage_bonus = d.get("enrage_bonus", 0)
        return slot


@dataclass
class Hero:
    name: str
    hp: int = STARTING_HP
    max_mana: int = 0
    current_mana: int = 0
    deck: list[Card] = field(default_factory=list)
    hand: list[Card] = field(default_factory=list)
    board: list[BoardSlot] = field(default_factory=list)
    hero_class: str = ""   # "ice_witch" | "drum_wizard" | ""

    def __post_init__(self):
        if not self.board:
            self.board = [BoardSlot() for _ in range(BOARD_SIZE)]

    def to_dict(self, include_hand: bool = True) -> dict:
        return {
            "name": self.name,
            "hp": self.hp,
            "max_mana": self.max_mana,
            "current_mana": self.current_mana,
            # Deck is persisted so mulligan can draw replacements
            "deck": [c.to_dict() for c in self.deck],
            "hand": [c.to_dict() for c in self.hand] if include_hand else [],
            "board": [s.to_dict() for s in self.board],
            "hero_class": self.hero_class,
        }

    @staticmethod
    def from_dict(d: dict) -> Hero:
        hero = Hero(name=d["name"])
        hero.hp = d["hp"]
        hero.max_mana = d["max_mana"]
        hero.current_mana = d["current_mana"]
        hero.deck = [_card_from_dict(c) for c in d.get("deck", [])]
        hero.hand = [_card_from_dict(c) for c in d.get("hand", [])]
        hero.board = [BoardSlot.from_dict(s) for s in d["board"]]
        hero.hero_class = d.get("hero_class", "")
        return hero


@dataclass
class GameState:
    turn: int = 1
    phase: Phase = Phase.START
    heroes: tuple[Hero, Hero] = field(default_factory=lambda: (Hero("Player 1"), Hero("Player 2")))
    action_stacks: tuple[list, list] = field(default_factory=lambda: ([], []))
    first_player: int = 0            # which player's actions go first; alternates each turn
    current_stack: list = field(default_factory=list)  # live execution queue for effects
    mulligan_done: tuple[bool, bool] = field(default_factory=lambda: (False, False))
    hero_power_used: tuple[bool, bool] = field(default_factory=lambda: (False, False))

    def to_dict(self, player_perspective: int | None = None) -> dict:
        """Serialize state. If player_perspective given, only include that player's hand."""
        heroes_data = []
        for i, hero in enumerate(self.heroes):
            include_hand = (player_perspective is None or i == player_perspective)
            heroes_data.append(hero.to_dict(include_hand=include_hand))
        return {
            "turn": self.turn,
            "phase": self.phase.value,
            "heroes": heroes_data,
            "first_player": self.first_player,
            "mulligan_done": list(self.mulligan_done),
            "hero_power_used": list(self.hero_power_used),
        }

    @staticmethod
    def from_dict(d: dict) -> GameState:
        state = GameState()
        state.turn = d["turn"]
        state.phase = Phase(d["phase"])
        h0 = Hero.from_dict(d["heroes"][0])
        h1 = Hero.from_dict(d["heroes"][1])
        state.heroes = (h0, h1)
        state.first_player = d.get("first_player", 0)
        raw = d.get("mulligan_done", [False, False])
        state.mulligan_done = (bool(raw[0]), bool(raw[1]))
        raw_hp = d.get("hero_power_used", [False, False])
        state.hero_power_used = (bool(raw_hp[0]), bool(raw_hp[1]))
        return state


# --- Serialization helpers ---

def _card_from_dict(d: dict) -> Card:
    ct = CardType(d["card_type"])
    timing = d.get("timing", "stack")
    if ct == CardType.CREATURE:
        c = CreatureCard(
            id=d["id"], name=d["name"], cost=d["cost"], card_type=ct,
            timing=timing,
            attack=d.get("attack", 0),
            max_health=d.get("max_health", 1),
            on_play_effect=d.get("on_play_effect"),
            on_death_effect=d.get("on_death_effect"),
            on_damage_effect=d.get("on_damage_effect"),
            on_attack_effect=d.get("on_attack_effect"),
            on_kill_effect=d.get("on_kill_effect"),
            post_attack_effect=d.get("post_attack_effect"),
            gender=d.get("gender", "neutral"),
            riposte=d.get("riposte", False),
            charge=d.get("charge", False),
            enrage=d.get("enrage", 0),
            shield_wall=d.get("shield_wall", 0),
            looks=d.get("looks", 5),
            fico=d.get("fico", 650),
            height_cm=d.get("height_cm", 170),
            reading_level=d.get("reading_level", 8),
            social_credit=d.get("social_credit", 750),
            noodles=d.get("noodles", 5),
            thumbs=d.get("thumbs", 2),
        )
        return c
    elif ct == CardType.BUFF:
        c = BuffCard(
            id=d["id"], name=d["name"], cost=d["cost"], card_type=ct,
            timing=timing,
            on_play_effect=d.get("on_play_effect", ""),
            target_type=TargetType(d.get("target_type", TargetType.FRIENDLY_CREATURE.value)),
            attack_bonus=d.get("attack_bonus", 0),
            health_bonus=d.get("health_bonus", 0),
            description=d.get("description", ""),
            temporary=d.get("temporary", False),
        )
        return c
    else:
        c = SpellCard(
            id=d["id"], name=d["name"], cost=d["cost"], card_type=ct,
            timing=timing,
            on_play_effect=d.get("on_play_effect", ""),
            target_type=TargetType(d.get("target_type", TargetType.ANY_TARGET.value)),
            description=d.get("description", ""),
        )
        return c
