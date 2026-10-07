"""Historical timing fixtures only; production Params cannot disable privilege gates."""
from dagp_ref.params import Params as ProductionParams

class HistoricalParams(ProductionParams):
    def __post_init__(self):
        fields=dict(citizen_activation_days=3,official_min_citizen_days=30,
                    official_activation_days=2,appointment_global_limit=20)
        original={k:getattr(self,k) for k in fields}
        for k,v in fields.items():object.__setattr__(self,k,v)
        try:super().__post_init__()
        finally:
            for k,v in original.items():object.__setattr__(self,k,v)

def Params(**kwargs):
    defaults=dict(citizen_activation_days=0,official_min_citizen_days=0,
                  official_activation_days=0,appointment_global_limit=1000)
    defaults.update(kwargs)
    return HistoricalParams(**defaults)
