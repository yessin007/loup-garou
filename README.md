# Loup Garou

Base de depart pour un projet `Loup Garou` avec:

- `frontend`: Django
- `backend`: Flask
- `docker-compose`: lancement local multi-conteneurs

## Objectif

Cette base permet de lancer l'application sur cette machine puis d'y acceder depuis un telephone sur le meme reseau.

## Demarrage

```bash
cd loup-garou
docker compose up --build
```

## Acces

- Frontend: `http://localhost:8000`
- Backend API: `http://localhost:5000/api/health`

Depuis un telephone sur le meme reseau:

- `http://IP_DE_TA_MACHINE:8000`
- `http://IP_DE_TA_MACHINE:5000/api/health`

## Suite proposee

1. Ajouter les premiers ecrans du jeu
2. Ajouter la gestion des joueurs et des rooms
3. Ajouter une base de donnees en conteneur
4. Ajouter websocket / temps reel
5. Basculer ensuite vers Kubernetes
