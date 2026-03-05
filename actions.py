from __future__ import annotations
from dataclasses import dataclass, field
import json


@dataclass
class PlayCardAction:
    player_id: int          # 0 or 1
    card_id: str            # card to play from hand
    target_slot: int | None = None     # board slot index (for creatures/buffs)
    target_player: int | None = None   # 0=self, 1=enemy (for targeted spells)
    charge_target: int | None = None   # target slot for Charge attack (if creature has charge)

    action_type: str = "play_card"

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type,
            "player_id": self.player_id,
            "card_id": self.card_id,
            "target_slot": self.target_slot,
            "target_player": self.target_player,
            "charge_target": self.charge_target,
        }


@dataclass
class AttackAction:
    player_id: int
    attacker_slot: int   # friendly board slot index
    target_slot: int     # enemy board slot index (-1 = hero)

    action_type: str = "attack"

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type,
            "player_id": self.player_id,
            "attacker_slot": self.attacker_slot,
            "target_slot": self.target_slot,
        }


@dataclass
class PassAction:
    player_id: int
    action_type: str = "pass"

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type,
            "player_id": self.player_id,
        }


@dataclass
class MulliganAction:
    player_id: int
    keep_indices: list[int] = field(default_factory=list)  # hand indices to KEEP (rest swapped)

    action_type: str = "mulligan"

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type,
            "player_id": self.player_id,
            "keep_indices": self.keep_indices,
        }


@dataclass
class HeroPowerAction:
    player_id: int
    target_player: int | None = None   # which side (0=self, 1=enemy)
    target_slot: int | None = None     # board slot index, or None for hero

    action_type: str = "hero_power"

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type,
            "player_id": self.player_id,
            "target_player": self.target_player,
            "target_slot": self.target_slot,
        }


Action = PlayCardAction | AttackAction | PassAction | MulliganAction | HeroPowerAction


def action_to_dict(action: Action) -> dict:
    return action.to_dict()


def action_from_dict(d: dict) -> Action:
    t = d["action_type"]
    if t == "play_card":
        return PlayCardAction(
            player_id=d["player_id"],
            card_id=d["card_id"],
            target_slot=d.get("target_slot"),
            target_player=d.get("target_player"),
            charge_target=d.get("charge_target"),
        )
    elif t == "attack":
        return AttackAction(
            player_id=d["player_id"],
            attacker_slot=d["attacker_slot"],
            target_slot=d["target_slot"],
        )
    elif t == "pass":
        return PassAction(player_id=d["player_id"])
    elif t == "mulligan":
        return MulliganAction(
            player_id=d["player_id"],
            keep_indices=d.get("keep_indices", []),
        )
    elif t == "hero_power":
        return HeroPowerAction(
            player_id=d["player_id"],
            target_player=d.get("target_player"),
            target_slot=d.get("target_slot"),
        )
    else:
        raise ValueError(f"Unknown action type: {t}")


def serialize_actions(actions: list[Action]) -> str:
    return json.dumps([action_to_dict(a) for a in actions], indent=2)


def deserialize_actions(s: str) -> list[Action]:
    return [action_from_dict(d) for d in json.loads(s)]
