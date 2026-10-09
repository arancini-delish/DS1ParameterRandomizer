from enum import Enum

# Some magic is worth keeping unchanged
# Homeward
MAGIC_TO_IGNORE = {5210}

class SpellTypes(Enum):
    # Spells with projectiles that move straight towards the target
    LINEAR = 1
    # Spells with projectiles that lob out from the caster
    LOBBED = 2
    # Spells with projectiles that orbit the target and potentially fire towards the target
    ORBIT = 3
    # Spells with projectiles that trace out from the caster, through repeated child projectiles
    GROUND_TRACE = 4
    # Spells with projectiles that immediately damage the target, a short distance away
    POINT_BLANK = 5
    # Spells that spawn multiple projectiles in a row to mimic a spray
    SPRAY = 6
    # Spells with projectiles that spawn on the ground around the caster
    AOE_GROUND = 7
    # Spells with projectiles that apply a buff to the casters weapon or shield
    WEAPON_BUFF = 8
    # Spells with projectiles that apply a single buff to the caster
    SELF_BUFF = 9
    # Spells with projectiles that apply a buff to the caster through a projectile, typically to apply multiple buffs
    SELF_BUFF_THROUGH_PROJECTILE = 10
    # Any strange spell effects, such as homeward
    TRIGGER_EFFECT = 11
    # Spells with projectiles that inflict damage over time, often in the form of a cloud
    LINGERING = 12

# We need to keep these in mind when we randomize so we don't miscategorize spells
SPRAY_ANIMATION_IDS = [23, 24]
GROUND_TRACE_MIN_SPAWN_COUNT = 3
GROUND_SPAWN_EMITTER_TYPE = 2
AOE_GROUND_SPAWN_EMITTER_TYPE = 1
LINGERING_MIN_LIFE = 2
LINGERING_MIN_DMG_HIT_RECORD_LIFE_TIME = 0.1
POINT_BLANK_MIN_LIFE = 0.1
POINT_BLANK_DISTANCE = 0
LOBBED_GRAVITY = 9.8