import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.utils import OperationalError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import GameRoom, RoomEvent
from .role_guides import ROLE_GUIDES
from .translations import ROLES
from .views import WOLF_ROLE_KEYS, shuffle_roles_for_players


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class RoomFlowTests(TestCase):
    def setUp(self):
        self.narrator = Client()
        self.narrator.post(reverse("home"), {"username": "yessin", "password": "yessin"})
        self.narrator.post(reverse("set_language"), {"language": "fr", "next": reverse("welcome")})
        self.composition = {role: 0 for role in ROLES["fr"]}
        self.composition.update({"simple_wolves": 2, "villagers": 6})

    def player_client(self, username):
        user, created = get_user_model().objects.get_or_create(username=username)
        if created:
            user.set_password("test-password")
            user.save(update_fields=["password"])
        client = Client()
        client.force_login(user)
        client.post(reverse("set_language"), {"language": "fr", "next": reverse("room_portal")})
        return client

    def visitor_client(self, language="fr"):
        client = Client()
        client.post(reverse("set_language"), {"language": language, "next": reverse("home")})
        return client

    def create_room(self):
        response = self.narrator.post(
            reverse("welcome"),
            {"player_count": 8, **self.composition},
        )
        self.assertRedirects(response, reverse("game"), fetch_redirect_response=False)
        return GameRoom.objects.get(code=self.narrator.session["game_setup"]["room_code"])

    def test_csrf_token_can_be_refreshed_and_used_by_long_lived_pages(self):
        client = Client(enforce_csrf_checks=True)
        refreshed = client.get(reverse("csrf_token_api"))
        self.assertEqual(refreshed.status_code, 200)
        self.assertIn("csrftoken", refreshed.cookies)
        fresh_token = refreshed.json()["csrfToken"]

        rejected = Client(enforce_csrf_checks=True).post(
            reverse("set_language"),
            {"language": "fr", "next": reverse("home")},
        )
        self.assertEqual(rejected.status_code, 403)
        accepted = client.post(
            reverse("set_language"),
            {"language": "fr", "next": reverse("home")},
            HTTP_X_CSRFTOKEN=fresh_token,
        )
        self.assertEqual(accepted.status_code, 302)

        home = client.get(reverse("home"))
        self.assertContains(home, "latestCsrfCookie")
        self.assertContains(home, 'input[name="csrfmiddlewaretoken"]')

    def test_marmour_has_a_ninety_percent_wolf_distribution_bias(self):
        roles = ["villagers", "cerberus_wolves", "seers"]
        random_source = Mock()
        random_source.random.return_value = 0.89
        random_source.choice.side_effect = lambda indexes: indexes[0]

        shuffle_roles_for_players(
            roles,
            [("Display name", "MaRmOuR"), ("Sarra",), ("Ali",)],
            random_source,
        )

        self.assertIn(roles[0], WOLF_ROLE_KEYS)
        random_source.shuffle.assert_called_once_with(roles)

    def test_marmour_gets_a_non_wolf_role_on_the_ten_percent_branch(self):
        roles = ["black_wolves", "villagers", "seers"]
        random_source = Mock()
        random_source.random.return_value = 0.9
        random_source.choice.side_effect = lambda indexes: indexes[-1]

        shuffle_roles_for_players(
            roles,
            [("MARMOUR",), ("Sarra",), ("Ali",)],
            random_source,
        )

        self.assertNotIn(roles[0], WOLF_ROLE_KEYS)

    def test_distribution_stays_fully_random_when_marmour_is_absent(self):
        roles = ["simple_wolves", "villagers"]
        random_source = Mock()

        shuffle_roles_for_players(roles, [("Sarra",), ("Ali",)], random_source)

        random_source.shuffle.assert_called_once_with(roles)
        random_source.random.assert_not_called()
        random_source.choice.assert_not_called()

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
        self.assertNotContains(new_game, 'class="players-row"')
        self.assertContains(new_game, 'id="player-count" name="player_count" type="hidden" value="0"')
        self.assertNotContains(new_game, 'id="suggest-button"')
        self.assertNotContains(new_game, "function suggestRoles()")
        self.assertNotContains(new_game, 'max="1" value="1"')
        self.assertNotContains(new_game, 'name="simple_wolves" type="number" min="0" value="1"')
        self.assertNotContains(new_game, 'name="villagers" type="number" min="0" value="5"')
        self.assertContains(new_game, "prepareSingletonRoleToggles()")
        self.assertContains(new_game, '["simple_wolves", "villagers"]')
        self.assertContains(new_game, "playerInput.value = assigned")
        self.assertContains(new_game, "const validCount = assigned >= 8 && assigned <= 30")
        self.assertNotContains(new_game, 'id="target-count"')

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
            'if (stage === "wild_child") return hasActiveAliveRole("wild_children") && !state.wildChildLinked',
        )
        self.assertContains(game, "function villagePowerLost(item)")
        self.assertContains(
            game,
            'const affected = state.players.filter(item => roleMeta[item.role]?.faction === "village" && item.role !== "villagers")',
        )
        self.assertNotContains(game, 'affected.forEach(item => { item.role = "villagers"; })')
        self.assertContains(game, 'item.role === "hunters" && !villagePowerLost(item)')
        self.assertContains(game, 'hasActiveAliveRole("witches")')
        self.assertNotContains(
            game,
            'player(state.witchKillId)?.role === "ancients") removeVillagePowersAfterAncientVote()',
        )
        self.assertEqual(game.content.decode().count("state.lostVillagePowerIds = [];"), 1)
        self.assertContains(
            game,
            '"protector", "prostitute", "cerberus", "pyromaniac", "wolves", "infection"',
        )
        self.assertContains(game, 'class="bilan-section night-death-section"')
        self.assertContains(game, 'const nightOutIds = [...new Set([...state.deaths, ...hunterOutIds])]')
        self.assertContains(game, 'const pendingNightHunter = state.pendingHunterSource === "night" && player(state.pendingHunterId)')
        self.assertContains(game, 'actionButton(L.hunter_last_shot, "begin-night-hunter-shot")')
        self.assertContains(game, 'action === "begin-night-hunter-shot"')
        self.assertContains(
            game,
            'state.pendingHunterSource = "night";\n          state.winner = null;\n          publishAliveRoleCounts();\n          state.stage = "dawn";',
        )
        self.assertContains(game, 'state.alienDeathIds = [...new Set([...(state.alienDeathIds || []), ...guessDeaths.map(item => item.id)])]')
        self.assertContains(game, 'cause === "hunter" ? "died_due_to_hunter_player_role"')
        self.assertContains(game, 'cause === "barber" ? "died_due_to_barber_player_role"')
        self.assertContains(game, 'cause === "alien" ? "died_due_to_alien_player_role"')
        self.assertContains(game, 'state.barberDeathIds = [...new Set([...(state.barberDeathIds || []), ...barberDeaths.map(item => item.id)])]')
        self.assertContains(game, 'class="bilan-section night-death-section day-death-section"')
        self.assertContains(game, "function dayDeathBilan(includeVote = false)")
        self.assertContains(game, "function renderLiveDayDeathBilan()")
        self.assertContains(game, "if (liveDayDeathStages.includes(state.stage)) renderLiveDayDeathBilan()")
        self.assertContains(game, "...(includeVote ? state.voteDeathIds || [] : [])")
        self.assertContains(game, '"died_during_day_player_role"')
        self.assertContains(game, 'state.hunterCausedDeathIds = [...new Set([...(state.hunterCausedDeathIds || []), ...hunterDeaths.map(item => item.id)])]')
        self.assertContains(game, 'class="witch-night-result ${nightVictim ? "danger" : "safe"}"')
        self.assertContains(game, 'nightVictim ? escapeHtml(nightVictim.name) : L.witch_nobody_died')
        self.assertContains(game, 'victim && !savedByProtector && !savedByRedHood ? victim : null')
        self.assertContains(game, 'class="bilan-section village-info-section"')
        self.assertContains(game, 'class="bilan-section day-instruction-section"')
        self.assertContains(game, 't(deathLabel, {name: escapeHtml(victim.name), role: escapeHtml(roleMeta[victim.role].name)})')
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
            'item?.role === "red_riding_hoods" && !villagePowerLost(item) && hasActiveAliveRole("hunters") && !isRoleBlocked("red_riding_hoods")',
        )
        self.assertContains(
            game,
            "!redHoodProtectionActive(wolfVictim)",
        )
        self.assertContains(game, "savedByProtector || savedByRedHood")
        self.assertContains(game, 'savedByRedHood ? L.witch_nobody_died')
        self.assertContains(game, "L.red_hood_protection_blocked")
        self.assertContains(game, 'class="day-effect-card passive-blocked"')

        setup = self.narrator.get(reverse("welcome"), {"mode": "new"})
        self.assertContains(setup, 'data-role="red_riding_hoods"')
        self.assertContains(setup, 'name="red_riding_hoods"')
        guide = self.visitor_client().get(reverse("roles_guide"))
        self.assertContains(guide, "Chaperon Rouge")
        self.assertContains(guide, "Protection bloquée par le Loup Cerbère")

    def test_cerberus_cannot_block_the_same_player_on_consecutive_nights(self):
        self.composition.update({"cerberus_wolves": 1, "villagers": 5})
        self.create_room()
        game = self.narrator.get(reverse("game"))
        self.assertContains(game, "lastBlockedPlayerId: null")
        self.assertContains(
            game,
            'item.role !== "cerberus_wolves" && item.id !== state.lastBlockedPlayerId',
        )
        self.assertContains(game, "targetId === state.lastBlockedPlayerId")
        self.assertContains(game, "state.lastBlockedPlayerId = targetId")
        self.assertContains(game, "L.cerberus_no_repeat")

    def test_talkative_wolf_cannot_target_the_same_player_on_consecutive_nights(self):
        self.composition.update({"talkative_wolves": 1, "villagers": 5})
        self.create_room()
        game = self.narrator.get(reverse("game"))
        self.assertContains(game, "lastTalkativePlayerId: null")
        self.assertContains(
            game,
            'item.id !== state.lastTalkativePlayerId',
        )
        self.assertContains(game, "targetId === state.lastTalkativePlayerId")
        self.assertContains(game, "state.lastTalkativePlayerId = targetId")
        self.assertContains(game, "L.talkative_no_repeat")

    def test_bear_uses_narrator_defined_circular_seating_order(self):
        self.composition.update({"bears": 1, "villagers": 5})
        self.create_room()
        game = self.narrator.get(reverse("game"))
        self.assertContains(
            game,
            'if (stage === "bear") return state.round === 1 && hasActiveAliveRole("bears");',
        )
        self.assertContains(
            game,
            'if (next === "bear" && (state.round !== 1 || !hasActiveAliveRole("bears")))',
        )
        self.assertContains(game, "seatingOrderIds: []")
        self.assertContains(game, "function normalizedSeatingOrder()")
        self.assertContains(game, "function moveSeat(playerId, direction)")
        self.assertContains(game, 'class="bear-seating-setup"')
        self.assertContains(game, 'data-action="move-seat"')
        self.assertContains(game, 'id="bear-infected-growl"')
        self.assertContains(game, 'id="bear-calculation-timing"')
        self.assertContains(game, "state.bearGrowlsWhenInfected = bearInfectedGrowlSelect.value === \"yes\"")
        self.assertContains(game, "const infectedBearGrowls = bear.infected && state.bearGrowlsWhenInfected")
        self.assertContains(game, 'if (state.bearCalculationTiming === "nightfall") captureBearStatus()')
        self.assertContains(game, 'if (state.bearCalculationTiming === "after_powers") captureBearStatus()')
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

        guide = self.visitor_client().get(reverse("roles_guide"))
        self.assertContains(guide, "narrateur classe les joueurs")
        self.assertContains(guide, "le dernier joueur est voisin du premier")

    def test_prostitute_redirects_pack_attack_unless_cerberus_blocks_her(self):
        self.create_room()
        game = self.narrator.get(reverse("game"))
        self.assertContains(
            game,
            'if (target?.role === "prostitutes" && !villagePowerLost(target) && !isRoleBlocked("prostitutes") && state.prostituteTargetId) return state.prostituteTargetId',
        )
        self.assertContains(game, "const actualWolfTargetId = effectiveWolfTargetId()")
        self.assertContains(
            game,
            'if (wolfVictimDies && wolfVictim?.role === "ancients" && !villagePowerLost(wolfVictim) && !state.ancientWolfHits[wolfVictim.id])',
        )

        guide = self.visitor_client().get(reverse("roles_guide"))
        self.assertContains(guide, "son attaque est redirigée vers la personne visitée")
        self.assertContains(guide, "la Pute reste la cible et peut être tuée ou infectée")

    def test_day_is_persisted_before_normal_or_forced_night_transition(self):
        self.create_room()
        game = self.narrator.get(reverse("game"))
        self.assertContains(game, "async function persistDayBeforeNight(forced = false)")
        self.assertContains(game, 'snapshot.stage = "day_end"')
        self.assertContains(game, 'snapshot.voteOutcome = "forced_transition"')
        self.assertContains(game, 'await persistDayBeforeNight(state.stage !== "day_end")')
        self.assertContains(game, "await persistDayBeforeNight()")
        self.assertContains(game, "if (!response.ok) throw new Error")
        self.assertContains(game, "L.day_sync_failed")

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

        guide = self.visitor_client().get(reverse("roles_guide"))
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
        guide = self.visitor_client().get(reverse("roles_guide"))
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
            'if (wolfVictimDies && wolfVictim?.role === "ancients" && !villagePowerLost(wolfVictim) && !state.ancientWolfHits[wolfVictim.id])',
        )
        self.assertContains(
            game,
            'if (target?.role === "ancients" && !villagePowerLost(target) && !state.ancientWolfHits?.[target.id]) return null',
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

        guide = self.visitor_client().get(reverse("roles_guide"))
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
            'if (witch && !villagePowerLost(witch) && state.witchKillId && !isRoleBlocked("witches") && !deathIds.includes(state.witchKillId)) deathIds.push(state.witchKillId)',
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

        guide = self.visitor_client().get(reverse("roles_guide"))
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
        self.assertNotContains(login_page, "yessin / yessin")
        self.assertNotContains(login_page, 'inputmode="numeric"')

        old_credentials = Client()
        response = old_credentials.post(reverse("home"), {"username": "123", "password": "123"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("authenticated", old_credentials.session)

        removed_admin = Client()
        response = removed_admin.post(reverse("home"), {"username": "admin", "password": "admin"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("authenticated", removed_admin.session)

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
        second_narrator = get_user_model().objects.create_user("narrateur-test", password="test-password")
        second_narrator.groups.add(Group.objects.get_or_create(name="narrators")[0])
        public_narrator.force_login(second_narrator)
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
        self.assertEqual(public_narrator.session.get("narrator_username"), None)
        self.assertEqual(private_narrator.session["narrator_username"], "yessin")

    def test_tunisian_pages_omit_removed_intro_copy(self):
        visitor = self.visitor_client("tn")
        self.assertNotContains(visitor.get(reverse("home")), "Od5ol lel game. Ra9eb. Chok. W ab9a 7ay.")
        self.assertNotContains(visitor.get(reverse("roles_guide")), "Pouvoirs, blocage mta3 Loup Cerbere")
        self.assertRedirects(visitor.get(reverse("room_history_list")), reverse("home"), fetch_redirect_response=False)

        self.narrator.post(reverse("set_language"), {"language": "tn", "next": reverse("welcome")})
        self.assertNotContains(self.narrator.get(reverse("welcome")), "E5tar action bech tetsarref")

    def test_tounsi_is_default_and_each_session_can_choose_all_three_languages(self):
        visitor = Client()
        default_page = visitor.get(reverse("home"))
        self.assertContains(default_page, 'option value="tn" selected')
        self.assertContains(default_page, "Connecti")
        self.assertContains(default_page, "Français")
        self.assertContains(default_page, "English")
        self.assertContains(default_page, "Tounsi")

        visitor.post(reverse("set_language"), {"language": "en", "next": reverse("home")})
        self.assertContains(visitor.get(reverse("home")), 'option value="en" selected')
        self.assertContains(visitor.get(reverse("home")), "Sign in")

        visitor.post(reverse("set_language"), {"language": "fr", "next": reverse("home")})
        self.assertContains(visitor.get(reverse("home")), 'option value="fr" selected')
        self.assertContains(visitor.get(reverse("home")), "Se connecter")

    def test_player_joins_and_receives_role_after_narrator_starts(self):
        room = self.create_room()
        self.assertTrue(room.code.isdigit())
        self.assertEqual(len(room.code), 6)
        player = self.player_client("Sarra")
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
        self.assertEqual(
            private_state["role"]["rules"],
            list(ROLE_GUIDES["fr"][private_state["role"]["code"]]),
        )
        self.assertEqual(private_state["alive_count"], 8)
        self.assertEqual(
            {item["code"]: item["count"] for item in private_state["alive_roles"]},
            {"simple_wolves": 2, "villagers": 6},
        )

        player_page = player.get(reverse("room_player", args=[room.code]))
        self.assertContains(player_page, 'id="alive-role-list"')
        self.assertContains(player_page, "renderRoleRoster")
        self.assertContains(player_page, 'id="dead-role-count"')
        self.assertContains(player_page, 'role.alive ? "alive" : "dead"')
        self.assertContains(player_page, 'id="toggle-private-role"')
        self.assertContains(player_page, "togglePrivateRole")
        self.assertContains(player_page, 'id="toggle-role-guide"')
        self.assertContains(player_page, 'aria-expanded="false"')
        self.assertContains(player_page, "toggleRoleGuide")
        self.assertContains(player_page, "Voir les pouvoirs et les cas particuliers")
        self.assertContains(player_page, 'id="private-player-name"')
        self.assertContains(player_page, 'class="language-selector"')
        self.assertContains(player_page, 'id="player-role-rules"')
        self.assertContains(player_page, "Règles et cas particuliers")
        self.assertContains(player_page, "role.rules || []")
        self.assertContains(player_page, "Masquer mon rôle")
        self.assertContains(player_page, "Afficher mon rôle")
        self.assertNotContains(player_page, "Garde cet écran secret")
        self.assertContains(player_page, 'if (data.status !== "finished") scheduleRoom()')

        role_code = private_state["role"]["code"]
        player.post(
            reverse("set_language"),
            {"language": "tn", "next": reverse("room_player", args=[room.code])},
        )
        tunisian_state = player.get(reverse("room_player_api", args=[room.code])).json()
        self.assertEqual(tunisian_state["role"]["code"], role_code)
        self.assertEqual(tunisian_state["role"]["rules"], list(ROLE_GUIDES["tn"][role_code]))
        self.assertTrue(any("Cerbere" in rule for rule in tunisian_state["role"]["rules"]))
        tunisian_page = player.get(reverse("room_player", args=[room.code]))
        self.assertContains(tunisian_page, 'option value="tn" selected')
        self.assertContains(tunisian_page, "Chouf el pouvoir w les cas particuliers")
        self.assertContains(tunisian_page, "T7eb tchouf el bilan en temps reel?")

        game_page = self.narrator.get(reverse("game"))
        self.assertContains(game_page, 'option value="fr" selected')
        self.assertContains(game_page, "async function csrfFetch")
        self.assertContains(game_page, 'response.status !== 403')
        self.assertContains(game_page, reverse("csrf_token_api"))
        self.assertContains(game_page, "function publishAliveRoleCounts()")
        self.assertContains(game_page, "state.publicAliveRoleCounts = alive().reduce")
        self.assertContains(game_page, 'if (source === "night") publishAliveRoleCounts()')

        assignment = started["assignments"][0]
        corrected_state = {
            "stage": "roles",
            "round": 1,
            "publicAliveRoleCounts": {"wild_children": 1, "simple_wolves": 1, "villagers": 1},
            "players": [
                {
                    "id": 1,
                    "roomPlayerId": assignment["room_player_id"],
                    "name": assignment["name"],
                    "role": "wild_children",
                    "alive": True,
                },
                {"id": 2, "name": "Alive wolf", "role": "simple_wolves", "alive": True},
                {"id": 3, "name": "Dead villager", "role": "villagers", "alive": False},
            ],
        }
        response = self.narrator.post(
            reverse("room_sync_api", args=[room.code]),
            json.dumps(corrected_state),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        private_state = player.get(reverse("room_player_api", args=[room.code])).json()
        self.assertEqual(private_state["role"]["code"], "wild_children")
        self.assertEqual(private_state["alive_count"], 3)
        self.assertEqual(
            {item["code"]: item["count"] for item in private_state["alive_roles"]},
            {"simple_wolves": 1, "wild_children": 1, "villagers": 1},
        )

        corrected_state["stage"] = "dawn"
        corrected_state["publicAliveRoleCounts"] = {"wild_children": 1, "simple_wolves": 1}
        self.narrator.post(
            reverse("room_sync_api", args=[room.code]),
            json.dumps(corrected_state),
            content_type="application/json",
        )
        private_state = player.get(reverse("room_player_api", args=[room.code])).json()
        self.assertEqual(private_state["alive_count"], 2)
        self.assertEqual(
            {item["code"]: item["count"] for item in private_state["alive_roles"]},
            {"simple_wolves": 1, "wild_children": 1},
        )
        self.assertEqual(private_state["dead_count"], 1)
        self.assertEqual(
            [(item["code"], item["alive"]) for item in private_state["role_roster"]],
            [("simple_wolves", True), ("wild_children", True), ("villagers", False)],
        )

    def test_only_eliminated_player_sees_and_can_open_active_game_summary(self):
        room = self.create_room()
        eliminated = self.player_client("EliminatedPlayer")
        living = self.player_client("LivingPlayer")
        eliminated.post(reverse("room_portal"), {"room_code": room.code})
        living.post(reverse("room_portal"), {"room_code": room.code})
        assignments = self.narrator.post(reverse("room_start_api", args=[room.code])).json()["assignments"]
        by_name = {item["name"]: item for item in assignments}
        state = {
            "stage": "dawn",
            "round": 1,
            "distributionStarted": True,
            "players": [
                {
                    "id": 1,
                    "roomPlayerId": by_name["EliminatedPlayer"]["room_player_id"],
                    "name": "EliminatedPlayer",
                    "role": by_name["EliminatedPlayer"]["role"],
                    "alive": False,
                },
                {
                    "id": 2,
                    "roomPlayerId": by_name["LivingPlayer"]["room_player_id"],
                    "name": "LivingPlayer",
                    "role": by_name["LivingPlayer"]["role"],
                    "alive": True,
                },
            ],
        }
        self.narrator.post(
            reverse("room_sync_api", args=[room.code]),
            json.dumps(state),
            content_type="application/json",
        )

        eliminated_state = eliminated.get(reverse("room_player_api", args=[room.code])).json()
        living_state = living.get(reverse("room_player_api", args=[room.code])).json()
        self.assertFalse(eliminated_state["player_alive"])
        self.assertTrue(living_state["player_alive"])

        eliminated_page = eliminated.get(reverse("room_player", args=[room.code]))
        self.assertContains(eliminated_page, 'id="eliminated-history-link"')
        self.assertContains(eliminated_page, "Voir le bilan de la partie en temps réel")
        self.assertContains(eliminated_page, 'aria-disabled="true"')
        self.assertContains(eliminated_page, 'tabindex="-1"')
        self.assertContains(eliminated_page, "updateHistoryLink(data.player_alive)")
        self.assertContains(eliminated_page, "if (enabled) link.href = link.dataset.historyUrl")
        self.assertContains(eliminated_page, 'link.removeAttribute("href")')

        history_url = reverse("room_history", args=[room.code])
        history_api_url = reverse("room_history_api", args=[room.code])
        self.assertEqual(eliminated.get(history_url).status_code, 200)
        self.assertEqual(eliminated.get(history_api_url).status_code, 200)
        self.assertEqual(living.get(history_url).status_code, 403)
        self.assertEqual(living.get(history_api_url).status_code, 403)

        state["players"][0]["alive"] = True
        self.narrator.post(
            reverse("room_sync_api", args=[room.code]),
            json.dumps(state),
            content_type="application/json",
        )
        self.assertTrue(eliminated.get(reverse("room_player_api", args=[room.code])).json()["player_alive"])
        self.assertEqual(eliminated.get(history_url).status_code, 403)

    def test_new_player_can_join_after_distribution_until_first_night_starts(self):
        room = self.create_room()
        first = self.player_client("BeforeDistribution")
        first.post(reverse("room_portal"), {"room_code": room.code})
        self.narrator.post(reverse("room_start_api", args=[room.code]))

        late = self.player_client("AfterDistribution")
        joined = late.post(reverse("room_portal"), {"room_code": room.code})

        self.assertRedirects(joined, reverse("room_player", args=[room.code]), fetch_redirect_response=False)
        late_role = late.get(reverse("room_player_api", args=[room.code])).json()["role"]
        self.assertIsNotNone(late_role)
        room.refresh_from_db()
        late_player = room.room_players.get(user__username="AfterDistribution")
        self.assertEqual(late_player.role, late_role["code"])
        self.assertTrue(any(item.get("roomPlayerId") == late_player.id for item in room.game_state["players"]))

        night_state = room.game_state
        night_state.update({"stage": "wolves", "round": 1, "gameplayStarted": True})
        self.narrator.post(
            reverse("room_sync_api", args=[room.code]),
            json.dumps(night_state),
            content_type="application/json",
        )
        too_late = self.player_client("AfterNightStarted").post(
            reverse("room_portal"),
            {"room_code": room.code},
        )
        self.assertContains(too_late, "Cette partie a déjà commencé.")
        self.assertFalse(room.room_players.filter(user__username="AfterNightStarted").exists())

    def test_narrator_lobby_shows_capacity_and_can_remove_players(self):
        room = self.create_room()
        sarra = self.player_client("Sarra")
        ali = self.player_client("Ali")
        sarra.post(reverse("room_portal"), {"room_code": room.code})
        ali.post(reverse("room_portal"), {"room_code": room.code})
        room.game_state = {"pendingManualPlayerNames": ["Joueur manuel"]}
        room.save(update_fields=["game_state"])

        lobby = self.narrator.get(reverse("room_lobby_api", args=[room.code])).json()
        self.assertEqual(lobby["registered_count"], 3)
        self.assertEqual(lobby["player_count"], 8)

        sarra_id = room.room_players.get(name="Sarra").id
        forbidden = ali.post(
            reverse("room_lobby_remove_api", args=[room.code]),
            json.dumps({"room_player_id": sarra_id}),
            content_type="application/json",
        )
        self.assertEqual(forbidden.status_code, 403)

        removed = self.narrator.post(
            reverse("room_lobby_remove_api", args=[room.code]),
            json.dumps({"room_player_id": sarra_id}),
            content_type="application/json",
        )
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.json()["registered_count"], 2)
        self.assertFalse(room.room_players.filter(name="Sarra").exists())

        removed_manual = self.narrator.post(
            reverse("room_lobby_remove_api", args=[room.code]),
            json.dumps({"manual_name": "Joueur manuel"}),
            content_type="application/json",
        )
        self.assertEqual(removed_manual.status_code, 200)
        self.assertEqual(removed_manual.json()["registered_count"], 1)
        room.refresh_from_db()
        self.assertEqual(room.game_state["pendingManualPlayerNames"], [])

        ali_id = room.room_players.get(name="Ali").id
        self.narrator.post(reverse("room_start_api", args=[room.code]))
        too_late = self.narrator.post(
            reverse("room_lobby_remove_api", args=[room.code]),
            json.dumps({"room_player_id": ali_id}),
            content_type="application/json",
        )
        self.assertEqual(too_late.status_code, 409)
        self.assertTrue(room.room_players.filter(name="Ali").exists())

        game = self.narrator.get(reverse("game"))
        self.assertContains(game, 'id="lobby-player-count"')
        self.assertContains(game, 'data-action="remove-lobby-player"')
        self.assertContains(game, "/lobby/remove/")

    def test_private_player_notes_are_saved_and_only_visible_to_their_owner(self):
        room = self.create_room()
        player = self.player_client("Sarra-notes")
        player.post(reverse("room_portal"), {"room_code": room.code})
        self.narrator.post(reverse("room_start_api", args=[room.code]))
        notes_url = reverse("room_player_notes_api", args=[room.code])

        notes = "La Voyante semble fiable.\nSuspect principal : joueur 04."
        saved = player.post(
            notes_url,
            json.dumps({"notes": notes}),
            content_type="application/json",
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["length"], len(notes))
        self.assertEqual(room.room_players.get(name="Sarra-notes").private_notes, notes)
        self.assertEqual(
            player.get(reverse("room_player_api", args=[room.code])).json()["private_notes"],
            notes,
        )

        too_long = player.post(
            notes_url,
            json.dumps({"notes": "x" * 601}),
            content_type="application/json",
        )
        self.assertEqual(too_long.status_code, 400)
        self.assertEqual(room.room_players.get(name="Sarra-notes").private_notes, notes)
        self.assertEqual(self.narrator.post(notes_url, json.dumps({"notes": "intrusion"}), content_type="application/json").status_code, 403)

        room.status = GameRoom.Status.FINISHED
        room.save(update_fields=["status"])
        final_notes = f"{notes}\nPartie terminée."
        self.assertEqual(
            player.post(notes_url, json.dumps({"notes": final_notes}), content_type="application/json").status_code,
            200,
        )
        owner_history = player.get(reverse("room_history", args=[room.code]))
        self.assertContains(owner_history, "Mes notes privées")
        self.assertContains(owner_history, "Partie terminée.")
        narrator_history = self.narrator.get(reverse("room_history", args=[room.code]))
        self.assertNotContains(narrator_history, "Partie terminée.")

        player_page = player.get(reverse("room_player", args=[room.code]))
        self.assertContains(player_page, 'maxlength="600"')
        self.assertContains(player_page, "schedulePrivateNotesSave")
        self.assertContains(player_page, "keepalive: true")
        self.assertContains(player_page, "async function csrfFetch")
        self.assertContains(player_page, reverse("csrf_token_api"))
        self.assertContains(player_page, 'const roleRevealed = card.classList.contains("revealed")')
        self.assertContains(player_page, "5000 + Math.random() * 3000")
        self.assertContains(player_page, "2500 + Math.random() * 1500")
        self.assertContains(player_page, "Connecté avec succès en tant que")
        self.assertContains(player_page, "Sarra-notes")

    def test_roster_sync_does_not_close_room_before_distribution(self):
        room = self.create_room()
        sarra = self.player_client("Sarra")
        sarra.post(reverse("room_portal"), {"room_code": room.code})

        response = self.narrator.post(
            reverse("room_sync_api", args=[room.code]),
            json.dumps({
                "stage": "roster",
                "round": 1,
                # A legacy browser could infer this from players.length even
                # though no role had been distributed yet.
                "roomStarted": True,
                "players": [{"id": 1, "name": "Sarra", "alive": True}],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        room.refresh_from_db()
        self.assertEqual(room.status, GameRoom.Status.WAITING)
        self.assertFalse(room.game_state["roomStarted"])

        waiting = sarra.get(reverse("room_player_api", args=[room.code])).json()
        self.assertEqual(waiting["status"], GameRoom.Status.WAITING)
        self.assertIsNone(waiting["role"])
        self.assertEqual(waiting["alive_roles"], [])

        nour = self.player_client("Nour")
        joined = nour.post(reverse("room_portal"), {"room_code": room.code})
        self.assertRedirects(joined, reverse("room_player", args=[room.code]), fetch_redirect_response=False)
        self.assertEqual(room.room_players.count(), 2)

    def test_legacy_active_room_without_distribution_is_repaired(self):
        room = self.create_room()
        room.status = GameRoom.Status.ACTIVE
        room.game_state = {"stage": "roster", "roomStarted": False}
        room.save(update_fields=["status", "game_state"])

        player = self.player_client("LegacyPlayer")
        joined = player.post(reverse("room_portal"), {"room_code": room.code})
        self.assertRedirects(joined, reverse("room_player", args=[room.code]), fetch_redirect_response=False)
        waiting = player.get(reverse("room_player_api", args=[room.code])).json()
        self.assertEqual(waiting["status"], GameRoom.Status.WAITING)
        self.assertIsNone(waiting["role"])

        started = self.narrator.post(reverse("room_start_api", args=[room.code]))
        self.assertEqual(started.status_code, 200)
        room.refresh_from_db()
        self.assertEqual(room.status, GameRoom.Status.ACTIVE)
        self.assertTrue(room.game_state["distributionStarted"])
        self.assertIsNotNone(player.get(reverse("room_player_api", args=[room.code])).json()["role"])

    def test_player_rejoins_started_room_with_same_name_without_duplicate_registration(self):
        room = self.create_room()
        first_phone = self.player_client("join-yessin")
        first_phone.post(reverse("room_portal"), {"room_code": room.code, "player_name": "Yessin"})
        assigned = self.narrator.post(reverse("room_start_api", args=[room.code])).json()["assignments"][0]

        second_phone = self.player_client("join-yessin")
        response = second_phone.post(reverse("room_portal"), {"room_code": room.code, "player_name": "yEsSiN"})

        self.assertRedirects(response, reverse("room_player", args=[room.code]), fetch_redirect_response=False)
        private_state = second_phone.get(reverse("room_player_api", args=[room.code])).json()
        self.assertEqual(private_state["role"]["code"], assigned["role"])
        self.assertEqual(room.room_players.filter(name="join-yessin").count(), 1)

    def test_manually_registered_player_can_connect_by_name_after_game_starts(self):
        room = self.create_room()
        self.narrator.post(reverse("room_start_api", args=[room.code]))
        state = {
            "stage": "roles",
            "round": 1,
            "players": [{"id": 1, "name": "manual-user", "role": "villagers", "alive": True}],
        }
        self.narrator.post(
            reverse("room_sync_api", args=[room.code]),
            json.dumps(state),
            content_type="application/json",
        )

        phone = self.player_client("manual-user")
        response = phone.post(reverse("room_portal"), {"room_code": room.code})

        self.assertRedirects(response, reverse("room_player", args=[room.code]), fetch_redirect_response=False)
        self.assertEqual(phone.get(reverse("room_player_api", args=[room.code])).json()["role"]["code"], "villagers")
        self.assertEqual(room.room_players.filter(name="manual-user").count(), 1)

    def test_narrator_can_reopen_lobby_and_redistribute_roles_to_phones(self):
        room = self.create_room()
        sarra = self.player_client("Sarra")
        ali = self.player_client("Ali")
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

        nour = self.player_client("Nour")
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
        sarra = self.player_client("Sarra")
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
            "deaths": [1], "wolfTargetId": 1, "wolfResolvedTargetId": 2,
            "alienDeathIds": [2],
            "barberDeathIds": [2],
            "hunterCausedDeathIds": [1],
            "hunterShotRecords": [
                {"source": "night", "targetId": 1, "deathIds": [1]},
                {"source": "alien", "targetId": 2, "deathIds": [2]},
            ],
            "coupleIds": [1, 2], "wildChildId": 1, "wildIdolId": 2,
            "prostituteTargetId": 2, "silencedPlayerId": 2,
            "talkativePlayerId": 1, "assignedWord": "lune",
            "alienLastGuessResults": [{"id": 2, "guessedRole": "villagers", "correct": True}],
            "blockedPlayerId": 1, "witchSave": True, "witchKillId": 2,
            "bearGrowled": True,
            "shepherdLastResults": [
                {"targetId": 1, "returned": False},
                {"targetId": 2, "returned": True},
            ],
            "sheepRemaining": 2, "shepherdWasBlocked": False,
            "judgeFirstId": 1, "judgeSecondId": 2, "judgeSameClan": False,
            "seerTargetId": 2, "seerDisplayedRole": "villagers",
            "winner": "wolves",
        }
        sync_url = reverse("room_sync_api", args=[room.code])
        self.narrator.post(sync_url, json.dumps(state), content_type="application/json")
        self.narrator.post(sync_url, json.dumps(state), content_type="application/json")
        state.update({
            "stage": "day_end", "lastVote": 1, "voteDeathIds": [1, 2], "voteOutcome": "eliminated",
            "speakerId": 2, "qualifiers": [1, 2],
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
        self.assertEqual(night["deaths"], ["Ahmed"])
        self.assertEqual(night["player_roles"], {"Ahmed": "witches", "Sarra": "villagers"})
        self.assertEqual(night["couple_members"], ["Ahmed", "Sarra"])
        self.assertEqual(night["wild_idol"], "Sarra")
        self.assertEqual(night["redirected_to"], "Sarra")
        self.assertEqual(night["silenced"], "Sarra")
        self.assertEqual(night["talkative_word"], "lune")
        self.assertEqual(night["wolves_target"], "Ahmed")
        self.assertEqual(night["wolves_final_target"], "Sarra")
        self.assertEqual(night["hunter_deaths"], ["Ahmed"])
        self.assertNotIn("alien_deaths", night)
        self.assertNotIn("barber_deaths", night)
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
        self.assertEqual(night["winner"], "wolves")
        day = history["events"][1]["details"]
        self.assertEqual(day["speaker"], "Sarra")
        self.assertEqual(day["accused"], ["Ahmed", "Sarra"])
        self.assertEqual(day["vote_deaths"], ["Ahmed", "Sarra"])
        self.assertEqual(day["alien_deaths"], ["Sarra"])
        self.assertEqual(day["alien_guesses"], [{"name": "Sarra", "role": "villagers", "correct": True}])
        self.assertEqual(day["barber_deaths"], ["Sarra"])
        self.assertEqual(day["hunter_deaths"], ["Sarra"])
        self.assertEqual(day["normal_votes"], ["Ahmed: 3"])
        self.assertEqual(day["cancelled_votes"], ["Ahmed"])
        self.assertEqual(day["secret_votes"], ["Ahmed → Sarra"])
        self.assertEqual(day["final_totals"], ["Ahmed: 1", "Sarra: 1"])

        history_page = self.narrator.get(reverse("room_history", args=[room.code]))
        self.assertContains(history_page, "function eventNarrative(event)")
        self.assertContains(history_page, 'class="history-story"')
        self.assertContains(history_page, "H.story_seer")
        self.assertContains(history_page, "H.story_prostitute")
        self.assertContains(history_page, "H.story_barber_hit")
        self.assertContains(history_page, "H.story_accused")
        self.assertContains(history_page, 'if (d.winner) add("winner", H.story_winner')
        self.assertContains(history_page, 'actor: actor("protectors")')
        self.assertContains(history_page, "`${roleLabels[role] || role} (${name})`")
        self.assertContains(history_page, "let renderedEventKeys = new Set()")
        self.assertContains(history_page, '.querySelectorAll(".history-event details[open]")')
        self.assertContains(history_page, "openEventKeys.has(eventKey) || isNewLatestEvent")

        self.assertRedirects(Client().get(reverse("room_history_list")), reverse("home"), fetch_redirect_response=False)

        state.update({"stage": "game_over", "winner": "village"})
        self.narrator.post(sync_url, json.dumps(state), content_type="application/json")
        self.assertEqual(Client().get(reverse("room_history_api", args=[room.code])).status_code, 403)
        self.assertEqual(Client().get(reverse("room_history", args=[room.code])).status_code, 403)

    def test_finished_history_cleans_stale_day_actions_and_restores_final_winner(self):
        room = self.create_room()
        room.status = GameRoom.Status.FINISHED
        room.game_state = {"winner": "wolves", "players": []}
        room.save(update_fields=["status", "game_state"])
        RoomEvent.objects.create(
            room=room,
            marker="day-1",
            event_type="day",
            round_number=1,
            details={
                "barber_target": "Dead wolf",
                "barber_hit": True,
                "barber_deaths": [],
                "alien_guesses": [{"name": "Dead seer", "role": "seers", "correct": True}],
                "alien_correct": True,
                "alien_deaths": [],
            },
        )

        details = self.narrator.get(reverse("room_history_api", args=[room.code])).json()["events"][0]["details"]

        self.assertIsNone(details["barber_target"])
        self.assertIsNone(details["barber_hit"])
        self.assertEqual(details["alien_guesses"], [])
        self.assertIsNone(details["alien_correct"])
        self.assertEqual(details["winner"], "wolves")

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

    def test_round_advance_recovers_a_missing_day_summary(self):
        room = self.create_room()
        self.narrator.post(reverse("room_start_api", args=[room.code]))
        sync_url = reverse("room_sync_api", args=[room.code])
        players = [
            {"id": 1, "name": "Ahmed", "role": "hunters", "alive": False},
            {"id": 2, "name": "Sarra", "role": "villagers", "alive": False},
            {"id": 3, "name": "Nour", "role": "villagers", "alive": True},
        ]
        self.narrator.post(sync_url, json.dumps({
            "stage": "dawn", "round": 1, "players": players, "deaths": [],
        }), content_type="application/json")
        self.narrator.post(sync_url, json.dumps({
            "stage": "accusation", "round": 1, "players": players,
            "speakerId": 3, "alienDeathIds": [2],
            "hunterShotRecords": [{"source": "alien", "targetId": 2, "deathIds": [2]}],
        }), content_type="application/json")

        self.assertFalse(RoomEvent.objects.filter(room=room, marker="day-1").exists())
        self.narrator.post(sync_url, json.dumps({
            "stage": "protector", "round": 2, "players": players,
        }), content_type="application/json")

        recovered = RoomEvent.objects.get(room=room, marker="day-1")
        self.assertEqual(recovered.details["vote_outcome"], "forced_transition")
        self.assertEqual(recovered.details["alien_deaths"], ["Sarra"])
        self.assertEqual(recovered.details["hunter_deaths"], ["Sarra"])

        self.narrator.post(sync_url, json.dumps({
            "stage": "dawn", "round": 2, "eventRound": 2, "players": players, "deaths": [],
        }), content_type="application/json")
        self.assertEqual(
            list(RoomEvent.objects.filter(room=room).values_list("marker", flat=True)),
            ["night-1", "day-1", "night-2"],
        )

    def test_history_explains_a_recovered_manual_day_transition(self):
        room = self.create_room()
        RoomEvent.objects.create(
            room=room,
            marker="day-1",
            event_type="day",
            round_number=1,
            details={"vote_outcome": "forced_transition"},
        )
        history_page = self.narrator.get(reverse("room_history", args=[room.code]))
        self.assertContains(history_page, "H.story_day_forced")
        self.assertContains(history_page, "H.history_day_forced")
        self.assertEqual(history_page.context["room"]["history_day_forced"], "Journée terminée manuellement")

    def test_admin_history_lists_and_resumes_active_games(self):
        room = self.create_room()
        self.narrator.post(reverse("room_start_api", args=[room.code]))

        visitor = Client()
        guest_history = visitor.get(reverse("room_history_list"))
        self.assertRedirects(guest_history, reverse("home"), fetch_redirect_response=False)
        self.assertEqual(visitor.get(reverse("room_history", args=[room.code])).status_code, 403)
        self.assertEqual(visitor.get(reverse("room_history_api", args=[room.code])).status_code, 403)

        returning_admin = Client()
        returning_admin.post(reverse("home"), {"username": "yessin", "password": "yessin"})
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

    def test_busy_room_join_shows_short_jittered_retry(self):
        room = self.create_room()
        player = self.player_client("queued-player")

        with patch(
            "pages.views.GameRoom.objects.select_for_update",
            side_effect=OperationalError("room is locked"),
        ):
            response = player.post(reverse("room_portal"), {"room_code": room.code, "join_attempt": "2"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["Retry-After"], "2")
        self.assertContains(response, 'data-retry-after="2"', status_code=503)
        self.assertContains(response, 'id="join-retry-countdown"', status_code=503)
        self.assertContains(response, 'name="join_attempt" value="2"', status_code=503)
        self.assertContains(response, "tentative <b id=\"join-attempt-label\">2</b>/5", status_code=503)
        self.assertContains(response, "Math.random() * .75", status_code=503)
        self.assertContains(response, "joinAttempt += 1", status_code=503)
        self.assertContains(response, "joinForm.requestSubmit()", status_code=503)
        self.assertContains(response, f'action="{reverse("room_portal")}"', status_code=503)
        self.assertNotContains(response, "new FormData(joinForm)", status_code=503)
        self.assertFalse(room.room_players.filter(name="queued-player").exists())

    def test_fifth_busy_join_attempt_stops_automatic_retry_but_stays_idempotent(self):
        room = self.create_room()
        player = self.player_client("patient-player")

        with patch(
            "pages.views.GameRoom.objects.select_for_update",
            side_effect=OperationalError("room is locked"),
        ):
            response = player.post(reverse("room_portal"), {"room_code": room.code, "join_attempt": "5"})

        self.assertEqual(response.status_code, 503)
        self.assertContains(response, 'name="join_attempt" value="5"', status_code=503)
        self.assertContains(response, "ton inscription ne sera jamais créée deux fois", status_code=503)
        self.assertNotContains(response, 'id="join-retry-countdown"', status_code=503)

    def test_registration_retry_with_matching_credentials_logs_into_committed_account(self):
        credentials = {
            "username": "registration-retry",
            "password": "safe-password",
            "password_confirmation": "safe-password",
        }
        first = Client()
        self.assertRedirects(first.post(reverse("register"), credentials), reverse("room_portal"), fetch_redirect_response=False)

        retry = Client()
        response = retry.post(reverse("register"), credentials)

        self.assertRedirects(response, reverse("room_portal"), fetch_redirect_response=False)
        self.assertEqual(retry.session["_auth_user_id"], str(get_user_model().objects.get(username="registration-retry").id))

    def test_registration_retry_does_not_accept_wrong_password(self):
        get_user_model().objects.create_user(username="existing-player", password="correct-password")

        response = Client().post(reverse("register"), {
            "username": "existing-player",
            "password": "wrong-password",
            "password_confirmation": "wrong-password",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ce nom d’utilisateur existe déjà.")

    def test_registration_page_retries_short_overloads_and_confirms_login(self):
        response = Client().get(reverse("register"))

        self.assertContains(response, 'id="registration-status"')
        self.assertContains(response, "tentative ${attempt}/${maxAttempts}")
        self.assertContains(response, "response.status === 502 || response.status === 503 || response.status === 504")
        self.assertContains(response, "Math.min(2")
        self.assertContains(response, "Compte créé et connexion réussie")
        self.assertContains(response, "window.location.assign(response.url)")

    def test_home_opens_general_room_join_form(self):
        home = Client().get(reverse("home"))
        self.assertNotContains(home, f'href="{reverse("room_portal")}"')
        portal = self.narrator.get(reverse("room_portal"))
        self.assertEqual(portal.status_code, 200)
        self.assertContains(portal, 'name="room_code"')
        self.assertNotContains(portal, 'name="player_name"')
        self.assertContains(portal, "Nom dans la partie")
        self.assertContains(portal, reverse("general_room_qr"))
        self.assertContains(portal, f'action="{reverse("room_portal")}"')
        self.assertNotContains(portal, "new FormData(joinForm)")
        self.assertContains(portal, "function submitJoin(event)")

    def test_authenticated_player_and_narrator_pages_have_home_buttons(self):
        room = self.create_room()
        player = self.player_client("home-button-player")

        portal = player.get(reverse("room_portal"))
        self.assertContains(portal, 'class="guide-back home-navigation"')
        self.assertContains(portal, "Retour à l’accueil")

        player.post(reverse("room_portal"), {"room_code": room.code})
        player_room = player.get(reverse("room_player", args=[room.code]))
        self.assertContains(player_room, 'class="guide-back home-navigation"')

        history = self.narrator.get(reverse("room_history", args=[room.code]))
        self.assertContains(history, 'class="guide-back home-navigation"')
        self.assertContains(history, 'class="language-selector"')

        narrator_game = self.narrator.get(reverse("game"))
        self.assertContains(narrator_game, 'class="header-action home-navigation"')

        narrator_setup = self.narrator.get(reverse("welcome") + "?mode=new")
        self.assertContains(narrator_setup, 'class="text-link home-navigation"')

        role_guide = player.get(reverse("roles_guide"))
        self.assertContains(role_guide, 'class="guide-back home-navigation"')

        users = self.narrator.get(reverse("user_management"))
        self.assertContains(users, 'class="text-link home-navigation"')

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
        returning_narrator.post(reverse("home"), {"username": "yessin", "password": "yessin"})
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
        returning_narrator.post(reverse("home"), {"username": "yessin", "password": "yessin"})
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

    def test_game_uses_only_the_general_website_qr_code(self):
        room = self.create_room()
        game = self.narrator.get(reverse("game"))
        self.assertContains(game, reverse("general_room_qr"))
        self.assertNotContains(game, f"/room/{room.code}/qr.svg")
        self.assertEqual(Client().get(f"/room/{room.code}/qr.svg").status_code, 404)

    def test_general_website_qr_code_is_available(self):
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
        self.assertEqual(manifest.json()["id"], "/")
        self.assertEqual(manifest.json()["start_url"], "/")
        self.assertEqual(manifest.json()["display"], "standalone")
        self.assertEqual(manifest.json()["scope"], "/")
        self.assertIn("no-store", manifest["Cache-Control"])

        worker = self.client.get(reverse("service_worker"))
        self.assertEqual(worker.status_code, 200)
        self.assertEqual(worker["Service-Worker-Allowed"], "/")
        self.assertContains(worker, "loup-garou-shell-v10")
        self.assertContains(worker, 'event.request.method !== "GET"')
        self.assertContains(worker, '!url.pathname.startsWith("/static/")')

        home = self.client.get(reverse("home"))
        self.assertContains(home, reverse("pwa_manifest"))
        self.assertContains(home, "apple-mobile-web-app-capable")
        self.assertContains(home, 'apple-mobile-web-app-status-bar-style" content="black"')
        self.assertContains(home, 'window.matchMedia("(display-mode: standalone)")')
        self.assertContains(home, 'updateViaCache: "none"')

        player = get_user_model().objects.create_user(username="pwa-player", password="test-password")
        player_client = Client()
        player_client.force_login(player)
        player_portal = player_client.get(reverse("room_portal"))
        self.assertIn("no-store", player_portal["Cache-Control"])
