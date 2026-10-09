from param_categorizer import SpEffect
from abc import ABC, abstractmethod

# TODO add default field values
class SpEffectSpecBase(ABC):
    def __init__(self, sp_effect: SpEffect, score: float):
        self.sp_effect = sp_effect
        self.score = score
        self.field_values = {}
        # Reset the references. Currently we don't use any of the spEffect references
        sp_effect.reset_references()

    @abstractmethod
    def randomize(self):
        pass

class SelfBuffSpEffectSpec(SpEffectSpecBase):
    def randomize(self):
        pass

class WeaponBuffSpEffectSpec(SpEffectSpecBase):
    def randomize(self):
        pass

class ProjectileSpEffectSpec(SpEffectSpecBase):
    def randomize(self):
        # TODO
        pass