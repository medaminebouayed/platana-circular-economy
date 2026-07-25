# Projet 3 — Circular Economy Intelligence : Refurbishment & Resale Engine

*CV multi-vues · Pricing prédictif · Optimisation combinatoire · GenAI*


## 1. Contexte et problématique

Les produits retournés en SAV et jugés non réparables économiquement sont aujourd'hui souvent mis
au rebut, alors qu'une partie pourrait être reconditionnée et revendue. Les obligations
réglementaires liées à l'économie circulaire et à la responsabilité élargie du producteur (REP)
augmentent, ce qui pousse les distributeurs à chercher des solutions pour valoriser ces retours plutôt
que de les détruire.


## 2. Objectifs du projet


### Objectif général

Construire un système qui évalue automatiquement l'état d'un produit retourné, décide de son
potentiel de reconditionnement, propose un prix de revente optimal, génère la fiche produit, et
optimise la logistique de redistribution.


### Objectifs spécifiques

- Automatiser le grading de l'état d'un produit à partir de photos multi-angles
- Prédire un prix de revente cohérent avec le marché et l'état du produit
- Générer automatiquement une fiche produit de revente prête à publier
- Optimiser l'allocation entre reconditionnement, stockage et canal de revente


## 3. Périmètre fonctionnel


> **Périmètre**


**Inclus dans le périmètre (MVP) :**
- Grading de l'état du produit sur une catégorie de produits limitée
- Modèle de pricing basique sur données historiques disponibles
- Génération de fiche produit textuelle
- Recommandation simple d'allocation (reconditionner/revendre/détruire)

**Exclus du périmètre (extensions futures) :**
- Publication automatique multi-canal en temps réel sans validation
- Optimisation logistique complète multi-entrepôts avec RL
- Intégration avec plusieurs marketplaces externes simultanément


## 4. Utilisateurs et parties prenantes

| Rôle | Besoin vis-à-vis du système |
|---|---|
| Responsable reconditionnement | Décision rapide et fiable sur la reconditionnabilité d'un produit |
| Équipe revente/e-commerce | Fiche produit prête à publier avec un prix cohérent |
| Direction RSE/conformité | Reporting sur le volume de produits valorisés plutôt que détruits |


## 5. Architecture et pipeline détaillé

```
[Produit retourné + photos multi-angles]
        ↓
[CV : grading de l'état du produit (note A/B/C/D) par fusion multi-vues]
        ↓
[Décision reconditionnable ? oui/non + estimation du coût de remise en état]
        ↓
[Modèle de pricing : prédiction du prix de revente optimal]
        ↓
[GenAI : génération automatique de la fiche produit]
        ↓
[Optimisation logistique : où reconditionner, où stocker, quel canal de revente]
        ↓
[Agent + MCP : publication/coordination sur les canaux de revente]
        ↓
[Suivi : prix prédit vs prix de vente réel → boucle de feedback économique]
```


## 6. Spécifications fonctionnelles détaillées

| ID | Fonctionnalité | Description | Priorité |
|---|---|---|---|
| F01 | Grading multi-vues | Note d'état à partir de plusieurs photos du même produit | Haute |
| F02 | Décision reconditionnable | Seuil de coût de remise en état vs valeur estimée | Haute |
| F03 | Prédiction de prix | Prix de revente optimal selon état, saisonnalité, historique | Haute |
| F04 | Génération de fiche produit | Titre, description, points forts/attention générés automatiquement | Moyenne |
| F05 | Optimisation logistique | Allocation reconditionnement/stockage/canal | Moyenne |
| F06 | Suivi de performance pricing | Comparaison prix prédit vs prix de vente réel | Moyenne |


## 7. Spécification des données

| Donnée | Source | Format | Remarque |
|---|---|---|---|
| Photos multi-angles de produits retournés | À collecter ou existant selon disponibilité | Images | Nécessite un protocole de prise de vue standardisé |
| Historique de revente (si existant) | Système de revente/occasion, si disponible chez le client | Structuré | Sinon, démarrer avec des données de marché externes comparables |
| Coûts de reconditionnement | Données internes ateliers | Structuré | Nécessaire pour la décision de reconditionnabilité |


## 8. Exigences non-fonctionnelles

| Catégorie | Exigence |
|---|---|
| Cohérence économique | Le prix prédit ne doit jamais être inférieur au coût de reconditionnement estimé |
| Traçabilité | Historique des décisions de grading pour audit qualité |
| Adaptabilité | Le modèle de pricing doit pouvoir être ré-entraîné facilement face aux évolutions de marché |


## 9. Actions disponibles pour l'agent IA

| Action | Fonction | Serveur MCP |
|---|---|---|
| Classer le produit (grade) | Détermine l'état et la reconditionnabilité | Service CV interne |
| Estimer le prix de revente | Propose un prix optimal selon état et marché | Service pricing interne |
| Publier l'annonce | Diffuse la fiche produit sur le(s) canal(aux) choisi(s) | MCP "marketplace" |
| Planifier la logistique | Décide du site de reconditionnement et du transport | MCP "logistics" |


## 10. Outils par composant

| Composant | Outils |
|---|---|
| CV grading | Vision Transformer (ViT) fine-tuné, fusion multi-images |
| Pricing | Gradient Boosting (XGBoost/LightGBM) |
| Génération de fiche produit | LLM génératif |
| Optimisation logistique | Google OR-Tools, éventuellement RL pour l'apprentissage continu |
| Publication | Agent LLM + MCP |


> **Outils Ops à découvrir**


**Outils Ops à découvrir dans ce projet :**
| Outil | Ce que tu découvres concrètement |
|---|---|
| Pipeline hybride batch + temps réel | Grading en batch, publication réactive |
| MLflow | Versioning du modèle de pricing, sensible au marché |
| Monitoring économique | Suivi de l'écart prix prédit vs prix réel |
| Intégration API marketplace | Gestion de contrats d'interface externes |
| CI/CD pour modèles de pricing | Déploiement sans casser les prix en production |


## 11. Phasage et jalons

| Phase | Contenu | Durée indicative |
|---|---|---|
| Phase 0 — Cadrage | Choix de la catégorie produit pilote, collecte des premières données | 1-2 semaines |
| Phase 1 — CV grading | Modèle de notation d'état fonctionnel | 3 semaines |
| Phase 2 — Pricing + génération de fiche | Prédiction de prix et fiche produit automatique | 3 semaines |
| Phase 3 — Optimisation logistique simple | Recommandation d'allocation basique | 2 semaines |
| Phase 4 — Suivi et consolidation | Boucle de feedback pricing, documentation, démonstration | 2 semaines |


## 12. Livrables attendus

- Modèle de grading CV fonctionnel sur la catégorie pilote
- Modèle de pricing avec ses métriques de précision
- Générateur automatique de fiche produit
- Rapport de stage incluant l'estimation du gain économique potentiel


## 13. Indicateurs de succès (KPIs)

| KPI | Cible indicative |
|---|---|
| Précision du grading vs évaluation humaine | À benchmarker sur un échantillon annoté |
| Écart moyen prix prédit vs prix de vente réel | À minimiser au fil des itérations |
| Taux de produits valorisés plutôt que détruits | Indicateur d'impact RSE direct |


> **Risques identifiés**


**Risques identifiés :**
- Peu de données historiques de revente disponibles au démarrage → s'appuyer sur des données de marché externes comparables
- Variabilité de l'éclairage/angle des photos → nécessite un protocole de prise de vue standardisé
- Risque de sous-évaluation ou sur-évaluation du prix → prévoir une validation humaine sur les premiers cycles
