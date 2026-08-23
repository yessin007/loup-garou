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

## Deploiement gratuit avec Render et Neon

L'application web actuelle fonctionne entierement dans le service Django. Le
service Flask est conserve pour le developpement local, mais il n'est pas
necessaire au deploiement public actuel.

### Methode automatique recommandee (Blueprint)

Le fichier `render.yaml` a la racine du depot configure automatiquement le
service Docker, le health check et les variables non secretes. La base de
donnees est hebergee separement sur Neon afin d'eviter l'expiration des bases
PostgreSQL gratuites de Render.

1. Creer un projet PostgreSQL gratuit sur Neon.
2. Dans **Connect**, choisir la chaine de connexion **Pooled connection** et la
   copier.
3. Dans Render, choisir **New > Blueprint**, connecter ce depot puis confirmer
   avec **Apply**.
4. Pour un nouveau Blueprint, saisir `DATABASE_URL` et choisir un
   `ADMIN_PASSWORD` robuste quand Render les demande.
5. Pour le service existant, synchroniser d'abord le Blueprint. Ouvrir ensuite
   le service **loup-garou > Environment**, remplacer `DATABASE_URL` par la
   chaine Neon, remplacer `ADMIN_PASSWORD`, puis choisir
   **Save, rebuild, and deploy**.

`DATABASE_URL` et `ADMIN_PASSWORD` sont declarees avec `sync: false`: leurs
valeurs restent secretes et ne doivent jamais etre ajoutees au depot Git.

Le Blueprint genere une cle Django aleatoire. L'administration est disponible
sur `/admin/` avec le compte configure par les variables `ADMIN_*`.

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
   - `DATABASE_URL=<Pooled connection string de Neon avec sslmode=require>`
   - `ADMIN_USERNAME=yessin`
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

Les rooms et leurs historiques sont conserves dans Neon apres les
redeploiements. Le compte configure par les variables `ADMIN_*` peut gerer et
supprimer les historiques depuis `/admin/`. La consultation de `/historique/`
demande une connexion et applique les droits du compte.

## Comptes et acces

- Le super-admin initial est configuré avec les variables d'environnement `ADMIN_*`.
- Le super-admin cree les comptes `Joueur` et `Narrateur` depuis `/utilisateurs/`.
- Un narrateur peut creer une partie, la reprendre, jouer lui-meme et consulter ses parties terminees.
- Un joueur peut rejoindre une room et ne voit dans son historique que ses propres parties terminees.

En local, Docker Compose demarre automatiquement PostgreSQL, applique les
migrations et conserve les donnees dans le volume `loup_garou_postgres`.

## Suite proposee

1. Ajouter les premiers ecrans du jeu
2. Ajouter la gestion des joueurs et des rooms
3. Ajouter websocket / temps reel
4. Basculer ensuite vers Kubernetes
