import json
import secrets
from io import BytesIO
from urllib.parse import urlencode

import qrcode
from qrcode.image.svg import SvgPathImage
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.utils import IntegrityError, OperationalError
from django.db.models import Count, Q
from django.conf import settings
from django.core.exceptions import PermissionDenied
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
SINGLETON_ROLE_KEYS = tuple(
    role for role in ROLE_KEYS if role not in {"simple_wolves", "villagers"}
)

NARRATOR_GROUP = "narrators"
DAY_STAGES = {
    "dawn", "accusation", "barber_shot", "barber_result", "alien_guess",
    "alien_result", "final_vote", "servant_choice", "hunter_shot", "day_end",
}
MARMOUR_USERNAME = "marmour"
MARMOUR_WOLF_CHANCE = 0.9


def shuffle_roles_for_players(roles, player_aliases, random_source=None):
    """Shuffle roles, giving Marmour an exact 90% chance of a wolf role."""
    random_source = random_source or secrets.SystemRandom()
    random_source.shuffle(roles)

    marmour_index = next(
        (
            index
            for index, aliases in enumerate(player_aliases)
            if any(str(alias).strip().casefold() == MARMOUR_USERNAME for alias in aliases if alias)
        ),
        None,
    )
    if marmour_index is None:
        return

    should_be_wolf = random_source.random() < MARMOUR_WOLF_CHANCE
    eligible_indexes = [
        index
        for index, role in enumerate(roles)
        if (role in WOLF_ROLE_KEYS) == should_be_wolf
    ]
    selected_index = random_source.choice(eligible_indexes)
    roles[marmour_index], roles[selected_index] = roles[selected_index], roles[marmour_index]


def is_narrator(user):
    return bool(
        user.is_authenticated
        and (user.is_superuser or user.groups.filter(name=NARRATOR_GROUP).exists())
    )


def narrator_can_manage(user, room):
    return is_narrator(user) and (user.is_superuser or room.narrator_id in {None, user.id})


def room_distribution_started(room, state=None):
    state = (room.game_state or {}) if state is None else state
    if room.status == GameRoom.Status.FINISHED:
        return True
    return bool(
        state.get("distributionStarted")
        or state.get("roomStarted")
        or room.room_players.exclude(role="").exists()
    )

ROOM_TEXT = {
    "fr": {
        "delete_history": "Supprimer", "delete_history_confirm": "Supprimer définitivement cette partie et tout son historique ?", "finish_game": "Terminer la partie", "finish_game_confirm": "Confirmer que cette partie est terminée ? Elle pourra ensuite être supprimée.",
        "room_title": "Rejoindre une partie", "room_intro": "Entre le code affiché sur le téléphone du narrateur. Ton nom de joueur sera ton nom d’utilisateur.", "room_code": "Code de la room", "player_name": "Ton prénom", "join": "Rejoindre", "general_qr": "QR du site", "general_qr_help": "Ce QR unique ouvre le site pour se connecter ou créer un compte. Ensuite, le joueur saisit le code de la room.", "history": "Historique", "all_histories": "Tous les historiques", "history_intro": "Consulte les parties précédentes sans saisir de code.", "open_history": "Voir l'historique", "scan_qr": "Scanner pour ouvrir le site", "qr_help": "Scanne le QR général, connecte-toi puis saisis ce code de room.", "waiting": "En attente du narrateur", "waiting_help": "Ton rôle apparaîtra ici quand le narrateur lancera la distribution.", "your_role": "Ton rôle secret", "keep_secret": "Garde cet écran secret.", "roles_alive": "Rôles encore en vie", "roles_alive_count": "joueur(s) en vie", "roles_alive_empty": "Aucun rôle encore en vie.", "joined": "Tu as rejoint la room", "players_joined": "joueur(s) connecté(s)", "events": "événement(s)", "yes": "Oui", "no": "Non", "invalid_room": "Room introuvable.", "invalid_code": "Le code doit contenir exactement 6 chiffres.", "room_started": "Cette partie a déjà commencé.", "name_used": "Ce nom d’utilisateur est déjà utilisé dans cette room.", "room_full": "La room est complète.", "history_empty": "Aucun jour ou aucune nuit terminé pour le moment.", "night": "Nuit", "day": "Jour", "back": "Retour", "back_home": "Retour à la page d’accueil", "continue_game": "Continuer la partie", "refreshing": "Mise à jour automatique", "room_access": "Rejoindre une room / historique",
    },
    "en": {
        "delete_history": "Delete", "delete_history_confirm": "Permanently delete this game and its entire history?", "finish_game": "Finish the game", "finish_game_confirm": "Confirm that this game is finished? It can then be deleted.",
        "room_title": "Join a game", "room_intro": "Enter the code displayed by the narrator. Your player name will be your username.", "room_code": "Room code", "player_name": "Your name", "join": "Join", "general_qr": "Website QR code", "general_qr_help": "This single QR code opens the website to sign in or create an account. Then enter the room code.", "history": "History", "all_histories": "All histories", "history_intro": "View previous games without entering a code.", "open_history": "View history", "scan_qr": "Scan to open the website", "qr_help": "Scan the general QR code, sign in, then enter this room code.", "waiting": "Waiting for the narrator", "waiting_help": "Your role will appear here when the narrator starts distribution.", "your_role": "Your secret role", "keep_secret": "Keep this screen private.", "roles_alive": "Roles still alive", "roles_alive_count": "player(s) alive", "roles_alive_empty": "No roles are still alive.", "joined": "You joined the room", "players_joined": "connected player(s)", "events": "event(s)", "yes": "Yes", "no": "No", "invalid_room": "Room not found.", "invalid_code": "The code must contain exactly 6 digits.", "room_started": "This game has already started.", "name_used": "This username is already used in this room.", "room_full": "The room is full.", "history_empty": "No completed day or night yet.", "night": "Night", "day": "Day", "back": "Back", "back_home": "Back to home page", "continue_game": "Continue game", "refreshing": "Updates automatically", "room_access": "Join a room / history",
    },
    "tn": {
        "delete_history": "Fasa5", "delete_history_confirm": "Met2aked t7eb tfasa5 el game hedhi w historique mte3ha lkol définitivement ?", "finish_game": "Finish the game", "finish_game_confirm": "Met2aked elli el game hedhi kemlet? Ba3d tnajem tfasa5ha.",
        "room_title": "Od5ol lel game", "room_intro": "Da5el code el room. Esmek fel game houwa username mte3ek.", "room_code": "Code mta3 el room", "player_name": "Esmek", "join": "Od5ol", "general_qr": "QR mta3 el site", "general_qr_help": "Fama QR wa7ed bark y7el el site bech tconnecti wala tasna3 compte. Ba3d da5el code el room.", "history": "Bilan w historique", "all_histories": "Archive mta3 les games", "history_intro": "", "open_history": "7ell el bilan direct", "scan_qr": "Scanni bch t7el el site", "qr_help": "Scanni el QR general, connecti w da5el code el room hedha.", "waiting": "Nestannew fel narrateur", "waiting_help": "Role mte3ek yodhher houni ki narrateur yabda el distribution.", "your_role": "Role mte3ek bel sir", "keep_secret": "Ma twarrich el ecran l 7ad.", "roles_alive": "Les roles eli mazelou 3aychin", "roles_alive_count": "joueur(s) mazelou 3aychin", "roles_alive_empty": "Ma fama 7atta role mezel 3ayech.", "joined": "D5alt lel room", "players_joined": "joueur(s) connectes", "events": "bilan(s)", "yes": "Ey", "no": "Le", "invalid_room": "El room mawjoudach.", "invalid_code": "El code lezem ykoun 6 ar9am bark.", "room_started": "El game hedhi bdet deja.", "name_used": "El username hedha mesta3mel fel room.", "room_full": "El room kemlet.", "history_empty": "Mezel ma fama 7atta bilan: kammel awel lil wala awel nhar.", "night": "Lil", "day": "Nhar", "back": "Erja3", "back_home": "Arja3 page d’accueil", "continue_game": "Kammel el game", "refreshing": "El bilan yetjadded wa7dou", "room_access": "Od5ol room / chouf el bilan",
    },
}
ROOM_TEXT["fr"].update({
    "roles_alive": "Rôles des joueurs", "roles_alive_count": "vivant(s)",
    "roles_dead_count": "mort(s)", "role_alive_status": "Vivant",
    "role_dead_status": "Mort", "roles_alive_empty": "Aucun rôle distribué.",
    "lobby_players": "Joueurs inscrits", "account_player": "Compte",
    "manual_player": "Manuel", "remove_player": "Retirer ce joueur",
    "empty_lobby": "Aucun joueur inscrit pour le moment.",
    "joining_room": "Inscription en cours…", "join_queue_wait": "Beaucoup de joueurs rejoignent la room en même temps.",
    "join_retrying": "Nouvelle tentative automatique dans", "join_retry_now": "Réessayer maintenant",
})
ROOM_TEXT["en"].update({
    "roles_alive": "Player roles", "roles_alive_count": "alive",
    "roles_dead_count": "dead", "role_alive_status": "Alive",
    "role_dead_status": "Dead", "roles_alive_empty": "No roles distributed.",
    "lobby_players": "Registered players", "account_player": "Account",
    "manual_player": "Manual", "remove_player": "Remove this player",
    "empty_lobby": "No registered players yet.",
    "joining_room": "Joining the room…", "join_queue_wait": "Many players are joining the room at the same time.",
    "join_retrying": "Retrying automatically in", "join_retry_now": "Retry now",
})
ROOM_TEXT["tn"].update({
    "roles_alive": "Roles mta3 les joueurs", "roles_alive_count": "3aychin",
    "roles_dead_count": "maytin", "role_alive_status": "3ayech",
    "role_dead_status": "meyet", "roles_alive_empty": "Ma fama 7atta role distribué.",
    "lobby_players": "Les joueurs eli da5lou", "account_player": "Compte",
    "manual_player": "Manuel", "remove_player": "Na7i el joueur",
    "empty_lobby": "Mezel ma d5al 7atta joueur.",
    "joining_room": "Da5la lel room…", "join_queue_wait": "Fama barcha joueurs ye7ebbou yod5lou fard wa9t.",
    "join_retrying": "Bech n3awdou automatiquement ba3d", "join_retry_now": "3awed taw",
})

ROOM_DETAIL_LABELS = {
    "fr": {"deaths": "Victimes", "protected": "Protection", "wolves_target": "Cible des loups", "blocked": "Pouvoir bloqué", "redirected_to": "Visite de la Pute", "pyromaniac_action": "Action du Pyromane", "pyromaniac_doused": "Aspergés cette nuit", "pyromaniac_ignited": "Incendiés cette nuit", "pyromaniac_oiled": "Encore aspergés", "infection_attempted": "Infection tentée", "infection_succeeded": "Infection réussie", "witch_saved": "Potion de vie", "witch_target": "Potion de mort", "bear_growled": "Ours", "sheep_returned": "Moutons revenus", "sheep_lost": "Moutons perdus", "sheep_remaining": "Moutons restants", "shepherd_blocked": "Berger bloqué", "judge_first": "Premier choix du Juge", "judge_second": "Deuxième choix du Juge", "judge_same_clan": "Même clan", "seer_target": "Vision de la Voyante", "seer_role": "Rôle aperçu", "eliminated": "Éliminé par vote", "vote_deaths": "Morts après le vote", "vote_outcome": "Résultat", "normal_votes": "Votes normaux", "cancelled_votes": "Votes annulés", "secret_votes": "Voix secrètes", "final_totals": "Total final", "hunter_targets": "Derniers tirs du Chasseur", "powers_lost": "Pouvoirs retirés", "barber_target": "Cible du Barbier", "barber_hit": "Tir du Barbier réussi", "alien_correct": "Réponse de l'Alien correcte", "winner": "Vainqueur"},
    "en": {"deaths": "Victims", "protected": "Protection", "wolves_target": "Wolves' target", "blocked": "Blocked power", "redirected_to": "Escort visit", "pyromaniac_action": "Arsonist action", "pyromaniac_doused": "Doused tonight", "pyromaniac_ignited": "Ignited tonight", "pyromaniac_oiled": "Still doused", "infection_attempted": "Infection attempted", "infection_succeeded": "Infection succeeded", "witch_saved": "Life potion", "witch_target": "Death potion", "bear_growled": "Bear", "sheep_returned": "Returned sheep", "sheep_lost": "Lost sheep", "sheep_remaining": "Sheep remaining", "shepherd_blocked": "Shepherd blocked", "judge_first": "Judge's first choice", "judge_second": "Judge's second choice", "judge_same_clan": "Same faction", "seer_target": "Seer's vision", "seer_role": "Role seen", "eliminated": "Voted out", "vote_deaths": "Deaths after the vote", "vote_outcome": "Result", "normal_votes": "Normal votes", "cancelled_votes": "Cancelled votes", "secret_votes": "Secret votes", "final_totals": "Final total", "hunter_targets": "Hunter's final shots", "powers_lost": "Powers removed", "barber_target": "Barber's target", "barber_hit": "Barber shot succeeded", "alien_correct": "Alien answer correct", "winner": "Winner"},
    "tn": {"deaths": "Chkoun met ellila", "protected": "Chkoun t7ama", "wolves_target": "Cible mta3 el loups", "blocked": "Joueur eli tblocka", "redirected_to": "Win r9adet el Pute", "pyromaniac_action": "Action mta3 Pyromane", "pyromaniac_doused": "Eli rachehom zit ellila", "pyromaniac_ignited": "Eli cha3alhom ellila", "pyromaniac_oiled": "Eli mazel 3lihom zit", "infection_attempted": "Saret tentative infection", "infection_succeeded": "El infection nej7et", "witch_saved": "Sorcière najjet el cible", "witch_target": "Cible mta3 potion de mort", "bear_growled": "El Ours garger", "sheep_returned": "3lelech eli raj3ou", "sheep_lost": "3lelech eli dha3ou", "sheep_remaining": "3lelech eli ba9aw", "shepherd_blocked": "Cerbère 9leb résultat el Berger", "judge_first": "Joueur louel mta3 Juge", "judge_second": "Joueur theni mta3 Juge", "judge_same_clan": "Nafs el clan", "seer_target": "Chkoun chefet el Voyante", "seer_role": "Role eli thaherelha", "eliminated": "Chkoun 5raj bel vote", "vote_deaths": "Eli metou ba3d el vote", "vote_outcome": "Kifeh wfa el vote", "normal_votes": "El votes normaux", "cancelled_votes": "El votes eli tna77aw", "secret_votes": "El voix bel sir", "final_totals": "Total final", "hunter_targets": "Chkoun dharab el Chasseur", "powers_lost": "Chkoun tna7alou el pouvoir", "barber_target": "Chkoun e5tar el Barbier", "barber_hit": "Tir el Barbier tla3 s7i7", "alien_correct": "Réponse mta3 Alien s7i7a", "winner": "Chkoun rba7"},
}
ROOM_DETAIL_LABELS["fr"].update({"alien_deaths": "Victimes de l’Alien", "barber_deaths": "Victimes du Barbier", "hunter_deaths": "Emportés par le Chasseur", "wolves_final_target": "Cible finale après redirection"})
ROOM_DETAIL_LABELS["en"].update({"alien_deaths": "Alien victims", "barber_deaths": "Barber victims", "hunter_deaths": "Taken by the Hunter", "wolves_final_target": "Final target after redirection"})
ROOM_DETAIL_LABELS["tn"].update({"alien_deaths": "Eli metou fi joret Alien", "barber_deaths": "Eli metou b tir Barbier", "hunter_deaths": "Eli hezhom Chasseur m3ah", "wolves_final_target": "Cible finale ba3d redirection"})

ROOM_HISTORY_TEXT = {
    "fr": {
        "history_kicker": "Journal de la partie", "history_live": "Partie en cours", "history_finished": "Partie terminée",
        "history_updated": "Actualisé à l'instant", "history_night_title": "Bilan de la nuit {round}", "history_day_title": "Bilan du jour {round}",
        "history_night_quiet": "Le village se réveille au complet", "history_night_deaths": "{count} victime(s) pendant la nuit",
        "history_day_eliminated": "{name} a été éliminé", "history_day_tie": "Égalité : personne n'est éliminé", "history_day_skipped": "Le vote a été passé", "history_day_forced": "Journée terminée manuellement", "history_day_deaths": "{count} mort(s) pendant la journée",
        "history_details": "Voir le déroulement", "history_no_details": "Aucun autre événement à signaler", "history_nights": "nuits", "history_days": "jours",
        "story_couple": "{actor} a lié {names}.", "story_wild": "{actor} a choisi {name} comme modèle.", "story_protected": "{actor} protège {name}.", "story_prostitute": "{actor} a dormi chez {name}.", "story_blocked": "{actor} a bloqué {name}.",
        "story_pyro": "{actor} a choisi : {action}.", "story_wolves": "{actor} ont ciblé {name}.", "story_redirect": "L’attaque a été redirigée vers {name}.", "story_infection_yes": "{actor} a infecté {name}.", "story_infection_no": "La tentative d’infection de {actor} sur {name} a échoué.",
        "story_white_wolf": "{actor} a ciblé {name}.", "story_silenced": "{actor} a réduit {name} au silence.", "story_talkative": "{actor} a donné le mot « {word} » à {name}.", "story_witch_saved": "{actor} a utilisé sa potion de vie.", "story_witch_killed": "{actor} a empoisonné {name}.",
        "story_seer": "{actor} a vu {name} : {role}.", "story_bear_yes": "{actor} a grogné.", "story_bear_no": "{actor} n’a pas grogné.", "story_sheep_returned": "Pour {actor}, les moutons sont revenus de chez : {names}.", "story_sheep_lost": "Pour {actor}, les moutons ont été perdus chez : {names}.", "story_sheep_left": "{actor} a encore {count} mouton(s).", "story_judge_same": "{actor} a comparé {first} et {second} : même clan.", "story_judge_diff": "{actor} a comparé {first} et {second} : clans différents.", "story_deaths": "Morts de la nuit : {names}.", "story_hunter": "{actor} a emporté : {names}.",
        "story_speaker": "La parole commence avec {name}.", "story_barber_hit": "{actor} a tiré sur {name} : c’était un Loup.", "story_barber_miss": "{actor} a tiré sur {name} : tir manqué.", "story_alien_yes": "La tentative de {actor} était correcte.", "story_alien_no": "La tentative de {actor} a échoué.", "story_alien_guess_yes": "{actor} a proposé {role} pour {name} : correct.", "story_alien_guess_no": "{actor} a proposé {role} pour {name} : incorrect.", "story_alien_deaths": "Victimes de l’Alien : {names}.", "story_barber_deaths": "Victimes du Barbier : {names}.", "story_accused": "Joueurs accusés : {names}.", "story_normal_votes": "Votes annoncés : {values}.", "story_cancelled_votes": "Votes annulés : {names}.", "story_secret_votes": "Votes secrets : {values}.", "story_vote_eliminated": "Le vote a éliminé {name}.", "story_vote_tie": "Le vote s’est terminé par une égalité.", "story_vote_skipped": "Le vote a été passé.", "story_day_forced": "Le narrateur a terminé manuellement la journée.", "story_vote_deaths": "Morts après le vote : {names}.", "story_powers_lost": "Pouvoirs retirés à : {names}.", "story_winner": "Vainqueur : {name}.",
        "outcome_eliminated": "Élimination", "outcome_tie": "Égalité", "outcome_skipped": "Vote passé", "outcome_forced_transition": "Fin manuelle", "pyro_action_douse": "Asperger", "pyro_action_ignite": "Incendier", "pyro_action_blocked": "Bloqué par le Cerbère", "winner_wolves": "Loups-Garous", "winner_village": "Village", "winner_white_wolf": "Loup Blanc", "winner_angel": "Ange", "winner_alien": "Alien", "winner_pyromaniac": "Pyromane", "winner_couple": "Couple", "winner_draw": "Égalité — aucun vainqueur", "not_recorded": "Non renseigné", "archive": "Archives des parties", "room_label": "Partie",
    },
    "en": {
        "history_kicker": "Game journal", "history_live": "Game in progress", "history_finished": "Game finished",
        "history_updated": "Updated just now", "history_night_title": "Night {round} summary", "history_day_title": "Day {round} summary",
        "history_night_quiet": "The whole village wakes up", "history_night_deaths": "{count} night victim(s)",
        "history_day_eliminated": "{name} was eliminated", "history_day_tie": "Tie: nobody was eliminated", "history_day_skipped": "The vote was skipped", "history_day_forced": "Day ended manually", "history_day_deaths": "{count} death(s) during the day",
        "history_details": "View the sequence", "history_no_details": "No other event to report", "history_nights": "nights", "history_days": "days",
        "story_couple": "{actor} linked {names}.", "story_wild": "{actor} chose {name} as a role model.", "story_protected": "{actor} protects {name}.", "story_prostitute": "{actor} stayed with {name}.", "story_blocked": "{actor} blocked {name}.",
        "story_pyro": "{actor} chose: {action}.", "story_wolves": "{actor} targeted {name}.", "story_redirect": "The attack was redirected to {name}.", "story_infection_yes": "{actor} infected {name}.", "story_infection_no": "{actor}'s infection attempt on {name} failed.",
        "story_white_wolf": "{actor} targeted {name}.", "story_silenced": "{actor} silenced {name}.", "story_talkative": "{actor} gave “{word}” to {name}.", "story_witch_saved": "{actor} used the life potion.", "story_witch_killed": "{actor} poisoned {name}.",
        "story_seer": "{actor} saw {name}: {role}.", "story_bear_yes": "{actor} growled.", "story_bear_no": "{actor} stayed silent.", "story_sheep_returned": "For {actor}, sheep returned from: {names}.", "story_sheep_lost": "For {actor}, sheep were lost at: {names}.", "story_sheep_left": "{actor} has {count} sheep left.", "story_judge_same": "{actor} compared {first} and {second}: same faction.", "story_judge_diff": "{actor} compared {first} and {second}: different factions.", "story_deaths": "Night deaths: {names}.", "story_hunter": "{actor} took: {names}.",
        "story_speaker": "Discussion starts with {name}.", "story_barber_hit": "{actor} shot {name}: the target was a Wolf.", "story_barber_miss": "{actor} shot {name}: the shot missed.", "story_alien_yes": "{actor}'s attempt was correct.", "story_alien_no": "{actor}'s attempt failed.", "story_alien_guess_yes": "{actor} guessed {role} for {name}: correct.", "story_alien_guess_no": "{actor} guessed {role} for {name}: incorrect.", "story_alien_deaths": "Alien victims: {names}.", "story_barber_deaths": "Barber victims: {names}.", "story_accused": "Accused players: {names}.", "story_normal_votes": "Announced votes: {values}.", "story_cancelled_votes": "Cancelled votes: {names}.", "story_secret_votes": "Secret votes: {values}.", "story_vote_eliminated": "The vote eliminated {name}.", "story_vote_tie": "The vote ended in a tie.", "story_vote_skipped": "The vote was skipped.", "story_day_forced": "The narrator ended the day manually.", "story_vote_deaths": "Deaths after the vote: {names}.", "story_powers_lost": "Powers removed from: {names}.", "story_winner": "Winner: {name}.",
        "outcome_eliminated": "Elimination", "outcome_tie": "Tie", "outcome_skipped": "Vote skipped", "outcome_forced_transition": "Manual ending", "pyro_action_douse": "Douse", "pyro_action_ignite": "Ignite", "pyro_action_blocked": "Blocked by Cerberus", "winner_wolves": "Werewolves", "winner_village": "Village", "winner_white_wolf": "White Wolf", "winner_angel": "Angel", "winner_alien": "Alien", "winner_pyromaniac": "Arsonist", "winner_couple": "Couple", "winner_draw": "Draw — no winner", "not_recorded": "Not recorded", "archive": "Game archive", "room_label": "Game",
    },
    "tn": {
        "history_kicker": "Journal mta3 el game", "history_live": "El game mazelt temchi", "history_finished": "El game wfet",
        "history_updated": "Tjadded taw", "history_night_title": "Bilan mta3 lil {round}", "history_day_title": "Bilan mta3 nhar {round}",
        "history_night_quiet": "El village fe9 kemel, 7ad ma met", "history_night_deaths": "{count} joueur(s) metou ellila",
        "history_day_eliminated": "{name} 5raj bel vote", "history_day_tie": "El vote égalité: 7ad ma 5raj", "history_day_skipped": "El village 3adda el vote", "history_day_forced": "El narrateur sakkar el nhar manuellement", "history_day_deaths": "{count} joueur(s) metou fel nhar",
        "history_details": "Chouf kifeh saret", "history_no_details": "Ma fama 7atta 7aja o5ra tet9al", "history_nights": "lilet", "history_days": "nharat",
        "story_couple": "{actor} rabat {names}.", "story_wild": "{actor} e5tar {name} modèle mte3ou.", "story_protected": "{actor} 7ma {name}.", "story_prostitute": "{actor} r9adet 3and {name}.", "story_blocked": "{actor} blocka {name}.",
        "story_pyro": "{actor} e5tar: {action}.", "story_wolves": "{actor} e5tarou {name}.", "story_redirect": "Attaque t7awlet l {name}.", "story_infection_yes": "{actor} infecta {name}.", "story_infection_no": "Tentative infection mta3 {actor} 3la {name} fachelet.",
        "story_white_wolf": "{actor} e5tar {name}.", "story_silenced": "{actor} sakket {name}.", "story_talkative": "{actor} 3ta kelmet « {word} » l {name}.", "story_witch_saved": "{actor} sta3mlet potion de vie.", "story_witch_killed": "{actor} sammet {name}.",
        "story_seer": "{actor} chefet {name}: {role}.", "story_bear_yes": "{actor} garger.", "story_bear_no": "{actor} ma gargerch.", "story_sheep_returned": "Mta3 {actor}, 3lelech raj3ou men 3and: {names}.", "story_sheep_lost": "Mta3 {actor}, 3lelech dha3ou 3and: {names}.", "story_sheep_left": "{actor} ba9awlouch {count} 3lelech.", "story_judge_same": "{actor} 9aren {first} w {second}: nafs el clan.", "story_judge_diff": "{actor} 9aren {first} w {second}: clans mo5talfin.", "story_deaths": "Eli metou ellila: {names}.", "story_hunter": "{actor} hezz m3ah: {names}.",
        "story_speaker": "El klem yabda m3a {name}.", "story_barber_hit": "{actor} dharab {name}: tla3 Loup.", "story_barber_miss": "{actor} dharab {name}: tir 8alet.", "story_alien_yes": "Tentative {actor} tla3et s7i7a.", "story_alien_no": "Tentative {actor} fachelet.", "story_alien_guess_yes": "{actor} 9al {name} role mte3ou {role}: s7i7.", "story_alien_guess_no": "{actor} 9al {name} role mte3ou {role}: 8alet.", "story_alien_deaths": "Eli metou fi joret Alien: {names}.", "story_barber_deaths": "Eli metou b Barbier: {names}.", "story_accused": "Eli tetwejhetelhom accusation: {names}.", "story_normal_votes": "El votes: {values}.", "story_cancelled_votes": "Votes eli tna77aw: {names}.", "story_secret_votes": "Votes bel sir: {values}.", "story_vote_eliminated": "El vote 5arrej {name}.", "story_vote_tie": "El vote wfa egalite.", "story_vote_skipped": "El vote t3adda.", "story_day_forced": "El narrateur sakkar el nhar manuellement.", "story_vote_deaths": "Eli metou ba3d el vote: {names}.", "story_powers_lost": "Pouvoirs tna77aw l: {names}.", "story_winner": "Eli rba7: {name}.",
        "outcome_eliminated": "Joueur 5raj", "outcome_tie": "Égalité", "outcome_skipped": "Vote t3adda", "outcome_forced_transition": "Nhar tsakker manuellement", "pyro_action_douse": "Rach zit", "pyro_action_ignite": "Cha3el", "pyro_action_blocked": "Cerbere blockeh", "winner_wolves": "El loups", "winner_village": "El Village", "winner_white_wolf": "Loup Blanc", "winner_angel": "Ange", "winner_alien": "Alien", "winner_pyromaniac": "Pyromane", "winner_couple": "El Couple", "winner_draw": "Égalité — 7ad ma rba7", "not_recorded": "Ma t7attetch", "archive": "Archive mta3 les games", "room_label": "Game",
    },
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
    language = current_language(request)
    return {**ROOM_TEXT[language], **ROOM_HISTORY_TEXT[language]}


def room_for_narrator(request, code):
    if not is_narrator(request.user):
        return None
    setup = request.session.get("game_setup", {})
    if setup.get("room_code") != code:
        return None
    room = GameRoom.objects.filter(code=code).first()
    return room if room and narrator_can_manage(request.user, room) else None


def can_view_room_history(request, room):
    if narrator_can_manage(request.user, room):
        return True
    return bool(
        request.user.is_authenticated
        and room.status == GameRoom.Status.FINISHED
        and room.room_players.filter(user=request.user).exists()
    )


def player_label(state, player_id):
    try:
        wanted = int(player_id)
    except (TypeError, ValueError):
        return None
    item = next((entry for entry in state.get("players", []) if entry.get("id") == wanted), None)
    return item.get("name") if item else None


def public_event_details(state, event_type):
    player_roles = {
        item.get("name"): item.get("role")
        for item in state.get("players", [])
        if item.get("name") and item.get("role") in ROLE_KEYS
    }
    hunter_records = state.get("hunterShotRecords", [])
    night_hunter_ids = [
        death_id
        for record in hunter_records
        if record.get("source") == "night"
        for death_id in (record.get("deathIds") or [record.get("targetId")])
        if death_id is not None
    ]
    day_hunter_ids = [
        death_id
        for record in hunter_records
        if record.get("source") != "night"
        for death_id in (record.get("deathIds") or [record.get("targetId")])
        if death_id is not None
    ]
    if event_type == "night":
        blocked_player = next((item for item in state.get("players", []) if item.get("id") == state.get("blockedPlayerId")), None)
        blocked_role = blocked_player.get("role") if blocked_player else None
        death_names = []
        all_death_entries = []
        seen_deaths = set()
        for entry in [
            *state.get("deaths", []),
            *night_hunter_ids,
        ]:
            identity = (entry.get("id"), entry.get("name")) if isinstance(entry, dict) else entry
            if identity in seen_deaths:
                continue
            seen_deaths.add(identity)
            all_death_entries.append(entry)
        for entry in all_death_entries:
            name = entry.get("name") if isinstance(entry, dict) else player_label(state, entry)
            if name:
                death_names.append(name)
        shepherd_results = state.get("shepherdLastResults") or []
        sheep_returned = [player_label(state, result.get("targetId")) for result in shepherd_results if result.get("returned")]
        sheep_lost = [player_label(state, result.get("targetId")) for result in shepherd_results if not result.get("returned")]
        has_shepherd = bool(shepherd_results) or any(item.get("role") == "shepherds" for item in state.get("players", []))
        return {
            "player_roles": player_roles,
            "couple_members": [name for name in (player_label(state, item) for item in state.get("coupleIds", [])) if name],
            "wild_child": player_label(state, state.get("wildChildId")),
            "wild_idol": player_label(state, state.get("wildIdolId")),
            "deaths": death_names,
            "hunter_deaths": [name for name in (player_label(state, item) for item in night_hunter_ids) if name],
            "protected": player_label(state, state.get("protectedId")),
            "wolves_target": player_label(state, state.get("wolfTargetId")),
            "wolves_final_target": player_label(state, state.get("wolfResolvedTargetId")) if state.get("wolfResolvedTargetId") != state.get("wolfTargetId") else None,
            "blocked": player_label(state, state.get("blockedPlayerId")),
            "redirected_to": player_label(state, state.get("prostituteTargetId")),
            "pyromaniac_action": state.get("pyromaniacAction"),
            "pyromaniac_doused": [name for name in (player_label(state, item) for item in state.get("pyromaniacDousedIds", [])) if name],
            "pyromaniac_ignited": [name for name in (player_label(state, item) for item in state.get("pyromaniacIgnitedIds", [])) if name],
            "pyromaniac_oiled": [name for name in (player_label(state, item) for item in state.get("pyromaniacOiledIds", [])) if name],
            "infection_attempted": bool(state.get("infectionAttempted")),
            "infection_succeeded": bool(state.get("infectionSucceeded")),
            "infection_target": player_label(state, state.get("infectedPlayerId") or state.get("wolfResolvedTargetId")),
            "white_wolf_target": player_label(state, state.get("whiteWolfTargetId")),
            "silenced": player_label(state, state.get("silencedPlayerId")),
            "talkative_target": player_label(state, state.get("talkativePlayerId")),
            "talkative_word": state.get("assignedWord"),
            "witch_saved": bool(state.get("witchSave")) and blocked_role != "witches",
            "witch_target": None if blocked_role == "witches" else player_label(state, state.get("witchKillId")),
            "bear_growled": state.get("bearGrowled"),
            "sheep_returned": [name for name in sheep_returned if name],
            "sheep_lost": [name for name in sheep_lost if name],
            "sheep_remaining": state.get("sheepRemaining") if has_shepherd else None,
            "shepherd_blocked": bool(state.get("shepherdWasBlocked")),
            "judge_first": player_label(state, state.get("judgeFirstId")),
            "judge_second": player_label(state, state.get("judgeSecondId")),
            "judge_same_clan": state.get("judgeSameClan"),
            "seer_target": player_label(state, state.get("seerTargetId")),
            "seer_role": state.get("seerDisplayedRole"),
        }
    hunter_targets = [player_label(state, record.get("targetId")) for record in state.get("hunterShotRecords", []) if record.get("source") != "night"]
    vote_breakdown = state.get("voteBreakdown") or {}
    vote_lines = lambda entries: [f"{player_label(state, entry.get('voterId'))} → {player_label(state, entry.get('targetId'))}" for entry in entries if player_label(state, entry.get("voterId")) and player_label(state, entry.get("targetId"))]
    normal_vote_lines = [
        f"{player_label(state, entry.get('targetId'))}: {entry.get('votes', 0)}"
        for entry in vote_breakdown.get("normal", [])
        if entry.get("votes") is not None and player_label(state, entry.get("targetId"))
    ] or vote_lines(vote_breakdown.get("normal", []))
    return {
        "player_roles": player_roles,
        "speaker": player_label(state, state.get("speakerId")),
        "accused": [name for name in (player_label(state, item) for item in state.get("qualifiers", [])) if name],
        "eliminated": player_label(state, state.get("lastVote")),
        "vote_deaths": [name for name in (player_label(state, item) for item in state.get("voteDeathIds", [])) if name],
        "alien_deaths": [name for name in (player_label(state, item) for item in state.get("alienDeathIds", [])) if name],
        "barber_deaths": [name for name in (player_label(state, item) for item in state.get("barberDeathIds", [])) if name],
        "hunter_deaths": [name for name in (player_label(state, item) for item in day_hunter_ids) if name],
        "vote_outcome": state.get("voteOutcome"),
        "normal_votes": normal_vote_lines,
        "cancelled_votes": [player_label(state, entry.get("voterId")) for entry in vote_breakdown.get("cancelled", []) if player_label(state, entry.get("voterId"))],
        "secret_votes": vote_lines(vote_breakdown.get("secret", [])),
        "final_totals": [f"{player_label(state, entry.get('id'))}: {entry.get('votes', 0)}" for entry in vote_breakdown.get("totals", []) if player_label(state, entry.get("id"))],
        "hunter_targets": [name for name in hunter_targets if name],
        "powers_lost": [name for name in (player_label(state, item) for item in state.get("lostVillagePowerIds", [])) if name],
        "barber_target": player_label(state, state.get("barberTargetId")),
        "barber_hit": state.get("barberHit"),
        "alien_guesses": [
            {
                "name": player_label(state, result.get("id")),
                "role": result.get("guessedRole"),
                "correct": bool(result.get("correct")),
            }
            for result in state.get("alienLastGuessResults", [])
            if player_label(state, result.get("id")) and result.get("guessedRole") in ROLE_KEYS
        ],
        "alien_correct": state.get("alienLastGuessCorrect"),
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
    if request.user.is_authenticated:
        return redirect("dashboard")

    error = None
    requested_next = request.POST.get("next") or request.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(requested_next, allowed_hosts={request.get_host()}):
        requested_next = ""
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)

        # Keep environment-configured narrator accounts compatible with older
        # installations, while persisting them as real Django users.
        if user is None:
            expected_password = settings.NARRATOR_CREDENTIALS.get(username)
            if expected_password is not None and secrets.compare_digest(password, expected_password):
                user_model = get_user_model()
                if not user_model.objects.filter(username=username).exists():
                    user = user_model.objects.create_user(username=username, password=password)
                    if username == "yessin":
                        user.is_staff = True
                        user.is_superuser = True
                        user.save(update_fields=["is_staff", "is_superuser"])
                    else:
                        user.groups.add(Group.objects.get_or_create(name=NARRATOR_GROUP)[0])

        if user is not None and user.is_active:
            login(request, user)
            # Retained for old signed-cookie sessions during the migration.
            request.session["authenticated"] = True
            request.session["narrator_username"] = user.username
            return redirect(requested_next or reverse("dashboard"))

        error = UI[current_language(request)]["auth_error"]

    return render(request, "pages/home.html", {"error": error, "next_url": requested_next})


def dashboard(request):
    if not request.user.is_authenticated:
        return redirect("home")
    return redirect("welcome" if is_narrator(request.user) else "room_portal")


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    error = None
    username = ""
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        password_confirmation = request.POST.get("password_confirmation", "")
        user_model = get_user_model()
        if not username:
            error = "Le nom d’utilisateur est obligatoire."
        elif user_model.objects.filter(username__iexact=username).exists():
            error = "Ce nom d’utilisateur existe déjà."
        elif len(password) < 4:
            error = "Le mot de passe doit contenir au moins 4 caractères."
        elif password != password_confirmation:
            error = "Les deux mots de passe ne correspondent pas."
        else:
            user = user_model.objects.create_user(username=username, password=password)
            login(request, user)
            return redirect("room_portal")

    return render(request, "pages/register.html", {"error": error, "username": username})


def user_management(request):
    if not request.user.is_authenticated or not request.user.is_superuser:
        raise PermissionDenied

    user_model = get_user_model()
    error = None
    success = None
    deleted_username = request.GET.get("deleted", "").strip()
    if deleted_username:
        success = f"Le compte {deleted_username} a été supprimé."
    if request.method == "POST":
        action = request.POST.get("action", "create")
        if action == "toggle":
            target = get_object_or_404(user_model, pk=request.POST.get("user_id"))
            if target.pk == request.user.pk or target.is_superuser:
                error = "Le compte super-admin ne peut pas être désactivé."
            else:
                target.is_active = not target.is_active
                target.save(update_fields=["is_active"])
        elif action == "create":
            username = request.POST.get("username", "").strip()
            password = request.POST.get("password", "")
            role = request.POST.get("role", "player")
            if not username or not password:
                error = "Le nom d’utilisateur et le mot de passe sont obligatoires."
            elif role not in {"player", "narrator"}:
                error = "Type de compte invalide."
            elif user_model.objects.filter(username__iexact=username).exists():
                error = "Ce nom d’utilisateur existe déjà."
            else:
                new_user = user_model.objects.create_user(username=username, password=password)
                if role == "narrator":
                    new_user.groups.add(Group.objects.get_or_create(name=NARRATOR_GROUP)[0])
                success = f"Le compte {username} a été créé."

    users = list(user_model.objects.prefetch_related("groups").order_by("username"))
    for account in users:
        account.account_role = (
            "Super admin" if account.is_superuser
            else "Narrateur" if any(group.name == NARRATOR_GROUP for group in account.groups.all())
            else "Joueur"
        )
    return render(request, "pages/user_management.html", {
        "managed_users": users,
        "error": error,
        "success": success,
    })


def user_detail(request, user_id):
    if not request.user.is_authenticated or not request.user.is_superuser:
        raise PermissionDenied

    user_model = get_user_model()
    account = get_object_or_404(user_model.objects.prefetch_related("groups"), pk=user_id)
    error = None
    success = None

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "toggle":
            if account.is_superuser:
                error = "Un compte super-admin ne peut pas être désactivé ici."
            else:
                account.is_active = not account.is_active
                account.save(update_fields=["is_active"])
                success = "Le compte a été réactivé." if account.is_active else "Le compte a été désactivé."
        elif action == "set_password":
            password = request.POST.get("password", "")
            confirmation = request.POST.get("password_confirmation", "")
            if len(password) < 4:
                error = "Le nouveau mot de passe doit contenir au moins 4 caractères."
            elif password != confirmation:
                error = "Les deux mots de passe ne correspondent pas."
            else:
                account.set_password(password)
                account.save(update_fields=["password"])
                success = "Le mot de passe a été modifié. L’ancien mot de passe ne fonctionne plus."
        elif action == "delete":
            if account.pk == request.user.pk or account.is_superuser:
                error = "Un compte super-admin ne peut pas être supprimé ici."
            else:
                deleted_username = account.username
                account.delete()
                return redirect(f"{reverse('user_management')}?{urlencode({'deleted': deleted_username})}")
        else:
            error = "Action invalide."

    account.account_role = (
        "Super admin" if account.is_superuser
        else "Narrateur" if any(group.name == NARRATOR_GROUP for group in account.groups.all())
        else "Joueur"
    )
    return render(request, "pages/user_detail.html", {
        "account": account,
        "narrated_room_count": account.narrated_rooms.count(),
        "participation_count": account.game_participations.count(),
        "can_manage_access": not account.is_superuser,
        "can_delete": not account.is_superuser and account.pk != request.user.pk,
        "error": error,
        "success": success,
    })


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
    if not request.user.is_authenticated:
        return redirect(f"{reverse('home')}?{urlencode({'next': request.get_full_path()})}")
    text = room_text(request)
    error = None
    retry_after = 0
    initial_code = request.GET.get("code", "").strip()
    if not (initial_code.isdigit() and len(initial_code) == 6):
        initial_code = ""
    if request.method == "POST":
        code = request.POST.get("room_code", "").strip()
        name = request.user.username
        initial_code = code
        if not code.isdigit() or len(code) != 6:
            error = text["invalid_code"]
        else:
            joined = None
            room = None
            try:
                with transaction.atomic():
                    room = GameRoom.objects.select_for_update(nowait=True).filter(code=code).first()
                    if room:
                        joined = room.room_players.filter(user=request.user).first()
                        name_owner = room.room_players.filter(name__iexact=name).first()
                        game_state = room.game_state or {}
                        pending_manual = game_state.get("pendingManualPlayerNames", [])
                        pending_name = next((item for item in pending_manual if item.casefold() == name.casefold()), None)
                        manual_state_player = next((item for item in game_state.get("players", []) if not item.get("roomPlayerId") and str(item.get("name", "")).casefold() == name.casefold()), None)
                        distribution_started = room_distribution_started(room, game_state)

                        if joined:
                            pass
                        elif name_owner:
                            error = text["name_used"]
                        elif not distribution_started and pending_name:
                            joined = RoomPlayer.objects.create(room=room, name=pending_name, user=request.user)
                            game_state["pendingManualPlayerNames"] = [item for item in pending_manual if item.casefold() != name.casefold()]
                            room.game_state = game_state
                            room.save(update_fields=["game_state", "updated_at"])
                        elif distribution_started and manual_state_player and manual_state_player.get("role") in ROLE_KEYS:
                            joined = RoomPlayer.objects.create(room=room, name=manual_state_player["name"], role=manual_state_player["role"], user=request.user)
                            manual_state_player["roomPlayerId"] = joined.id
                            room.game_state = game_state
                            room.save(update_fields=["game_state", "updated_at"])
                        elif distribution_started:
                            error = text["room_started"]
                        elif room.room_players.count() + len(pending_manual) >= room.player_count:
                            error = text["room_full"]
                        else:
                            joined = RoomPlayer.objects.create(room=room, name=name, user=request.user)
            except (IntegrityError, OperationalError):
                retry_after = 15

            if not room and not retry_after:
                error = text["invalid_room"]
            elif joined and not error and not retry_after:
                tokens = request.session.get("room_player_tokens", {})
                tokens[room.code] = str(joined.token)
                request.session["room_player_tokens"] = tokens
                return redirect("room_player", code=room.code)
    response = render(request, "pages/room_portal.html", {
        "room": text,
        "error": error,
        "initial_code": initial_code,
        "narrator_mode": is_narrator(request.user),
        "retry_after": retry_after,
    })
    if retry_after:
        response.status_code = 503
        response["Retry-After"] = str(retry_after)
    return response


def room_player(request, code):
    room = get_object_or_404(GameRoom, code=code.upper())
    token = request.session.get("room_player_tokens", {}).get(room.code)
    joined = room.room_players.filter(token=token).first()
    if not joined:
        return redirect("room_portal")
    return render(request, "pages/room_player.html", {"game_room": room, "joined_player": joined, "room": room_text(request)})


def room_history(request, code):
    room = get_object_or_404(GameRoom, code=code)
    if not can_view_room_history(request, room):
        raise PermissionDenied
    language = current_language(request)
    return render(request, "pages/room_history.html", {
        "game_room": room,
        "room": room_text(request),
        "history_labels": ROOM_DETAIL_LABELS[language],
        "role_labels": {key: value[0] for key, value in ROLES[language].items()},
    })


@require_safe
def general_room_qr(request):
    website_url = request.build_absolute_uri(reverse("home"))
    return qr_svg_response(website_url, max_age=86400 * 365)


def qr_svg_response(url, max_age):
    image = qrcode.make(url, image_factory=SvgPathImage, box_size=10, border=3)
    output = BytesIO()
    image.save(output)
    response = HttpResponse(output.getvalue(), content_type="image/svg+xml")
    response["Cache-Control"] = f"public, max-age={max_age}"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def room_history_list(request):
    if not request.user.is_authenticated:
        return redirect("home")
    rooms = GameRoom.objects.annotate(event_count=Count("events", distinct=True))
    player_history = not is_narrator(request.user) or request.GET.get("mine") == "1"
    if player_history:
        rooms = rooms.filter(status=GameRoom.Status.FINISHED, room_players__user=request.user)
    else:
        rooms = rooms.filter(Q(status=GameRoom.Status.ACTIVE) | Q(status=GameRoom.Status.FINISHED))
        if not request.user.is_superuser:
            rooms = rooms.filter(Q(narrator=request.user) | Q(narrator__isnull=True))
    rooms = rooms.order_by("-updated_at")
    return render(request, "pages/room_history_list.html", {
        "history_rooms": rooms,
        "room": room_text(request),
        "can_delete_history": is_narrator(request.user) and not player_history,
        "player_history": player_history,
    })


@require_POST
def room_history_finish(request, code):
    room = get_object_or_404(GameRoom, code=code, status=GameRoom.Status.ACTIVE)
    if not narrator_can_manage(request.user, room):
        raise PermissionDenied
    room.status = GameRoom.Status.FINISHED
    room.save(update_fields=["status", "updated_at"])
    return redirect("room_history_list")


@require_POST
def room_history_delete(request, code):
    room = get_object_or_404(
        GameRoom,
        Q(status=GameRoom.Status.ACTIVE) | Q(status=GameRoom.Status.FINISHED),
        code=code,
    )
    if not narrator_can_manage(request.user, room):
        raise PermissionDenied
    room.delete()
    return redirect("room_history_list")


def welcome(request):
    if not request.user.is_authenticated:
        return redirect("home")
    if not is_narrator(request.user):
        return redirect("room_portal")

    error = None
    resume_error = None
    resume_code = ""
    dashboard_mode = request.GET.get("mode", "dashboard")
    if dashboard_mode not in {"dashboard", "new", "resume"}:
        dashboard_mode = "dashboard"
    if request.method == "POST":
        if request.POST.get("action") == "resume":
            dashboard_mode = "resume"
            resume_code = request.POST.get("room_code", "").strip()
            if not (resume_code.isdigit() and len(resume_code) == 6):
                resume_error = UI[current_language(request)]["resume_invalid_code"]
            else:
                room = GameRoom.objects.filter(code=resume_code).first()
                if not room:
                    resume_error = UI[current_language(request)]["resume_not_found"]
                elif not narrator_can_manage(request.user, room):
                    raise PermissionDenied
                else:
                    request.session["game_setup"] = {
                        "player_count": room.player_count,
                        "composition": room.composition,
                        "room_code": room.code,
                    }
                    request.session["resume_from_server"] = True
                    return redirect("game")

            return render(request, "pages/welcome.html", {
                "error": error,
                "resume_error": resume_error,
                "resume_code": resume_code,
                "dashboard_mode": dashboard_mode,
            })

        dashboard_mode = "new"
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
            elif sum(composition[role] for role in WOLF_ROLE_KEYS) == player_count:
                error = UI[current_language(request)]["non_wolf_required"]
            elif any(composition[role] > 1 for role in SINGLETON_ROLE_KEYS):
                error = UI[current_language(request)]["singleton_roles"]
            else:
                room = GameRoom.objects.create(player_count=player_count, composition=composition, narrator=request.user)
                request.session["game_setup"] = {
                    "player_count": player_count,
                    "composition": composition,
                    "room_code": room.code,
                }
                return redirect("game")

    return render(request, "pages/welcome.html", {
        "error": error,
        "resume_error": resume_error,
        "resume_code": resume_code,
        "dashboard_mode": dashboard_mode,
    })


def game(request):
    if not request.user.is_authenticated:
        return redirect("home")
    if not is_narrator(request.user):
        return redirect("room_portal")

    setup = request.session.get("game_setup")
    if not setup:
        return redirect("welcome")
    if not setup.get("room_code"):
        room = GameRoom.objects.create(
            player_count=setup["player_count"], composition=setup["composition"], narrator=request.user
        )
        setup["room_code"] = room.code
        request.session["game_setup"] = setup
    room = GameRoom.objects.filter(code=setup["room_code"]).first()
    if not room:
        request.session.pop("game_setup", None)
        request.session.pop("resume_from_server", None)
        return redirect("welcome")

    resume_requested = bool(request.session.pop("resume_from_server", False))

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
            # The narrator is already behind admin authentication. Keep the
            # test distribution helper available on deployed environments too.
            "test_mode": True,
            "resume_requested": resume_requested,
            "server_game_state": room.game_state if resume_requested else {},
        },
    )


@require_GET
def room_lobby_api(request, code):
    room = room_for_narrator(request, code.upper())
    if not room:
        return JsonResponse({"error": "forbidden"}, status=403)
    effective_status = room.status if room_distribution_started(room) else GameRoom.Status.WAITING
    manual_players = (room.game_state or {}).get("pendingManualPlayerNames", [])
    players = [{"id": item.id, "name": item.name} for item in room.room_players.all()]
    return JsonResponse({
        "code": room.code,
        "status": effective_status,
        "player_count": room.player_count,
        "registered_count": len(players) + len(manual_players),
        "players": players,
        "manual_players": manual_players,
    })


@require_POST
@transaction.atomic
def room_lobby_remove_api(request, code):
    room = room_for_narrator(request, code.upper())
    if not room:
        return JsonResponse({"error": "forbidden"}, status=403)
    room = GameRoom.objects.select_for_update().get(code=room.code)
    if room_distribution_started(room):
        return JsonResponse({"error": "distribution_started"}, status=409)
    try:
        payload = json.loads(request.body)
        room_player_id = int(payload.get("room_player_id", 0) or 0)
        manual_name = str(payload.get("manual_name", "")).strip()
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "invalid_player"}, status=400)

    if room_player_id:
        deleted, _ = room.room_players.filter(id=room_player_id).delete()
        if not deleted:
            return JsonResponse({"error": "player_not_found"}, status=404)
    elif manual_name:
        game_state = room.game_state or {}
        manual_players = game_state.get("pendingManualPlayerNames", [])
        matching_name = next(
            (name for name in manual_players if str(name).casefold() == manual_name.casefold()),
            None,
        )
        if matching_name is None:
            return JsonResponse({"error": "player_not_found"}, status=404)
        game_state["pendingManualPlayerNames"] = [
            name for name in manual_players if name != matching_name
        ]
        room.game_state = game_state
        room.save(update_fields=["game_state", "updated_at"])
    else:
        return JsonResponse({"error": "invalid_player"}, status=400)

    manual_players = (room.game_state or {}).get("pendingManualPlayerNames", [])
    return JsonResponse({
        "status": "removed",
        "registered_count": room.room_players.count() + len(manual_players),
        "player_count": room.player_count,
        "manual_players": manual_players,
    })


@require_POST
@transaction.atomic
def room_start_api(request, code):
    room = room_for_narrator(request, code.upper())
    if not room:
        return JsonResponse({"error": "forbidden"}, status=403)
    room = GameRoom.objects.select_for_update().get(code=room.code)
    if room.status != GameRoom.Status.WAITING and not room_distribution_started(room):
        room.status = GameRoom.Status.WAITING
        room.save(update_fields=["status", "updated_at"])
    if room.status != GameRoom.Status.WAITING:
        return JsonResponse({"error": "already_started"}, status=409)
    joined = list(room.room_players.select_for_update())
    manual_players = (room.game_state or {}).get("pendingManualPlayerNames", [])
    roles = [role for role, count in room.composition.items() for _ in range(count)]
    if len(joined) + len(manual_players) > len(roles):
        return JsonResponse({"error": "too_many_players"}, status=409)
    player_aliases = [
        (joined_player.name, joined_player.user.username if joined_player.user else None)
        for joined_player in joined
    ] + [(name,) for name in manual_players]
    shuffle_roles_for_players(roles, player_aliases)
    assignments = []
    for index, joined_player in enumerate(joined):
        joined_player.role = roles[index]
        joined_player.save(update_fields=["role"])
        assignments.append({"room_player_id": joined_player.id, "name": joined_player.name, "role": joined_player.role})
    game_state = room.game_state or {}
    game_state["distributionStarted"] = True
    room.game_state = game_state
    room.status = GameRoom.Status.ACTIVE
    room.save(update_fields=["game_state", "status", "updated_at"])
    return JsonResponse({"assignments": assignments, "remaining_roles": roles[len(joined):], "manual_players": manual_players})


@require_POST
@transaction.atomic
def room_reconfigure_api(request, code):
    room = room_for_narrator(request, code.upper())
    if not room:
        return JsonResponse({"error": "forbidden"}, status=403)
    room = GameRoom.objects.select_for_update().get(code=room.code)
    if room.status == GameRoom.Status.FINISHED or room.events.exists():
        return JsonResponse({"error": "distribution_closed"}, status=409)
    try:
        payload = json.loads(request.body)
        composition = {role: int(payload.get("composition", {}).get(role, 0)) for role in ROLE_KEYS}
        removed_ids = {int(item) for item in payload.get("removed_player_ids", [])}
        manual_players = [str(item).strip()[:40] for item in payload.get("manual_players", []) if str(item).strip()]
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "invalid_setup"}, status=400)

    player_count = sum(composition.values())
    if not 8 <= player_count <= 30:
        return JsonResponse({"error": "player_range"}, status=400)
    if any(count < 0 for count in composition.values()):
        return JsonResponse({"error": "negative_roles"}, status=400)
    wolf_count = sum(composition[role] for role in WOLF_ROLE_KEYS)
    if wolf_count < 1:
        return JsonResponse({"error": "wolf_required"}, status=400)
    if wolf_count == player_count:
        return JsonResponse({"error": "non_wolf_required"}, status=400)
    if any(composition[role] > 1 for role in SINGLETON_ROLE_KEYS):
        return JsonResponse({"error": "singleton_roles"}, status=400)

    players = room.room_players.select_for_update()
    if len({name.casefold() for name in manual_players}) != len(manual_players):
        return JsonResponse({"error": "duplicate_players"}, status=400)
    connected_names = {name.casefold() for name in players.exclude(id__in=removed_ids).values_list("name", flat=True)}
    if connected_names.intersection(name.casefold() for name in manual_players):
        return JsonResponse({"error": "duplicate_players"}, status=400)
    remaining_count = players.exclude(id__in=removed_ids).count() + len(manual_players)
    if remaining_count > player_count:
        return JsonResponse({"error": "too_many_players"}, status=400)

    players.filter(id__in=removed_ids).delete()
    room.room_players.update(role="")
    room.player_count = player_count
    room.composition = composition
    room.status = GameRoom.Status.WAITING
    room.game_state = {"pendingManualPlayerNames": manual_players}
    room.save(update_fields=["player_count", "composition", "status", "game_state", "updated_at"])
    request.session["game_setup"] = {
        "player_count": player_count,
        "composition": composition,
        "room_code": room.code,
    }
    return JsonResponse({
        "status": room.status,
        "player_count": player_count,
        "composition": composition,
        "manual_players": manual_players,
        "players": [{"id": item.id, "name": item.name} for item in room.room_players.all()],
    })


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
    distribution_started = room_distribution_started(room, previous_state)
    if distribution_started:
        state.setdefault("distributionStarted", True)
    undo_requested = request.headers.get("X-Game-Undo") == "1"
    room.game_state = state
    if state.get("stage") == "game_over":
        room.status = GameRoom.Status.FINISHED
    elif distribution_started or state.get("roomStarted") or state.get("distributionStarted"):
        room.status = GameRoom.Status.ACTIVE
    else:
        room.status = GameRoom.Status.WAITING
    room.save(update_fields=["game_state", "status", "updated_at"])
    valid_roles = set(ROLES["fr"])
    for item in state.get("players", []):
        room_player_id = item.get("roomPlayerId")
        role = item.get("role")
        if room_player_id and role in valid_roles:
            room.room_players.filter(id=room_player_id).exclude(role=role).update(role=role)

    previous_round = max(1, int(previous_state.get("round", 1) or 1))
    current_round = max(1, int(state.get("round", previous_round) or previous_round))
    previous_stage = previous_state.get("stage")
    if current_round > previous_round and previous_stage in DAY_STAGES:
        recovered_day_state = {
            **previous_state,
            "stage": "day_end",
            "round": previous_round,
            "voteOutcome": previous_state.get("voteOutcome") or "forced_transition",
        }
        RoomEvent.objects.get_or_create(
            room=room,
            marker=f"day-{previous_round}",
            defaults={
                "event_type": "day",
                "round_number": previous_round,
                "details": public_event_details(recovered_day_state, "day"),
            },
        )

    event_type = "night" if state.get("stage") == "dawn" else "day" if state.get("stage") == "day_end" else None
    event_round = state.get("eventRound") if event_type == "night" else state.get("round", 1)
    round_number = max(1, int(event_round or state.get("round", 1)))

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
    game_state = room.game_state or {}
    distribution_started = room_distribution_started(room, game_state)
    effective_status = room.status if distribution_started else GameRoom.Status.WAITING
    role = joined.role if distribution_started else ""
    published_role_counts = game_state.get("publicAliveRoleCounts")
    state_players = game_state.get("players")
    role_counts = {}
    if distribution_started and isinstance(published_role_counts, dict):
        for item_role in ROLE_KEYS:
            try:
                count = int(published_role_counts.get(item_role, 0))
            except (TypeError, ValueError):
                count = 0
            if count > 0:
                role_counts[item_role] = count
    elif distribution_started and isinstance(state_players, list) and state_players and game_state.get("stage") not in {"roster", "player_reveal", "roles"}:
        for item in state_players:
            item_role = item.get("role") if isinstance(item, dict) else None
            if item_role in ROLE_KEYS and item.get("alive", True):
                role_counts[item_role] = role_counts.get(item_role, 0) + 1
    elif distribution_started:
        role_counts = {
            item_role: int(room.composition.get(item_role, 0))
            for item_role in ROLE_KEYS
            if int(room.composition.get(item_role, 0)) > 0
        }
    alive_roles = [
        {"code": item_role, "name": ROLES[language][item_role][0], "count": role_counts[item_role]}
        for item_role in ROLE_KEYS
        if role_counts.get(item_role, 0) > 0
    ]
    if (
        distribution_started
        and isinstance(state_players, list)
        and game_state.get("stage") not in {"roster", "player_reveal"}
    ):
        total_role_counts = {}
        for item in state_players:
            item_role = item.get("role") if isinstance(item, dict) else None
            if item_role in ROLE_KEYS:
                total_role_counts[item_role] = total_role_counts.get(item_role, 0) + 1
    else:
        total_role_counts = {
            item_role: int(room.composition.get(item_role, 0))
            for item_role in ROLE_KEYS
            if int(room.composition.get(item_role, 0)) > 0
        }
    role_roster = []
    for item_role in ROLE_KEYS:
        total = total_role_counts.get(item_role, 0)
        alive = min(role_counts.get(item_role, 0), total)
        role_roster.extend(
            {"code": item_role, "name": ROLES[language][item_role][0], "alive": True}
            for _ in range(alive)
        )
        role_roster.extend(
            {"code": item_role, "name": ROLES[language][item_role][0], "alive": False}
            for _ in range(total - alive)
        )
    return JsonResponse({
        "status": effective_status,
        "joined_count": room.room_players.count(),
        "player_count": room.player_count,
        "role": {"code": role, "name": ROLES[language][role][0], "description": ROLES[language][role][1]} if role else None,
        "alive_roles": alive_roles,
        "alive_count": sum(item["count"] for item in alive_roles),
        "role_roster": role_roster,
        "dead_count": sum(not item["alive"] for item in role_roster),
    })


@require_GET
def room_history_api(request, code):
    room = get_object_or_404(GameRoom, code=code.upper())
    if not can_view_room_history(request, room):
        return JsonResponse({"error": "forbidden"}, status=403)
    current_player_roles = {
        item.get("name"): item.get("role")
        for item in (room.game_state or {}).get("players", [])
        if item.get("name") and item.get("role") in ROLE_KEYS
    }
    events = []
    for event in room.events.all():
        details = dict(event.details or {})
        if current_player_roles and not details.get("player_roles"):
            details["player_roles"] = current_player_roles
        events.append({
            "type": event.event_type,
            "round": event.round_number,
            "details": details,
            "created_at": event.created_at.isoformat(),
        })
    return JsonResponse({"status": room.status, "events": events})


def logout_view(request):
    language = current_language(request)
    logout(request)
    request.session["language"] = language
    return redirect("home")
