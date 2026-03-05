from __future__ import annotations
import copy
import random
from models import CreatureCard, SpellCard, BuffCard, CardType, TargetType

# ---------------------------------------------------------------------------
# Neutral creatures — Cost 1
# ---------------------------------------------------------------------------

TASTY_FISH = CreatureCard(
    id="tasty_fish", name="Tasty Fish", cost=1, card_type=CardType.CREATURE,
    attack=1, max_health=1, gender="female",
    on_death_effect="tasty_fish_death",
    thumbs=0, looks=1, fico=50, height_cm=23, reading_level=1, social_credit=200, noodles=4,
)

SKINNY_ELF = CreatureCard(
    id="skinny_elf", name="Skinny Elf", cost=1, card_type=CardType.CREATURE,
    attack=1, max_health=2, gender="male",
    thumbs=2, looks=7, fico=620, height_cm=175, reading_level=9, social_credit=720, noodles=1,
)

GREEDY_DWARF = CreatureCard(
    id="greedy_dwarf", name="Greedy Dwarf", cost=1, card_type=CardType.CREATURE,
    attack=1, max_health=1, gender="male",
    on_play_effect="survivor_draw_card",  # Survivor: draw a card each turn
    thumbs=2, looks=5, fico=760, height_cm=107, reading_level=8, social_credit=680, noodles=5,
)

EAGER_SQUIRE = CreatureCard(
    id="eager_squire", name="Eager Squire", cost=1, card_type=CardType.CREATURE,
    attack=1, max_health=1, gender="male",
    shield_wall=1,
    thumbs=2, looks=6, fico=510, height_cm=155, reading_level=6, social_credit=600, noodles=4,
)

SINISTER_SPY = CreatureCard(
    id="sinister_spy", name="Sinister Spy", cost=1, card_type=CardType.CREATURE,
    attack=1, max_health=1, gender="female",
    on_play_effect="sinister_spy_reveal",  # Battle Cry: reveal opponent's hand
    thumbs=2, looks=8, fico=650, height_cm=168, reading_level=3, social_credit=520, noodles=1,
)

WEIRD_FISH = CreatureCard(
    id="weird_fish", name="Weird Fish", cost=1, card_type=CardType.CREATURE,
    attack=1, max_health=1, gender="female",
    on_play_effect="weird_fish_reverse",  # Battle Cry: reverse the action stack
    thumbs=0, looks=1, fico=10, height_cm=51, reading_level=1, social_credit=100, noodles=1,
)

# ---------------------------------------------------------------------------
# Neutral creatures — Cost 2
# ---------------------------------------------------------------------------

MEAN_BEAR = CreatureCard(
    id="mean_bear", name="Mean Bear", cost=2, card_type=CardType.CREATURE,
    attack=1, max_health=3, gender="female",
    enrage=2,  # Enrage: +2 attack each time damaged
    thumbs=0, looks=5, fico=410, height_cm=218, reading_level=1, social_credit=400, noodles=6,
)

BIG_BEAR = CreatureCard(
    id="big_bear", name="Big Bear", cost=2, card_type=CardType.CREATURE,
    attack=1, max_health=4, gender="male",
    thumbs=0, looks=6, fico=310, height_cm=239, reading_level=1, social_credit=350, noodles=10,
)

HORNY_FROG = CreatureCard(
    id="horny_frog", name="Horny Frog", cost=2, card_type=CardType.CREATURE,
    attack=1, max_health=2, gender="female",
    riposte=True,  # Counterstrike: deals damage back to attacker
    thumbs=0, looks=3, fico=10, height_cm=38, reading_level=1, social_credit=150, noodles=1,
)

HAPPY_COW = CreatureCard(
    id="happy_cow", name="Happy Cow", cost=2, card_type=CardType.CREATURE,
    attack=1, max_health=3, gender="female",
    on_play_effect="survivor_heal_3",  # Survivor: restore 3 HP each turn
    thumbs=0, looks=4, fico=20, height_cm=157, reading_level=2, social_credit=200, noodles=2,
)

NEGLIGENT_ZOOKEEPER = CreatureCard(
    id="negligent_zookeeper", name="Negligent Zookeeper", cost=2, card_type=CardType.CREATURE,
    attack=1, max_health=2, gender="male",
    on_play_effect="negligent_zookeeper_draw",  # Battle Cry: draw 3 from Zoo (STUB)
    thumbs=2, looks=5, fico=480, height_cm=168, reading_level=6, social_credit=520, noodles=8,
)

SNAKE_OIL_SALESMAN = CreatureCard(
    id="snake_oil_salesman", name="Snake Oil Salesman", cost=2, card_type=CardType.CREATURE,
    attack=1, max_health=3, gender="female",
    on_attack_effect="snake_oil_bloodlust",  # Bloodlust: reduce enemy attacks to 1 on hero hit
    thumbs=2, looks=6, fico=800, height_cm=163, reading_level=12, social_credit=800, noodles=2,
)

MAN_AT_ARMS = CreatureCard(
    id="man_at_arms", name="Man-At-Arms", cost=2, card_type=CardType.CREATURE,
    attack=1, max_health=3, gender="male",
    shield_wall=1,
    thumbs=2, looks=5, fico=620, height_cm=168, reading_level=6, social_credit=620, noodles=3,
)

TINY_TURTLE = CreatureCard(
    id="tiny_turtle", name="Tiny Turtle", cost=2, card_type=CardType.CREATURE,
    attack=1, max_health=2, gender="female",
    on_damage_effect="armored_1",  # Armored 1: reduce all incoming damage by 1
    thumbs=0, looks=4, fico=750, height_cm=30, reading_level=11, social_credit=700, noodles=1,
)

MUSICAL_BANDIT = CreatureCard(
    id="musical_bandit", name="Musical Bandit", cost=2, card_type=CardType.CREATURE,
    attack=1, max_health=2, gender="male",
    on_attack_effect="musical_bandit_bloodlust",  # Bloodlust: draw a card on hero hit
    thumbs=2, looks=8, fico=550, height_cm=163, reading_level=8, social_credit=580, noodles=3,
)

OLD_BEAR = CreatureCard(
    id="old_bear", name="Old Bear", cost=2, card_type=CardType.CREATURE,
    attack=2, max_health=3, gender="female",
    thumbs=0, looks=3, fico=660, height_cm=234, reading_level=11, social_credit=600, noodles=2,
)

# ---------------------------------------------------------------------------
# Neutral creatures — Cost 3
# ---------------------------------------------------------------------------

HARDENED_HOPLITE = CreatureCard(
    id="hardened_hoplite", name="Hardened Hoplite", cost=3, card_type=CardType.CREATURE,
    attack=2, max_health=3, gender="male",
    riposte=True,   # Counterstrike
    shield_wall=1,
    thumbs=2, looks=6, fico=520, height_cm=157, reading_level=3, social_credit=560, noodles=3,
)

BUSTY_ESKIMO = CreatureCard(
    id="busty_eskimo", name="Busty Eskimo", cost=3, card_type=CardType.CREATURE,
    attack=2, max_health=6, gender="female",
    thumbs=2, looks=9, fico=780, height_cm=163, reading_level=12, social_credit=810, noodles=4,
)

NOBLE_KNIGHT = CreatureCard(
    id="noble_knight", name="Noble Knight", cost=3, card_type=CardType.CREATURE,
    attack=2, max_health=2, gender="male",
    on_damage_effect="armored_1",  # Armored 1
    thumbs=2, looks=8, fico=750, height_cm=168, reading_level=2, social_credit=780, noodles=2,
)

UGLY_ORC = CreatureCard(
    id="ugly_orc", name="Ugly Orc", cost=3, card_type=CardType.CREATURE,
    attack=3, max_health=2, gender="female",
    thumbs=2, looks=3, fico=520, height_cm=198, reading_level=3, social_credit=420, noodles=3,
)

BARBARIAN_BEASTMASTER = CreatureCard(
    id="barbarian_beastmaster", name="Barbarian Beastmaster", cost=3, card_type=CardType.CREATURE,
    attack=1, max_health=3, gender="male",
    on_play_effect="barbarian_beastmaster_send",  # Battle Cry: send enemy animal to Zoo
    thumbs=2, looks=7, fico=650, height_cm=180, reading_level=3, social_credit=530, noodles=7,
)

RAGIN_RHINO = CreatureCard(
    id="ragin_rhino", name="Ragin Rhino", cost=3, card_type=CardType.CREATURE,
    attack=3, max_health=1, gender="male",
    charge=True,
    thumbs=0, looks=3, fico=680, height_cm=249, reading_level=1, social_credit=400, noodles=6,
)

SHERIFF_OF_NOTTINGHAM = CreatureCard(
    id="sheriff_of_nottingham", name="Sheriff of Nottingham", cost=3, card_type=CardType.CREATURE,
    attack=1, max_health=3, gender="male",
    on_play_effect="sheriff_jail",  # Battle Cry: send enemy debtor (FICO < 600) to jail
    thumbs=2, looks=4, fico=760, height_cm=173, reading_level=10, social_credit=840, noodles=2,
)

PRICKLY_PORCUPINE = CreatureCard(
    id="prickly_porcupine", name="Prickly Porcupine", cost=3, card_type=CardType.CREATURE,
    attack=2, max_health=3, gender="female",
    riposte=True,  # Counterstrike
    thumbs=0, looks=5, fico=120, height_cm=97, reading_level=4, social_credit=280, noodles=2,
)

TINY_DRAGON = CreatureCard(
    id="tiny_dragon", name="Tiny Dragon", cost=3, card_type=CardType.CREATURE,
    attack=3, max_health=4, gender="female",
    thumbs=0, looks=6, fico=700, height_cm=63, reading_level=3, social_credit=650, noodles=1,
)

# ---------------------------------------------------------------------------
# Neutral creatures — Cost 4
# ---------------------------------------------------------------------------

BIGGER_BEAR = CreatureCard(
    id="bigger_bear", name="Bigger Bear", cost=4, card_type=CardType.CREATURE,
    attack=3, max_health=6, gender="male",
    thumbs=0, looks=5, fico=500, height_cm=315, reading_level=1, social_credit=380, noodles=12,
)

HUNGRY_CENTURION = CreatureCard(
    id="hungry_centurion", name="Hungry Centurion", cost=4, card_type=CardType.CREATURE,
    attack=2, max_health=4, gender="male",
    shield_wall=2,
    thumbs=2, looks=7, fico=610, height_cm=180, reading_level=6, social_credit=660, noodles=15,
)

LUSTY_TIGER = CreatureCard(
    id="lusty_tiger", name="Lusty Tiger", cost=4, card_type=CardType.CREATURE,
    attack=2, max_health=4, gender="female",
    enrage=3,  # Enrage: +3 attack each time damaged
    thumbs=0, looks=6, fico=300, height_cm=137, reading_level=1, social_credit=320, noodles=6,
)

TUMBLY_PANDA = CreatureCard(
    id="tumbly_panda", name="Tumbly Panda", cost=4, card_type=CardType.CREATURE,
    attack=2, max_health=5, gender="male",
    on_play_effect="survivor_draw_card",  # Survivor: draw a card each turn
    thumbs=0, looks=7, fico=250, height_cm=190, reading_level=2, social_credit=310, noodles=8,
)

LITERARY_LANCER = CreatureCard(
    id="literary_lancer", name="Literary Lancer", cost=4, card_type=CardType.CREATURE,
    attack=3, max_health=3, gender="female",
    charge=True,
    thumbs=2, looks=8, fico=760, height_cm=188, reading_level=13, social_credit=890, noodles=4,
)

GIANT_TURTLE = CreatureCard(
    id="giant_turtle", name="Giant Turtle", cost=4, card_type=CardType.CREATURE,
    attack=2, max_health=6, gender="male",
    on_damage_effect="armored_1",  # Armored 1
    thumbs=0, looks=4, fico=600, height_cm=368, reading_level=1, social_credit=500, noodles=10,
)

CORRUPTED_ZOOKEEPER = CreatureCard(
    id="corrupted_zookeeper", name="Corrupted Zookeeper", cost=4, card_type=CardType.CREATURE,
    attack=3, max_health=5, gender="male",
    on_play_effect="corrupted_zookeeper_purge",  # Battle Cry: send Zoo to Shadow Realm (STUB)
    thumbs=2, looks=1, fico=520, height_cm=157, reading_level=4, social_credit=480, noodles=1,
)

# ---------------------------------------------------------------------------
# Neutral creatures — Cost 5
# ---------------------------------------------------------------------------

OILED_UP_ELF_LORD = CreatureCard(
    id="oiled_up_elf_lord", name="Oiled Up Elf Lord", cost=5, card_type=CardType.CREATURE,
    attack=4, max_health=6, gender="male",
    thumbs=2, looks=9, fico=790, height_cm=198, reading_level=12, social_credit=870, noodles=10,
)

SKINNY_BLOOD_WITCH = CreatureCard(
    id="skinny_blood_witch", name="Skinny Blood Witch", cost=5, card_type=CardType.CREATURE,
    attack=1, max_health=4, gender="female",
    on_attack_effect="skinny_blood_witch_bloodlust",  # Bloodlust: summon from Shadow Realm (STUB)
    thumbs=2, looks=8, fico=650, height_cm=185, reading_level=10, social_credit=710, noodles=0,
)

BARBARIAN_BARBER = CreatureCard(
    id="barbarian_barber", name="Barbarian Barber", cost=5, card_type=CardType.CREATURE,
    attack=3, max_health=6, gender="male",
    enrage=3,  # Enrage: +3 attack each time damaged
    thumbs=2, looks=6, fico=400, height_cm=183, reading_level=7, social_credit=460, noodles=6,
)

BIG_TROLL = CreatureCard(
    id="big_troll", name="Big Troll", cost=5, card_type=CardType.CREATURE,
    attack=3, max_health=9, gender="male",
    thumbs=2, looks=1, fico=300, height_cm=391, reading_level=1, social_credit=280, noodles=7,
)

FOUR_ARMED_DEATH_GECKO = CreatureCard(
    id="four_armed_death_gecko", name="4 Armed Death Gecko", cost=5, card_type=CardType.CREATURE,
    attack=5, max_health=4, gender="male",
    thumbs=4, looks=2, fico=350, height_cm=185, reading_level=2, social_credit=350, noodles=4,
)

DR_LAZER = CreatureCard(
    id="dr_lazer", name="Dr. Lazer", cost=5, card_type=CardType.CREATURE,
    attack=4, max_health=3, gender="male",
    charge=True,
    thumbs=2, looks=7, fico=400, height_cm=168, reading_level=13, social_credit=620, noodles=2,
)

# ---------------------------------------------------------------------------
# Neutral spells — Mogg & Max (hidden-attribute targeting)
# ---------------------------------------------------------------------------

# Choose-a-friendly Moggs (target_type=FRIENDLY_CREATURE) — cost 2
THUMBMOGG = SpellCard(
    id="thumbmogg", name="ThumbMogg", cost=2, card_type=CardType.SPELL,
    on_play_effect="thumbmogg",
    target_type=TargetType.FRIENDLY_CREATURE,
    description="Choose a friendly. Send all minions with fewer thumbs than it to the Zoo",
)

FICOMOGG = SpellCard(
    id="ficomogg", name="FicoMogg", cost=2, card_type=CardType.SPELL,
    on_play_effect="ficomogg",
    target_type=TargetType.FRIENDLY_CREATURE,
    description="Choose a friendly. Destroy all minions with a lower FICO score",
)

HEIGHMOGG = SpellCard(
    id="heighmogg", name="HeighMogg", cost=2, card_type=CardType.SPELL,
    on_play_effect="heighmogg",
    target_type=TargetType.FRIENDLY_CREATURE,
    description="Choose a friendly. Destroy all male minions shorter than it",
)

PASTAMOGG = SpellCard(
    id="pastamogg", name="PastaMogg", cost=2, card_type=CardType.SPELL,
    on_play_effect="pastamogg",
    target_type=TargetType.FRIENDLY_CREATURE,
    description="Choose a friendly. Send all minions that eat less pasta than it to the Shadow Realm",
)

BOOKMOGG = SpellCard(
    id="bookmogg", name="BookMogg", cost=2, card_type=CardType.SPELL,
    on_play_effect="bookmogg_choose",
    target_type=TargetType.FRIENDLY_CREATURE,
    description="Choose a friendly. Destroy all minions that read at a lower level",
)

LOOKSMOGG = SpellCard(
    id="looksmogg", name="LooksMogg", cost=2, card_type=CardType.SPELL,
    on_play_effect="looksmogg",
    target_type=TargetType.FRIENDLY_CREATURE,
    description="Choose a friendly. Destroy all minions that are less good-looking than it",
)

# Auto-targeting Moggs — cost 3
LEGALMOGG = SpellCard(
    id="legalmogg", name="LegalMogg", cost=3, card_type=CardType.SPELL,
    on_play_effect="legalmogg",
    target_type=TargetType.ENEMY_HERO,
    description="Send all minions that read at 6th grade level or below to county jail",
)

FISTMOGG = SpellCard(
    id="fistmogg", name="FistMogg", cost=3, card_type=CardType.SPELL,
    on_play_effect="fistmogg",
    target_type=TargetType.ENEMY_HERO,
    description="Destroy all minions with less than 2 attack",
)

# Persistent Max spells — cost 2
LOOKSMAX = SpellCard(
    id="looksmax", name="LooksMax", cost=2, card_type=CardType.SPELL,
    on_play_effect="looksmax",
    target_type=TargetType.ENEMY_HERO,
    description="Each turn end: if your minion is most beautiful, draw a card. If not, self-destruct",
)

PASTAMAX = SpellCard(
    id="pastamax", name="PastaMax", cost=2, card_type=CardType.SPELL,
    on_play_effect="pastamax_persistent",
    target_type=TargetType.ENEMY_HERO,
    description="Each turn end: if your minion eats the most, give friendlies +2 health. If not, self-destruct",
)

# ---------------------------------------------------------------------------
# Ice Witch cards (timing="stack")
# ---------------------------------------------------------------------------

HUSKY_DOG = CreatureCard(
    id="husky_dog", name="Husky Dog", cost=1, card_type=CardType.CREATURE,
    attack=1, max_health=2, gender="neutral",
    looks=9, fico=400, height_cm=58, reading_level=3, social_credit=900, noodles=5,
)

ICE_BEAM = SpellCard(
    id="ice_beam", name="Ice Beam", cost=2, card_type=CardType.SPELL,
    on_play_effect="deal_6_to_creature",
    target_type=TargetType.ENEMY_CREATURE,
    description="Deal 6 damage to an enemy creature",
)

HOT_GIRL_WINTER = SpellCard(
    id="hot_girl_winter", name="Hot Girl Winter", cost=2, card_type=CardType.SPELL,
    on_play_effect="hot_girl_winter",
    target_type=TargetType.ENEMY_HERO,
    description="Freeze all male minions and give them -attack (Shrunk)",
)

BLIZZARD = SpellCard(
    id="blizzard", name="Blizzard", cost=3, card_type=CardType.SPELL,
    on_play_effect="blizzard",
    target_type=TargetType.ENEMY_HERO,
    description="Deal 2 damage to all minions and Freeze them",
)

BEAUTY_CONTEST = SpellCard(
    id="beauty_contest", name="Beauty Contest", cost=2, card_type=CardType.SPELL,
    on_play_effect="beauty_contest",
    target_type=TargetType.ENEMY_HERO,
    description="At end of turn, the player with the best-looking minion draws 3 cards",
)

# ---------------------------------------------------------------------------
# Drum Wizard cards (timing="prep")
# ---------------------------------------------------------------------------

TEMPO_PENGUINS = CreatureCard(
    id="tempo_penguins", name="Tempo-Penguins", cost=2, card_type=CardType.CREATURE,
    attack=1, max_health=4, gender="neutral",
    on_attack_effect="double_attack",
    looks=8, fico=540, height_cm=100, reading_level=5, social_credit=830, noodles=6,
)

SYMBOL_HEAD = CreatureCard(
    id="symbol_head", name="Symbol Head", cost=1, card_type=CardType.CREATURE,
    attack=1, max_health=3, gender="male",
    riposte=True,
    looks=6, fico=690, height_cm=173, reading_level=11, social_credit=760, noodles=5,
)

LAZER_FOX = CreatureCard(
    id="lazer_fox", name="Lazer Fox", cost=1, card_type=CardType.CREATURE,
    attack=2, max_health=1, gender="neutral",
    charge=True,
    looks=8, fico=480, height_cm=65, reading_level=7, social_credit=590, noodles=6,
)

DJ_TIGHTPANTS = CreatureCard(
    id="dj_tightpants", name="DJ Tightpants", cost=3, card_type=CardType.CREATURE,
    attack=3, max_health=6, gender="male",
    on_attack_effect="dj_lone_wolf",
    looks=9, fico=560, height_cm=182, reading_level=9, social_credit=630, noodles=7,
)

COCONUT_CAPIBARRA = CreatureCard(
    id="coconut_capibarra", name="Coconut Capibarra", cost=2, card_type=CardType.CREATURE,
    attack=2, max_health=3, gender="neutral",
    on_play_effect="capibarra_register",
    looks=10, fico=490, height_cm=130, reading_level=4, social_credit=950, noodles=9,
)

RAGING_RHINO = CreatureCard(
    id="raging_rhino", name="Raging Rhino", cost=4, card_type=CardType.CREATURE,
    attack=4, max_health=3, gender="male",
    charge=True,
    on_kill_effect="rhino_splash",
    looks=5, fico=570, height_cm=168, reading_level=4, social_credit=610, noodles=10,
)

BASS_GIANT = CreatureCard(
    id="bass_giant", name="Bass Giant", cost=5, card_type=CardType.CREATURE,
    attack=3, max_health=6, gender="male",
    shield_wall=3,
    looks=6, fico=750, height_cm=330, reading_level=8, social_credit=820, noodles=10,
)

# Token — not in deck, summoned by Mariachi March
MARIACHI_BAND = CreatureCard(
    id="mariachi_band", name="Mariachi Band", cost=0, card_type=CardType.CREATURE,
    attack=2, max_health=3, gender="male",
    looks=8, fico=520, height_cm=172, reading_level=8, social_credit=760, noodles=7,
)

GUITAR_SOLO = SpellCard(
    id="guitar_solo", name="Guitar Solo", cost=1, card_type=CardType.SPELL,
    on_play_effect="guitar_solo",
    target_type=TargetType.ENEMY_HERO,
    description="Your next 5 stack actions happen consecutively",
)

DOUBLE_TIME = SpellCard(
    id="double_time", name="Double Time", cost=2, card_type=CardType.SPELL,
    on_play_effect="double_time",
    target_type=TargetType.ENEMY_HERO,
    description="Your next 2 stack actions happen consecutively",
)

HORNS_OF_POWER = SpellCard(
    id="horns_of_power", name="Horns of Power", cost=2, card_type=CardType.SPELL,
    on_play_effect="horns_of_power",
    target_type=TargetType.ENEMY_HERO,
    description="Double your minions' attack until end of turn",
)

HORN_OF_TERROR = SpellCard(
    id="horn_of_terror", name="Horn of Terror", cost=1, card_type=CardType.SPELL,
    on_play_effect="horn_of_terror",
    target_type=TargetType.ENEMY_CREATURE,
    description="Return an enemy minion to their hand",
)

GRAPESHOT = SpellCard(
    id="grapeshot", name="Grapeshot", cost=3, card_type=CardType.SPELL,
    on_play_effect="grapeshot",
    target_type=TargetType.ENEMY_CREATURE,
    description="Deal 6 damage to target and 2 to adjacent enemies",
)

MARIACHI_MARCH = SpellCard(
    id="mariachi_march", name="Mariachi March", cost=3, card_type=CardType.SPELL,
    on_play_effect="mariachi_march",
    target_type=TargetType.ENEMY_HERO,
    description="Fill each empty friendly slot with a 2/3 Mariachi Band",
)

FRAMEMOGG = SpellCard(
    id="framemogg", name="FrameMogg", cost=1, card_type=CardType.SPELL,
    on_play_effect="framemogg",
    target_type=TargetType.ENEMY_HERO,
    description="Destroy all minions with less HP than your healthiest creature",
)

MARCH_OF_THE_TITANS = SpellCard(
    id="march_of_the_titans", name="March of the Titans", cost=2, card_type=CardType.SPELL,
    on_play_effect="march_of_the_titans",
    target_type=TargetType.ENEMY_HERO,
    description="Give all your minions +2/+2",
)

LOVE_SONG = SpellCard(
    id="love_song", name="Love Song", cost=3, card_type=CardType.SPELL,
    on_play_effect="love_song",
    target_type=TargetType.ENEMY_CREATURE,
    description="Steal an enemy minion — it joins your hand",
)

# ---------------------------------------------------------------------------
# Blood Witch / Cult cards (timing="stack")
# ---------------------------------------------------------------------------

BLACK_CAT = CreatureCard(
    id="black_cat", name="Black Cat", cost=1, card_type=CardType.CREATURE,
    attack=1, max_health=1, gender="neutral",
    on_play_effect="black_cat_register",
    looks=8, fico=450, height_cm=45, reading_level=5, social_credit=600, noodles=2,
)

BAT_NINJA = CreatureCard(
    id="bat_ninja", name="Bat Ninja", cost=1, card_type=CardType.CREATURE,
    attack=1, max_health=2, gender="female",
    post_attack_effect="bat_ninja_return",
    looks=8, fico=520, height_cm=162, reading_level=9, social_credit=680, noodles=5,
)

HONE_OF_TINDERLOST = CreatureCard(
    id="hone_of_tinderlost", name="Hone of Tinderlost", cost=4, card_type=CardType.CREATURE,
    attack=4, max_health=6, gender="neutral",
    on_play_effect="reverse_stack",
    looks=6, fico=700, height_cm=180, reading_level=10, social_credit=770, noodles=3,
)

HOT_VAMPIRE_DUDE = CreatureCard(
    id="hot_vampire_dude", name="Hot Vampire Dude", cost=3, card_type=CardType.CREATURE,
    attack=3, max_health=6, gender="male",
    on_play_effect="vampire_buff_females",
    looks=10, fico=800, height_cm=185, reading_level=12, social_credit=850, noodles=4,
)

SQUID_DEMON = CreatureCard(
    id="squid_demon", name="Squid Demon", cost=3, card_type=CardType.CREATURE,
    attack=2, max_health=6, gender="neutral",
    enrage=2,
    looks=4, fico=300, height_cm=220, reading_level=3, social_credit=400, noodles=8,
)

VOODOO_DOLL = BuffCard(
    id="voodoo_doll", name="Voodoo Doll", cost=1, card_type=CardType.BUFF,
    on_play_effect="voodoo_doll_register",
    target_type=TargetType.FRIENDLY_CREATURE,
    attack_bonus=0,
    health_bonus=0,
    description="Enchant a friendly minion. When it is damaged, deal 2x that to the enemy hero.",
)

# ---------------------------------------------------------------------------
# Spellbook — draw spell (timing="prep" so cards arrive before stack resolves)
# ---------------------------------------------------------------------------

SPELLBOOK = SpellCard(
    id="spellbook", name="Spellbook", cost=2, card_type=CardType.SPELL,
    timing="prep",
    on_play_effect="spellbook",
    target_type=TargetType.ENEMY_HERO,
    description="Add 3 random spells to your hand",
)

# ---------------------------------------------------------------------------
# Catalog (for serialization lookups)
# ---------------------------------------------------------------------------

CARD_CATALOG: dict[str, object] = {
    card.id: card for card in [
        # Neutral — Cost 1
        TASTY_FISH, SKINNY_ELF, GREEDY_DWARF, EAGER_SQUIRE, SINISTER_SPY, WEIRD_FISH,
        # Neutral — Cost 2
        MEAN_BEAR, BIG_BEAR, HORNY_FROG, HAPPY_COW, NEGLIGENT_ZOOKEEPER,
        SNAKE_OIL_SALESMAN, MAN_AT_ARMS, TINY_TURTLE, MUSICAL_BANDIT, OLD_BEAR,
        # Neutral — Cost 3
        HARDENED_HOPLITE, BUSTY_ESKIMO, NOBLE_KNIGHT, UGLY_ORC, BARBARIAN_BEASTMASTER,
        RAGIN_RHINO, SHERIFF_OF_NOTTINGHAM, PRICKLY_PORCUPINE, TINY_DRAGON,
        # Neutral — Cost 4
        BIGGER_BEAR, HUNGRY_CENTURION, LUSTY_TIGER, TUMBLY_PANDA, LITERARY_LANCER,
        GIANT_TURTLE, CORRUPTED_ZOOKEEPER,
        # Neutral — Cost 5
        OILED_UP_ELF_LORD, SKINNY_BLOOD_WITCH, BARBARIAN_BARBER, BIG_TROLL,
        FOUR_ARMED_DEATH_GECKO, DR_LAZER,
        # Neutral spells — Mogg & Max
        THUMBMOGG, FICOMOGG, HEIGHMOGG, PASTAMOGG, BOOKMOGG, LOOKSMOGG,
        LEGALMOGG, FISTMOGG, LOOKSMAX, PASTAMAX,
        # Ice Witch
        HUSKY_DOG, ICE_BEAM, HOT_GIRL_WINTER, BLIZZARD, BEAUTY_CONTEST,
        # Drum Wizard
        TEMPO_PENGUINS, SYMBOL_HEAD, LAZER_FOX, DJ_TIGHTPANTS,
        COCONUT_CAPIBARRA, RAGING_RHINO, BASS_GIANT,
        GUITAR_SOLO, DOUBLE_TIME, HORNS_OF_POWER, HORN_OF_TERROR,
        GRAPESHOT, MARIACHI_MARCH, FRAMEMOGG, MARCH_OF_THE_TITANS, LOVE_SONG,
        # Blood Witch
        BLACK_CAT, BAT_NINJA, HONE_OF_TINDERLOST, HOT_VAMPIRE_DUDE,
        SQUID_DEMON, VOODOO_DOLL,
        # Shared draw spell + token
        SPELLBOOK, MARIACHI_BAND,
    ]
}


def get_card(card_id: str):
    """Return a fresh copy of a card by ID."""
    card = CARD_CATALOG.get(card_id)
    if card is None:
        raise KeyError(f"Unknown card: {card_id}")
    return copy.deepcopy(card)


# ---------------------------------------------------------------------------
# Class pools for deck building
# ---------------------------------------------------------------------------

NEUTRAL_POOL = [
    # Cost 1
    "tasty_fish", "skinny_elf", "greedy_dwarf", "eager_squire", "sinister_spy", "weird_fish",
    # Cost 2
    "mean_bear", "big_bear", "horny_frog", "happy_cow", "negligent_zookeeper",
    "snake_oil_salesman", "man_at_arms", "tiny_turtle", "musical_bandit", "old_bear",
    # Cost 3
    "hardened_hoplite", "busty_eskimo", "noble_knight", "ugly_orc", "barbarian_beastmaster",
    "ragin_rhino", "sheriff_of_nottingham", "prickly_porcupine", "tiny_dragon",
    # Cost 4
    "bigger_bear", "hungry_centurion", "lusty_tiger", "tumbly_panda", "literary_lancer",
    "giant_turtle", "corrupted_zookeeper",
    # Cost 5
    "oiled_up_elf_lord", "skinny_blood_witch", "barbarian_barber", "big_troll",
    "four_armed_death_gecko", "dr_lazer",
    # Mogg & Max spells
    "thumbmogg", "ficomogg", "heighmogg", "pastamogg", "bookmogg", "looksmogg",
    "legalmogg", "fistmogg", "looksmax", "pastamax",
]

# All spell card IDs (used by Spellbook effect to pick random spells)
SPELL_POOL = [
    # Neutral Mogg & Max spells
    "thumbmogg", "ficomogg", "heighmogg", "pastamogg", "bookmogg", "looksmogg",
    "legalmogg", "fistmogg", "looksmax", "pastamax",
    # Ice Witch spells
    "ice_beam", "hot_girl_winter", "blizzard", "beauty_contest",
    # Drum Wizard spells
    "guitar_solo", "double_time", "horns_of_power", "horn_of_terror",
    "grapeshot", "mariachi_march", "framemogg", "march_of_the_titans", "love_song",
]

ICE_WITCH_POOL = [
    "husky_dog", "ice_beam", "hot_girl_winter", "blizzard", "beauty_contest",
    "spellbook",
]

DRUM_WIZARD_POOL = [
    "tempo_penguins", "symbol_head", "lazer_fox", "dj_tightpants",
    "coconut_capibarra", "raging_rhino", "bass_giant",
    "guitar_solo", "double_time", "horns_of_power", "horn_of_terror",
    "grapeshot", "mariachi_march", "framemogg", "march_of_the_titans", "love_song",
    "spellbook",
]

BLOOD_WITCH_POOL = [
    "black_cat", "bat_ninja", "hone_of_tinderlost", "hot_vampire_dude",
    "squid_demon", "voodoo_doll",
    "spellbook",
]

CLASS_POOLS = {
    "ice_witch": ICE_WITCH_POOL,
    "drum_wizard": DRUM_WIZARD_POOL,
    "blood_witch": BLOOD_WITCH_POOL,
}

CLASS_DISPLAY_NAMES = {
    "ice_witch": "Ice Witch",
    "drum_wizard": "Drum Wizard",
    "blood_witch": "Blood Witch",
}

# Hero power definitions — sent to client so it knows the button label, description, target type
HERO_POWERS = {
    "ice_witch": {
        "name": "Frost Shard",
        "description": "Deal 2 damage to any target",
        "target_type": "any_target",
    },
    "drum_wizard": {
        "name": "Tempo Freeze",
        "description": "Freeze a minion — moves its attack to the bottom of the stack",
        "target_type": "any_creature",
    },
    "blood_witch": {
        "name": "Sacrifice",
        "description": "Destroy a friendly minion and gain mana equal to its cost",
        "target_type": "friendly_creature",
    },
}


def build_player_deck(class_name: str) -> list:
    """Build a 20-card deck: 10 random class cards + 10 random neutral cards."""
    pool = CLASS_POOLS.get(class_name, [])

    # 10 class cards — sample with replacement if pool is small
    if len(pool) >= 10:
        class_ids = random.sample(pool, 10)
    else:
        # Repeat cards to fill 10 (Ice Witch only has 5 unique cards → 2 of each)
        class_ids = []
        while len(class_ids) < 10:
            class_ids += pool
        class_ids = class_ids[:10]
        random.shuffle(class_ids)

    # 10 neutral cards — sample without replacement for variety
    neutral_sample = random.sample(NEUTRAL_POOL, min(10, len(NEUTRAL_POOL)))

    deck = [get_card(cid) for cid in class_ids] + [get_card(cid) for cid in neutral_sample]
    random.shuffle(deck)
    return deck


def get_starter_deck() -> list:
    """Legacy: return a shuffled 40-card deck (2x each class + neutral).
    Use build_player_deck() for new sessions."""
    deck = []
    for card_id in CARD_CATALOG:
        if card_id != "mariachi_band":  # token, not in decks
            deck.append(get_card(card_id))
            deck.append(get_card(card_id))
    random.shuffle(deck)
    return deck
