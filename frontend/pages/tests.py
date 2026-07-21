import json
from unittest.mock import patch

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
        self.narrator.post(reverse("home"), {"username": "123", "password": "123"})
        self.composition = {role: 0 for role in ROLES["fr"]}
        self.composition.update({"simple_wolves": 2, "villagers": 6})

    def create_room(self):
        response = self.narrator.post(
            reverse("welcome"),
            {"player_count": 8, **self.composition},
        )
        self.assertRedirects(response, reverse("game"), fetch_redirect_response=False)
        return GameRoom.objects.get(code=self.narrator.session["game_setup"]["room_code"])

    def test_player_joins_and_receives_role_after_narrator_starts(self):
        room = self.create_room()
        self.assertTrue(room.code.isdigit())
        self.assertEqual(len(room.code), 6)
        player = Client()
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

    def test_night_and_day_history_are_created_once(self):
        room = self.create_room()
        self.narrator.post(reverse("room_start_api", args=[room.code]))
        state = {
            "stage": "dawn", "round": 1,
            "players": [
                {"id": 1, "name": "Ahmed", "alive": False},
                {"id": 2, "name": "Sarra", "alive": True},
            ],
            "deaths": [1], "wolfTargetId": 1,
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
                "normal": [{"voterId": 2, "targetId": 1}],
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
        self.assertEqual(night["judge_first"], "Ahmed")
        self.assertEqual(night["judge_second"], "Sarra")
        self.assertFalse(night["judge_same_clan"])
        self.assertEqual(night["seer_target"], "Sarra")
        self.assertEqual(night["seer_role"], "villagers")
        day = history["events"][1]["details"]
        self.assertEqual(day["vote_deaths"], ["Ahmed", "Sarra"])
        self.assertEqual(day["normal_votes"], ["Sarra → Ahmed"])
        self.assertEqual(day["cancelled_votes"], ["Ahmed"])
        self.assertEqual(day["secret_votes"], ["Ahmed → Sarra"])
        self.assertEqual(day["final_totals"], ["Ahmed: 1", "Sarra: 1"])

        public_list = Client().get(reverse("room_history_list"))
        self.assertNotContains(public_list, room.code)

        state.update({"stage": "game_over", "winner": "village"})
        self.narrator.post(sync_url, json.dumps(state), content_type="application/json")
        self.assertEqual(Client().get(reverse("room_history_api", args=[room.code])).status_code, 200)
        self.assertEqual(Client().get(reverse("room_history", args=[room.code])).status_code, 200)
        public_list = Client().get(reverse("room_history_list"))
        self.assertContains(public_list, room.code)

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

    def test_angel_opening_day_keeps_first_night_number(self):
        room = self.create_room()
        self.narrator.post(reverse("room_start_api", args=[room.code]))
        sync_url = reverse("room_sync_api", args=[room.code])
        players = [{"id": 1, "name": "Ahmed", "alive": True}, {"id": 2, "name": "Sarra", "alive": True}]
        self.narrator.post(sync_url, json.dumps({"stage": "day_end", "round": 1, "players": players, "voteOutcome": "skipped"}), content_type="application/json")
        self.narrator.post(sync_url, json.dumps({"stage": "dawn", "round": 2, "eventRound": 1, "players": players, "deaths": []}), content_type="application/json")
        self.assertTrue(RoomEvent.objects.filter(room=room, marker="day-1").exists())
        self.assertTrue(RoomEvent.objects.filter(room=room, marker="night-1").exists())
        self.assertFalse(RoomEvent.objects.filter(room=room, marker="night-2").exists())

    def test_room_join_rejects_non_numeric_code(self):
        response = Client().post(
            reverse("room_portal"),
            {"action": "join", "room_code": "ABC123", "player_name": "Sarra"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "exactement 6 chiffres")

    def test_qr_code_contains_prefilled_room_link(self):
        room = self.create_room()
        response = Client(HTTP_HOST="testserver").get(reverse("room_qr", args=[room.code]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/svg+xml")
        self.assertIn(b"<svg", response.content)
        self.assertEqual(Client().head(reverse("room_qr", args=[room.code])).status_code, 200)

        portal = Client().get(reverse("room_portal"), {"code": room.code})
        self.assertContains(portal, f'value="{room.code}"')

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
        self.assertContains(worker, "loup-garou-shell-v7")

        home = self.client.get(reverse("home"))
        self.assertContains(home, reverse("pwa_manifest"))
        self.assertContains(home, "apple-mobile-web-app-capable")
