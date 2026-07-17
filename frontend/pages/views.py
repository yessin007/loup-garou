from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .translations import LANGUAGES, ROLES, UI


ROLE_KEYS = tuple(ROLES["fr"])
WOLF_ROLE_KEYS = (
    "simple_wolves",
    "infecting_fathers",
    "cerberus_wolves",
    "black_wolves",
    "talkative_wolves",
)


def current_language(request):
    code = request.session.get("language", "fr")
    return code if code in LANGUAGES else "fr"


def set_language(request):
    if request.method == "POST":
        code = request.POST.get("language", "fr")
        if code in LANGUAGES:
            request.session["language"] = code
    target = request.POST.get("next", reverse("home"))
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        target = reverse("home")
    return redirect(target)


def home(request):
    if request.session.get("authenticated"):
        return redirect("welcome")

    error = None
    if request.method == "POST":
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")

        if username == "123" and password == "123":
            request.session["authenticated"] = True
            return redirect("welcome")

        error = UI[current_language(request)]["auth_error"]

    return render(request, "pages/home.html", {"error": error})


def welcome(request):
    if not request.session.get("authenticated"):
        return redirect("home")

    error = None
    if request.method == "POST":
        try:
            player_count = int(request.POST.get("player_count", 0))
            composition = {
                role: int(request.POST.get(role, 0)) for role in ROLE_KEYS
            }
        except (TypeError, ValueError):
            error = UI[current_language(request)]["invalid_setup"]
        else:
            if not 8 <= player_count <= 30:
                error = UI[current_language(request)]["player_range"]
            elif any(count < 0 for count in composition.values()):
                error = UI[current_language(request)]["negative_roles"]
            elif sum(composition.values()) != player_count:
                error = UI[current_language(request)]["roles_sum"]
            elif sum(composition[role] for role in WOLF_ROLE_KEYS) < 1:
                error = UI[current_language(request)]["wolf_required"]
            else:
                request.session["game_setup"] = {
                    "player_count": player_count,
                    "composition": composition,
                }
                return redirect("game")

    return render(request, "pages/welcome.html", {"error": error})


def game(request):
    if not request.session.get("authenticated"):
        return redirect("home")

    setup = request.session.get("game_setup")
    if not setup:
        return redirect("welcome")

    role_labels = {key: values[0] for key, values in ROLES[current_language(request)].items()}
    roles = [
        {"label": role_labels[key], "count": count}
        for key, count in setup["composition"].items()
        if count > 0
    ]
    return render(
        request,
        "pages/game.html",
        {
            "player_count": setup["player_count"],
            "roles": roles,
            "game_setup": {
                **setup,
                "role_labels": role_labels,
                "role_descriptions": {key: values[1] for key, values in ROLES[current_language(request)].items()},
            },
        },
    )


def logout_view(request):
    language = current_language(request)
    request.session.flush()
    request.session["language"] = language
    return redirect("home")
