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

## Paramètres communs

Passés en arguments de la tâche (`--nom valeur`) :

```
--pg-host            <PGHOST du projet Lakebase>
--pg-database        databricks_postgres
--pg-schema          bl_demat
--pg-user            <utilisateur ou service principal>
--lakebase-endpoint  projects/<id>/branches/<b>/endpoints/<ep>
```

Le job s'authentifie auprès de Lakebase avec
`generate_database_credential` : aucun mot de passe n'est stocké.

## Dépendances

Déclarer dans l'environnement de la tâche serverless :

```
psycopg[binary]==3.2.3
databricks-sdk>=0.81.0
```
