import json

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from .models import GameRoom, RoomPlayer, ScoreAward


class LeagueScoringTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.narrator_user = users.objects.create_superuser("score-admin", password="secret")
        self.alice = users.objects.create_user("alice", password="secret")
        self.bob = users.objects.create_user("bob", password="secret")
        self.wolf = users.objects.create_user("wolf", password="secret")
        self.room = GameRoom.objects.create(
            player_count=3,
            composition={"villagers": 1, "witches": 1, "simple_wolves": 1},
            narrator=self.narrator_user,
            status=GameRoom.Status.ACTIVE,
        )
        self.alice_seat = RoomPlayer.objects.create(room=self.room, name="alice", role="villagers", user=self.alice)
        self.bob_seat = RoomPlayer.objects.create(room=self.room, name="bob", role="witches", user=self.bob)
        self.wolf_seat = RoomPlayer.objects.create(room=self.room, name="wolf", role="simple_wolves", user=self.wolf)
        self.client = Client()
        self.client.force_login(self.narrator_user)
        session = self.client.session
        session["game_setup"] = {"room_code": self.room.code, "player_count": 3, "composition": self.room.composition}
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

    def players(self, wolf_alive=True):
        return [
            {"id": 1, "roomPlayerId": self.alice_seat.id, "name": "alice", "role": "villagers", "initialRole": "villagers", "alive": True},
            {"id": 2, "roomPlayerId": self.bob_seat.id, "name": "bob", "role": "witches", "initialRole": "witches", "alive": True},
            {"id": 3, "roomPlayerId": self.wolf_seat.id, "name": "wolf", "role": "simple_wolves", "initialRole": "simple_wolves", "alive": wolf_alive},
        ]

    def sync(self, state, undo=False):
        return self.client.post(
            reverse("room_sync_api", args=[self.room.code]),
            json.dumps(state),
            content_type="application/json",
            **({"HTTP_X_GAME_UNDO": "1"} if undo else {}),
        )

    def test_day_scoring_is_idempotent_and_undo_removes_it(self):
        state = {
            "stage": "day_end", "round": 1, "players": self.players(wolf_alive=False),
            "lastVote": 3, "voteDeathIds": [3], "voteOutcome": "eliminated",
            "voteBreakdown": {"normal": [], "cancelled": [], "secret": [], "totals": []},
        }
        self.assertEqual(self.sync(state).status_code, 200)
        self.assertEqual(self.sync(state).status_code, 200)
        self.assertEqual(ScoreAward.objects.count(), 4)
        self.assertEqual(sum(ScoreAward.objects.filter(user=self.alice).values_list("points", flat=True)), 3)
        self.assertEqual(sum(ScoreAward.objects.filter(user=self.bob).values_list("points", flat=True)), 3)

        undo_state = {**state, "stage": "final_vote", "players": self.players(wolf_alive=True)}
        self.assertEqual(self.sync(undo_state, undo=True).status_code, 200)
        self.assertFalse(ScoreAward.objects.exists())

    def test_witch_decisive_save_scores_four(self):
        state = {
            "stage": "dawn", "round": 1, "eventRound": 1, "players": self.players(),
            "wolfTargetId": 1, "wolfResolvedTargetId": 1, "witchSave": True,
            "protectedId": None, "deaths": [], "hunterShotRecords": [],
        }
        self.assertEqual(self.sync(state).status_code, 200)
        award = ScoreAward.objects.get(user=self.bob, rule_code="witch_save")
        self.assertEqual(award.points, 4)
        self.assertFalse(ScoreAward.objects.filter(rule_code="wolves_hunt").exists())

    def test_witch_save_of_major_allied_power_scores_five(self):
        players = self.players()
        players[0]["role"] = "seers"
        state = {
            "stage": "dawn", "round": 1, "eventRound": 1, "players": players,
            "wolfTargetId": 1, "wolfResolvedTargetId": 1, "witchSave": True,
            "protectedId": None, "deaths": [], "hunterShotRecords": [],
        }
        self.assertEqual(self.sync(state).status_code, 200)
        award = ScoreAward.objects.get(user=self.bob, rule_code="witch_critical_save")
        self.assertEqual(award.points, 5)

    def test_finished_game_awards_five_to_winning_team_and_renders_league(self):
        state = {
            "stage": "game_over", "round": 2, "players": self.players(wolf_alive=False),
            "winner": "village", "angelChanceExpired": True, "coupleIds": [],
        }
        self.assertEqual(self.sync(state).status_code, 200)
        self.assertEqual(ScoreAward.objects.get(user=self.alice, rule_code="victory").points, 5)
        self.assertEqual(ScoreAward.objects.get(user=self.bob, rule_code="victory").points, 5)
        self.assertFalse(ScoreAward.objects.filter(user=self.wolf, rule_code="victory").exists())
        self.assertFalse(ScoreAward.objects.filter(points__gt=5).exists())

        ScoreAward.objects.all().delete()
        call_command("rebuild_scores", verbosity=0)
        self.assertEqual(ScoreAward.objects.get(user=self.alice, rule_code="victory").points, 5)

        player_client = Client()
        player_client.force_login(self.alice)
        player_client.post(reverse("set_language"), {"language": "fr", "next": reverse("league")})
        response = player_client.get(reverse("league"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alice")
        self.assertContains(response, "Règles de score")
        self.assertContains(response, "+5")

    def test_player_portal_has_join_history_and_league_choices(self):
        player_client = Client()
        player_client.force_login(self.alice)
        response = player_client.get(reverse("room_portal"))
        self.assertContains(response, reverse("room_history_list") + "?mine=1")
        self.assertContains(response, reverse("league"))
        self.assertContains(response, "01")
        self.assertContains(response, "02")
        self.assertContains(response, "03")
