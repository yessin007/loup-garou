"""Auditable league scoring derived only from completed server-side game events."""

from dataclasses import dataclass

from .models import ScoreAward
from .role_guides import ROLE_CAMPS


@dataclass(frozen=True)
class Award:
    player_id: int
    key: str
    rule_code: str
    points: int
    phase: str
    round_number: int | None
    metadata: dict


ACTIVE_VILLAGE_ROLES = {
    "protectors", "prostitutes", "servants", "ancients", "hunters",
    "red_riding_hoods", "bears", "shepherds", "cupids", "judges",
    "wild_children", "ankous", "seers", "witches",
}


RULEBOOK = {
    "fr": [
        (1, "Survie", "Chaque joueur encore vivant à la fin d’un jour terminé gagne +1."),
        (1, "Information et contrôle", "Ours : rapport valide. Juge : comparaison. Loup Noir : silence utile. Loup Bavard : mot imposé. Pyromane : au moins une cible aspergée."),
        (1, "Voyante", "Une vision valide d’une cible non hostile rapporte +1."),
        (2, "Action collective", "Meute : victime tuée la nuit. Village : hostile éliminé au vote. Loups : Villageois éliminé au vote."),
        (2, "Déductions et pouvoirs", "Voyante qui identifie un hostile, Berger non bloqué, Cupidon qui forme le Couple, Cerbère qui bloque un pouvoir, ou Loup Bleu qui trompe la Voyante."),
        (2, "Alien et Servante", "Chaque rôle correctement deviné par l’Alien rapporte +2. La Servante qui hérite d’un rôle rapporte +2."),
        (2, "Ankou", "Son vote secret rapporte +2 s’il contribue à éliminer un adversaire."),
        (3, "Sauvetages et ripostes", "Protecteur, Pute ou Chaperon Rouge qui neutralise réellement l’attaque des Loups : +3. Ancien qui résiste : +3."),
        (3, "Actions décisives", "Infection réussie, tir utile du Chasseur, tir du Loup Blanc, potion de mort sur un hostile, ou incendie réussi du Pyromane : +3."),
        (4, "Actions exceptionnelles", "Potion de vie décisive sur un allié : +4. Bonne cible du Barbier : +4."),
        (5, "Victoire et sauvetage critique", "Chaque membre du camp gagnant reçoit +5. Sauver un allié à pouvoir majeur avec la Sorcière rapporte aussi +5. Les objectifs solo et le Couple ne récompensent que leurs gagnants."),
        (1, "Rôles physiques", "Villageois, Petite Fille et Enfant Sauvage n’ont pas toujours une action vérifiable par l’application : ils marquent avec la survie, l’action collective et la victoire."),
    ],
    "en": [
        (1, "Survival", "Every player still alive at the end of a completed day earns +1."),
        (1, "Information and control", "Bear: valid report. Judge: comparison. Black Wolf: useful silence. Talkative Wolf: assigned word. Arsonist: at least one player doused."),
        (1, "Seer", "A valid vision of a non-hostile target earns +1."),
        (2, "Team action", "Pack: a night victim is killed. Village: a hostile is voted out. Wolves: a Villager is voted out."),
        (2, "Deductions and powers", "Seer identifying a hostile, unblocked Shepherd report, Cupid forming the Couple, Cerberus blocking a power, or Blue Wolf deceiving the Seer."),
        (2, "Alien and Servant", "Each role correctly guessed by the Alien earns +2. A Servant who inherits a role earns +2."),
        (2, "Ankou", "A secret vote earns +2 when it helps eliminate an opponent."),
        (3, "Saves and retaliation", "Protector, Escort or Red Riding Hood genuinely stopping a Wolf attack: +3. Ancient resisting it: +3."),
        (3, "Decisive actions", "Successful infection, useful Hunter shot, White Wolf kill, death potion on a hostile, or successful Arsonist ignition: +3."),
        (4, "Exceptional actions", "A decisive life potion on an ally: +4. A correct Barber target: +4."),
        (5, "Victory and critical save", "Every member of the winning team earns +5. A Witch saving an allied major power also earns +5. Solo and Couple objectives reward only their winners."),
        (1, "Physical roles", "Villager, Little Girl and Wild Child do not always have an app-verifiable action, so they score through survival, team actions and victory."),
    ],
    "tn": [
        (1, "Survie", "Kol joueur mezel 3ayech fi e5er nhar kemel ye5ou +1."),
        (1, "Information w contrôle", "Ours: résultat valide. Juge: comparaison. Loup Noir: silence. Loup Bavard: kelma. Pyromane: yarach zit 3la cible."),
        (1, "Voyante", "Vision valide mta3 cible mahich hostile ta3ti +1."),
        (2, "Action collective", "Meute: victime tet9tal ellil. Village: hostile yo5rej bel vote. Loups: Villageois yo5rej bel vote."),
        (2, "Pouvoirs", "Voyante tal9a hostile, Berger mahouch bloqué, Cupidon ya3mel Couple, Cerbère yblocki pouvoir, wala Loup Bleu y8alet el Voyante."),
        (2, "Alien w Servante", "Kol role ye7zrou Alien s7i7 +2. Servante ki te5ou role +2."),
        (2, "Ankou", "Vote secret +2 ki yse3ed y5arrej adversaire."),
        (3, "Sauvetage", "Protecteur, Pute wala Chaperon Rouge ki ywa9fou attaque s7i7a: +3. Ancien ki yest7amel: +3."),
        (3, "Action décisive", "Infection, tir Chasseur, tir Loup Blanc, potion mort 3la hostile, wala incendie Pyromane réussi: +3."),
        (4, "Action exceptionnelle", "Potion de vie tnajji allié bel7a9: +4. Tir Barbier s7i7: +4."),
        (5, "Victoire w sauvetage critique", "Kol membre mel camp reb7an +5. Sorcière ki tnajji allié 3andou pouvoir important te5ou +5 zeda."),
        (1, "Roles physiques", "Villageois, Petite Fille w Enfant Sauvage ma 3andhomch dima action vérifiable fel app: points mte3hom men survie, équipe w victoire."),
    ],
}


AWARD_COPY = {
    "fr": {
        "day_survived": "Jour {round} survécu", "victory": "Victoire avec {winner}",
        "wolves_hunt": "Chasse nocturne réussie", "village_vote": "Hostile éliminé par le Village",
        "wolves_vote": "Vote détourné par les Loups", "cerberus_block": "Pouvoir adverse bloqué",
        "infection": "Infection réussie", "white_wolf_kill": "Tir du Loup Blanc réussi",
        "black_wolf_silence": "Silence imposé", "talkative_word": "Mot imposé",
        "pyro_douse": "Cible aspergée", "pyro_ignite": "Incendie réussi",
        "escort_save": "Attaque redirigée et survécue", "ancient_resist": "Attaque des Loups résistée",
        "bear_report": "Rapport de l’Ours", "shepherd_report": "Rapport utile du Berger",
        "cupid_link": "Couple formé", "judge_compare": "Comparaison du Juge",
        "seer_vision": "Vision de la Voyante", "seer_hostile": "Hostile identifié par la Voyante",
        "blue_wolf_deception": "Voyante trompée", "witch_save": "Allié sauvé par la Sorcière", "witch_critical_save": "Pouvoir majeur sauvé par la Sorcière",
        "witch_kill": "Hostile éliminé par la Sorcière", "protector_save": "Attaque bloquée par le Protecteur",
        "red_hood_save": "Protection du Chaperon Rouge", "barber_hit": "Bonne cible du Barbier",
        "alien_guess": "Rôle correctement deviné", "hunter_shot": "Tir utile du Chasseur",
        "servant_inherit": "Rôle hérité par la Servante", "ankou_vote": "Vote décisif de l’Ankou",
    },
    "en": {
        "day_survived": "Survived day {round}", "victory": "Victory with {winner}",
        "wolves_hunt": "Successful night hunt", "village_vote": "Hostile voted out by the Village",
        "wolves_vote": "Vote steered by the Wolves", "cerberus_block": "Opponent power blocked",
        "infection": "Successful infection", "white_wolf_kill": "Successful White Wolf kill",
        "black_wolf_silence": "Silence imposed", "talkative_word": "Word imposed",
        "pyro_douse": "Target doused", "pyro_ignite": "Successful ignition",
        "escort_save": "Attack redirected and survived", "ancient_resist": "Resisted the Wolf attack",
        "bear_report": "Bear report", "shepherd_report": "Useful Shepherd report",
        "cupid_link": "Couple formed", "judge_compare": "Judge comparison",
        "seer_vision": "Seer vision", "seer_hostile": "Hostile identified by the Seer",
        "blue_wolf_deception": "Seer deceived", "witch_save": "Ally saved by the Witch", "witch_critical_save": "Major allied power saved by the Witch",
        "witch_kill": "Hostile killed by the Witch", "protector_save": "Attack blocked by the Protector",
        "red_hood_save": "Red Riding Hood protection", "barber_hit": "Correct Barber target",
        "alien_guess": "Role guessed correctly", "hunter_shot": "Useful Hunter shot",
        "servant_inherit": "Role inherited by the Servant", "ankou_vote": "Decisive Ankou vote",
    },
    "tn": {},
}
AWARD_COPY["tn"] = AWARD_COPY["fr"]


def award_label(award, language):
    template = AWARD_COPY.get(language, AWARD_COPY["fr"]).get(award.rule_code, award.rule_code)
    values = {"round": award.round_number or "—", **(award.metadata or {})}
    try:
        return template.format(**values)
    except (KeyError, ValueError):
        return template


def scoring_snapshot(state):
    """Keep the minimum private state needed to audit score decisions."""
    keys = (
        "coupleIds", "angelChanceExpired", "winner", "wolfTargetId", "wolfResolvedTargetId",
        "protectedId", "prostituteTargetId", "blockedPlayerId", "infectionAttempted",
        "infectionSucceeded", "infectedPlayerId", "whiteWolfTargetId", "silencedPlayerId",
        "talkativePlayerId", "pyromaniacAction", "pyromaniacDousedIds", "pyromaniacIgnitedIds",
        "ancientResistedPlayerId", "bearPlayerId", "bearGrowled", "bearNeighborIds",
        "shepherdLastResults", "shepherdWasBlocked", "cupidLinked", "judgeFirstId",
        "judgeSecondId", "judgeSameClan", "seerActorId", "seerTargetId", "seerDisplayedRole",
        "witchSave", "witchKillId", "lastVote", "voteDeathIds", "voteOutcome",
        "barberPlayerId", "barberTargetId", "barberHit", "alienLastGuessResults",
        "servantAccepted", "servantPlayerId", "servantInheritedRole", "voteBreakdown",
        "hunterShotRecords", "round",
    )
    snapshot = {key: state.get(key) for key in keys}
    snapshot["players"] = [
        {
            "id": item.get("id"), "room_player_id": item.get("roomPlayerId"),
            "name": item.get("name"), "role": item.get("role"),
            "initial_role": item.get("initialRole") or item.get("role"),
            "alive": bool(item.get("alive", True)), "infected": bool(item.get("infected")),
            "wild_turned": bool(item.get("wildTurned")),
        }
        for item in state.get("players", []) if isinstance(item, dict)
    ]
    snapshot["death_ids"] = [
        item.get("id") if isinstance(item, dict) else item for item in state.get("deaths", [])
    ]
    return snapshot


def _is_wolf(player):
    return bool(player and (ROLE_CAMPS.get(player.get("role")) == "wolf" or player.get("infected") or player.get("wild_turned")))


def _is_hostile(player):
    return bool(player and (_is_wolf(player) or player.get("role") in {"aliens", "pyromaniacs"}))


def _base_faction(player, snapshot):
    if _is_wolf(player):
        return "wolf"
    role = player.get("role")
    in_couple = player.get("id") in (snapshot.get("coupleIds") or [])
    if role == "angels":
        return "village" if snapshot.get("angelChanceExpired") or snapshot.get("round", 1) > 1 or in_couple else "angel"
    return {"aliens": "alien", "pyromaniacs": "pyromaniac", "fools": "fool"}.get(role, "village")


def _winner_player_ids(state):
    winner = state.get("winner")
    players = [item for item in state.get("players", []) if isinstance(item, dict)]
    if not winner or winner == "draw":
        return []
    if winner == "couple":
        return list(state.get("coupleIds") or [])
    if winner in {"angel", "fool"}:
        role = "angels" if winner == "angel" else "fools"
        return [item.get("id") for item in players if item.get("role") == role]
    if winner == "white_wolf":
        return [item.get("id") for item in players if item.get("role") == "white_wolves"]
    if winner == "alien":
        return [item.get("id") for item in players if item.get("role") == "aliens"]
    if winner == "pyromaniac":
        return [item.get("id") for item in players if item.get("role") == "pyromaniacs"]
    if winner == "wolves":
        return [item.get("id") for item in players if _is_wolf(item) and item.get("role") != "white_wolves"]
    if winner == "village":
        return [item.get("id") for item in players if _base_faction(item, state) == "village"]
    return []


def calculate_room_awards(room):
    room_players = list(room.room_players.select_related("user"))
    by_id = {item.id: item for item in room_players if item.user_id}
    by_name = {item.name.casefold(): item for item in room_players if item.user_id}
    awards = {}

    def linked(scoring_player):
        if not scoring_player:
            return None
        try:
            direct = by_id.get(int(scoring_player.get("room_player_id") or 0))
        except (TypeError, ValueError):
            direct = None
        return direct or by_name.get(str(scoring_player.get("name") or "").casefold())

    def add(scoring_player, key, rule_code, points, phase, round_number, metadata=None):
        player = linked(scoring_player)
        if not player or not 1 <= points <= 5:
            return
        award = Award(player.id, key, rule_code, points, phase, round_number, metadata or {})
        awards[(player.id, key)] = award

    def add_actor(players, role, *args, actor_id=None, **kwargs):
        actor = next((item for item in players if item.get("id") == actor_id), None) if actor_id else None
        actor = actor or next((item for item in players if item.get("role") == role), None)
        if actor:
            add(actor, *args, **kwargs)

    def opposed(first, second, snapshot):
        return first and second and _base_faction(first, snapshot) != _base_faction(second, snapshot)

    for event in room.events.all():
        details = event.details or {}
        snapshot = details.get("_scoring") or {}
        players = snapshot.get("players") or [
            {"id": index + 1, "name": item.get("name"), "role": item.get("role"), "alive": item.get("alive", True)}
            for index, item in enumerate(details.get("player_statuses") or [])
        ]
        indexed = {item.get("id"): item for item in players}
        round_number = event.round_number

        if event.event_type == "day":
            for item in players:
                if item.get("alive"):
                    add(item, f"survival-day-{round_number}", "day_survived", 1, "day", round_number)

            voted = indexed.get(snapshot.get("lastVote"))
            if snapshot.get("voteOutcome") == "eliminated" and voted:
                if _is_hostile(voted):
                    for item in players:
                        if item.get("alive") and _base_faction(item, snapshot) == "village":
                            add(item, f"village-vote-{round_number}", "village_vote", 2, "day", round_number, {"target": voted.get("name", "")})
                elif _base_faction(voted, snapshot) == "village":
                    for item in players:
                        if item.get("alive") and _is_wolf(item):
                            add(item, f"wolves-vote-{round_number}", "wolves_vote", 2, "day", round_number, {"target": voted.get("name", "")})

            if snapshot.get("barberHit"):
                add_actor(players, "barbers", f"barber-{round_number}", "barber_hit", 4, "day", round_number, actor_id=snapshot.get("barberPlayerId"))

            for index, result in enumerate(snapshot.get("alienLastGuessResults") or []):
                if result.get("correct"):
                    add_actor(players, "aliens", f"alien-guess-{round_number}-{index}-{result.get('id')}", "alien_guess", 2, "day", round_number)

            if snapshot.get("servantAccepted") and snapshot.get("servantPlayerId"):
                add(indexed.get(snapshot.get("servantPlayerId")), f"servant-{round_number}", "servant_inherit", 2, "day", round_number)

            secret_votes = (snapshot.get("voteBreakdown") or {}).get("secret") or []
            for entry in secret_votes:
                voter, target = indexed.get(entry.get("voterId")), indexed.get(entry.get("targetId"))
                if target and target is voted and opposed(voter, target, snapshot):
                    add(voter, f"ankou-vote-{round_number}", "ankou_vote", 2, "day", round_number)

        if event.event_type == "night":
            death_ids = {int(item) for item in snapshot.get("death_ids") or [] if str(item).isdigit()}
            wolf_target = indexed.get(snapshot.get("wolfResolvedTargetId") or snapshot.get("wolfTargetId"))
            if wolf_target and wolf_target.get("id") in death_ids:
                for item in players:
                    if _is_wolf(item):
                        add(item, f"hunt-{round_number}", "wolves_hunt", 2, "night", round_number, {"target": wolf_target.get("name", "")})

            blocked = indexed.get(snapshot.get("blockedPlayerId"))
            if blocked and blocked.get("role") in ACTIVE_VILLAGE_ROLES:
                add_actor(players, "cerberus_wolves", f"block-{round_number}", "cerberus_block", 2, "night", round_number)
            if snapshot.get("infectionSucceeded"):
                add_actor(players, "infecting_fathers", f"infection-{round_number}", "infection", 3, "night", round_number)
            white_target = indexed.get(snapshot.get("whiteWolfTargetId"))
            if white_target and white_target.get("id") in death_ids:
                add_actor(players, "white_wolves", f"white-wolf-{round_number}", "white_wolf_kill", 3, "night", round_number)
            if snapshot.get("silencedPlayerId") and (blocked or {}).get("role") != "black_wolves":
                add_actor(players, "black_wolves", f"silence-{round_number}", "black_wolf_silence", 1, "night", round_number)
            if snapshot.get("talkativePlayerId") and (blocked or {}).get("role") != "talkative_wolves":
                add_actor(players, "talkative_wolves", f"word-{round_number}", "talkative_word", 1, "night", round_number)
            if snapshot.get("pyromaniacAction") == "douse" and snapshot.get("pyromaniacDousedIds"):
                add_actor(players, "pyromaniacs", f"douse-{round_number}", "pyro_douse", 1, "night", round_number)
            if snapshot.get("pyromaniacAction") == "ignite" and snapshot.get("pyromaniacIgnitedIds"):
                add_actor(players, "pyromaniacs", f"ignite-{round_number}", "pyro_ignite", 3, "night", round_number)

            original_target = indexed.get(snapshot.get("wolfTargetId"))
            escort = next((item for item in players if item.get("role") == "prostitutes"), None)
            if original_target is escort and wolf_target is not escort and escort and escort.get("alive"):
                add(escort, f"escort-{round_number}", "escort_save", 3, "night", round_number)
            ancient = indexed.get(snapshot.get("ancientResistedPlayerId"))
            if ancient:
                add(ancient, f"ancient-{round_number}", "ancient_resist", 3, "night", round_number)
            if snapshot.get("bearPlayerId") and snapshot.get("bearGrowled") is not None:
                add(indexed.get(snapshot.get("bearPlayerId")), f"bear-{round_number}", "bear_report", 1, "night", round_number)
            if snapshot.get("shepherdLastResults") and not snapshot.get("shepherdWasBlocked"):
                add_actor(players, "shepherds", f"shepherd-{round_number}", "shepherd_report", 2, "night", round_number)
            if snapshot.get("cupidLinked") and snapshot.get("coupleIds"):
                add_actor(players, "cupids", "cupid-link", "cupid_link", 2, "night", round_number)
            if snapshot.get("judgeFirstId") and snapshot.get("judgeSecondId"):
                add_actor(players, "judges", f"judge-{round_number}", "judge_compare", 1, "night", round_number)

            seer = indexed.get(snapshot.get("seerActorId"))
            seer_target = indexed.get(snapshot.get("seerTargetId"))
            if seer and seer_target:
                rule, points = ("seer_hostile", 2) if _is_hostile(seer_target) and snapshot.get("seerDisplayedRole") == seer_target.get("role") else ("seer_vision", 1)
                add(seer, f"seer-{round_number}", rule, points, "night", round_number)
                if seer_target.get("role") == "blue_wolves" and snapshot.get("seerDisplayedRole") != "blue_wolves":
                    add(seer_target, f"blue-deception-{round_number}", "blue_wolf_deception", 2, "night", round_number)

            protected_id = snapshot.get("protectedId")
            effective_attack = wolf_target and (wolf_target.get("id") not in death_ids)
            infection_stopped = snapshot.get("infectionAttempted") and not snapshot.get("infectionSucceeded")
            protection_needed = wolf_target and wolf_target.get("role") != "aliens"
            if protected_id and protection_needed and protected_id == wolf_target.get("id") and (effective_attack or infection_stopped):
                add_actor(players, "protectors", f"protector-{round_number}", "protector_save", 3, "night", round_number)
            witch = next((item for item in players if item.get("role") == "witches"), None)
            if snapshot.get("witchSave") and wolf_target and wolf_target.get("id") not in death_ids and protected_id != wolf_target.get("id") and witch and not opposed(witch, wolf_target, snapshot):
                critical_roles = {"seers", "protectors", "hunters", "ancients", "witches", "bears", "judges", "shepherds"}
                critical = wolf_target.get("role") in critical_roles
                add(witch, f"witch-save-{round_number}", "witch_critical_save" if critical else "witch_save", 5 if critical else 4, "night", round_number)
            witch_target = indexed.get(snapshot.get("witchKillId"))
            if witch_target and witch_target.get("id") in death_ids and _is_hostile(witch_target):
                add_actor(players, "witches", f"witch-kill-{round_number}", "witch_kill", 3, "night", round_number)
            if wolf_target and wolf_target.get("role") == "red_riding_hoods" and wolf_target.get("alive") and protected_id != wolf_target.get("id") and not snapshot.get("witchSave"):
                add(wolf_target, f"red-hood-{round_number}", "red_hood_save", 3, "night", round_number)

        for index, shot in enumerate(snapshot.get("hunterShotRecords") or []):
            hunter, target = indexed.get(shot.get("hunterId")), indexed.get(shot.get("targetId"))
            if opposed(hunter, target, snapshot):
                add(hunter, f"hunter-{event.event_type}-{round_number}-{index}-{target.get('id')}", "hunter_shot", 3, event.event_type, round_number)

    final_state = room.game_state or {}
    if room.status == room.Status.FINISHED and final_state.get("winner"):
        final_players = final_state.get("players") or []
        final_indexed = {item.get("id"): item for item in final_players if isinstance(item, dict)}
        for player_id in _winner_player_ids(final_state):
            item = final_indexed.get(player_id)
            if item:
                add(item, "victory", "victory", 5, "game", None, {"winner": final_state.get("winner", "")})
    return awards


def reconcile_room_scores(room):
    """Make the persisted ledger exactly match the room's completed events."""
    desired = calculate_room_awards(room)
    existing = {(item.player_id, item.award_key): item for item in room.score_awards.all()}
    stale_ids = [item.id for key, item in existing.items() if key not in desired]
    if stale_ids:
        ScoreAward.objects.filter(id__in=stale_ids).delete()
    for identity, award in desired.items():
        player = room.room_players.select_related("user").get(id=award.player_id)
        ScoreAward.objects.update_or_create(
            room=room,
            player=player,
            award_key=award.key,
            defaults={
                "user": player.user,
                "rule_code": award.rule_code,
                "points": award.points,
                "phase": award.phase,
                "round_number": award.round_number,
                "metadata": award.metadata,
            },
        )
