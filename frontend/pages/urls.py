from django.urls import path

from .views import game, health, home, logout_view, roles_guide, set_language, welcome

urlpatterns = [
    path("health/", health, name="health"),
    path("", home, name="home"),
    path("roles/", roles_guide, name="roles_guide"),
    path("accueil/", welcome, name="welcome"),
    path("partie/", game, name="game"),
    path("deconnexion/", logout_view, name="logout"),
    path("langue/", set_language, name="set_language"),
]
