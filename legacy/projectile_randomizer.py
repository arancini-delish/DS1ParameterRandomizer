from param_categorizer import Bullet, SpEffect
from abc import ABC, abstractmethod
from sp_effect_randomizer import SelfBuffSpEffectSpec

# TODO add default field values
class BulletSpecBase(ABC):
    def __init__(self, bullet: Bullet, score: float):
        self.bullet = bullet
        self.score = score
        self.field_values = {}
        # Reset the references to the spEffect and bullet, so we can assign new ones
        bullet.reset_references()

    def update_hit_bullet(self, hit_bullet: Bullet):
        self.field_values["HitBulletID"] = str(hit_bullet.id)
        self.bullet.hit_bullet = hit_bullet

    def update_shooter_sp_effect(self, shooter_sp_effect: SpEffect):
        self.field_values["spEffectIDForShooter"] = str(shooter_sp_effect.id)
        self.bullet.shooter_sp_effect = shooter_sp_effect
        
    @abstractmethod
    def randomize(self):
        pass


class SelfBuffBulletSpec(BulletSpecBase):
    """
    This is a bullet that applies a buff to the shooter, potentially chained to another self buff bullet
    """
    def randomize(self, sp_effect):
        # Self buff bullets are not really projectile but just a vector to apply a buff to the shooter
        # The score of the bullet is fully passed to the spEffect
        sp_effec_spec = SelfBuffSpEffectSpec(sp_effect, self.score)
        sp_effec_spec.randomize()
        self.update_shooter_sp_effect(sp_effect)