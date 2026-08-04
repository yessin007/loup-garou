from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import GameRoom, RoomPlayer
from .views import NARRATOR_GROUP


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class AccountFlowTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.super_admin = user_model.objects.create_superuser("yessin", password="yessin")
        self.narrator = user_model.objects.create_user("nour", password="secret")
        self.narrator.groups.add(Group.objects.create(name=NARRATOR_GROUP))
        self.player = user_model.objects.create_user("sarra", password="secret")

    def test_super_admin_creates_both_account_types(self):
        client = Client()
        client.force_login(self.super_admin)
        response = client.post(reverse("user_management"), {
            "action": "create", "username": "amine", "password": "pass1234", "role": "narrator",
        })
        self.assertContains(response, "Le compte amine a été créé")
        self.assertTrue(get_user_model().objects.get(username="amine").groups.filter(name=NARRATOR_GROUP).exists())

        client.post(reverse("user_management"), {
            "action": "create", "username": "rim", "password": "pass1234", "role": "player",
        })
        self.assertFalse(get_user_model().objects.get(username="rim").groups.exists())

    def test_visitor_registers_as_player_and_appears_in_admin_list(self):
        client = Client()
        response = client.post(reverse("register"), {
            "username": "firas",
            "password": "secret",
            "password_confirmation": "secret",
        })
        self.assertRedirects(response, reverse("room_portal"), fetch_redirect_response=False)
        account = get_user_model().objects.get(username="firas")
        self.assertTrue(account.is_active)
        self.assertFalse(account.is_superuser)
        self.assertFalse(account.groups.exists())
        self.assertEqual(int(client.session["_auth_user_id"]), account.id)

        admin = Client()
        admin.force_login(self.super_admin)
        users = admin.get(reverse("user_management"))
        self.assertContains(users, "firas")
        self.assertContains(users, "Joueur · Actif")

    def test_super_admin_can_open_user_details_and_change_password(self):
        client = Client()
        client.force_login(self.super_admin)
        detail_url = reverse("user_detail", args=[self.player.pk])

        response = client.get(detail_url)
        self.assertContains(response, "sarra")
        self.assertContains(response, "Le mot de passe actuel ne peut pas être affiché")

        response = client.post(detail_url, {
            "action": "set_password",
            "password": "nouveau-secret",
            "password_confirmation": "nouveau-secret",
        })
        self.assertContains(response, "Le mot de passe a été modifié")
        self.player.refresh_from_db()
        self.assertTrue(self.player.check_password("nouveau-secret"))
        self.assertFalse(self.player.check_password("secret"))

    def test_super_admin_can_disable_enable_and_delete_regular_user(self):
        client = Client()
        client.force_login(self.super_admin)
        detail_url = reverse("user_detail", args=[self.player.pk])

        client.post(detail_url, {"action": "toggle"})
        self.player.refresh_from_db()
        self.assertFalse(self.player.is_active)

        client.post(detail_url, {"action": "toggle"})
        self.player.refresh_from_db()
        self.assertTrue(self.player.is_active)

        response = client.post(detail_url, {"action": "delete"})
        self.assertRedirects(response, reverse("user_management") + "?deleted=sarra", fetch_redirect_response=False)
        self.assertFalse(get_user_model().objects.filter(pk=self.player.pk).exists())

    def test_super_admin_cannot_disable_or_delete_super_admin(self):
        client = Client()
        client.force_login(self.super_admin)
        detail_url = reverse("user_detail", args=[self.super_admin.pk])

        response = client.post(detail_url, {"action": "toggle"})
        self.assertContains(response, "ne peut pas être désactivé")
        response = client.post(detail_url, {"action": "delete"})
        self.assertContains(response, "ne peut pas être supprimé")
        self.assertTrue(get_user_model().objects.filter(pk=self.super_admin.pk).exists())

    def test_non_super_admin_cannot_open_user_management_details(self):
        client = Client()
        client.force_login(self.narrator)
        self.assertEqual(client.get(reverse("user_detail", args=[self.player.pk])).status_code, 403)

    def test_registration_rejects_duplicate_username(self):
        response = Client().post(reverse("register"), {
            "username": "SARRA",
            "password": "secret",
            "password_confirmation": "secret",
        })
        self.assertContains(response, "existe déjà")
        self.assertEqual(get_user_model().objects.filter(username__iexact="sarra").count(), 1)

    def test_player_only_sees_finished_games_they_played(self):
        room = GameRoom.objects.create(player_count=8, composition={}, narrator=self.narrator)
        RoomPlayer.objects.create(room=room, name="Sarra", user=self.player)
        other = GameRoom.objects.create(player_count=8, composition={}, status=GameRoom.Status.FINISHED)

        client = Client()
        client.force_login(self.player)
        active_history = client.get(reverse("room_history_list"))
        self.assertNotContains(active_history, room.code)
        self.assertNotContains(active_history, other.code)
        self.assertEqual(client.get(reverse("room_history", args=[room.code])).status_code, 403)

        room.status = GameRoom.Status.FINISHED
        room.save(update_fields=["status"])
        finished_history = client.get(reverse("room_history_list"))
        self.assertContains(finished_history, room.code)
        self.assertNotContains(finished_history, other.code)
        self.assertEqual(client.get(reverse("room_history", args=[room.code])).status_code, 200)

    def test_logged_in_player_join_is_linked_to_account(self):
        room = GameRoom.objects.create(player_count=8, composition={})
        client = Client()
        client.force_login(self.player)
        response = client.post(reverse("room_portal"), {"room_code": room.code})
        self.assertRedirects(response, reverse("room_player", args=[room.code]), fetch_redirect_response=False)
        self.assertTrue(RoomPlayer.objects.filter(room=room, user=self.player, name="sarra").exists())

    def test_room_link_survives_login(self):
        room = GameRoom.objects.create(player_count=8, composition={})
        client = Client()
        login_page = client.get(f"{reverse('room_portal')}?code={room.code}")
        self.assertRedirects(
            login_page,
            f"{reverse('home')}?next=%2Froom%2F%3Fcode%3D{room.code}",
            fetch_redirect_response=False,
        )
        response = client.post(reverse("home"), {
            "username": "sarra", "password": "secret", "next": f"/room/?code={room.code}",
        })
        self.assertRedirects(response, f"/room/?code={room.code}", fetch_redirect_response=False)

    def test_narrator_has_game_and_player_actions(self):
        client = Client()
        client.force_login(self.narrator)
        client.post(reverse("set_language"), {"language": "fr", "next": reverse("welcome")})
        response = client.get(reverse("welcome"))
        self.assertContains(response, 'class="account-username"')
        self.assertContains(response, "nour")
        self.assertContains(response, "Commencer une nouvelle partie")
        self.assertContains(response, "Rejoindre une partie")
        self.assertContains(response, "Mes parties jouées")
        self.assertNotContains(response, reverse("user_management"))
