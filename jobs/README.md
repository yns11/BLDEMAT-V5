# Jobs Lakeflow — BLDEMAT V5 Professional

Les trois tâches sont déployées par `databricks.yml` sur compute serverless :

- `sync_referentiels_erp.py` historise le staging Delta, synchronise les tiers
  et DESADV par lots, gère les renommages/inactivations et recalcule les
  rapprochements dans les deux sens (`true` et `false`). Le flux DESADV vente
  est activable après validation des champs ERP `DespatchAdvice-Sales` et
  `salesordernum` ; il est désactivé par défaut.
- `dispatch_notifications.py` consomme une outbox par canal avec
  `FOR UPDATE SKIP LOCKED`, clé d'idempotence, backoff exponentiel et
  dead-letter après le nombre maximal de tentatives.
- `maintenance.py` marque en erreur les brouillons interrompus depuis plus de
  24 heures et clôt les exécutions de job restées `STARTED`.

Les URL de destination ne sont jamais passées en paramètres de job : elles
sont lues dans un secret scope Databricks selon la configuration de la table
`notification_canaux`.
