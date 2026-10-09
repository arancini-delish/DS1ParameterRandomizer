"""
Reads all of the params from the game and categorizes them into groups based on their properties and behaviors. This is used to facilitate 
randomization of parameters while maintaining some level of coherence in the game mechanics. 

For randomization we typically want to do a ground up approach. First we find the atomic params associated with a sub category of something
we want to randomize, such as spells. All of the atk_params, spEffects and bullet param records associated with a sub category of spell can 
be randomized in a constrained fashion, while still maintaining the overall feel of the spell. 

Occasionally we also want to know if a atomic param is used by many different sources, in which case we need to take a careful approach.

The following is a list of all known categories and subcategories
Spells
    Linear
    Lobbed
    Orbit/Delayed
    Ground-Trace
    Point Blank
    Spray
    AOE Ground
    Weapon Buffs
    Self Buffs
    Trigger Effects
Rings
    effects
Projectiles
    Linear
    Lobbed
    Homing
    Exploding
    Spawn on hit
    Spray


"""
import xml.etree.ElementTree as ET

from id_to_names.EquipParamAccessory import ring_id_to_name
from id_to_names.Magic import magic_id_to_name
from id_to_names.Bullet import bullet_id_to_name
from constants import (
    SpellTypes, 
    MAGIC_TO_IGNORE,
    SPRAY_ANIMATION_IDS,
    GROUND_TRACE_MIN_SPAWN_COUNT,
    GROUND_SPAWN_EMITTER_TYPE,
    AOE_GROUND_SPAWN_EMITTER_TYPE,
    LINGERING_MIN_LIFE,
    LINGERING_MIN_DMG_HIT_RECORD_LIFE_TIME,
    POINT_BLANK_MIN_LIFE,
    POINT_BLANK_DISTANCE,
    LOBBED_GRAVITY
)
from abc import ABC, abstractmethod

from pprint import pprint



class ReferencedObject(ABC):
    def __init__(self, id, raw):
        self.id = id
        self.raw = raw
        self.referenced_by = set()  # Keep track of which other objects reference this one
        self.spec = None
        self.raw_updated = False

    def update_raw_using_spec(self):
        if self.raw_updated:
            raise RuntimeError("Cannot update raw twice")
        if self.spec is not None:
            for field_name, value in self.spec.field_values.items():
                self.raw.set(field_name, value)
            self.raw_updated = True

    def set_spec(self, spec):
        if self.spec is not None:
            raise RuntimeError("Cannot set spec twice")
        self.spec = spec
    
    @abstractmethod
    def reset_references(self):
        pass

    def __repr__(self):
        return self.__str__()
    
class SpEffect(ReferencedObject):
    def __init__(self, id, raw: ET.Element):
        super().__init__(id, raw)

    def reset_references(self):
        pass
    
    def __str__(self):
        return f"SpEffect:{self.id}"
    
    
class Atk(ReferencedObject):
    def __init__(self, id, raw: ET.Element, target_sp_effect_1: SpEffect | None, target_sp_effect_2: SpEffect | None, target_sp_effect_3: SpEffect | None, 
                        target_sp_effect_4: SpEffect | None, target_sp_effect_5: SpEffect | None):
        super().__init__(id, raw)
        self.target_sp_effect_1 = target_sp_effect_1
        self.target_sp_effect_2 = target_sp_effect_2
        self.target_sp_effect_3 = target_sp_effect_3
        self.target_sp_effect_4 = target_sp_effect_4
        self.target_sp_effect_5 = target_sp_effect_5

        # Update referenced_by for the sp effects
        if target_sp_effect_1 is not None:
            target_sp_effect_1.referenced_by.add(self)
        if target_sp_effect_2 is not None:
            target_sp_effect_2.referenced_by.add(self)
        if target_sp_effect_3 is not None:
            target_sp_effect_3.referenced_by.add(self)
        if target_sp_effect_4 is not None:
            target_sp_effect_4.referenced_by.add(self)
        if target_sp_effect_5 is not None:
            target_sp_effect_5.referenced_by.add(self)

    def reset_references(self):
        self.target_sp_effect_1 = None
        self.target_sp_effect_2 = None
        self.target_sp_effect_3 = None
        self.target_sp_effect_4 = None
        self.target_sp_effect_5 = None

    def __str__(self):
        return f"Atk:{self.id}"

class Bullet(ReferencedObject):
    def __init__(self, id, raw: ET.Element, atk: Atk | None, shooter_sp_effect: SpEffect | None, target_sp_effect_1: SpEffect | None, 
                 target_sp_effect_2: SpEffect | None, target_sp_effect_3: SpEffect | None, target_sp_effect_4: SpEffect | None, 
                 target_sp_effect_5: SpEffect | None, bullet_on_hit: "Bullet | None"):
        super().__init__(id, raw)
        self.atk = atk
        self.shooter_sp_effect = shooter_sp_effect
        self.target_sp_effect_1 = target_sp_effect_1
        self.target_sp_effect_2 = target_sp_effect_2
        self.target_sp_effect_3 = target_sp_effect_3
        self.target_sp_effect_4 = target_sp_effect_4
        self.target_sp_effect_5 = target_sp_effect_5
        self.bullet_on_hit = bullet_on_hit
        self.name = bullet_id_to_name.get(id, f"Unknown Bullet {id}")

        # Update referenced_by for the atk param, shooter sp effect, target sp effects and bullet on hit
        if atk is not None:
            atk.referenced_by.add(self)
        if shooter_sp_effect is not None:
            shooter_sp_effect.referenced_by.add(self)
        if bullet_on_hit is not None:
            bullet_on_hit.referenced_by.add(self)
        if target_sp_effect_1 is not None:
            target_sp_effect_1.referenced_by.add(self)
        if target_sp_effect_2 is not None:
            target_sp_effect_2.referenced_by.add(self)
        if target_sp_effect_3 is not None:
            target_sp_effect_3.referenced_by.add(self)
        if target_sp_effect_4 is not None:
            target_sp_effect_4.referenced_by.add(self)
        if target_sp_effect_5 is not None:
            target_sp_effect_5.referenced_by.add(self)

    def reset_references(self):
        self.atk = None
        self.shooter_sp_effect = None
        self.target_sp_effect_1 = None
        self.target_sp_effect_2 = None
        self.target_sp_effect_3 = None
        self.target_sp_effect_4 = None
        self.target_sp_effect_5 = None
        self.bullet_on_hit = None

    def __str__(self):
        return f"Bullet:{self.name}"

class Spell(ReferencedObject):
    def __init__(self, id, raw, sp_effect: SpEffect | None, bullet: Bullet | None):
        super().__init__(id, raw)
        self.type = None
        self.sp_effect = sp_effect
        self.bullet = bullet
        self.name = magic_id_to_name.get(id, f"Unknown Spell {id}")
        self.school_id = self.raw.get("ezStateBehaviorType")

        # Update referenced_by for the sp effect and bullet       
        if sp_effect is not None:
            sp_effect.referenced_by.add(self)
        if bullet is not None:
            bullet.referenced_by.add(self)

    def reset_references(self):
        self.sp_effect = None
        self.bullet = None

    def __str__(self):
        return f"Spell:{self.name}"

class Ring(ReferencedObject):
    """
    Rings are a bit more straightforward, they typically just have an associated spEffect that defines the properties of the ring, 
    such as if it is a buff or a debuff and what stats it modifies
    """
    def __init__(self, id, raw, sp_effect: SpEffect | None):
        super().__init__(id, raw)
        self.sp_effect = sp_effect
        self.name = ring_id_to_name.get(id, f"Unknown Ring {id}")

        # Update referenced_by for the sp effect
        if sp_effect is not None:
            sp_effect.referenced_by.add(self)

    def reset_references(self):
        self.sp_effect = None

    def __str__(self):
        return f"Ring:{self.name}"

sp_effect_cache = {}
atk_cache = {}
bullet_cache = {}

class ParamParser():
    """
    Ongoing effort to categorize all of the params in the game into groups based on their properties and behaviors
    """

    def __init__(self, game_params):
        self.ring_param = game_params.param_mapping["EquipParamAccessory"]
        self.sp_effect_param = game_params.param_mapping["SpEffectParam"]
        self.bullet_param = game_params.param_mapping["Bullet"]
        self.magic_param = game_params.param_mapping["Magic"]
        self.atk_param_pc = game_params.param_mapping["AtkParam_Pc"]
        self.atk_param_npc = game_params.param_mapping["AtkParam_Npc"]

        self.spells: list[Spell] = []
        self.rings: list[Ring] = []
        self.spells_by_type = {spell_type: [] for spell_type in SpellTypes}

    def build_graph(self):
        # Rings
        # For each ring in EquipParamAccessory, find the assocaited spEffect and add that to a list
        for ring in self.ring_param.root.findall("rows/row"):
            sp_effect_id = ring.get("refId")
            ring_id = ring.get("id")
            ring_sp_effect = self.get_sp_effect(sp_effect_id)
            self.rings.append(Ring(ring_id, ring, ring_sp_effect))

        # Spells
        # Spells can be categorized by following along the chain of references from Magic to SpEffect to Bullet to AtkParam, and 
        # categorizing based on the properties of each param in the chain
        for spell in self.magic_param.root.findall("rows/row"):
            if int(spell.get("id")) in MAGIC_TO_IGNORE:
                continue
            self.parse_spell(spell)
        self.categorize_spells()
            
    def get_sp_effect(self, sp_effect_id):
        if sp_effect_id == "0" or sp_effect_id == "-1" or sp_effect_id is None:
            return None
        if sp_effect_id in sp_effect_cache:
            sp_effect = sp_effect_cache[sp_effect_id]
        else:
            raw = self.sp_effect_param.get_row_by_id(sp_effect_id)
            sp_effect = SpEffect(sp_effect_id, raw)
            sp_effect_cache[sp_effect_id] = sp_effect
        return sp_effect
        
    def parse_spell(self, spell_row):
        sp_effect_or_bullet_id = spell_row.get("refId")
        # Is the refId a spEffect or a bullet? 1 is bullet, 2 is spEffect
        id_type = spell_row.get("refCategory")
        spell_id = spell_row.get("id")
        if id_type == "2":  # spEffect
            # This spell references a sp effect directly, so it is some type of buff for certain. Some buffs use the bullet param to 
            # define a buff projectile
            sp_effect = self.get_sp_effect(sp_effect_or_bullet_id)
            self.spells.append(Spell(spell_id, spell_row, sp_effect, None))
        else:  # bullet
            bullet = self.get_bullet(sp_effect_or_bullet_id)
            self.spells.append(Spell(spell_id, spell_row, None, bullet))

    def get_bullet(self, bullet_id):
        if bullet_id == "-1" or bullet_id is None:
            return None
        if bullet_id in bullet_cache:
            bullet = bullet_cache[bullet_id]
        else:
            bullet_row = self.bullet_param.get_row_by_id(bullet_id)
            bullet = self.parse_bullet(bullet_row)
            bullet_cache[bullet_id] = bullet
        return bullet
    
    def parse_bullet(self, bullet_row):
        """
        Bullets are a bit more complex, but roughly they either emit another projectile, cause damage or apply an sp effect to the shooter
        or a combination of all.
        """
        atk_id = bullet_row.get("atkId_Bullet")
        bullet_id = bullet_row.get("id")
        shooter_sp_effect_id = bullet_row.get("spEffectIDForShooter")
        target_sp_effect_1_id = bullet_row.get("spEffectId0")
        target_sp_effect_2_id = bullet_row.get("spEffectId1")
        target_sp_effect_3_id = bullet_row.get("spEffectId2")
        target_sp_effect_4_id = bullet_row.get("spEffectId3")
        target_sp_effect_5_id = bullet_row.get("spEffectId4")
        hit_bullet_id = bullet_row.get("HitBulletID")

        atk = self.get_atk(atk_id)
        shooter_sp_effect = self.get_sp_effect(shooter_sp_effect_id)
        target_sp_effect_1 = self.get_sp_effect(target_sp_effect_1_id)
        target_sp_effect_2 = self.get_sp_effect(target_sp_effect_2_id)
        target_sp_effect_3 = self.get_sp_effect(target_sp_effect_3_id)
        target_sp_effect_4 = self.get_sp_effect(target_sp_effect_4_id)
        target_sp_effect_5 = self.get_sp_effect(target_sp_effect_5_id)

        bullet_on_hit = self.get_bullet(hit_bullet_id)
            
        return Bullet(bullet_id, bullet_row, atk, shooter_sp_effect, target_sp_effect_1, target_sp_effect_2, target_sp_effect_3, 
                      target_sp_effect_4, target_sp_effect_5, bullet_on_hit)
    
    def get_atk(self, atk_id):
        if atk_id == "0" or atk_id == "-1" or atk_id is None:
            return None
        if atk_id in atk_cache:
            atk = atk_cache[atk_id]
        else:
            atk_row = self.atk_param_pc.get_row_by_id(atk_id)
            if atk_row is None:
                atk_row = self.atk_param_npc.get_row_by_id(atk_id)
            atk = self.parse_atk(atk_row)
            atk_cache[atk_id] = atk
        return atk
    
    def parse_atk(self, atk_row):
        atk_id = atk_row.get("id")
        target_sp_effect_1_id = atk_row.get("spEffectId0")
        target_sp_effect_2_id = atk_row.get("spEffectId1")
        target_sp_effect_3_id = atk_row.get("spEffectId2")
        target_sp_effect_4_id = atk_row.get("spEffectId3")
        target_sp_effect_5_id = atk_row.get("spEffectId4")
        target_sp_effect_1 = self.get_sp_effect(target_sp_effect_1_id)
        target_sp_effect_2 = self.get_sp_effect(target_sp_effect_2_id)
        target_sp_effect_3 = self.get_sp_effect(target_sp_effect_3_id)
        target_sp_effect_4 = self.get_sp_effect(target_sp_effect_4_id)
        target_sp_effect_5 = self.get_sp_effect(target_sp_effect_5_id)
        return Atk(atk_id, atk_row, target_sp_effect_1, target_sp_effect_2, target_sp_effect_3, 
                        target_sp_effect_4, target_sp_effect_5)
    
    def categorize_spells(self):
        for spell in self.spells:
            spell.type = self._classify_spell(spell)
            if spell.type is not None:
                self.spells_by_type[spell.type].append(spell)

        return self.spells_by_type

    def _classify_spell(self, spell: Spell):
        if spell.sp_effect is not None:
            return self._classify_sp_effect_spell(spell, spell.sp_effect)
        if spell.bullet is not None:
            return self._classify_bullet_spell(spell, spell.bullet)
        return None

    def _classify_sp_effect_spell(self, spell: Spell, sp_effect: SpEffect):
        """
        These are obvious effect only spells since they have no projectile
        However some effect spells use a projectile as a proxy to apply multiple effects
        """
        if spell.raw.get("isEnchant") == "1" or spell.raw.get("isShieldEnchant") == "1":
            return SpellTypes.WEAPON_BUFF

        if sp_effect.raw.get("replaceSpEffectId") not in ("-1", None):
            return SpellTypes.TRIGGER_EFFECT

        return SpellTypes.SELF_BUFF

    def _classify_bullet_spell(self, spell: Spell, bullet: Bullet):
        child_bullets = []
        while True:
            if not child_bullets:
                if bullet.bullet_on_hit is not None:
                    child_bullets.append(bullet.bullet_on_hit)
                    continue
                else:
                    break
            if child_bullets[-1].bullet_on_hit is not None:
                child_bullets.append(child_bullets[-1].bullet_on_hit)
            else:
                break

        if bullet.shooter_sp_effect is not None:
            # Projectiles that apply an effect to the shooter are typically self buffs
            return SpellTypes.SELF_BUFF_THROUGH_PROJECTILE
        
        # Rough check, spray spells work by having a special animation that continually emits a projectile
        # this makes identifying the spell difficult on anything but a hardcoded animation ID.
        if self._get_field_value(spell, "refType") in SPRAY_ANIMATION_IDS:
            return SpellTypes.SPRAY

        if self._get_field_value(bullet, "autoSearchNPCThinkID") != 0:
            # Any AI behaviour for the projectile probably means this spell is an orbit type spell
            return SpellTypes.ORBIT
 
        # Check that at least 3 child bullets are spawned, and the first N-1 are identical
        if len(child_bullets) >= GROUND_TRACE_MIN_SPAWN_COUNT:
            # Check that we spawn the hit bullet on the ground infront of the parent bullet
            if self._get_field_value(child_bullets[0], "EmittePosType") == GROUND_SPAWN_EMITTER_TYPE:
                # Make sure all the child bullets are identical bar id and hit bullet id
                is_trace = True
                for child_bullet_1, child_bullet_2 in zip(child_bullets[:-1], child_bullets[1:-1]):
                    set_1 = set(child_bullet_1.raw.items())
                    set_2 = set(child_bullet_2.raw.items())
                    diff = set_1.symmetric_difference(set_2)
                    if any([field_name not in ["name", "id", "HitBulletID"] for field_name, field_value in diff]):
                        is_trace = False
                        break
                if is_trace:
                    return SpellTypes.GROUND_TRACE

        # Check that we spawn the bullet on the ground randomly around the player
        if self._get_field_value(bullet, "EmittePosType") == AOE_GROUND_SPAWN_EMITTER_TYPE:
            return SpellTypes.AOE_GROUND
        
        # Lingering spells, the child bullets typically last a while and have a damage over time interval set
        if len(child_bullets) >= 1:
            if self._get_field_value(child_bullets[0], "life") >= LINGERING_MIN_LIFE and self._get_field_value(child_bullets[0], "dmgHitRecordLifeTime") > LINGERING_MIN_DMG_HIT_RECORD_LIFE_TIME:
                return SpellTypes.LINGERING

        # Immediate damage. Spell might have some velocity but has no distance. 
        if self._get_field_value(bullet, "dist") == POINT_BLANK_DISTANCE and self._get_field_value(bullet, "life") <= POINT_BLANK_MIN_LIFE:
            return SpellTypes.POINT_BLANK

        # Spells with an immediate gravity equal to real gravity are likely lobbed spells
        if self._get_field_value(bullet, "gravityInRange") == LOBBED_GRAVITY:
            return SpellTypes.LOBBED

        # All other spells are probably linear
        return SpellTypes.LINEAR


    def _get_field_value(self, bullet, field_name, default=0.0):
        value = bullet.raw.get(field_name, None)
        if value in {None, "", "-1"}:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            print(f"Failed to parse float value for bullet {bullet.name} field {field_name}")
            return default

    def _get_field_int(self, bullet, field_name, default=0):
        value = bullet.raw.get(field_name, None)
        if value in {None, "", "-1"}:
            return default
        try:
            return int(float(value))
        except (TypeError, ValueError):
            print(f"Failed to parse int value for bullet {bullet.name} field {field_name}")
            return default

    def gather_spell_related_hit_bullets_atk_sp_effects(self):
        known_bullets = []
        known_atks = []
        known_sp_effects = []
        for spell in self.spells:
            if spell.sp_effect is not None:
                known_sp_effects.append(spell.sp_effect)
            if spell.bullet is not None:
                target = spell.bullet
                while target is not None:
                    known_bullets.append(target)
                    if target.atk is not None:
                        known_atks.append(target.atk)
                    if target.shooter_sp_effect is not None:
                        known_sp_effects.append(target.shooter_sp_effect)
                    if target.target_sp_effect_1 is not None:
                        known_sp_effects.append(target.target_sp_effect_1)
                    if target.target_sp_effect_2 is not None:
                        known_sp_effects.append(target.target_sp_effect_2)
                    if target.target_sp_effect_3 is not None:
                        known_sp_effects.append(target.target_sp_effect_3)
                    if target.target_sp_effect_4 is not None:
                        known_sp_effects.append(target.target_sp_effect_4)
                    if target.target_sp_effect_5 is not None:
                        known_sp_effects.append(target.target_sp_effect_5)
                    target = target.bullet_on_hit
        return known_bullets, known_atks, known_sp_effects



    def categorize_projectiles(self):
        # This function would contain logic to categorize projectiles based on their properties
        pass

    def categorize_rings(self):
        # This function would contain logic to categorize rings based on their properties
        pass

if __name__ == "__main__":
    from witchy_util import GameParams
    # Instantiate GameParams and load existing XML files
    # Requires a previous unpacking of GameParams using unpack()
    gp = GameParams("C:\Program Files (x86)\Steam\steamapps\common\DARK SOULS REMASTERED\param\GameParam\GameParam.parambnd.dcx", 
                    "C:\Program Files (x86)\Steam\steamapps\common\DARK SOULS REMASTERED\msg\ENGLISH\item.msgbnd.dcx")
    gp.load_existing_xml(unpack_if_missing=True)
    parser = ParamParser(gp)
    parser.build_graph()
    print("Spells by type:")
    pprint(parser.spells_by_type)
    parser.gather_spell_related_hit_bullets_atk_sp_effects()
