from django.urls import path

from .views import game, home, logout_view, set_language, welcome

urlpatterns = [
    path("", home, name="home"),
    path("accueil/", welcome, name="welcome"),
    path("partie/", game, name="game"),
    path("deconnexion/", logout_view, name="logout"),
    path("langue/", set_language, name="set_language"),
]
