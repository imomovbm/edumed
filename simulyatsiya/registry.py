"""The list of simulations.

To add one: write ``templates/simulyatsiya/sims/<id>.html`` (it extends
``simulyatsiya/frame_base.html``, see the existing ones) and add an entry below.
Nothing else has to change. ``enabled=False`` hides an entry without deleting it.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Simulation:
    id: str                   # used in the URL: /simulyatsiya/<id>/
    title: str
    description: str
    icon: str                 # a Font Awesome icon (the site already ships Font Awesome)
    enabled: bool = True

    @property
    def template(self):
        return f'simulyatsiya/sims/{self.id}.html'


SIMULATIONS = [
    Simulation(
        id='venadan-qon-olish',
        title="Venadan qon olish",
        description="Tirsak bukilmasidagi (kubital) venadan qon olish uchun to'g'ri nuqtani toping.",
        icon='fa-tint',
    ),
    Simulation(
        id='gluteal-inyeksiya',
        title="Gluteal inyeksiya",
        description="Dumba mushagiga inyeksiya uchun xavfsiz kvadrantni aniqlang.",
        icon='fa-syringe',
    ),
    Simulation(
        id='deltoid-inyeksiya',
        title="Deltoid inyeksiya",
        description="Yelka (deltasimon) mushagiga inyeksiya uchun to'g'ri zonani toping.",
        icon='fa-user-injured',
    ),
    Simulation(
        id='insulin-inyeksiya',
        title="Insulin (teri osti)",
        description="Qorin terisi ostiga insulin yuborish uchun to'g'ri zonani tanlang.",
        icon='fa-prescription-bottle-alt',
    ),
]


def enabled_simulations():
    return [s for s in SIMULATIONS if s.enabled]


def get_simulation(simulation_id):
    """The enabled simulation with this id, or None."""
    return next((s for s in enabled_simulations() if s.id == simulation_id), None)
