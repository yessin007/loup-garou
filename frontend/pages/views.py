from django.shortcuts import redirect, render


ROLE_LABELS = {
    "simple_wolves": "Loups-Garous simples",
    "infecting_fathers": "Loups-Pères infects",
    "seers": "Voyantes",
    "witches": "Sorcières",
    "protectors": "Protecteurs / Salvateurs",
    "villagers": "Simples Villageois",
}


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

        error = "Nom d'utilisateur ou mot de passe incorrect."

    return render(request, "pages/home.html", {"error": error})


def welcome(request):
    if not request.session.get("authenticated"):
        return redirect("home")

    error = None
    if request.method == "POST":
        try:
            player_count = int(request.POST.get("player_count", 0))
            composition = {
                role: int(request.POST.get(role, 0)) for role in ROLE_LABELS
            }
        except (TypeError, ValueError):
            error = "La configuration contient une valeur invalide."
        else:
            if not 8 <= player_count <= 30:
                error = "Le nombre de joueurs doit être compris entre 8 et 30."
            elif any(count < 0 for count in composition.values()):
                error = "Le nombre de rôles ne peut pas être négatif."
            elif sum(composition.values()) != player_count:
                error = "La somme des rôles doit correspondre au nombre de joueurs."
            elif composition["simple_wolves"] + composition["infecting_fathers"] < 1:
                error = "La partie doit contenir au moins un loup."
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

    roles = [
        {"label": ROLE_LABELS[key], "count": count}
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
                "role_labels": ROLE_LABELS,
            },
        },
    )


def logout_view(request):
    request.session.flush()
    return redirect("home")
