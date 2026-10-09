import random 
from enum import IntEnum, StrEnum
from typing import Optional, Union

# TODO a lot of this can be converted to use the classes produced by param_categorizer.py
# The new flow is
# 1. Run param_categorizer.py to generate a list of all considered objects
# 2. Generate a spec for each object across all of the randomizers which dictates how things will change
# 3. Write the spec to the raw xml files


class RingEffectLevel(StrEnum):
    NEGATIVE = "Negative"
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    LEGENDARY = "Legendary"

class RingTier(IntEnum):
    STANDARD = 0
    UNCOMMON = 1
    RARE = 2
    LEGENDARY = 3
    
# These rings are required to beat the game in some fashion.
# Randomizing their effects could be game-breaking
# Or they are generaly useful to keep as they are
# Important: Darkmoon Seance Ring, Covenant of Artorias, Orange Charred Ring
# Keep as is: Ring of Sacrifice, Rare Ring of Sacrifice
RING_IDS_TO_IGNORE = [149, 138, 139, 126, 127]

DISTRIBUTION_RANK_TO_TEMPLATES = {
    RingTier.STANDARD: (
        (0.8, (RingEffectLevel.LOW,)), 
        (0.2, (RingEffectLevel.MEDIUM, RingEffectLevel.NEGATIVE))),

    RingTier.UNCOMMON: (
        (0.6, (RingEffectLevel.MEDIUM,)), 
        (0.2, (RingEffectLevel.LOW, RingEffectLevel.LOW,)), 
        (0.2, (RingEffectLevel.HIGH, RingEffectLevel.NEGATIVE))),

    RingTier.RARE: (
        (0.6, (RingEffectLevel.HIGH,)), 
        (0.2, (RingEffectLevel.MEDIUM, RingEffectLevel.LOW,)), 
        (0.2, (RingEffectLevel.HIGH, RingEffectLevel.MEDIUM, RingEffectLevel.NEGATIVE))),

    RingTier.LEGENDARY: (
        (0.6, (RingEffectLevel.LEGENDARY,)), 
        (0.2, (RingEffectLevel.HIGH, RingEffectLevel.MEDIUM,)), 
        (0.2, (RingEffectLevel.LEGENDARY, RingEffectLevel.MEDIUM, RingEffectLevel.NEGATIVE))),
}
class RingEffects:
    def __init__(self, effect_names: list[str], effect_values: list[Union[int, float]], num_effects=None, hidden_effect_names=None, hidden_effect_values=None):
        self.effects = list(zip(effect_names, effect_values))
        hidden_effect_names = hidden_effect_names or []
        hidden_effect_values = hidden_effect_values or []
        self.hidden_effects = list(zip(hidden_effect_names, hidden_effect_values))
        self.num_effects = num_effects or len(effect_names)
    
    def get_all_effect_names(self):
        effect_names = [effect[0] for effect in self.effects]
        hidden_effect_names = [effect[0] for effect in self.hidden_effects]
        return effect_names + hidden_effect_names
    
    def check_no_duplicate_effects(self, other_effect_names):
        all_effect_names = self.get_all_effect_names()
        return not any(effect in all_effect_names for effect in other_effect_names)
    
    def modify_sp_effect_row_and_generate_summary_text(self, sp_effect_row):
        summary_texts = []
        for effect_name, effect_value in random.choices(self.effects, k=self.num_effects):
            sp_effect_row.set(effect_name, str(effect_value))
            print(effect_name, effect_value)
            summary_texts.append(self.generate_ring_summary_text(effect_name, effect_value))
        for effect_name, effect_value in self.hidden_effects:
            sp_effect_row.set(effect_name, str(effect_value))
        return summary_texts
    
    @staticmethod
    def generate_ring_summary_text(effect_name, value):
        summary_text_and_display_func = RING_EFFECT_TO_SUMMARY_TEXT_MAPPING_AND_DISPLAY_FUNC[effect_name]
        if isinstance(summary_text_and_display_func, tuple):
            summary_text = summary_text_and_display_func[0]
            display_func = summary_text_and_display_func[1]
            display_value = display_func(value)
            return summary_text.format(value=display_value)
        else:
            summary_text = summary_text_and_display_func
            return summary_text.format(value=value)

class RingStateInfoEffect(RingEffects):
    """
    Special class for ring effects that are triggered by stateInfo
    Extra effects are hidden from the player. Typically these are internal trigger fields
    """
    def __init__(self, state_info_id, hidden_effect_names=None, hidden_effect_values=None):
        super().__init__(["stateInfo"], [state_info_id], num_effects=1, hidden_effect_names=hidden_effect_names, 
                         hidden_effect_values=hidden_effect_values)

    @staticmethod
    def generate_ring_summary_text(effect_name, value):
        assert effect_name == "stateInfo", "RingStateInfoEffect should only have stateInfo as its effect name"
        summary_text = STATE_INFO_ID_TO_SUMMARY_TEXT_MAPPING[value]
        return summary_text
        
NEGATIVE_RING_EFFECTS: list[Union[RingEffects, RingStateInfoEffect]] = [
    # Defense
    RingEffects(["physicsDiffence"], [-25]),
    RingEffects(["physicsDiffence", "magicDiffence", "fireDiffence", "thunderDiffence"], [-20, -20, -20, -20], num_effects=2),
    RingEffects(["slashDamageCutRate", "blowDamageCutRate", "thrustDamageCutRate", "neutralDamageCutRate", "magicDamageCutRate", 
                 "fireDamageCutRate", "thunderDamageCutRate"], [1.15, 1.15, 1.15, 1.15, 1.15, 1.15, 1.15], num_effects=2),
    # Attack Power
    RingEffects(["physicsAttackPowerRate", "magicAttackPowerRate", "fireAttackPowerRate", "thunderAttackPowerRate"], [0.8, 0.8, 0.8, 0.8], num_effects=1),
    # Equip Weight Change ratio
    RingEffects(["equipWeightChangeRate"], [0.8]),
    # At which minimum HP percentage the ring effects will activate. 
    RingEffects(["conditionHp"], [0.5]),
    # Stamina recovery speed
    RingEffects(["staminaRecoverChangeSpeed"], [-10]),

    # Resistance
    RingEffects(["registPoizonChangeRate", "registCurseChangeRate", "registIllnessChangeRate", "registBloodChangeRate"], [0.5, 0.5, 0.5, 0.5], num_effects=2),

    # HP
    RingEffects(["maxHpRate"], [0.75], hidden_effect_names=["bCurrHPIndependeMaxHP"], hidden_effect_values=[1]),
    RingEffects(["changeHpRate"], [1], num_effects=1, hidden_effect_names=["motionInterval"], hidden_effect_values=[1]),

    # Stamina
    RingEffects(["maxStaminaRate"], [0.75]),

    # Arrow distance,
    RingEffects(["bowDistRate"], [-20]),

    # Poise
    RingEffects(["changeSuperArmorPoint"], [-20]),

    # Soul Absorption
    RingEffects(["soulRate"], [0.8]),
]

LOW_RING_EFFECTS: list[Union[RingEffects, RingStateInfoEffect]] = [
    # Defense
    RingEffects(["physicsDiffence"], [15]),
    RingEffects(["physicsDiffence", "magicDiffence", "fireDiffence", "thunderDiffence"], [10, 10, 10, 10], num_effects=2),
    RingEffects(["slashDamageCutRate", "blowDamageCutRate", "thrustDamageCutRate", "neutralDamageCutRate", "magicDamageCutRate", 
                "fireDamageCutRate", "thunderDamageCutRate"], [0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9], num_effects=2),
    # Attack Power
    RingEffects(["physicsAttackPowerRate", "magicAttackPowerRate", "fireAttackPowerRate", "thunderAttackPowerRate"], [1.1, 1.1, 1.1, 1.1], num_effects=1),
    # Equip Weight Change ratio
    RingEffects(["equipWeightChangeRate"], [1.1]),
    # Attunement slots
    RingEffects(["changeMagicSlot"], [1]),
    # Enemy Search Visual Reduction
    RingEffects(["sightSearchEnemyCut"], [35]),
    # Weapon durability
    RingEffects(["maxDurability"], [10]),
    # Stamina recovery speed
    RingEffects(["staminaRecoverChangeSpeed"], [5]),
    # Resistance
    RingEffects(["registPoizonChangeRate", "registCurseChangeRate", "registIllnessChangeRate", "registBloodChangeRate"], [1.25, 1.25, 1.25, 1.25], num_effects=2),
    # HP
    RingEffects(["maxHpRate"], [1.05], hidden_effect_names=["bCurrHPIndependeMaxHP"], hidden_effect_values=[1]),
    # Hp changed per second. Negative restores hp
    RingEffects(["changeHpRate"], [-0.5], num_effects=1, hidden_effect_names=["motionInterval"], hidden_effect_values=[1]),
    # Stamina
    RingEffects(["maxStaminaRate"], [1.1]),
    # Arrow distance,
    RingEffects(["bowDistRate"], [10]),
    # Poise
    RingEffects(["changeSuperArmorPoint"], [10]),
    # Soul Absorption
    RingEffects(["soulRate"], [1.05]),
]

MEDIUM_RING_EFFECTS: list[Union[RingEffects, RingStateInfoEffect]] = [
    # Enemy Search Hearing Reduction
    RingEffects(["hearingSearchEnemyCut"], [100]),
    # Enemy Search Visual Reduction
    RingEffects(["sightSearchEnemyCut"], [70]),
    # Increased Item Discovery
    RingStateInfoEffect(66),
    # Better Dodge
    RingStateInfoEffect(115),
    # Absorb HP. Trigger params dictate when this effect procs
    RingStateInfoEffect(199, ["effectTargetFriend", "effectTargetEnemy", "magParamChange", "miracleParamChange"], [0, 0, 1, 1]),

    # Defense
    RingEffects(["physicsDiffence"], [25]),
    RingEffects(["physicsDiffence", "magicDiffence", "fireDiffence", "thunderDiffence"], [20, 20, 20, 20], num_effects=2),
    RingEffects(["slashDamageCutRate", "blowDamageCutRate", "thrustDamageCutRate", "neutralDamageCutRate", "magicDamageCutRate", 
                "fireDamageCutRate", "thunderDamageCutRate"], [0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8], num_effects=2),
    # Attack Power
    RingEffects(["physicsAttackPowerRate", "magicAttackPowerRate", "fireAttackPowerRate", "thunderAttackPowerRate"], [1.15, 1.15, 1.15, 1.15], num_effects=1),
    # Equip Weight Change ratio
    RingEffects(["equipWeightChangeRate"], [1.2]),
    # Stamina recovery speed
    RingEffects(["staminaRecoverChangeSpeed"], [10]),
    # Resistance
    RingEffects(["registPoizonChangeRate", "registCurseChangeRate", "registIllnessChangeRate", "registBloodChangeRate"], [1.5, 1.5, 1.5, 1.5], num_effects=2),
    # HP
    RingEffects(["maxHpRate"], [1.1], hidden_effect_names=["bCurrHPIndependeMaxHP"], hidden_effect_values=[1]),
    # Hp changed per second. Negative restores hp
    RingEffects(["changeHpRate"], [-1], num_effects=1, hidden_effect_names=["motionInterval"], hidden_effect_values=[1]),
    # Stamina
    RingEffects(["maxStaminaRate"], [1.2]),
    # Arrow distance,
    RingEffects(["bowDistRate"], [30]),
    # Poise
    RingEffects(["changeSuperArmorPoint"], [20]),
    # Soul Absorption
    RingEffects(["soulRate"], [1.1]),

]
HIGH_RING_EFFECTS: list[Union[RingEffects, RingStateInfoEffect]] = [
    # Defense
    RingEffects(["physicsDiffence"], [50]),
    RingEffects(["physicsDiffence", "magicDiffence", "fireDiffence", "thunderDiffence"], [35, 35, 35, 35], num_effects=2),
    RingEffects(["slashDamageCutRate", "blowDamageCutRate", "thrustDamageCutRate", "neutralDamageCutRate", "magicDamageCutRate", 
                "fireDamageCutRate", "thunderDamageCutRate"], [0.75, 0.75, 0.75, 0.75, 0.75, 0.75, 0.75], num_effects=2),
    # Attack Power
    RingEffects(["physicsAttackPowerRate", "magicAttackPowerRate", "fireAttackPowerRate", "thunderAttackPowerRate"], [1.2, 1.2, 1.2, 1.2], num_effects=1),
    # Equip Weight Change ratio
    RingEffects(["equipWeightChangeRate"], [1.35]),
    # Stamina recovery speed
    RingEffects(["staminaRecoverChangeSpeed"], [20]),
    # Resistance
    RingEffects(["registPoizonChangeRate", "registCurseChangeRate", "registIllnessChangeRate", "registBloodChangeRate"], [1.5, 1.5, 1.5, 1.5], num_effects=2),
    # HP
    RingEffects(["maxHpRate"], [1.2], hidden_effect_names=["bCurrHPIndependeMaxHP"], hidden_effect_values=[1]),
    # Stamina
    RingEffects(["maxStaminaRate"], [1.35]),
    # Poise
    RingEffects(["changeSuperArmorPoint"], [40]),
    # Soul Absorption
    RingEffects(["soulRate"], [1.25]),
]
LEGENDARY_RING_EFFECTS: list[Union[RingEffects, RingStateInfoEffect]] = [
    # Defense
    RingEffects(["physicsDiffence"], [75]),
    RingEffects(["physicsDiffence", "magicDiffence", "fireDiffence", "thunderDiffence"], [40, 40, 40, 40], num_effects=2),
    RingEffects(["slashDamageCutRate", "blowDamageCutRate", "thrustDamageCutRate", "neutralDamageCutRate", "magicDamageCutRate", 
                "fireDamageCutRate", "thunderDamageCutRate"], [0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7], num_effects=2),
    # Attack Power
    RingEffects(["physicsAttackPowerRate", "magicAttackPowerRate", "fireAttackPowerRate", "thunderAttackPowerRate"], [1.25, 1.25, 1.25, 1.25], num_effects=1),
    # Equip Weight Change ratio
    RingEffects(["equipWeightChangeRate"], [1.5]),
    # Stamina recovery speed
    RingEffects(["staminaRecoverChangeSpeed"], [30]),
    # Resistance
    RingEffects(["registPoizonChangeRate", "registCurseChangeRate", "registIllnessChangeRate", "registBloodChangeRate"], [4, 4, 4, 4], num_effects=2),
    # HP
    RingEffects(["maxHpRate"], [1.3], hidden_effect_names=["bCurrHPIndependeMaxHP"], hidden_effect_values=[1]),
    # Stamina
    RingEffects(["maxStaminaRate"], [1.45]),
    # Poise
    RingEffects(["changeSuperArmorPoint"], [60]),
    # Soul Absorption
    RingEffects(["soulRate"], [1.5]),
]

RING_EFFECT_LEVEL_TO_EFFECTS = {
    RingEffectLevel.NEGATIVE: NEGATIVE_RING_EFFECTS,
    RingEffectLevel.LOW: LOW_RING_EFFECTS,
    RingEffectLevel.MEDIUM: MEDIUM_RING_EFFECTS,
    RingEffectLevel.HIGH: HIGH_RING_EFFECTS,
    RingEffectLevel.LEGENDARY: LEGENDARY_RING_EFFECTS,
}

RING_EFFECT_TO_SUMMARY_TEXT_MAPPING_AND_DISPLAY_FUNC = {
    "physicsDiffence": "Physical Defense: {value:+g}",
    "magicDiffence": "Magic Defense: {value:+g}",
    "fireDiffence": "Fire Defense: {value:+g}",
    "thunderDiffence": "Lightning Defense: {value:+g}",
    "equipWeightChangeRate": "Equipment Weight Capacity: {value:.0%}",
    "staminaRecoverChangeSpeed": "Stamina Recovery Speed: {value:+g}",
    "conditionHp": "Ring effects activate at {value:.0%} HP",
    "physicsAttackPowerRate": "Physical Attack Power: {value:.0%}",
    "magicAttackPowerRate": "Magic Attack Power: {value:.0%}",
    "fireAttackPowerRate": "Fire Attack Power: {value:.0%}",
    "thunderAttackPowerRate": "Lightning Attack Power: {value:.0%}",
    "registPoizonChangeRate": "Poison Resistance: {value:.0%}",
    "registCurseChangeRate": "Curse Resistance: {value:.0%}",
    "registIllnessChangeRate": "Disease Resistance: {value:.0%}",
    "registBloodChangeRate": "Blood Loss Resistance: {value:.0%}",
    "changeMagicSlot": "Attunement Slots: {value:+g}",
    "maxHpRate": "Max HP: {value:.0%}",
    "changeHpRate": ("HP % per Sec: {value:+g}%", lambda x: x*-1),
    # bowDistRate is a flat number that represents a percentage. Weird
    "bowDistRate": "Arrow Distance: {value:+g}%",
    "changeSuperArmorPoint": "Poise: {value:+g}",
    "soulRate": "Additional Souls: {value:.0%}",
    "sightSearchEnemyCut": "Enemy Vision: {value:+g}%",
    "hearingSearchEnemyCut": "Enemy Hearing: {value:+g}%",
    "maxStaminaRate": "Max Stamina: {value:.0%}",
    "maxDurability": "Equipment Durability: {value:+g}",
    "slashDamageCutRate": "Slash Damage Taken: {value:.0%}", 
    "blowDamageCutRate": "Strike Damage Taken: {value:.0%}", 
    "thrustDamageCutRate": "Thrust Damage Taken: {value:.0%}",
    "neutralDamageCutRate": "Physical Damage Taken: {value:.0%}",  
    "magicDamageCutRate": "Magic Damage Taken: {value:.0%}", 
    "fireDamageCutRate": "Fire Damage Taken: {value:.0%}", 
    "thunderDamageCutRate": "Lightning Damage Taken: {value:.0%}",
}

STATE_INFO_ID_TO_SUMMARY_TEXT_MAPPING = {
    66: "Item Discovery +",
    115: "Better Dodge",
    193: "Spell Duration +",
    199: "Absorb HP on hit",
}


class RingRandomizer:
    """
    Randomize the rings in the game by modifying their associated SpEffectParam values.
    This resets all rings to a default template, ignoring the three rings that are required to beat the game in some fashion.
    Afterwards each ring is a assigned a template based on the provided distribution. This template determines how many affects and how 
    strong those affects are.
    """

    def __init__(self, game_params, distribution, write_item_summary):
        self.distribution = distribution
        self.ring_param = game_params.param_mapping["EquipParamAccessory"]
        self.sp_effect_param = game_params.param_mapping["SpEffectParam"]
        self.ring_item_summary_msg = game_params.item_msg_mapping["Accessory_description_"]
        self.ring_effect_to_default = self.generate_blank_ring_template()
        self.write_item_summary = write_item_summary

    def generate_blank_ring_template(self):
        # Load the csv file containing the ring effect template
        with open("default_vals\\RingSpEffectParam.csv", "r") as f:
            effect_column_names = f.readline().strip().split(",")
            effect_values = f.readline().strip().split(",")
        ring_effect_to_default = {}
        for column_name, value in zip(effect_column_names, effect_values):
            ring_effect_to_default[column_name] = value
        return ring_effect_to_default

    def generate_sp_effects(self, sp_effect_row, ring_id):
        max_effects = 4
        ring_template, ring_tier = self.select_ring_tier_and_template()
        ring_summary_txts = []
        selected_effects = []
        for effect_level in ring_template:
            while True:
                # Pick a random choice from the associated ring effect level to value mapping
                all_effects = RING_EFFECT_LEVEL_TO_EFFECTS[effect_level]
                chosen_effect = random.choice(all_effects)
                # Make sure we have less than max effects
                if (len(ring_summary_txts) + chosen_effect.num_effects) > max_effects:
                    continue
                # Repick if the chosen effect has an effect that is already on the ring. 
                if chosen_effect.check_no_duplicate_effects(selected_effects):
                    break
            selected_effects.extend(chosen_effect.get_all_effect_names())
            summary_texts = chosen_effect.modify_sp_effect_row_and_generate_summary_text(sp_effect_row)
            ring_summary_txts.extend(summary_texts)

        print(ring_summary_txts)
        # Replace the item summary text for the ring with a new one that includes the effects of the ring
        print(f"Generated the following summary text for ring id {ring_id}: {', '.join(ring_summary_txts)}")
        print(f"Ring tier was {ring_tier.name}")
        if self.write_item_summary:
            self.ring_item_summary_msg.replace_text_by_id(
                ring_id, f"{', '.join(ring_summary_txts)}")

    def default_sp_effect_row(self, sp_effect_row):
        for key, value in list(self.ring_effect_to_default.items()):
            sp_effect_row.set(key, str(value))

    def select_ring_tier_and_template(self) -> tuple[list[RingEffectLevel], RingTier]:
        distribution_rank = random.choices(range(len(self.distribution)), weights=self.distribution)[0]
        ring_tier = RingTier(distribution_rank)
        tier_distribution = DISTRIBUTION_RANK_TO_TEMPLATES[ring_tier]
        selected_template = random.choices(tier_distribution, weights=[t[0] for t in tier_distribution])[0][1]
        return selected_template, ring_tier

    def randomize(self):
        valid_ring_sp_effect_ids = []
        # For each ring in EquipParamAccessory, find the assocaited spEffect and add that to a list
        for ring in self.ring_param.root.findall("rows/row"):
            if int(ring.get("id")) not in RING_IDS_TO_IGNORE:
                valid_ring_sp_effect_ids.append((ring.get("refId"), ring.get("id")))
        
        for sp_effect_id, ring_id in valid_ring_sp_effect_ids:
            print(f"\nRandomizing ring with id {ring_id} and sp effect id {sp_effect_id}")
            sp_effect_row = self.sp_effect_param.get_row_by_id(sp_effect_id)
            self.default_sp_effect_row(sp_effect_row)
            self.generate_sp_effects(sp_effect_row, ring_id)            

if __name__ == "__main__":
    from witchy_util import GameParams
    # Instantiate GameParams and load existing XML files
    # Requires a previous unpacking of GameParams using unpack()
    gp = GameParams(None, None)
    gp.load_existing_xml()
    randomizer = RingRandomizer(gp, [0.25, 0.25, 0.25, 0.25])
    randomizer.randomize()