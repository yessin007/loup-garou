from django.urls import path

from .views import game, home, logout_view, welcome

urlpatterns = [
    path("", home, name="home"),
    path("accueil/", welcome, name="welcome"),
    path("partie/", game, name="game"),
    path("deconnexion/", logout_view, name="logout"),
]
