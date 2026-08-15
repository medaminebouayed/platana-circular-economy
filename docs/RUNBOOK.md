# Guide de démarrage — Exécuter Platana de A à Z

Ce guide explique, **étape par étape**, comment faire tourner l'application
complète Platana sur une machine locale (Windows + Docker Desktop) : stack
Docker, bases de données, MLflow, Dify et le frontend Angular.

> Français — les autres documents du dépôt sont en anglais
> (`ARCHITECTURE.md`, `API.md`, `DEPLOYMENT.md`, `MLOPS.md`, `AUDIT.md`).

---

## 1. Vue d'ensemble

| Brique | Rôle | Accès |
|---|---|---|
| Traefik | Point d'entrée unique (reverse proxy) | `http://localhost:8081` |
| Frontend Angular | SPA (login, dashboard, admin, tools AI) | via Traefik |
| main-service (:8003) | Auth, produits, évaluation Dify, review, PDF, stats, training proxy | via Traefik `/api` |
| orchestrator (:8000) | Pipeline CV → Pricing → GenAI (local, outils/tests) | interne |
| cv-service (:8001) | Note visuelle (A–D) + détection de défauts (ONNX) | interne |
| pricing-service (:8002) | Prédiction de prix XGBoost + cache Redis | interne |
| training-service (:8010) | Retraining continu guardé (pricing / CV), promotion | interne |
| MongoDB | Données produits, users, samples d'entraînement | `27017` (debug) |
| Redis | Cache des prédictions de prix | interne |
| MLflow | Tracking des expériences | `http://localhost:8081/mlflow` |
| Dify | Workflows GenAI (évaluation + publication) | projet Docker séparé |

---

## 2. Prérequis

- **Docker Desktop** avec **Compose v2** (Windows).
- **Git** (pour cloner les dépôts, déjà fait ici).
- Les dépôts suivants sur le disque :
  - **Platana** : `…\platana-circular-economy`
  - **Dify** : `C:\Users\amine\OneDrive\Desktop\dify-main` (séparé de Platana).

---

## 3. Étape 0 — Réseau partagé & Dify

Platana et Dify tournent dans **deux projets Compose différents** (deux réseaux
privés distincts). Pour que `main-service` (Platana) appelle l'API de Dify, on
a créé un **réseau Docker partagé** (`platana-shared-network`) et branché les
deux projets dessus. En plus, le `.env` de Dify a été modifié pour laisser Dify
joindre les microservices Platana (proxy SSRF).

### 3.1 Créer le réseau partagé (une seule fois)

```powershell
docker network create platana-shared-network
```

Ce réseau est déclaré **externe** dans les deux fichiers Compose (il n'est
jamais recréé par `docker compose down`).

### 3.2 Modifications côté Platana (déjà en place)

Dans `docker-compose.yaml` de Platana :

```yaml
networks:
  platana-shared-network:
    external: true
```

Services rattachés à `platana-shared-network` : `mongodb`, `cv-service`,
`pricing-service`, `orchestrator`, `main-service`.

### 3.3 Modifications côté Dify (déjà en place)

Fichiers : `docker-compose.yaml` et `.env` du projet Dify
(`…\dify-main\docker`).

**Compose (`docker-compose.yaml`)** — les services `api` et `worker` sont
rattachés au réseau partagé :

```yaml
services:
  api:
    networks:
      - ssrf_proxy_network
      - default
      - platana-shared-network
  worker:
    networks:
      - ssrf_proxy_network
      - default
      - platana-shared-network

networks:
  platana-shared-network:
    external: true
```

**.env (`…\dify-main\docker\.env`)** — le proxy SSRF de Dify autorise les
microservices Platana à être joints par les workflows. Deux lignes ont été
étendues (au-delà des valeurs par défaut `127.0.0.1,localhost`) :

```dotenv
# Domains privés autorisés par le proxy SSRF (services Platana + Dify)
SSRF_PROXY_ALLOW_PRIVATE_DOMAINS=orchestrator,cv-service,pricing-service,api,localhost,127.0.0.1

# Plages privées autorisées
SSRF_PROXY_ALLOW_PRIVATE_IPS=host.docker.internal,172.16.0.0/12,192.168.0.0/16,10.0.0.0/8
```

> **Note sur le « SSRF désactivé ».** Le trafic sortant de Dify passe encore par
> le proxy Squid (`SSRF_PROXY_HTTP_URL=http://ssrf_proxy:3128`) mais la liste
> blanche a été élargie pour que les appels vers les services Platana ne soient
> plus bloqués. Pour **désactiver complètement** le proxy (sortie directe),
> vider ces deux variables puis recréer les conteneurs API :
>
> ```dotenv
> SSRF_PROXY_HTTP_URL=
> SSRF_PROXY_HTTPS_URL=
> ```
>
> ```powershell
> cd C:\Users\amine\OneDrive\Desktop\dify-main\docker
> docker compose up -d api worker
> ```
>
> Vérifier la config effective d'un conteneur : `docker exec docker-api-1 printenv | findstr SSRF_PROXY`

### 3.4 Point d'entrée Dify vu par Platana

Dans le `.env` de **Platana** :

```dotenv
DIFY_API_URL=http://api:5001/v1
```

`api` est le nom du service de l'API Dify dans son Compose, `5001` son port
interne. Comme `api` est sur `platana-shared-network`, le DNS `http://api:5001`
résout directement vers Dify — aucune IP `host.docker.internal` ni port exposé
nécessaire.

### 3.5 Vérifier la connexion

```powershell
docker network inspect platana-shared-network --format "{{range .Containers}}{{.Name}} {{end}}"
```

Doit lister les conteneurs Platana (`platana-mongodb`, `platana-cv`,
`platana-pricing`, `platana-orchestrator`, `platana-main`) **et** ceux de Dify
(`docker-api-1`, `docker-worker-1`).

---

## 4. Étape 1 — Configurer le `.env` de Platana

```powershell
Copy-Item .env.example .env
```

Variables obligatoires (détails dans [`DEPLOYMENT.md`](DEPLOYMENT.md)) :

| Variable | Exemple | Rôle |
|---|---|---|
| `DIFY_API_URL` | `http://api:5001/v1` | API Dify via le réseau partagé |
| `DIFY_EVAL_API_KEY` | `app-…` | Clé du workflow d'évaluation Dify |
| `DIFY_PUBLISH_API_KEY` | `app-…` | Clé du workflow de publication Dify |
| `GROQ_API_KEY` | `gsk_…` | Génération de listing GenAI (orchestrator) |
| `MONGO_URL` | `mongodb://mongodb:27017` | MongoDB interne |
| `JWT_SECRET` | base64 ≥ 32 octets | Signature des JWT (**à changer**) |
| `TRAINING_SERVICE_TOKEN` | chaîne longue | HMAC main ↔ training |
| `MLFLOW_BASIC_AUTH_USERS` | `admin:$2y$…` | Login MLflow (`htpasswd -nbB admin '<pass>'`) |

---

## 5. Étape 2 — Démarrer la stack

```powershell
cd …\platana-circular-economy
docker compose up -d --build
```

Attendre que **tous** les conteneurs soient `healthy` :

```powershell
docker compose ps
```

11 services attendus. Si un service tourne en boucle `starting`, voir la
[section Dépannage](#11-dépannage).

---

## 6. Étape 3 — Amorcer les données

Le premier démarrage crée automatiquement les comptes et le catalogue. Pour la
démo, amorcer aussi les **2000 échantillons d'entraînement pricing** :

```powershell
docker exec platana-training python scripts/seed_pricing_catalog.py --regenerate
```

> Les scripts (`seed_pricing_catalog.py`, `continuous_train.py`,
> `export_cv_onnx.py`) sont copiés dans l'image `training` sous `/app/scripts`.

Vérifier l'état de la base :

```powershell
docker exec platana-mongodb mongosh --quiet platana_circular_economy --eval "print(db.pricing_training_samples.countDocuments()); print(db.products.countDocuments())"
```

---

## 7. Étape 4 — Se connecter

| URL | Rôle |
|---|---|
| `http://localhost:8081` | Application (frontend) |
| `http://localhost:8081/api/docs` | Swagger main-service |
| `http://localhost:8081/mlflow` | MLflow (BasicAuth) |

Comptes par défaut (créés si la base est vide) :

| Rôle | Email | Mot de passe |
|---|---|---|
| Admin | `thomas.dubois@platana.fr` | `admin` |
| User | `user@example.com` | `user` |

> ⚠️ À changer en production.

---

## 8. Étape 5 — Parcours de démonstration complet

1. **Connexion** : se connecter en `user@example.com` / `user`.
2. **Nouveau produit** : créer un produit avec 1 à 5 photos (marque, modèle,
   année, prix neuf).
3. **Évaluation AI** : `main-service` envoie les photos à Dify (workflow
   d'évaluation) → note A–D, défauts, prix marché, décision
   (`RESALE_DIRECT` / `RECONDITION` / `RECYCLE`).
4. **Rapport PDF** : généré automatiquement et téléchargeable.
5. **Se connecter en admin** : `thomas.dubois@platana.fr` / `admin`.
6. **Validation** : file des produits à valider → corriger note / prix / coût /
   défauts → **Enregistrer**. Le rapport PDF est **régénéré**, l'échantillon
   étiqueté est écrit dans `pricing_training_samples`, et l'image exportée dans
   `data/processed/` (closed loop).
7. **Rejeter / ré-évaluer / publier** : actions admin sur le produit
   (publication via le workflow Dify → URL Shopify).
8. **Suivi** : tableau de bord (KPIs), alertes de drift (bannière si le seuil
   `maxAIFaults` est dépassé).

---

## 9. Étape 6 — Outils AI de l'admin (pages dédiées)

Trois pages admin utilisent directement les microservices internes (proxies
de `main-service`) :

| Page | Endpoint | Description |
|---|---|---|
| Grading | `POST /api/cv/grade` | Envoyer des photos → note + défauts (cv-service) |
| Pricing | `POST /api/pricing/predict` | Saisir grade/caractéristiques → prix prédit (pricing-service) |
| Product sheet | `POST /api/sheet/generate` | Formulaire libre → fiche produit + décision + canaux |

La fiche (`sheet`) réutilise les **mêmes seuils** que le pipeline
(`derive_decision`, refactoring coûts par défaut) : la décision affichée
correspond toujours aux règles métier.

---

## 10. Étape 7 — Retraining continu (pricing / CV)

Lancer un job depuis l'API (admin) :

```powershell
# Pricing
curl.exe -X POST http://localhost:8081/api/training/jobs -H "Authorization: Bearer <JWT_ADMIN>" -H "Content-Type: application/json" -d "{\"model\": \"pricing\"}"

# CV
curl.exe -X POST http://localhost:8081/api/training/jobs -H "Authorization: Bearer <JWT_ADMIN>" -H "Content-Type: application/json" -d "{\"model\": \"cv\"}"
```

- **Pricing** : exige un minimum de 500 échantillons dans
  `pricing_training_samples` (sinon le job est rejeté).
- **CV** : reprend du backbone actif sur `data/processed/smartphone_grading/`
  (ré-exporté depuis MongoDB avant chaque run) ; nécessite le **même**
  `shm_size: 2g` (les workers PyTorch en DataLoader échouent sans mémoire
  partagée suffisante).
- Les deux journalisent dans **MLflow** (`http://localhost:8081/mlflow`) et ne
  **promote que si la métrique s'améliore** (MAPE −0.05 pricing,
  macro-F1 +0.002 CV).
- À la promotion : artefacts immuables dans
  `models/*/checkpoints/versions/<id>/`, pointeur `latest.json` mis à jour,
  puis **hot-reload** du service d'inférence concerné
  (`POST /internal/reload`, HMAC `X-Training-Service-Token`).

Suivi en temps réel : page **Admin settings** (jobs, auto-refresh 30 s).

### Test rapide (1 époque)

Pour valider la chaîne sans attendre un entraînement complet, le script CV
accepte `--epochs` :

```powershell
docker exec platana-training python -m models.cv.train --mode continue --epochs 1
```

---

## 11. Dépannage

| Problème | Cause probable | Solution |
|---|---|---|
| `platana-training` crashe (DataLoader) | `shm_size` insuffisant | `shm_size: 2g` dans `docker-compose.yaml` (déjà en place) |
| Job pricing rejeté | < 500 échantillons | `docker exec platana-training python scripts/seed_pricing_catalog.py --regenerate` |
| `cv-service` / `pricing-service` → `503` | modèle non promu | Lancer un job / un entraînement, puis vérifier `models/*/checkpoints/latest.json` |
| CV ne sert pas le dernier modèle | pointeur `latest.json` absent | `docker exec platana-training python scripts/export_cv_onnx.py` |
| MLflow « no experiments » | expérience supprimée dans l'UI | Restaurer : `MlflowClient().restore_experiment('1')` (cv) / `('2')` (pricing) |
| Dify injoignable | réseau partagé absent | `docker network create platana-shared-network` puis redémarrer les deux stacks |
| Workflows Dify bloqués sur services privés | SSRF trop restrictif | Voir §3.3 (liste blanche ou désactivation totale du proxy) |
| Données « fantômes » en local | 2e MongoDB sur `127.0.0.1:27017` (install Windows) | Toujours interroger la base Docker : `docker exec platana-mongodb mongosh …` |
| `docker compose up` refusé (réseau) | `platana-shared-network` supprimé | `docker network create platana-shared-network` |

---

## 12. Arrêt / redémarrage / réinitialisation

```powershell
docker compose stop                 # arrêt (conserve les volumes)
docker compose start                # redémarrage rapide
docker compose up -d                # recréer si la config a changé
docker compose down                 # arrêt, garde les volumes
docker compose down -v              # + supprime volumes (les seeds repassent)
```

Le réseau externe `platana-shared-network`, lui, n'est **jamais** supprimé par
Compose.

---

## 13. Commandes utiles

```powershell
docker compose ps                       # état de santé
docker compose logs -f main-service     # logs d'un service
docker exec platana-training python scripts/continuous_train.py pricing --dry-run   # test sans entraîner
docker exec platana-training python scripts/export_cv_onnx.py                        # promouvoir le ONNX CV
docker exec platana-mongodb mongosh --quiet platana_circular_economy                # shell Mongo de la vraie base
```
