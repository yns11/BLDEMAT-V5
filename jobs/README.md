# Jobs Lakeflow — BLDEMAT

Deux tâches, à créer dans l'interface Databricks (Lakeflow Jobs ▸ Create job,
tâche « Python script » sur compute **serverless**). Il n'y a **plus de bundle
ni de job d'envoi de notifications** : les cartes Teams sont publiées
directement par les applications au moment de l'événement.

| Script | Rôle | Planification conseillée |
|---|---|---|
| `sync_referentiels_erp.py` | Historise le staging Delta, synchronise tiers et DESADV achat par lots (avec `statut_edi` issu de `messagestate`), gère renommages/inactivations et recalcule le rapprochement BL ⇄ DESADV dans les deux sens. | quotidienne, 05h30 |
| `maintenance.py` | Marque en erreur les brouillons interrompus depuis plus de 24 h et clôt les exécutions de job restées `STARTED`. | quotidienne, 04h00 |

`common.py` est partagé par les deux scripts (connexion Lakebase, journal
d'exécution, métriques). Il doit être déposé **dans le même dossier** que les
scripts dans l'espace de travail.

## Paramètres (job parameters)

Les scripts lisent les **job parameters** de la tâche (onglet *Parameters*,
Key/Value), via `dbutils.widgets` — plus d'`argparse`. Renseigner ces clés :

**`sync_referentiels_erp`**

| Key | Exemple / défaut |
|---|---|
| `catalogue_erp` | `emotors_data_platform` |
| `schema_erp` | `bronze_erp` |
| `catalogue_staging` | `emotors_data_champions` |
| `schema_staging` | `bl_demat_staging` |
| `pg_host` | *(PGHOST du projet Lakebase — obligatoire)* |
| `pg_database` | `databricks_postgres` |
| `pg_schema` | `bl_demat` |
| `lakebase_endpoint` | *(facultatif — déduit de `pg_host` si vide)* |
| `pg_user` | *(utilisateur ou service principal — obligatoire)* |
| `sales_desadv_enabled` | `false` (ou `true` pour le DESADV vente) |

**`maintenance`**

| Key | Exemple / défaut |
|---|---|
| `pg_host`, `pg_database`, `pg_schema`, `lakebase_endpoint`, `pg_user` | *(comme ci-dessus)* |
| `draft_hours` | `24` (1–168) |
| `stale_job_hours` | `6` (1–48) |

Chaque clé a une valeur par défaut ; la valeur saisie dans l'interface la
remplace. Une valeur manquante ou invalide fait échouer la tâche avec un
message explicite.

**`lakebase_endpoint` est facultatif** : laissé vide, il est retrouvé
automatiquement à partir de `pg_host` (parcours des projets/branches/endpoints
du workspace, comparaison du nom d'hôte). Le renseigner explicitement évite
ces appels de découverte. Le job s'authentifie auprès de Lakebase avec
`generate_database_credential` : aucun mot de passe n'est stocké.

## Dépendances

Déclarer dans l'environnement de la tâche serverless :

```
psycopg[binary]==3.2.3
databricks-sdk>=0.81.0
```
