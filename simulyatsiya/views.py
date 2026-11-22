import secrets

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.clickjacking import xframe_options_sameorigin

from user.permissions import require_profile

from .registry import enabled_simulations, get_simulation

LOGIN_URL = 'user:login'

# The simulation document runs in <iframe sandbox="allow-scripts"> (no same-origin access).
# Its own policy allows only its inline code (by nonce) and no network requests at all.
FRAME_CSP = (
    "default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; img-src data:; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
)


def _not_found(request, simulation_id):
    return render(request, 'simulyatsiya/not_found.html', {'simulation_id': simulation_id}, status=404)


@login_required(login_url=LOGIN_URL)
@require_profile
def index_view(request):
    return render(request, 'simulyatsiya/index.html', {'simulations': enabled_simulations()})


@login_required(login_url=LOGIN_URL)
@require_profile
def detail_view(request, simulation_id):
    simulation = get_simulation(simulation_id)
    if simulation is None:
        return _not_found(request, simulation_id)
    return render(request, 'simulyatsiya/detail.html', {'simulation': simulation})


@login_required(login_url=LOGIN_URL)
@require_profile
@xframe_options_sameorigin
def frame_view(request, simulation_id):
    """The simulation itself, loaded only inside the sandboxed iframe of detail_view."""
    simulation = get_simulation(simulation_id)
    if simulation is None:
        return _not_found(request, simulation_id)
    nonce = secrets.token_urlsafe(16)
    response = render(request, simulation.template, {'simulation': simulation, 'nonce': nonce})
    response['Content-Security-Policy'] = FRAME_CSP.format(nonce=nonce)
    response['Referrer-Policy'] = 'no-referrer'
    response['Cache-Control'] = 'private, no-store'
    return response
