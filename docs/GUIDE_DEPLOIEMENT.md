# Guide de déploiement

Ce guide décrit un déploiement contrôlé en développement, recette puis
production. Les commandes sont à exécuter depuis la racine du projet.

## 1. Prérequis

- Workspace Databricks avec Databricks Apps, Lakebase Autoscaling, Unity
  Catalog, Jobs serverless et Model Serving.
- Databricks CLI 1.9.0 ou version compatible plus récente.
- Python 3.11.
- Droit `CAN MANAGE` sur le projet Lakebase pour attacher la base aux apps.
- Droits de création/usage sur le catalogue et le schéma UC choisis.
- Groupes :
  - opérateurs de création ;
  - administrateurs métier ;
  - administrateurs techniques.
- Un service principal de jobs avec accès workspace.
- Un endpoint vision acceptant des images, si l'assistance IA est activée.

La syntaxe des ressources utilisée dans `databricks.yml` suit la
[référence officielle des ressources de bundle](https://docs.databricks.com/aws/en/dev-tools/bundles/resources).

## 2. Préparer les ressources

### 2.1 Lakebase

Créer un projet Lakebase Autoscaling, une branche par environnement et une
base. Relever :

- resource name de la branche ;
- resource name de la base ;
- resource name du compute endpoint ;
- `PGHOST` ;
- nom de base, généralement `databricks_postgres`.

### 2.2 Unity Catalog

Créer un volume, par exemple :

```sql
CREATE CATALOG IF NOT EXISTS main;
CREATE SCHEMA IF NOT EXISTS main.bldemat;
CREATE VOLUME IF NOT EXISTS main.bldemat.documents;
```

Le chemin transmis au bundle est `main.bldemat.documents`, sans `/Volumes/`.
Le bundle accorde l'écriture à l'app Création et la lecture à
l'Administration.

### 2.3 Groupes et service principal

Créer ou identifier les groupes et le service principal de jobs. Accorder au
service principal :

- accès au workspace ;
- `USE CATALOG`, `USE SCHEMA`, `SELECT` sur les tables/vues ERP ;
- création et écriture dans le schéma de staging ;
- lecture des secrets de notification utilisés.

### 2.4 Notifications

Créer le scope `bldemat` et, selon les canaux utilisés, les secrets :

```bash
databricks secrets create-scope bldemat
databricks secrets put-secret bldemat teams-webhook-url
databricks secrets put-secret bldemat power-automate-url
```

Ne placer aucune URL dans Git, le bundle ou une variable de job.

## 3. Configurer les variables

Copier le modèle :

```bash
cp deployment/bundle.env.example deployment/bundle.env
```

Renseigner toutes les valeurs puis charger le fichier :

```bash
set -a
source deployment/bundle.env
set +a
```

Le fichier `deployment/bundle.env` est ignoré par Git. Pour la CI/CD, stocker
les variables dans le coffre de la plateforme.

`BUNDLE_VAR_bootstrap_admins` contient initialement l'email du responsable du
bootstrap. Il est retiré après l'attribution d'un vrai rôle
`ADMIN_METIER`.

## 4. Contrôler la source

Créer un environnement virtuel et installer les dépendances :

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
make check
```

`make check` synchronise `shared/bl_core` dans les deux apps, exécute lint,
tests et contrôles de release.

## 5. Préparer la base

S'authentifier comme propriétaire de migration :

```bash
databricks auth login --host "$DATABRICKS_HOST"
export PGHOST="$BUNDLE_VAR_pg_host"
export PGDATABASE="$BUNDLE_VAR_pg_database"
export PGUSER="votre.email@entreprise.fr"
export PGPORT=5432
export PGSSLMODE=require
export LAKEBASE_ENDPOINT="$BUNDLE_VAR_lakebase_endpoint"
export BL_PG_SCHEMA="$BUNDLE_VAR_pg_schema"
export BL_ENVIRONMENT=dev
export BL_IMAGE_BACKEND=database
python tools/migrate.py
```

Le backend `database` est uniquement utilisé ici pour satisfaire le contrôle
local de configuration ; la configuration des apps reste `volume`.

Comportement :

- base neuve : exécution de `V001` ;
- base V4 détectée : baseline de `V001` puis exécution additive de `V002` ;
- checksum différent pour une version déjà appliquée : arrêt immédiat.

Pour une montée depuis V4, faire d'abord un test sur une branche Lakebase
clonée et conserver un point de retour. Les anciennes images `BYTEA` restent
lisibles.

## 6. Valider et déployer le bundle

```bash
databricks bundle validate -t dev
databricks bundle deploy -t dev
```

Le déploiement crée ou met à jour :

- deux Databricks Apps ;
- le rattachement Lakebase, Volume et Model Serving ;
- trois jobs serverless ;
- leurs horaires, paramètres, identités et permissions.

La ressource Postgres crée automatiquement les rôles des apps et leur accorde
initialement `CONNECT` et `CREATE`, conformément au
[fonctionnement des ressources Lakebase d'Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/lakebase).
L'étape suivante réduit ces privilèges.

## 7. Créer le rôle OAuth du job

Dans l'éditeur SQL Lakebase, avec un administrateur :

```sql
CREATE EXTENSION IF NOT EXISTS databricks_auth;
SELECT databricks_create_role(
  '<CLIENT_ID_SERVICE_PRINCIPAL_JOBS>',
  'SERVICE_PRINCIPAL'
);
GRANT CONNECT ON DATABASE databricks_postgres
  TO "<CLIENT_ID_SERVICE_PRINCIPAL_JOBS>";
```

Les rôles des apps sont normalement créés par leurs ressources. Relever leurs
`DATABRICKS_CLIENT_ID` dans les détails des apps.

## 8. Appliquer le moindre privilège

Avec le même environnement PG que pour la migration :

```bash
python tools/grant_privileges.py \
  --creation-role "<CLIENT_ID_APP_CREATION>" \
  --admin-role "<CLIENT_ID_APP_ADMINISTRATION>" \
  --jobs-role "<CLIENT_ID_SERVICE_PRINCIPAL_JOBS>"
```

Le script :

- retire `CREATE` sur la base et le schéma ;
- accorde uniquement les tables et opérations nécessaires ;
- accorde les séquences requises ;
- sépare clairement Création, Administration et Jobs.

Ne pas utiliser le même principal pour les trois responsabilités.

## 9. Initialiser le RBAC

1. Ouvrir l'app Administration avec l'adresse présente dans
   `bootstrap_admins`.
2. Aller dans **Gestion → Rôles**.
3. Créer au moins deux attributions `ADMIN_METIER` nominatives.
4. Ajouter les autres rôles.
5. Vider `BUNDLE_VAR_bootstrap_admins`.
6. Redéployer le bundle.
7. Vérifier qu'un utilisateur sans rôle reçoit bien un refus.

Le dernier rôle `ADMIN_METIER` déclaré ne peut pas être supprimé depuis
l'interface.

## 10. Activer les canaux

Après création des secrets et autorisation du principal de jobs :

```sql
UPDATE bl_demat.notification_canaux
SET actif = true, modifie_le = now()
WHERE code IN ('TEAMS', 'POWER_AUTOMATE');
```

N'activer que les canaux réellement configurés. Exécuter le job
`dispatch-notifications` manuellement et vérifier
`notification_livraisons`.

## 11. Adapter et tester la synchronisation ERP

Les trois sources attendues sont :

- `siledimessage` ;
- `purch_table` et `sales_table` ;
- `siledi_item_line`.

Valider les colonnes et les conventions dans
`jobs/sync_referentiels_erp.py`. La première exécution écrit un snapshot
horodaté dans le schéma staging puis met à jour Lakebase en transaction.

Le DESADV achat est actif par défaut. Le DESADV vente peut être activé avec
`BUNDLE_VAR_sales_desadv_enabled=true` uniquement si l'ERP expose bien
`messagetype='DespatchAdvice-Sales'` et `siledi_item_line.salesordernum`.
Sinon, la vue vente reste alimentable manuellement sans que le job ne désactive
ces lignes.

Garde-fous : si le snapshot fournisseur ou client est vide, la transaction
est annulée. Si un snapshot DESADV est vide, les DESADV actifs correspondants
sont conservés. Après un run, vérifier :

```sql
SELECT * FROM bl_demat.job_executions
ORDER BY started_at DESC LIMIT 10;
```

## 12. Préflight et recette

Depuis un poste authentifié :

```bash
export BL_ENVIRONMENT=dev
export BL_IMAGE_BACKEND=volume
export BL_VOLUME_PATH="/Volumes/$BUNDLE_VAR_documents_volume"
python tools/preflight.py
```

Recette minimale :

1. utilisateur sans rôle : accès refusé ;
2. LOG : création réception et expédition, pas d'administration ;
3. APPROS : archivage achat, modification BL réception ;
4. ADV : miroir vente ;
5. FINANCE : lecture seule ;
6. ADMIN_METIER : toutes les vues et écritures ;
7. création de deux pages, réordonnancement puis finalisation ;
8. doublon même sens refusé, même numéro sens opposé accepté ;
9. modification concurrente refusée ;
10. image lue et empreinte valide ;
11. extraction IA indisponible : saisie manuelle non bloquée ;
12. DESADV rapproché puis déréconcilié lors d'un snapshot suivant ;
13. notification envoyée, retry puis dead-letter simulés ;
14. audit BL et audit référentiel consultables ;
15. export PDF lisible sur mobile et poste bureautique.

## 13. Promotion recette et production

```bash
databricks bundle validate -t rec
databricks bundle deploy -t rec

databricks bundle validate -t prod
databricks bundle deploy -t prod
```

Utiliser des branches Lakebase, Volumes, groupes, secrets et service
principals distincts par environnement. Ne jamais promouvoir des données de
test en production.

## 14. Retour arrière

- Code : redéployer le tag ou l'artefact précédent.
- Apps/Jobs : le bundle réapplique l'état de la version choisie.
- Base : les migrations sont forward-only. Restaurer/cloner la branche
  préparée avant migration uniquement si aucune écriture V5 ne doit être
  conservée.
- Données : ne jamais supprimer les nouvelles colonnes en urgence ; l'ancienne
  version peut ignorer les ajouts.
- Volume : conserver les objets ; les références restent auditables.

Documenter la décision, l'heure, l'auteur et les contrôles après retour.

## 15. Passage en production

La mise en production est autorisée lorsque :

- CI verte ;
- recette métier signée ;
- revue SSI et données personnelles terminée ;
- sauvegarde/restauration testée ;
- tests de charge conformes ;
- alertes et astreinte renseignées ;
- RPO/RTO et conservation validés ;
- runbook ADMIN_METIER transmis.
