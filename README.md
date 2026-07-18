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

## Deploiement gratuit sur Koyeb

L'application web actuelle fonctionne entierement dans le service Django. Le
service Flask est conserve pour le developpement local, mais il n'est pas
necessaire au deploiement public actuel.

Dans le panneau Koyeb:

1. Creer une Web Service depuis le depot GitHub `yessin007/loup-garou`.
2. Choisir la branche `main` et activer le deploiement automatique.
3. Choisir le builder `Dockerfile`.
4. Definir le **Work directory** sur `frontend` et conserver `Dockerfile` comme
   chemin du Dockerfile.
5. Exposer le port HTTP `8000` et router `/` vers ce port.
6. Ajouter les variables d'environnement suivantes:

   - `PORT=8000`
   - `DJANGO_DEBUG=0`
   - `DJANGO_ALLOWED_HOSTS=.koyeb.app`
   - `DJANGO_SECRET_KEY=<une longue valeur aleatoire et privee>`

7. Configurer le health check HTTP avec la methode `GET` et le chemin
   `/health/` sur le port `8000`.
8. Lancer le deploiement. Les prochains push sur `main` seront redeployes
   automatiquement.

Le endpoint de verification renvoie un statut HTTP 200:

```text
https://VOTRE-DOMAINE.koyeb.app/health/
```

Koyeb construit un seul conteneur a partir de `frontend/Dockerfile`. Il
n'execute pas le fichier `docker-compose.yml`; celui-ci reste destine au
developpement local.

## Suite proposee

1. Ajouter les premiers ecrans du jeu
2. Ajouter la gestion des joueurs et des rooms
3. Ajouter une base de donnees en conteneur
4. Ajouter websocket / temps reel
5. Basculer ensuite vers Kubernetes
