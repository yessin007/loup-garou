import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import GameRoom, RoomEvent
from .translations import ROLES


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class RoomFlowTests(TestCase):
    def setUp(self):
        self.narrator = Client()
        self.narrator.post(reverse("home"), {"username": "admin", "password": "admin"})
        self.composition = {role: 0 for role in ROLES["fr"]}
        self.composition.update({"simple_wolves": 2, "villagers": 6})

    def player_client(self, username):
        user, created = get_user_model().objects.get_or_create(username=username)
        if created:
            user.set_password("test-password")
            user.save(update_fields=["password"])
        client = Client()
        client.force_login(user)
        return client

    def create_room(self):
        response = self.narrator.post(
            reverse("welcome"),
            {"player_count": 8, **self.composition},
        )
        self.assertRedirects(response, reverse("game"), fetch_redirect_response=False)
        return GameRoom.objects.get(code=self.narrator.session["game_setup"]["room_code"])

    def test_narrator_dashboard_routes_each_admin_action(self):
        dashboard = self.narrator.get(reverse("welcome"))
        self.assertContains(dashboard, reverse("room_history_list"))
        self.assertContains(dashboard, f'{reverse("welcome")}?mode=new')
        self.assertContains(dashboard, f'{reverse("welcome")}?mode=resume')
        self.assertNotContains(dashboard, 'id="setup-form"')
        self.assertNotContains(dashboard, 'id="resume-room-code"')

        new_game = self.narrator.get(reverse("welcome"), {"mode": "new"})
        self.assertContains(new_game, 'id="setup-form"')
        self.assertNotContains(new_game, 'id="resume-room-code"')
        self.assertContains(new_game, "const wolfRolePriority")
        self.assertContains(new_game, "const specialRolePriority")
        self.assertContains(new_game, 'nonWolfSlots - specialRolePriority.length')
        self.assertContains(new_game, "prepareSingletonRoleToggles()")
        self.assertContains(new_game, '["simple_wolves", "villagers"]')

        resume_game = self.narrator.get(reverse("welcome"), {"mode": "resume"})
        self.assertContains(resume_game, 'id="resume-room-code"')
        self.assertNotContains(resume_game, 'id="setup-form"')

        history = self.narrator.get(reverse("room_history_list"))
        self.assertContains(history, 'class="history-home-link"')
        self.assertContains(history, f'href="{reverse("dashboard")}"')

    @override_settings(DEBUG=True)
    def test_development_mode_exposes_automatic_test_distribution(self):
        self.create_room()
        game = self.narrator.get(reverse("game"))
        self.assertContains(game, 'id="test-mode" type="application/json">true</script>')
        self.assertContains(game, '"auto-distribute-test"')
        self.assertContains(game, "autoDistributeTestPlayers")

    def test_night_summary_sections_and_single_candidate_majority_rule_are_present(self):
        self.create_room()
        game = self.narrator.get(reverse("game"))
        self.assertContains(game, 'id="village-state-open"')
        self.assertContains(game, 'id="village-state-dialog"')
        self.assertContains(game, 'data-village-state-mode="phase"')
        self.assertContains(game, 'data-village-state-mode="player"')
        self.assertContains(game, 'id="village-state-phase"')
        self.assertContains(game, "setVillageStateMode")
        self.assertContains(game, "resetStateForManualPhase")
        self.assertContains(game, "restartDayAfterVillageModification")
        self.assertContains(game, 'if (phaseBeforeModification === "night")')
        self.assertContains(game, "resetStateForManualPhase(false)")
        self.assertContains(game, 'state.stage = "dawn"')
        self.assertContains(game, 'nextNightStage("")')
        self.assertContains(game, "applyVillageStateModification")
        self.assertContains(game, 'action === "disqualify"')
        self.assertContains(game, 'action === "revive"')
        self.assertContains(game, 'action === "change_role"')
        self.assertContains(game, "changeVillagePlayerRole")
        self.assertContains(
            game,
            "${escapeHtml(roleMeta[item.role]?.name || item.role)} · ${item.alive ? L.alive : L.eliminated}",
        )
        self.assertContains(
            game,
            'if (stage === "wild_child") return hasAliveRole("wild_children") && !state.wildChildLinked',
        )
        self.assertContains(
            game,
            '"protector", "prostitute", "cerberus", "pyromaniac", "wolves", "infection"',
        )
        self.assertContains(game, 'class="bilan-section night-death-section"')
        self.assertContains(game, 'class="bilan-section village-info-section"')
        self.assertContains(game, 'class="bilan-section day-instruction-section"')
        self.assertContains(game, 't("died_tonight_player_role", {name: escapeHtml(victim.name), role: escapeHtml(roleMeta[victim.role].name)})')
        self.assertNotContains(game, '<strong>#${String(id).padStart(2, "0")} · ${escapeHtml(victim.name)}</strong>')
        self.assertContains(game, '${L.seer_bilan_label} <mark>${escapeHtml(seerSeenRole)}</mark>')
        self.assertContains(game, '${L.bear_bilan_label} <mark>${state.bearGrowled ? L.bear_bilan_growls : L.bear_bilan_silent}</mark>')
        self.assertContains(game, '${L.shepherd_bilan_label} <mark>${t("shepherd_bilan_value", {count: state.sheepRemaining})}</mark>')
        self.assertContains(game, '${L.judge_saw} <mark>${judgeVerdict}</mark>')
        self.assertContains(game, '${L.speaking_starts} ${escapeHtml(speaker.name)}')
        self.assertContains(game, 'classList.toggle("bilan-mode"')
        self.assertContains(game, 'class="bear-neighbor-card ${factionClass}"')
        self.assertContains(game, "status.leftNeighbor")
        self.assertContains(game, "status.rightNeighbor")
        self.assertContains(game, 'id="shepherd-selection-count"')
        self.assertContains(game, 'class="sheep-check"')
        self.assertNotContains(game, "button.disabled = !rows.length")
        self.assertNotContains(game, "if (!rows.length || rows.some")
        self.assertContains(game, "max > alive().length / 2")
        self.assertContains(game, '"insufficient_majority"')
        self.assertContains(game, 'data-action="majority-eliminate"')
        self.assertContains(game, 'selected.length !== 1')
        self.assertContains(game, 'confirm(L.accusation_majority_confirm)')
        self.assertContains(game, 'state.stage = "servant_choice"')
        self.assertContains(game, 'finalizeVoteDeath()')

    def test_barber_kills_only_a_wolf_or_dies_with_a_non_wolf_target(self):
        self.create_room()
        game = self.narrator.get(reverse("game"))
        self.assertContains(game, 'const signalStages = ["dawn", "accusation", "final_vote"]')
        self.assertContains(
            game,
            "return barberPowerAvailable()",
        )
        self.assertContains(
            game,
            "return alienPowerAvailable()",
        )
        self.assertNotContains(
            game,
            'return barberPowerAvailable() && !isRoleBlocked("barbers")',
        )
        self.assertNotContains(
            game,
            'return alienPowerAvailable() && !isRoleBlocked("aliens")',
        )
        self.assertNotContains(game, "L.cerberus_day_blocked")
        self.assertContains(
            game,
            "state.qualifiers.map(player).filter(item => item?.alive)",
        )
        self.assertContains(game, "state.stage = daySpecialReturnStage()")
        self.assertContains(game, "state.barberHit = isWolfPlayer(target)")
        self.assertContains(
            game,
            "killPlayersWithLovers(state.barberHit ? [target.id] : [barber.id, target.id])",
        )
        self.assertContains(
            game,
            'roleMeta[item.role].faction === "wolf" || item.infected || item.wildTurned',
        )

    def test_red_riding_hood_is_protected_by_a_living_hunter_unless_cerberus_blocks_it(self):
        self.composition.update({"red_riding_hoods": 1, "villagers": 5})
        self.create_room()
        game = self.narrator.get(reverse("game"))
        self.assertContains(game, 'red_riding_hoods: { short: "CR"')
        self.assertContains(
            game,
            'item?.role === "red_riding_hoods" && hasAliveRole("hunters") && !isRoleBlocked("red_riding_hoods")',
        )
        self.assertContains(
            game,
            "!redHoodProtectionActive(wolfVictim)",
        )
        self.assertContains(game, "savedByProtector || savedByRedHood")
        self.assertContains(game, 't("red_hood_saved"')
        self.assertContains(game, "L.red_hood_protection_blocked")
        self.assertContains(game, 'class="day-effect-card passive-blocked"')

        setup = self.narrator.get(reverse("welcome"), {"mode": "new"})
        self.assertContains(setup, 'data-role="red_riding_hoods"')
        self.assertContains(setup, 'name="red_riding_hoods"')
        guide = Client().get(reverse("roles_guide"))
        self.assertContains(guide, "Chaperon Rouge")
        self.assertContains(guide, "Protection bloquée par le Loup Cerbère")

    def test_bear_uses_narrator_defined_circular_seating_order(self):
        self.composition.update({"bears": 1, "villagers": 5})
        self.create_room()
        game = self.narrator.get(reverse("game"))
        self.assertContains(game, "seatingOrderIds: []")
        self.assertContains(game, "function normalizedSeatingOrder()")
        self.assertContains(game, "function moveSeat(playerId, direction)")
        self.assertContains(game, 'class="bear-seating-setup"')
        self.assertContains(game, 'data-action="move-seat"')
        self.assertContains(
            game,
            "const seated = normalizedSeatingOrder().map(player).filter(item => item?.alive)",
        )
        self.assertContains(
            game,
            "seated[(index - 1 + seated.length) % seated.length]",
        )
        self.assertContains(
            game,
            "seated[(index + 1) % seated.length]",
        )
        self.assertContains(game, 't("bear_seating_loop"')

        guide = Client().get(reverse("roles_guide"))
        self.assertContains(guide, "narrateur classe les joueurs")
        self.assertContains(guide, "le dernier joueur est voisin du premier")

    def test_prostitute_visit_makes_pack_attack_miss_without_harming_visited_ancient(self):
        self.create_room()
        game = self.narrator.get(reverse("game"))
        self.assertContains(
            game,
            'if (target?.role === "prostitutes" && !isRoleBlocked("prostitutes") && state.prostituteTargetId) return null',
        )
        self.assertNotContains(
            game,
            'if (target?.role === "prostitutes" && !isRoleBlocked("prostitutes") && state.prostituteTargetId) return state.prostituteTargetId',
        )
        self.assertContains(game, "const actualWolfTargetId = effectiveWolfTargetId()")
        self.assertContains(
            game,
            'if (wolfVictimDies && wolfVictim?.role === "ancients" && !state.ancientWolfHits[wolfVictim.id])',
        )

        guide = Client().get(reverse("roles_guide"))
        self.assertContains(guide, "ni la Pute ni la personne visitée ne subissent")
        self.assertContains(guide, "Ancien visité ne perd donc aucune vie")

    def test_narrator_chooses_shepherd_starting_stock_after_distribution(self):
        self.composition.update({"shepherds": 1, "villagers": 5})
        self.create_room()
        game = self.narrator.get(reverse("game"))
        self.assertContains(game, 'id="shepherd-starting-stock"')
        self.assertContains(game, "L.shepherd_stock_title")
        self.assertContains(game, "Array.from({length: 10}")
        self.assertContains(game, "state.sheepInitialCount = stock")
        self.assertContains(game, "state.sheepRemaining = stock")
        self.assertContains(game, "state.shepherdStockConfigured = true")

        guide = Client().get(reverse("roles_guide"))
        self.assertContains(guide, "stock initial de un à dix moutons")

    def test_pyromaniac_douses_or_ignites_once_per_night_and_can_be_blocked(self):
        self.composition.update({"pyromaniacs": 1, "villagers": 5})
        self.create_room()
        game = self.narrator.get(reverse("game"))
        self.assertContains(game, 'pyromaniacs: { short: "PY"')
        self.assertContains(
            game,
            '"cerberus", "pyromaniac", "wolves"',
        )
        self.assertContains(game, "pyromaniacOiledIds: []")
        self.assertContains(game, 'action === "confirm-pyromaniac-douse"')
        self.assertContains(game, 'action === "confirm-pyromaniac-ignite"')
        self.assertContains(game, 'action === "finish-pyromaniac-blocked"')
        self.assertContains(game, 'isRoleBlocked("pyromaniacs")')
        self.assertContains(game, 'blocked ? "cerberus-blocked-action" : ""')
        self.assertContains(
            game,
            "state.pyromaniacOiledIds = [...new Set([...(state.pyromaniacOiledIds || []), ...selectedIds])]",
        )
        self.assertContains(game, "state.pyromaniacIgnitedIds = targetIds")
        self.assertContains(game, "state.pyromaniacOiledIds = []")
        self.assertContains(game, "(state.pyromaniacIgnitedIds || []).forEach")
        self.assertContains(game, 'return "pyromaniac"')
        self.assertContains(game, "L.pyromaniac_victory_help")

        setup = self.narrator.get(reverse("welcome"), {"mode": "new"})
        self.assertContains(setup, 'data-role="pyromaniacs"')
        self.assertContains(setup, 'name="pyromaniacs"')
        guide = Client().get(reverse("roles_guide"))
        self.assertContains(guide, "Pyromane")
        self.assertContains(guide, "exactement une action")
        self.assertContains(guide, "désactivés et rouges")

    def test_failed_infection_against_ancient_cancels_attack_without_consuming_a_life(self):
        self.create_room()
        game = self.narrator.get(reverse("game"))
        self.assertContains(
            game,
            'if (state.infectionAttempted && !isRoleBlocked("infecting_fathers")) return null',
        )
        self.assertContains(
            game,
            'if (!blocked) state.infectionAvailable = false',
        )
        self.assertContains(
            game,
            'if (wolfVictimDies && wolfVictim?.role === "ancients" && !state.ancientWolfHits[wolfVictim.id])',
        )
        self.assertContains(
            game,
            'if (target?.role === "ancients" && !state.ancientWolfHits?.[target.id]) return null',
        )
        self.assertContains(game, "const victim = wolfVictimVisibleToWitch()")
        self.assertContains(
            game,
            'const targets = alive().filter(item => item.id !== victim?.id && item.id !== witch?.id)',
        )

    def test_servant_infection_immunity_is_bypassed_by_cerberus_without_blocking_inheritance(self):
        self.create_room()
        game = self.narrator.get(reverse("game"))
        self.assertContains(
            game,
            'servants: { short: "SE", name: setup.role_labels.servants, faction: "village", description: setup.role_descriptions.servants, infectionImmune: true, infectionImmunityBlockable: true }',
        )
        self.assertContains(
            game,
            "const immunityBypassed = meta.infectionImmune && meta.infectionImmunityBlockable && isRoleBlocked(target.role)",
        )
        self.assertContains(
            game,
            'state.infectionSucceeded = !blocked && infectionCanSucceed(target?.id)',
        )
        self.assertContains(game, "if (state.infectionSucceeded) target.infected = true")
        self.assertContains(game, 'if (!blocked) state.infectionAvailable = false')
        self.assertContains(
            game,
            "state.lastVote && livingServant()",
        )
        self.assertNotContains(
            game,
            'livingServant() && !isRoleBlocked("servants")',
        )
        self.assertNotContains(game, 'isRoleBlocked("servants")) return')

        guide = Client().get(reverse("roles_guide"))
        self.assertContains(guide, "Normalement, la Servante est immunisée")
        self.assertContains(guide, "son immunité nocturne disparaît")
        self.assertContains(guide, "garde son choix")

    def test_alien_resists_pack_and_infection_but_dies_from_witch_poison(self):
        self.create_room()
        game = self.narrator.get(reverse("game"))
        self.assertContains(
            game,
            'aliens: { short: "AL", name: setup.role_labels.aliens, faction: "alien", description: setup.role_descriptions.aliens, infectionImmune: true, infectionImmunityBlockable: false }',
        )
        self.assertContains(
            game,
            'else if (wolfVictimDies && wolfVictim?.role !== "aliens")',
        )
        self.assertContains(
            game,
            'if (state.witchKillId && !isRoleBlocked("witches") && !deathIds.includes(state.witchKillId)) deathIds.push(state.witchKillId)',
        )

    def test_alien_can_signal_without_daily_limit_and_guess_multiple_players(self):
        self.create_room()
        game = self.narrator.get(reverse("game"))
        self.assertContains(
            game,
            "return Boolean(alien && state.alienSignalReady && contactReady)",
        )
        self.assertNotContains(
            game,
            "state.alienLastActionRound !== state.round && contactReady",
        )
        self.assertContains(game, 'class="alien-guess-row alien-player-guess"')
        self.assertContains(
            game,
            'const guesses = [...document.querySelectorAll(".alien-player-guess")]',
        )
        self.assertContains(
            game,
            "for (const guess of guesses)",
        )
        self.assertContains(
            game,
            "if (!result.correct) break",
        )
        self.assertContains(
            game,
            "state.alienLastGuessCorrect = state.alienLastGuessResults.every",
        )
        self.assertContains(
            game,
            "const guessDeaths = killPlayersWithLovers(guessDeathIds)",
        )
        self.assertContains(game, 'state.pendingHunterSource = "alien"')
        self.assertNotContains(game, 'document.getElementById("alien-target")')
        self.assertNotContains(game, 'document.getElementById("alien-role")')

        guide = Client().get(reverse("roles_guide"))
        self.assertContains(guide, "utiliser son signal sans limite")
        self.assertContains(guide, "autant de survivants non validés")
        self.assertContains(guide, "à la première erreur")
        self.assertContains(guide, "Les réponses sont vérifiées")
        self.assertContains(guide, "réponses suivantes sont ignorées")

    def test_night_wake_titles_include_the_players_names(self):
        self.create_room()
        game = self.narrator.get(reverse("game"))
        self.assertContains(game, 'class="wake-player-names"')
        self.assertContains(game, 'roleWakeTitle(L.judge_wake, "judges")')
        self.assertContains(game, 'roleWakeTitle(L.seer_wake, "seers")')
        self.assertContains(game, 'roleWakeTitle(L.witch_wake, "witches")')
        self.assertContains(game, 'wakeTitle(L.wolves_wake, wolves())')
        self.assertContains(game, 'wakeTitle(L.couple_wake, coupleMembers())')

    @override_settings(DEBUG=False)
    def test_production_mode_exposes_automatic_test_distribution_to_narrator(self):
        self.create_room()
        game = self.narrator.get(reverse("game"))
        self.assertContains(game, 'id="test-mode" type="application/json">true</script>')
        self.assertContains(game, '"auto-distribute-test"')

    def test_narrator_login_accepts_text_credentials_only(self):
        login_page = Client().get(reverse("home"))
        self.assertContains(login_page, "yessin / yessin")
        self.assertNotContains(login_page, 'inputmode="numeric"')

        old_credentials = Client()
        response = old_credentials.post(reverse("home"), {"username": "123", "password": "123"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("authenticated", old_credentials.session)

        text_credentials = Client()
        response = text_credentials.post(reverse("home"), {"username": "admin", "password": "admin"})
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        self.assertTrue(text_credentials.session["authenticated"])
        self.assertEqual(text_credentials.session["narrator_username"], "admin")

        private_credentials = Client()
        response = private_credentials.post(
            reverse("home"),
            {"username": "yessin", "password": "yessin"},
        )
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        self.assertTrue(private_credentials.session["authenticated"])
        self.assertEqual(private_credentials.session["narrator_username"], "yessin")

    def test_public_and_private_narrators_can_run_separate_rooms_at_the_same_time(self):
        public_narrator = Client()
        private_narrator = Client()
        public_narrator.post(reverse("home"), {"username": "admin", "password": "admin"})
        private_narrator.post(reverse("home"), {"username": "yessin", "password": "yessin"})

        setup = {"player_count": 8, **self.composition}
        public_response = public_narrator.post(reverse("welcome"), setup)
        private_response = private_narrator.post(reverse("welcome"), setup)

        self.assertRedirects(public_response, reverse("game"), fetch_redirect_response=False)
        self.assertRedirects(private_response, reverse("game"), fetch_redirect_response=False)
        public_code = public_narrator.session["game_setup"]["room_code"]
        private_code = private_narrator.session["game_setup"]["room_code"]
        self.assertNotEqual(public_code, private_code)
        self.assertEqual(GameRoom.objects.filter(code__in=[public_code, private_code]).count(), 2)
        self.assertEqual(public_narrator.session["narrator_username"], "admin")
        self.assertEqual(private_narrator.session["narrator_username"], "yessin")

    def test_tunisian_pages_omit_removed_intro_copy(self):
        visitor = Client()
        session = visitor.session
        session["language"] = "tn"
        session.save()
        self.assertNotContains(visitor.get(reverse("home")), "Od5ol lel game. Ra9eb. Chok. W ab9a 7ay.")
        self.assertNotContains(visitor.get(reverse("roles_guide")), "Pouvoirs, blocage mta3 Loup Cerbere")
        self.assertRedirects(visitor.get(reverse("room_history_list")), reverse("home"), fetch_redirect_response=False)

        session = self.narrator.session
        session["language"] = "tn"
        session.save()
        self.assertNotContains(self.narrator.get(reverse("welcome")), "E5tar action bech tetsarref")

    def test_player_joins_and_receives_role_after_narrator_starts(self):
        room = self.create_room()
        self.assertTrue(room.code.isdigit())
        self.assertEqual(len(room.code), 6)
        player = self.player_client("sarra")
        response = player.post(
            reverse("room_portal"),
            {"action": "join", "room_code": room.code.lower(), "player_name": "Sarra"},
        )
        self.assertRedirects(response, reverse("room_player", args=[room.code]), fetch_redirect_response=False)

        lobby = self.narrator.get(reverse("room_lobby_api", args=[room.code])).json()
        self.assertEqual(lobby["players"][0]["name"], "Sarra")

        started = self.narrator.post(reverse("room_start_api", args=[room.code])).json()
        self.assertEqual(len(started["assignments"]), 1)
        self.assertEqual(len(started["remaining_roles"]), 7)

        private_state = player.get(reverse("room_player_api", args=[room.code])).json()
        self.assertEqual(private_state["status"], GameRoom.Status.ACTIVE)
        self.assertIsNotNone(private_state["role"])

        assignment = started["assignments"][0]
        corrected_state = {
            "stage": "roles",
            "round": 1,
            "players": [{
                "id": 1,
                "roomPlayerId": assignment["room_player_id"],
                "name": assignment["name"],
                "role": "wild_children",
                "alive": True,
            }],
        }
        response = self.narrator.post(
            reverse("room_sync_api", args=[room.code]),
            json.dumps(corrected_state),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        private_state = player.get(reverse("room_player_api", args=[room.code])).json()
        self.assertEqual(private_state["role"]["code"], "wild_children")

    def test_player_rejoins_started_room_with_same_name_without_duplicate_registration(self):
        room = self.create_room()
        first_phone = self.player_client("yessin-player")
        first_phone.post(reverse("room_portal"), {"room_code": room.code, "player_name": "Yessin"})
        assigned = self.narrator.post(reverse("room_start_api", args=[room.code])).json()["assignments"][0]

        second_phone = self.player_client("yessin-player")
        response = second_phone.post(reverse("room_portal"), {"room_code": room.code, "player_name": "yEsSiN"})

        self.assertRedirects(response, reverse("room_player", args=[room.code]), fetch_redirect_response=False)
        private_state = second_phone.get(reverse("room_player_api", args=[room.code])).json()
        self.assertEqual(private_state["role"]["code"], assigned["role"])
        self.assertEqual(room.room_players.filter(name__iexact="Yessin").count(), 1)

    def test_manually_registered_player_can_connect_by_name_after_game_starts(self):
        room = self.create_room()
        self.narrator.post(reverse("room_start_api", args=[room.code]))
        state = {
            "stage": "roles",
            "round": 1,
            "players": [{"id": 1, "name": "Yessin", "role": "villagers", "alive": True}],
        }
        self.narrator.post(
            reverse("room_sync_api", args=[room.code]),
            json.dumps(state),
            content_type="application/json",
        )

        phone = self.player_client("yessin-manual")
        response = phone.post(reverse("room_portal"), {"room_code": room.code, "player_name": "Yessin"})

        self.assertRedirects(response, reverse("room_player", args=[room.code]), fetch_redirect_response=False)
        self.assertEqual(phone.get(reverse("room_player_api", args=[room.code])).json()["role"]["code"], "villagers")
        self.assertEqual(room.room_players.filter(name="Yessin").count(), 1)

    def test_narrator_can_reopen_lobby_and_redistribute_roles_to_phones(self):
        room = self.create_room()
        sarra = self.player_client("sarra")
        ali = self.player_client("ali")
        for client, name in ((sarra, "Sarra"), (ali, "Ali")):
            client.post(reverse("room_portal"), {"room_code": room.code, "player_name": name})

        self.narrator.post(reverse("room_start_api", args=[room.code]))
        sarra_player = room.room_players.get(name="Sarra")
        sarra_player.role = "seers"
        sarra_player.save(update_fields=["role"])
        self.assertEqual(sarra.get(reverse("room_player_api", args=[room.code])).json()["role"]["code"], "seers")

        new_composition = {role: 0 for role in ROLES["fr"]}
        new_composition.update({"simple_wolves": 1, "villagers": 8})
        ali_id = room.room_players.get(name="Ali").id
        response = self.narrator.post(
            reverse("room_reconfigure_api", args=[room.code]),
            json.dumps({"composition": new_composition, "removed_player_ids": [ali_id]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        room.refresh_from_db()
        self.assertEqual(room.status, GameRoom.Status.WAITING)
        self.assertEqual(room.player_count, 9)
        self.assertFalse(room.room_players.filter(name="Ali").exists())
        self.assertEqual(room.room_players.get(name="Sarra").role, "")
        waiting = sarra.get(reverse("room_player_api", args=[room.code])).json()
        self.assertEqual(waiting["status"], GameRoom.Status.WAITING)
        self.assertIsNone(waiting["role"])

        nour = self.player_client("nour-player")
        joined = nour.post(reverse("room_portal"), {"room_code": room.code, "player_name": "Nour"})
        self.assertRedirects(joined, reverse("room_player", args=[room.code]), fetch_redirect_response=False)
        redistributed = self.narrator.post(reverse("room_start_api", args=[room.code])).json()
        self.assertEqual(len(redistributed["assignments"]), 2)
        self.assertEqual(len(redistributed["remaining_roles"]), 7)
        new_private_role = sarra.get(reverse("room_player_api", args=[room.code])).json()["role"]["code"]
        self.assertIn(new_private_role, {"simple_wolves", "villagers"})
        self.assertNotEqual(new_private_role, "seers")

        game = self.narrator.get(reverse("game"))
        self.assertContains(game, "modify_distribution")
        self.assertContains(game, "/reconfigure/")
        self.assertContains(game, "redistribution-role-toggle")
        self.assertContains(game, "data-distribution-toggle-role")
        self.assertContains(game, 'input.type === "checkbox" ? Number(input.checked)')
        self.assertContains(game, "data-remove-local-player")

    def test_redistribution_keeps_unchecked_manual_players_and_reserves_their_places(self):
        room = self.create_room()
        sarra = self.player_client("sarra")
        sarra.post(reverse("room_portal"), {"room_code": room.code, "player_name": "Sarra"})
        self.narrator.post(reverse("room_start_api", args=[room.code]))
        composition = {role: 0 for role in ROLES["fr"]}
        composition.update({"simple_wolves": 1, "villagers": 7})

        response = self.narrator.post(
            reverse("room_reconfigure_api", args=[room.code]),
            json.dumps({"composition": composition, "removed_player_ids": [], "manual_players": ["Yessin"]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["manual_players"], ["Yessin"])
        lobby = self.narrator.get(reverse("room_lobby_api", args=[room.code])).json()
        self.assertEqual(lobby["manual_players"], ["Yessin"])
        redistributed = self.narrator.post(reverse("room_start_api", args=[room.code])).json()
        self.assertEqual(redistributed["manual_players"], ["Yessin"])
        self.assertEqual(len(redistributed["remaining_roles"]), 7)

    def test_night_and_day_history_are_created_once(self):
        room = self.create_room()
        self.narrator.post(reverse("room_start_api", args=[room.code]))
        state = {
            "stage": "dawn", "round": 1,
            "players": [
                {"id": 1, "name": "Ahmed", "role": "witches", "alive": False},
                {"id": 2, "name": "Sarra", "role": "villagers", "alive": True},
            ],
            "deaths": [1], "wolfTargetId": 1,
            "blockedPlayerId": 1, "witchSave": True, "witchKillId": 2,
            "bearGrowled": True,
            "shepherdLastResults": [
                {"targetId": 1, "returned": False},
                {"targetId": 2, "returned": True},
            ],
            "sheepRemaining": 2, "shepherdWasBlocked": False,
            "judgeFirstId": 1, "judgeSecondId": 2, "judgeSameClan": False,
            "seerTargetId": 2, "seerDisplayedRole": "villagers",
        }
        sync_url = reverse("room_sync_api", args=[room.code])
        self.narrator.post(sync_url, json.dumps(state), content_type="application/json")
        self.narrator.post(sync_url, json.dumps(state), content_type="application/json")
        state.update({
            "stage": "day_end", "lastVote": 1, "voteDeathIds": [1, 2], "voteOutcome": "eliminated",
            "voteBreakdown": {
                "normal": [{"targetId": 1, "votes": 3}],
                "cancelled": [{"voterId": 1, "reason": "silenced"}],
                "secret": [{"voterId": 1, "targetId": 2}],
                "totals": [{"id": 1, "votes": 1}, {"id": 2, "votes": 1}],
            },
        })
        self.narrator.post(sync_url, json.dumps(state), content_type="application/json")

        self.assertEqual(RoomEvent.objects.filter(room=room).count(), 2)
        self.assertEqual(Client().get(reverse("room_history_api", args=[room.code])).status_code, 403)
        self.assertEqual(Client().get(reverse("room_history", args=[room.code])).status_code, 403)
        history = self.narrator.get(reverse("room_history_api", args=[room.code])).json()
        self.assertEqual([event["type"] for event in history["events"]], ["night", "day"])
        night = history["events"][0]["details"]
        self.assertTrue(night["bear_growled"])
        self.assertEqual(night["sheep_lost"], ["Ahmed"])
        self.assertEqual(night["sheep_returned"], ["Sarra"])
        self.assertEqual(night["sheep_remaining"], 2)
        self.assertFalse(night["shepherd_blocked"])
        self.assertFalse(night["witch_saved"])
        self.assertIsNone(night["witch_target"])
        self.assertEqual(night["judge_first"], "Ahmed")
        self.assertEqual(night["judge_second"], "Sarra")
        self.assertFalse(night["judge_same_clan"])
        self.assertEqual(night["seer_target"], "Sarra")
        self.assertEqual(night["seer_role"], "villagers")
        day = history["events"][1]["details"]
        self.assertEqual(day["vote_deaths"], ["Ahmed", "Sarra"])
        self.assertEqual(day["normal_votes"], ["Ahmed: 3"])
        self.assertEqual(day["cancelled_votes"], ["Ahmed"])
        self.assertEqual(day["secret_votes"], ["Ahmed → Sarra"])
        self.assertEqual(day["final_totals"], ["Ahmed: 1", "Sarra: 1"])

        self.assertRedirects(Client().get(reverse("room_history_list")), reverse("home"), fetch_redirect_response=False)

        state.update({"stage": "game_over", "winner": "village"})
        self.narrator.post(sync_url, json.dumps(state), content_type="application/json")
        self.assertEqual(Client().get(reverse("room_history_api", args=[room.code])).status_code, 403)
        self.assertEqual(Client().get(reverse("room_history", args=[room.code])).status_code, 403)

    def test_setup_rejects_duplicate_special_roles_and_all_wolves(self):
        duplicate_seer = {**self.composition, "seers": 2, "villagers": 4}
        response = self.narrator.post(reverse("welcome"), {"player_count": 8, **duplicate_seer})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "limité à un seul joueur")
        self.assertEqual(GameRoom.objects.count(), 0)

        all_wolves = {role: 0 for role in ROLES["fr"]}
        all_wolves["simple_wolves"] = 8
        response = self.narrator.post(reverse("welcome"), {"player_count": 8, **all_wolves})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ajoute au moins un joueur")
        self.assertEqual(GameRoom.objects.count(), 0)

    def test_narrator_undo_restores_active_state_and_corrects_history(self):
        room = self.create_room()
        self.narrator.post(reverse("room_start_api", args=[room.code]))
        sync_url = reverse("room_sync_api", args=[room.code])
        dawn = {
            "stage": "dawn",
            "round": 1,
            "players": [
                {"id": 1, "name": "Ahmed", "alive": True},
                {"id": 2, "name": "Sarra", "alive": True},
            ],
            "deaths": [],
            "wolfTargetId": 1,
        }
        self.narrator.post(sync_url, json.dumps(dawn), content_type="application/json")
        self.assertTrue(RoomEvent.objects.filter(room=room, marker="night-1").exists())

        before_dawn = {**dawn, "stage": "seer", "wolfTargetId": 2}
        response = self.narrator.post(
            sync_url,
            json.dumps(before_dawn),
            content_type="application/json",
            HTTP_X_GAME_UNDO="1",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(RoomEvent.objects.filter(room=room, marker="night-1").exists())

        corrected_dawn = {**before_dawn, "stage": "dawn"}
        self.narrator.post(sync_url, json.dumps(corrected_dawn), content_type="application/json")
        event = RoomEvent.objects.get(room=room, marker="night-1")
        self.assertEqual(event.details["wolves_target"], "Sarra")

        day_end = {**corrected_dawn, "stage": "day_end", "lastVote": 1, "voteOutcome": "eliminated"}
        self.narrator.post(sync_url, json.dumps(day_end), content_type="application/json")
        self.assertTrue(RoomEvent.objects.filter(room=room, marker="day-1").exists())
        before_verdict = {**day_end, "stage": "final_vote", "lastVote": None, "voteOutcome": None}
        self.narrator.post(
            sync_url,
            json.dumps(before_verdict),
            content_type="application/json",
            HTTP_X_GAME_UNDO="1",
        )
        self.assertFalse(RoomEvent.objects.filter(room=room, marker="day-1").exists())

        self.narrator.post(sync_url, json.dumps({**before_verdict, "stage": "game_over"}), content_type="application/json")
        room.refresh_from_db()
        self.assertEqual(room.status, GameRoom.Status.FINISHED)
        self.narrator.post(
            sync_url,
            json.dumps(before_verdict),
            content_type="application/json",
            HTTP_X_GAME_UNDO="1",
        )
        room.refresh_from_db()
        self.assertEqual(room.status, GameRoom.Status.ACTIVE)

    def test_first_night_is_recorded_before_first_day(self):
        room = self.create_room()
        self.narrator.post(reverse("room_start_api", args=[room.code]))
        sync_url = reverse("room_sync_api", args=[room.code])
        players = [{"id": 1, "name": "Ahmed", "alive": True}, {"id": 2, "name": "Sarra", "alive": True}]
        self.narrator.post(sync_url, json.dumps({"stage": "dawn", "round": 1, "players": players, "deaths": []}), content_type="application/json")
        self.narrator.post(sync_url, json.dumps({"stage": "day_end", "round": 1, "players": players, "voteOutcome": "skipped"}), content_type="application/json")
        self.assertTrue(RoomEvent.objects.filter(room=room, marker="night-1").exists())
        self.assertTrue(RoomEvent.objects.filter(room=room, marker="day-1").exists())
        self.assertEqual(
            list(RoomEvent.objects.filter(room=room).values_list("event_type", flat=True)),
            ["night", "day"],
        )

    def test_admin_history_lists_and_resumes_active_games(self):
        room = self.create_room()
        self.narrator.post(reverse("room_start_api", args=[room.code]))

        visitor = Client()
        guest_history = visitor.get(reverse("room_history_list"))
        self.assertRedirects(guest_history, reverse("home"), fetch_redirect_response=False)
        self.assertEqual(visitor.get(reverse("room_history", args=[room.code])).status_code, 403)
        self.assertEqual(visitor.get(reverse("room_history_api", args=[room.code])).status_code, 403)

        returning_admin = Client()
        returning_admin.post(reverse("home"), {"username": "admin", "password": "admin"})
        history_list = returning_admin.get(reverse("room_history_list"))
        self.assertContains(history_list, room.code)
        self.assertContains(history_list, 'class="history-continue-button"')
        self.assertContains(history_list, 'class="history-finish-button"')
        self.assertContains(history_list, 'class="history-delete-button"')
        self.assertContains(history_list, f'name="room_code" value="{room.code}"')
        self.assertEqual(returning_admin.get(reverse("room_history", args=[room.code])).status_code, 200)

        response = returning_admin.post(
            reverse("welcome"),
            {"action": "resume", "room_code": room.code},
        )
        self.assertRedirects(response, reverse("game"), fetch_redirect_response=False)

    def test_admin_can_finish_then_delete_an_active_game_without_events(self):
        room = self.create_room()
        self.narrator.post(reverse("room_start_api", args=[room.code]))
        finish_url = reverse("room_history_finish", args=[room.code])

        self.assertEqual(Client().post(finish_url).status_code, 403)
        response = self.narrator.post(finish_url)
        self.assertRedirects(response, reverse("room_history_list"), fetch_redirect_response=False)

        room.refresh_from_db()
        self.assertEqual(room.status, GameRoom.Status.FINISHED)
        archive = self.narrator.get(reverse("room_history_list"))
        self.assertContains(archive, room.code)
        self.assertContains(archive, reverse("room_history_delete", args=[room.code]))
        self.assertNotContains(archive, finish_url)

    def test_authenticated_narrator_can_delete_an_active_game_directly(self):
        room = self.create_room()
        self.narrator.post(reverse("room_start_api", args=[room.code]))
        delete_url = reverse("room_history_delete", args=[room.code])

        self.assertEqual(Client().post(delete_url).status_code, 403)
        response = self.narrator.post(delete_url)

        self.assertRedirects(response, reverse("room_history_list"), fetch_redirect_response=False)
        self.assertFalse(GameRoom.objects.filter(code=room.code).exists())

    def test_room_join_rejects_non_numeric_code(self):
        response = self.player_client("sarra-invalid").post(
            reverse("room_portal"),
            {"action": "join", "room_code": "ABC123", "player_name": "Sarra"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "exactement 6 chiffres")

    def test_home_opens_general_room_join_form(self):
        home = Client().get(reverse("home"))
        self.assertNotContains(home, f'href="{reverse("room_portal")}"')
        portal = self.narrator.get(reverse("room_portal"))
        self.assertEqual(portal.status_code, 200)
        self.assertContains(portal, 'name="room_code"')
        self.assertContains(portal, 'name="player_name"')
        self.assertContains(portal, reverse("general_room_qr"))

    def test_narrator_can_resume_active_room_from_another_session(self):
        room = self.create_room()
        self.narrator.post(reverse("room_start_api", args=[room.code]))
        saved_state = {
            "stage": "seer", "round": 2, "roomStarted": True,
            "players": [{"id": 1, "name": "Sarra", "role": "seers", "alive": True}],
        }
        self.narrator.post(
            reverse("room_sync_api", args=[room.code]),
            json.dumps(saved_state),
            content_type="application/json",
        )

        returning_narrator = Client()
        returning_narrator.post(reverse("home"), {"username": "admin", "password": "admin"})
        response = returning_narrator.post(
            reverse("welcome"),
            {"action": "resume", "room_code": room.code},
        )
        self.assertRedirects(response, reverse("game"), fetch_redirect_response=False)
        self.assertEqual(returning_narrator.session["game_setup"]["room_code"], room.code)

        game = returning_narrator.get(reverse("game"))
        self.assertContains(game, '"stage": "seer"')
        self.assertContains(game, 'id="resume-requested" type="application/json">true</script>')
        self.assertNotIn("resume_from_server", returning_narrator.session)

    def test_narrator_can_resume_finished_room_and_continue(self):
        room = self.create_room()
        self.narrator.post(reverse("room_start_api", args=[room.code]))
        self.narrator.post(
            reverse("room_sync_api", args=[room.code]),
            json.dumps({"stage": "game_over", "round": 2, "players": [], "winner": "village"}),
            content_type="application/json",
        )

        returning_narrator = Client()
        returning_narrator.post(reverse("home"), {"username": "admin", "password": "admin"})
        response = returning_narrator.post(
            reverse("welcome"),
            {"action": "resume", "room_code": room.code},
        )
        self.assertRedirects(response, reverse("game"), fetch_redirect_response=False)
        self.assertEqual(returning_narrator.session["game_setup"]["room_code"], room.code)

        game = returning_narrator.get(reverse("game"))
        self.assertContains(game, '"stage": "game_over"')
        self.assertContains(game, 'id="resume-requested" type="application/json">true</script>')
        self.assertContains(game, 'actionButton(L.continue_game, "continue-game")')
        self.assertContains(game, 'id="wolf-target"')
        self.assertNotContains(game, 'id="wolf-change-target"')
        self.assertContains(game, "wolvesHaveTarget()")

        continued_state = {
            "stage": "day_end",
            "round": 2,
            "players": [{"id": 1, "name": "Loup final", "role": "simple_wolves", "alive": True}],
            "winner": None,
        }
        response = returning_narrator.post(
            reverse("room_sync_api", args=[room.code]),
            json.dumps(continued_state),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        room.refresh_from_db()
        self.assertEqual(room.status, GameRoom.Status.ACTIVE)
        self.assertEqual(room.game_state["stage"], "day_end")

    def test_only_authenticated_admin_can_delete_finished_history(self):
        room = self.create_room()
        self.narrator.post(reverse("room_start_api", args=[room.code]))
        sync_url = reverse("room_sync_api", args=[room.code])
        self.narrator.post(
            sync_url,
            json.dumps({"stage": "dawn", "round": 1, "players": [], "deaths": []}),
            content_type="application/json",
        )
        self.narrator.post(
            sync_url,
            json.dumps({"stage": "game_over", "round": 1, "players": [], "winner": "village"}),
            content_type="application/json",
        )
        delete_url = reverse("room_history_delete", args=[room.code])

        visitor = Client()
        self.assertRedirects(visitor.get(reverse("room_history_list")), reverse("home"), fetch_redirect_response=False)
        self.assertEqual(visitor.post(delete_url).status_code, 403)
        self.assertTrue(GameRoom.objects.filter(code=room.code).exists())

        archive = self.narrator.get(reverse("room_history_list"))
        self.assertContains(archive, delete_url)
        response = self.narrator.post(delete_url)
        self.assertRedirects(response, reverse("room_history_list"), fetch_redirect_response=False)
        self.assertFalse(GameRoom.objects.filter(code=room.code).exists())

    def test_qr_code_contains_prefilled_room_link(self):
        room = self.create_room()
        response = Client(HTTP_HOST="testserver").get(reverse("room_qr", args=[room.code]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/svg+xml")
        self.assertIn(b"<svg", response.content)
        self.assertEqual(Client().head(reverse("room_qr", args=[room.code])).status_code, 200)

        portal = self.player_client("qr-player").get(reverse("room_portal"), {"code": room.code})
        self.assertContains(portal, f'value="{room.code}"')

    def test_general_qr_code_opens_unprefilled_room_portal(self):
        response = Client(HTTP_HOST="testserver").get(reverse("general_room_qr"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/svg+xml")
        self.assertIn(b"<svg", response.content)
        self.assertIn("max-age=31536000", response["Cache-Control"])
        self.assertEqual(Client().head(reverse("general_room_qr")).status_code, 200)

    @patch.dict("os.environ", {"ADMIN_USERNAME": "admin", "ADMIN_PASSWORD": "safe-test-password"})
    def test_admin_is_created_as_superuser(self):
        from django.contrib.auth import get_user_model
        from django.core.management import call_command

        call_command("ensure_admin")
        admin = get_user_model().objects.get(username="admin")
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.check_password("safe-test-password"))


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class PwaTests(TestCase):
    def test_manifest_and_service_worker_are_available_at_root_scope(self):
        manifest = self.client.get(reverse("pwa_manifest"))
        self.assertEqual(manifest.status_code, 200)
        self.assertEqual(manifest["Content-Type"], "application/manifest+json")
        self.assertEqual(manifest.json()["display"], "standalone")
        self.assertEqual(manifest.json()["scope"], "/")

        worker = self.client.get(reverse("service_worker"))
        self.assertEqual(worker.status_code, 200)
        self.assertEqual(worker["Service-Worker-Allowed"], "/")
        self.assertContains(worker, "loup-garou-shell-v9")

        home = self.client.get(reverse("home"))
        self.assertContains(home, reverse("pwa_manifest"))
        self.assertContains(home, "apple-mobile-web-app-capable")
