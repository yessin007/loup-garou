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

## Deploiement gratuit sur Render

L'application web actuelle fonctionne entierement dans le service Django. Le
service Flask est conserve pour le developpement local, mais il n'est pas
necessaire au deploiement public actuel.

### Methode automatique recommandee (Blueprint)

Le fichier `render.yaml` a la racine du depot configure automatiquement le
service Docker, PostgreSQL, le health check et toutes les variables. Dans
Render, choisir **New > Blueprint**, connecter ce depot puis confirmer avec
**Apply**. Aucune variable d'environnement ne doit etre saisie manuellement.

Le Blueprint genere une cle Django aleatoire et relie automatiquement
`DATABASE_URL` a la base PostgreSQL. L'administration est disponible sur
`/admin/` avec `admin / admin`.

### Configuration manuelle alternative

Dans le panneau Render:

1. Creer une Web Service depuis le depot GitHub `yessin007/loup-garou`.
2. Choisir la branche `main` et activer le deploiement automatique.
3. Choisir le builder `Dockerfile`.
4. Definir le **Root directory** sur `frontend` et conserver `Dockerfile` comme
   chemin du Dockerfile.
5. Exposer le port HTTP `8000` et router `/` vers ce port.
6. Ajouter les variables d'environnement suivantes:

   - `PORT=8000`
   - `DJANGO_DEBUG=0`
   - `DJANGO_ALLOWED_HOSTS=.onrender.com`
   - `DJANGO_SECRET_KEY=<une longue valeur aleatoire et privee>`
   - `DATABASE_URL=<Internal Database URL de Render Postgres>`
   - `ADMIN_USERNAME=admin`
   - `ADMIN_EMAIL=<adresse email admin>`
   - `ADMIN_PASSWORD=<mot de passe admin fort et prive>`

7. Configurer le health check HTTP avec la methode `GET` et le chemin
   `/health/` sur le port `8000`.
8. Lancer le deploiement. Les prochains push sur `main` seront redeployes
   automatiquement.

Le endpoint de verification renvoie un statut HTTP 200:

```text
https://VOTRE-DOMAINE.onrender.com/health/
```

Render construit un seul conteneur a partir de `frontend/Dockerfile`. Il
n'execute pas le fichier `docker-compose.yml`; celui-ci reste destine au
developpement local.

Creer une base Render Postgres dans la meme region que le service web et utiliser
son URL interne pour `DATABASE_URL`. Les rooms et leurs historiques restent
alors disponibles apres les redeploiements. Le compte configure par les
variables `ADMIN_*` peut gerer et supprimer les historiques depuis `/admin/`.
La consultation publique reste en lecture seule sur `/historique/`.

En local, Docker Compose demarre automatiquement PostgreSQL, applique les
migrations et conserve les donnees dans le volume `loup_garou_postgres`.

## Suite proposee

1. Ajouter les premiers ecrans du jeu
2. Ajouter la gestion des joueurs et des rooms
3. Ajouter websocket / temps reel
4. Basculer ensuite vers Kubernetes
