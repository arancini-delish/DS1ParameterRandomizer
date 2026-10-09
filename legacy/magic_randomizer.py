import math
import random

from param_categorizer import ParamParser
from sp_effect_randomizer import SelfBuffSpEffectSpec, WeaponBuffSpEffectSpec
from projectile_randomizer import SelfBuffBulletSpec
from constants import GROUND_TRACE_MIN_SPAWN_COUNT, SpellTypes

MAGIC_TIER_TO_SCORE = [100, 125, 150, 200]


class MultSpellProperty:
    def __init__(self):
        self.multiplier = 1.0

    def get_field_values(self):
        return {}


class AdditiveSpellProperty:
    def __init__(self):
        self.score = 0

    def get_field_values(self):
        return {}


class UsageCount(MultSpellProperty):
    USAGES = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 30]
    # At first having less usages is a big detriment, so scale quickly
    # After 8 each subsequent usage has about the same utility. Scale linearly down
    USAGE_TO_MULTIPLIER = [3.0, 2.0, 1.5, 1.25, 1.125, 1.1, 1.0, 0.95, 0.9, 0.8, 0.73, 0.64, 0.5]

    def __init__(self):
        super().__init__()
        # All usage counts occur equally randomly. A weighted distribution can be added if this is not fun
        usage, multiplier = random.choice(list(zip(self.USAGES, self.USAGE_TO_MULTIPLIER)))
        self.usage = usage
        self.multiplier = multiplier
    
    def get_field_values(self):
        return {"maxQuantity": str(self.usage)}
    
    def __repr__(self):
        return f"UsageCount:{self.usage}"


class ContinuousUsageCount(UsageCount):
    USAGES = [40, 60, 80, 100, 120, 160]
    USAGE_TO_MULTIPLIER = [2.0, 1.5, 1.0, 0.8, 0.6, 0.4]


class SlotUsage(AdditiveSpellProperty):
    def __init__(self):
        # Simple rule, 1 is default, 2 grants a flat score of 50, but this only occurs 10% of the time
        # TODO should we add in 3 slots ultimate spells
        if random.random() < 0.10:
            self.slot_count = 2
            self.score = 50
        else:
            self.score = 0
            self.slot_count = 1

    def get_field_values(self):
        return {"slotLength": str(self.slot_count)}
    
    def __repr__(self):
        return f"SlotUsage:{self.slot_count}"


class StatRequirement(AdditiveSpellProperty):
    REQ_STAT_TO_SCORE = [
        (10, -50),
        (12, -40),
        (14, -30),
        (15, -35),
        (16, 0),
        (18, 10),
        (20, 15),
        (24, 20),
        (32, 50),
        (40, 75),
        (45, 100),
    ]

    ID_TO_SCHOOL = {"0": "sorcery", "1": "miracle", "2": "pyromancy"}
    def __init__(self, school_id):
        # 1/3rd of the time we make each respective magic school
        self.school = self.ID_TO_SCHOOL[school_id]
        self.school_id = school_id
        if self.school == "pyromancy":
            self.faith_req = 0
            self.int_req = 0
            self.score = -75
            return
        req, score = random.choice(self.REQ_STAT_TO_SCORE)
        self.score = score
        if self.school == "sorcery":
            self.int_req = req
            self.faith_req = 0
        else:
            self.int_req = 0
            self.faith_req = req
    
    def get_field_values(self):
        if self.school == "sorcery":
            return {"requirementIntellect": str(self.int_req), "requirementFaith": str(self.faith_req), "ezStateBehaviorType": str(self.school_id)}
        elif self.school == "miracle":
            return {"requirementIntellect": str(self.int_req), "requirementFaith": str(self.faith_req), "ezStateBehaviorType": str(self.school_id)}
        else:
            return {"requirementIntellect": str(self.int_req), "requirementFaith": str(self.faith_req), "ezStateBehaviorType": str(self.school_id)}
    
    def __repr__(self):
        if self.school == "sorcery":
            return f"StatRequirement:sorcery:{self.int_req}"
        elif self.school == "miracle":
            return f"StatRequirement:miracle:{self.faith_req}"
        else:
            return f"StatRequirement:pyromancy"
    

class MagicTypeSpecBase:
    IS_CONTINUOUS_SPELL = False

    def __init__(self, spell, magic_score):
        self.magic_score = magic_score
        self.spell = spell
        self.field_values = {}
        # Reset the references to the spEffect and bullet, so we can assign new ones
        spell.reset_references()

    def randomize_spell_attributes(self) -> float:
        """
        Default randomization, should work for everything but spray type spells
        Returns the remaining budget to be used for the spEffect or bullet spawned by the spell
        """
        # Picks from relevant properties until we hit a score
        all_selected_properties = []
        # Start with multipliers.
        if self.IS_CONTINUOUS_SPELL:
            usage_count = ContinuousUsageCount()
        else:
            usage_count = UsageCount()
        budget = self.magic_score * usage_count.multiplier
        all_selected_properties.append(usage_count)

        slot_usage = SlotUsage()
        budget += slot_usage.score
        all_selected_properties.append(slot_usage)

        stat_requirement = StatRequirement(self.spell.school_id)
        budget += stat_requirement.score
        all_selected_properties.append(stat_requirement)

        self.field_values = self.default_magic_row()
        for selected_property in all_selected_properties:
            self.field_values.update(selected_property.get_field_values())
        
        return budget
    
    def update_sp_efffect_field_values(self, sp_effect):
        self.field_values["refId"] = str(sp_effect.id)
        self.field_values["refCategory"] = "2"
        self.spell.sp_effect = sp_effect

    def update_bullet_field_values(self, bullet):
        self.field_values["refId"] = str(bullet.id)
        self.field_values["refCategory"] = "1"
        self.spell.bullet = bullet

    def randomize_name(self):
        raise NotImplementedError

class LinearSpellSpec(MagicTypeSpecBase):
    """
    Spells that shoot a projectile straight at a target from a wand
    """
    def default_magic_row(self):
        # Load the csv file containing the magic param defaults for linear spells
        with open("default_vals\\default_linear_magic_param.csv", "r") as f:
            field_column_names = f.readline().strip().split(",")
            field_values = f.readline().strip().split(",")
        magic_field_to_default = {}
        for column_name, value in zip(field_column_names, field_values):
            magic_field_to_default[column_name] = value
        return magic_field_to_default
            

class SelfBuffSpellSpec(MagicTypeSpecBase):
    # TODO use the right spell default
    def default_magic_row(self):
        # Load the csv file containing the magic param defaults for linear spells
        with open("default_vals\\default_linear_magic_param.csv", "r") as f:
            field_column_names = f.readline().strip().split(",")
            field_values = f.readline().strip().split(",")
        magic_field_to_default = {}
        for column_name, value in zip(field_column_names, field_values):
            magic_field_to_default[column_name] = value
        return magic_field_to_default
    
    def randomize_sp_effect(self, remaining_budget):
        # Generate a spEffectSpec
        effect_spec = SelfBuffSpEffectSpec(self.sp_effect, remaining_budget)
        effect_spec.randomize()
        self.spell.sp_effect.set_spec(effect_spec)


class WeaponBuffSpellSpec(MagicTypeSpecBase):
    def default_magic_row(self):
        # Load the csv file containing the magic param defaults for linear spells
        with open("default_vals\\default_linear_magic_param.csv", "r") as f:
            field_column_names = f.readline().strip().split(",")
            field_values = f.readline().strip().split(",")
        magic_field_to_default = {}
        for column_name, value in zip(field_column_names, field_values):
            magic_field_to_default[column_name] = value
        return magic_field_to_default
    
    def randomize_sp_effect(self, remaining_budget):
        # Generate a spEffectSpec
        effect_spec = WeaponBuffSpEffectSpec(self.sp_effect, remaining_budget)
        effect_spec.randomize()
        self.spell.sp_effect.set_spec(effect_spec)


class SelfBuffThroughProjectileSpellSpec(MagicTypeSpecBase):
    def default_magic_row(self):
        # Load the csv file containing the magic param defaults for linear spells
        with open("default_vals\\default_linear_magic_param.csv", "r") as f:
            field_column_names = f.readline().strip().split(",")
            field_values = f.readline().strip().split(",")
        magic_field_to_default = {}
        for column_name, value in zip(field_column_names, field_values):
            magic_field_to_default[column_name] = value
        return magic_field_to_default
    
    def randomize_bullet(self, bullets, sp_effects, remaining_budget):
        budget_per_effect = remaining_budget / len(bullets)
        for bullet, sp_effect in zip(bullets, sp_effects):
            bullet_spec = SelfBuffBulletSpec(bullet, budget_per_effect)
            bullet_spec.randomize(sp_effect)
            bullet.set_spec(bullet_spec)
        
        # Make the bullets chain to the next bullet
        for i in range(len(bullets)-1):
            bullets[i].spec.update_hit_bullet(bullets[i+1])

class GroundTraceSpellSpec(MagicTypeSpecBase):
    def randomize_spell_attributes(self) -> float:
        remaining_budget = super().randomize_spell_attributes()
        # Pick a random number of spawns
        num_spawns = random.randint(GROUND_TRACE_MIN_SPAWN_COUNT, 12)
        return remaining_budget, num_spawns
    
    def randomize_bullet(self, bullets, atk, remaining_budget):
        # first projectile is special and casts towards the ground to start the trace
        # the remaining projectiles spawn in a row and are all essentially a copy of each other
        # Half the remaining budget is allocated to projectile properties
        # The other half is allocated to the atk param, which is shared by all projectiles
        # Since each projectile in the trace is treated as a single attack we do not split the budget 
        # between projectiles
        spawn_bullet_spec = GroundTraceSpawnBulletSpec(bullets[0])
        spawn_bullet_spec.randomize(remaining_budget // 2, atk)
        bullets[0].set_spec(spawn_bullet_spec)
        for i in range(1, len(bullets)):
            trace_bullet_spec = GroundTraceBulletSpec(bullets[i], remaining_budget // 2)
            trace_bullet_spec.randomize(remaining_budget // 2, atk)
            bullets[i].set_spec(trace_bullet_spec)

class MagicRandomizer:
    """
    Randomizes the magic used by the player and npcs
    Magic in dark souls is a complicated mess of different types of spells, each with their own properties and behaviors. Some are expected
    but others "hack" existing systems. 
    We want to use all existing SP effects, bullets and atk params to randomize magic. This keeps network of associated ids intact.

    Doing this is a bit tricky but can be achieved by ordering the spells by type
    1. Single effect spells, use up 1 sp effect which simply scales to the score
    2. Weapon buffs, use up 1 sp effect which scales to the score
    3. Multi effect spells. These use chained projectiles, each applying a different effect to the shooter.
    4. At this point, we need to figure out the non negotiable bullets and hit bullets. Atk params are straight forwards, we can just make a distribution of them and re-use as needed
    5. Any remaining sp effects and bullets should be distributed to the remaining spells, in order of highest to lowest score
    6. Then with the full graph for each spell we can fill out the actual values used
    """
    def __init__(self, distribution, param_parser):
        self.distribution = distribution
        self.param_parser = param_parser
    
    def randomize(self):
        known_bullets, known_atks, known_sp_effects = self.param_parser.gather_spell_related_hit_bullets_atk_sp_effects()
        bullet_pointer = 0
        atk_pointer = 0
        sp_effect_pointer = 0
        print(len(known_bullets), len(known_atks), len(known_sp_effects), len(self.param_parser.spells))
        for spell in self.param_parser.spells_by_type[SpellTypes.SELF_BUFF]:
            magic_score = random.choices(MAGIC_TIER_TO_SCORE, weights=self.distribution)[0]
            spec = SelfBuffSpellSpec(spell, magic_score)
            remaining_budget = spec.randomize_spell_attributes()
            # Assign an spEffect, randomize is using the remaining budget
            sp_effect = known_sp_effects[sp_effect_pointer]
            sp_effect_pointer += 1
            spec.update_sp_efffect_field_values(sp_effect)
            spec.randomize_sp_effect()
        
        for spell in self.param_parser.spells_by_type[SpellTypes.WEAPON_BUFF]:
            magic_score = random.choices(MAGIC_TIER_TO_SCORE, weights=self.distribution)[0]
            spec = LinearSpellSpec(spell, magic_score)
            remaining_budget = spec.randomize_spell_attributes()
            # Assign an spEffect, randomize is using the remaining budget
            sp_effect = known_sp_effects[sp_effect_pointer]
            sp_effect_pointer += 1
            spec.update_sp_efffect_field_values(sp_effect)
            spec.randomize_sp_effect()

        for spell in self.param_parser.spells_by_type[SpellTypes.SELF_BUFF_THROUGH_PROJECTILE]:
            magic_score = random.choices(MAGIC_TIER_TO_SCORE, weights=self.distribution)[0]
            spec = SelfBuffThroughProjectileSpellSpec(spell, magic_score)
            remaining_budget = spec.randomize_spell_attributes()
            # Pick between 2 and 4 effects, each with a different projectile
            num_effects = random.choices([2, 3, 4], weights=[0.5, 0.25, 0.25])[0]
            sp_effects = known_sp_effects[sp_effect_pointer:sp_effect_pointer + num_effects]
            bullets = known_bullets[bullet_pointer:bullet_pointer + num_effects]
            sp_effect_pointer += num_effects
            bullet_pointer += num_effects
            spec.update_bullet_field_values(bullets[0])
            spec.randomize_bullet(bullets, sp_effects, remaining_budget)
        
        # Ground trace spells require a set amount of bullets. Get this out of the way
        for spell in self.param_parser.spells_by_type[SpellTypes.GROUND_TRACE]:
            magic_score = random.choices(MAGIC_TIER_TO_SCORE, weights=self.distribution)[0]
            spec = GroundTraceSpellSpec(spell, magic_score)
            remaining_budget, num_spawn_count = spec.randomize_spell_attributes()


        # All the non negotiable spells are done, now we can start randomizing the rest
        # Linear, lobbed, spray and aoe ground are all single projectile spell in that the projectile travels and does 
        # a portion of the primary damage. Any of these are free to have a hitbullet or spEffect assigned to them
        # Orbit, Lingering and point blank are all projectiles that spawn a projectile that travels or does damage. These travelling
        # projectiles are free to have a hitbullet or spEffect assigned to them
        # So we can figure out the non negotiable projectiles first. Any remaining projectiles and spEffects will get
        # assigned to the remaining spells in order of highest to lowest score




if __name__ == "__main__":
    from witchy_util import GameParams
    # Instantiate GameParams and load existing XML files
    # Requires a previous unpacking of GameParams using unpack()
    gp = GameParams("C:\Program Files (x86)\Steam\steamapps\common\DARK SOULS REMASTERED\param\GameParam\GameParam.parambnd.dcx", 
                    "C:\Program Files (x86)\Steam\steamapps\common\DARK SOULS REMASTERED\msg\ENGLISH\item.msgbnd.dcx")
    gp.load_existing_xml(unpack_if_missing=True)
    param_parser = ParamParser(gp)
    param_parser.build_graph()
    randomizer = MagicRandomizer([0.25, 0.25, 0.25, 0.25], param_parser)
    randomizer.randomize()

    # Test num combinations, and distribution
    unique_scores = set()
    for i in range(100):
        magic_score = random.choices(MAGIC_TIER_TO_SCORE, weights=[0.25, 0.25, 0.25, 0.25])[0]
        spell = random.choice(param_parser.spells)
        spec = LinearSpellSpec(spell, magic_score)
        budget = spec.generate_spell_spec_using_score()
        unique_scores.add(budget)

    print(len(unique_scores))
    print(unique_scores)
    print(sum(unique_scores) / len(unique_scores))
    sorted_scores = sorted(unique_scores)
    print(sorted_scores)
    # median
    print(sorted_scores[len(sorted_scores) // 2])
    import matplotlib.pyplot as plt
    plt.hist(unique_scores, bins=100)
    plt.show()