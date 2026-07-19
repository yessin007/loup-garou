import json
import secrets
from io import BytesIO

import qrcode
from qrcode.image.svg import SvgPathImage
from django.db import transaction
from django.db.models import Count
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST, require_safe

from .models import GameRoom, RoomEvent, RoomPlayer
from .role_guides import ROLE_CAMPS, ROLE_CODES, ROLE_GUIDES
from .translations import LANGUAGES, ROLES, UI


ROLE_KEYS = tuple(ROLES["fr"])
WOLF_ROLE_KEYS = (
    "simple_wolves",
    "infecting_fathers",
    "cerberus_wolves",
    "black_wolves",
    "talkative_wolves",
    "blue_wolves",
    "white_wolves",
)

ROOM_TEXT = {
    "fr": {
        "room_title": "Rejoindre une partie", "room_intro": "Entre le code affiché sur le téléphone du narrateur.", "room_code": "Code de la room", "player_name": "Ton prénom", "join": "Rejoindre", "history": "Historique", "all_histories": "Tous les historiques", "history_intro": "Consulte les parties précédentes sans saisir de code.", "open_history": "Voir l'historique", "scan_qr": "Scanner pour rejoindre", "qr_help": "Scanne le QR ou saisis le code sur ton téléphone.", "waiting": "En attente du narrateur", "waiting_help": "Ton rôle apparaîtra ici quand le narrateur lancera la distribution.", "your_role": "Ton rôle secret", "keep_secret": "Garde cet écran secret.", "joined": "Tu as rejoint la room", "players_joined": "joueur(s) connecté(s)", "events": "événement(s)", "yes": "Oui", "no": "Non", "invalid_room": "Room introuvable.", "invalid_code": "Le code doit contenir exactement 6 chiffres.", "room_started": "Cette partie a déjà commencé.", "name_used": "Ce prénom est déjà utilisé dans cette room.", "room_full": "La room est complète.", "history_empty": "Aucun jour ou aucune nuit terminé pour le moment.", "night": "Nuit", "day": "Jour", "back": "Retour", "refreshing": "Mise à jour automatique", "room_access": "Rejoindre une room / historique",
    },
    "en": {
        "room_title": "Join a game", "room_intro": "Enter the code displayed on the narrator's phone.", "room_code": "Room code", "player_name": "Your name", "join": "Join", "history": "History", "all_histories": "All histories", "history_intro": "View previous games without entering a code.", "open_history": "View history", "scan_qr": "Scan to join", "qr_help": "Scan the QR or enter the code on your phone.", "waiting": "Waiting for the narrator", "waiting_help": "Your role will appear here when the narrator starts distribution.", "your_role": "Your secret role", "keep_secret": "Keep this screen private.", "joined": "You joined the room", "players_joined": "connected player(s)", "events": "event(s)", "yes": "Yes", "no": "No", "invalid_room": "Room not found.", "invalid_code": "The code must contain exactly 6 digits.", "room_started": "This game has already started.", "name_used": "This name is already used in this room.", "room_full": "The room is full.", "history_empty": "No completed day or night yet.", "night": "Night", "day": "Day", "back": "Back", "refreshing": "Updates automatically", "room_access": "Join a room / history",
    },
    "tn": {
        "room_title": "Od5ol lel game", "room_intro": "Da5el el code eli thaher fi telephone mta3 el narrateur.", "room_code": "Code mta3 el room", "player_name": "Esmek", "join": "Od5ol", "history": "Historique", "all_histories": "Les historiques lkol", "history_intro": "Chouf les games eli fetou blech ma tda5el code.", "open_history": "Chouf el historique", "scan_qr": "Scanni bch tod5ol", "qr_help": "Scanni el QR wala da5el el code fi telephone mte3ek.", "waiting": "Nestannew fel narrateur", "waiting_help": "Role mte3ek yodhher houni ki narrateur yabda el distribution.", "your_role": "Role mte3ek bel sir", "keep_secret": "Ma twarrich el ecran l 7ad.", "joined": "D5alt lel room", "players_joined": "joueur(s) connectes", "events": "event(s)", "yes": "Ey", "no": "Le", "invalid_room": "El room mawjoudach.", "invalid_code": "El code lezem ykoun 6 ar9am bark.", "room_started": "El game hedhi bdet deja.", "name_used": "El esm hedha mesta3mel fel room.", "room_full": "El room kemlet.", "history_empty": "Mezel ma fama 7atta lil wala nhar kemel.", "night": "Lil", "day": "Nhar", "back": "Erja3", "refreshing": "Updates automatiquement", "room_access": "Od5ol room / historique",
    },
}

ROOM_DETAIL_LABELS = {
    "fr": {"deaths": "Victimes", "protected": "Protection", "wolves_target": "Cible des loups", "blocked": "Pouvoir bloqué", "redirected_to": "Redirection", "infection_attempted": "Infection tentée", "infection_succeeded": "Infection réussie", "witch_saved": "Potion de vie", "witch_target": "Potion de mort", "bear_growled": "Ours", "judge_first": "Premier choix du Juge", "judge_second": "Deuxième choix du Juge", "judge_same_clan": "Même clan", "seer_target": "Vision de la Voyante", "seer_role": "Rôle aperçu", "eliminated": "Éliminé par vote", "vote_outcome": "Résultat", "winner": "Vainqueur"},
    "en": {"deaths": "Victims", "protected": "Protection", "wolves_target": "Wolves' target", "blocked": "Blocked power", "redirected_to": "Redirected to", "infection_attempted": "Infection attempted", "infection_succeeded": "Infection succeeded", "witch_saved": "Life potion", "witch_target": "Death potion", "bear_growled": "Bear", "judge_first": "Judge's first choice", "judge_second": "Judge's second choice", "judge_same_clan": "Same faction", "seer_target": "Seer's vision", "seer_role": "Role seen", "eliminated": "Voted out", "vote_outcome": "Result", "winner": "Winner"},
    "tn": {"deaths": "Eli metou", "protected": "Protection", "wolves_target": "Cible mta3 el loups", "blocked": "Pouvoir bloque", "redirected_to": "Redirection", "infection_attempted": "Jarbet infection", "infection_succeeded": "Infection nej7et", "witch_saved": "Potion de vie", "witch_target": "Potion de mort", "bear_growled": "Ours", "judge_first": "Choix louel mta3 Juge", "judge_second": "Choix theni mta3 Juge", "judge_same_clan": "Nafs el clan", "seer_target": "Vision mta3 el Voyante", "seer_role": "Role eli chefetou", "eliminated": "5raj bel vote", "vote_outcome": "Resultat", "winner": "Eli rba7"},
}


def health(request):
    return JsonResponse(
        {
            "service": "loup-garou-frontend",
            "status": "ok",
        }
    )


@require_GET
def pwa_manifest(request):
    return JsonResponse(
        {
            "name": "Loup Garou — Narrateur",
            "short_name": "Loup Garou",
            "description": "Parties de Loup Garou avec narrateur, rooms et rôles secrets.",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "background_color": "#070d12",
            "theme_color": "#080d12",
            "icons": [
                {
                    "src": f"{settings.STATIC_URL}images/favicon-wolf.png",
                    "sizes": "1254x1254",
                    "type": "image/png",
                    "purpose": "any maskable",
                }
            ],
        },
        content_type="application/manifest+json",
    )


@require_GET
def service_worker(request):
    response = render(
        request,
        "pages/service_worker.js",
        content_type="application/javascript",
    )
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Service-Worker-Allowed"] = "/"
    return response


def current_language(request):
    code = request.session.get("language", "fr")
    return code if code in LANGUAGES else "fr"


def room_text(request):
    return ROOM_TEXT[current_language(request)]


def room_for_narrator(request, code):
    if not request.session.get("authenticated"):
        return None
    setup = request.session.get("game_setup", {})
    if setup.get("room_code") != code:
        return None
    return GameRoom.objects.filter(code=code).first()


def player_label(state, player_id):
    try:
        wanted = int(player_id)
    except (TypeError, ValueError):
        return None
    item = next((entry for entry in state.get("players", []) if entry.get("id") == wanted), None)
    return item.get("name") if item else None


def public_event_details(state, event_type):
    if event_type == "night":
        death_names = []
        for entry in state.get("deaths", []):
            name = entry.get("name") if isinstance(entry, dict) else player_label(state, entry)
            if name:
                death_names.append(name)
        return {
            "deaths": death_names,
            "protected": player_label(state, state.get("protectedId")),
            "wolves_target": player_label(state, state.get("wolfTargetId")),
            "blocked": player_label(state, state.get("blockedPlayerId")),
            "redirected_to": player_label(state, state.get("prostituteTargetId")),
            "infection_attempted": bool(state.get("infectionAttempted")),
            "infection_succeeded": bool(state.get("infectionSucceeded")),
            "witch_saved": bool(state.get("witchSave")),
            "witch_target": player_label(state, state.get("witchKillId")),
            "bear_growled": state.get("bearGrowled"),
            "judge_first": player_label(state, state.get("judgeFirstId")),
            "judge_second": player_label(state, state.get("judgeSecondId")),
            "judge_same_clan": state.get("judgeSameClan"),
            "seer_target": player_label(state, state.get("seerTargetId")),
            "seer_role": state.get("seerDisplayedRole"),
        }
    return {
        "eliminated": player_label(state, state.get("lastVote")),
        "vote_outcome": state.get("voteOutcome"),
        "winner": state.get("winner"),
    }


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


def roles_guide(request):
    language = current_language(request)
    guides = [
        {
            "key": role,
            "name": ROLES[language][role][0],
            "summary": ROLES[language][role][1],
            "code": ROLE_CODES[role],
            "camp": ROLE_CAMPS[role],
            "rules": ROLE_GUIDES[language][role],
        }
        for role in ROLE_KEYS
    ]
    return render(request, "pages/roles_guide.html", {"role_guides": guides})


def room_portal(request):
    text = room_text(request)
    error = None
    initial_code = request.GET.get("code", "").strip()
    if not (initial_code.isdigit() and len(initial_code) == 6):
        initial_code = ""
    if request.method == "POST":
        code = request.POST.get("room_code", "").strip()
        room = GameRoom.objects.filter(code=code).first() if code.isdigit() and len(code) == 6 else None
        if not code.isdigit() or len(code) != 6:
            error = text["invalid_code"]
        elif not room:
            error = text["invalid_room"]
        elif room.status != GameRoom.Status.WAITING:
            error = text["room_started"]
        elif room.room_players.count() >= room.player_count:
            error = text["room_full"]
        else:
            name = request.POST.get("player_name", "").strip()[:40]
            if not name:
                error = text["player_name"]
            elif room.room_players.filter(name__iexact=name).exists():
                error = text["name_used"]
            else:
                joined = RoomPlayer.objects.create(room=room, name=name)
                tokens = request.session.get("room_player_tokens", {})
                tokens[room.code] = str(joined.token)
                request.session["room_player_tokens"] = tokens
                return redirect("room_player", code=room.code)
    return render(request, "pages/room_portal.html", {"room": text, "error": error, "initial_code": initial_code})


def room_player(request, code):
    room = get_object_or_404(GameRoom, code=code.upper())
    token = request.session.get("room_player_tokens", {}).get(room.code)
    joined = room.room_players.filter(token=token).first()
    if not joined:
        return redirect("room_portal")
    return render(request, "pages/room_player.html", {"game_room": room, "joined_player": joined, "room": room_text(request)})


def room_history(request, code):
    room = get_object_or_404(GameRoom, code=code)
    return render(request, "pages/room_history.html", {"game_room": room, "room": room_text(request), "history_labels": ROOM_DETAIL_LABELS[current_language(request)]})


@require_safe
def room_qr(request, code):
    room = get_object_or_404(GameRoom, code=code)
    join_path = f"{reverse('room_portal')}?code={room.code}"
    join_url = request.build_absolute_uri(join_path)
    image = qrcode.make(join_url, image_factory=SvgPathImage, box_size=10, border=3)
    output = BytesIO()
    image.save(output)
    response = HttpResponse(output.getvalue(), content_type="image/svg+xml")
    response["Cache-Control"] = "public, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def room_history_list(request):
    rooms = (
        GameRoom.objects.annotate(event_count=Count("events"))
        .filter(event_count__gt=0)
        .order_by("-updated_at")
    )
    return render(request, "pages/room_history_list.html", {"history_rooms": rooms, "room": room_text(request)})


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
                room = GameRoom.objects.create(player_count=player_count, composition=composition)
                request.session["game_setup"] = {
                    "player_count": player_count,
                    "composition": composition,
                    "room_code": room.code,
                }
                return redirect("game")

    return render(request, "pages/welcome.html", {"error": error})


def game(request):
    if not request.session.get("authenticated"):
        return redirect("home")

    setup = request.session.get("game_setup")
    if not setup:
        return redirect("welcome")
    if not setup.get("room_code"):
        room = GameRoom.objects.create(
            player_count=setup["player_count"], composition=setup["composition"]
        )
        setup["room_code"] = room.code
        request.session["game_setup"] = setup

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
            "room_code": setup["room_code"],
            "room": room_text(request),
        },
    )


@require_GET
def room_lobby_api(request, code):
    room = room_for_narrator(request, code.upper())
    if not room:
        return JsonResponse({"error": "forbidden"}, status=403)
    return JsonResponse({"code": room.code, "status": room.status, "player_count": room.player_count, "players": [{"id": item.id, "name": item.name} for item in room.room_players.all()]})


@require_POST
@transaction.atomic
def room_start_api(request, code):
    room = room_for_narrator(request, code.upper())
    if not room:
        return JsonResponse({"error": "forbidden"}, status=403)
    room = GameRoom.objects.select_for_update().get(code=room.code)
    if room.status != GameRoom.Status.WAITING:
        return JsonResponse({"error": "already_started"}, status=409)
    joined = list(room.room_players.select_for_update().all())
    roles = [role for role, count in room.composition.items() for _ in range(count)]
    secrets.SystemRandom().shuffle(roles)
    assignments = []
    for index, joined_player in enumerate(joined):
        joined_player.role = roles[index]
        joined_player.save(update_fields=["role"])
        assignments.append({"room_player_id": joined_player.id, "name": joined_player.name, "role": joined_player.role})
    room.status = GameRoom.Status.ACTIVE
    room.save(update_fields=["status", "updated_at"])
    return JsonResponse({"assignments": assignments, "remaining_roles": roles[len(joined):]})


@require_POST
@transaction.atomic
def room_sync_api(request, code):
    room = room_for_narrator(request, code.upper())
    if not room:
        return JsonResponse({"error": "forbidden"}, status=403)
    room = GameRoom.objects.select_for_update().get(code=room.code)
    try:
        state = json.loads(request.body)
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "invalid_json"}, status=400)
    previous_state = room.game_state or {}
    undo_requested = request.headers.get("X-Game-Undo") == "1"
    room.game_state = state
    room.status = GameRoom.Status.FINISHED if state.get("stage") == "game_over" else GameRoom.Status.ACTIVE
    room.save(update_fields=["game_state", "status", "updated_at"])
    round_number = max(1, int(state.get("round", 1)))

    if undo_requested:
        previous_round = max(1, int(previous_state.get("round", round_number)))
        previous_stage = previous_state.get("stage")
        current_stage = state.get("stage")
        if round_number < previous_round:
            room.events.filter(round_number__gt=round_number).delete()
        if previous_round == round_number and previous_stage == "dawn" and current_stage != "dawn":
            room.events.filter(marker=f"night-{round_number}").delete()
        if previous_round == round_number and previous_stage == "day_end" and current_stage != "day_end":
            room.events.filter(marker=f"day-{round_number}").delete()

    event_type = "night" if state.get("stage") == "dawn" else "day" if state.get("stage") == "day_end" else None
    if event_type:
        RoomEvent.objects.update_or_create(
            room=room,
            marker=f"{event_type}-{round_number}",
            defaults={"event_type": event_type, "round_number": round_number, "details": public_event_details(state, event_type)},
        )
    return JsonResponse({"status": "ok"})


@require_GET
def room_player_api(request, code):
    room = get_object_or_404(GameRoom, code=code.upper())
    token = request.session.get("room_player_tokens", {}).get(room.code)
    joined = room.room_players.filter(token=token).first()
    if not joined:
        return JsonResponse({"error": "forbidden"}, status=403)
    language = current_language(request)
    role = joined.role
    return JsonResponse({
        "status": room.status,
        "joined_count": room.room_players.count(),
        "player_count": room.player_count,
        "role": {"code": role, "name": ROLES[language][role][0], "description": ROLES[language][role][1]} if role else None,
    })


@require_GET
def room_history_api(request, code):
    room = get_object_or_404(GameRoom, code=code.upper())
    return JsonResponse({"status": room.status, "events": [{"type": event.event_type, "round": event.round_number, "details": event.details, "created_at": event.created_at.isoformat()} for event in room.events.all()]})


def logout_view(request):
    language = current_language(request)
    request.session.flush()
    request.session["language"] = language
    return redirect("home")
