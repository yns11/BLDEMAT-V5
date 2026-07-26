# BLDEMAT V5 Professional

Solution Databricks prête à industrialiser pour numériser, enrichir, rapprocher,
rechercher et administrer les bordereaux de livraison (BL) achat et vente.

## Contenu

- `src/app_creation` : parcours terrain Streamlit en quatre étapes, capture
  multi-page, traitement d'image, extraction vision assistée et validation.
- `src/app_administration` : recherche, tableaux de bord, rapprochement
  BL/DESADV, référentiels, audit, qualité IA, rôles et notifications.
- `shared/bl_core` : cœur partagé : configuration, RBAC, transactions,
  repository, stockage Volume, validations et design system.
- `jobs` : synchronisation ERP historisée, dispatcher de notifications
  idempotent et maintenance des exécutions interrompues.
- `sql/migrations` : baseline professionnelle et montée contrôlée depuis V4.
- `tools` : migration, privilèges minimaux, préflight, synchronisation du cœur
  partagé et contrôle du paquet.
- `databricks.yml` : bundle Databricks `dev` / `rec` / `prod`.
- `tests` et `.github/workflows/ci.yml` : tests, lint et validation continue.
- `docs` : architecture, déploiement, exploitation ADMIN_METIER et inventaire
  détaillé des changements.

## Principes d'architecture

- Lakebase PostgreSQL porte les métadonnées, transactions et audits.
- Un Volume Unity Catalog porte les images ; Lakebase ne conserve que URI,
  empreinte SHA-256 et taille.
- Les apps utilisent leur identité de service Databricks et des credentials
  OAuth Lakebase renouvelés ; aucun mot de passe n'est stocké.
- Le RBAC est strict et fermé par défaut. Un utilisateur sans rôle n'a aucun
  droit, y compris lorsque la table de rôles est vide ou indisponible.
- Les mutations critiques sont transactionnelles et auditées ; les
  modifications concurrentes utilisent un numéro de version.
- Les synchronisations et notifications sont rejouables et observables.

## Démarrage

1. Lire `docs/GUIDE_DEPLOIEMENT.md`.
2. Copier `deployment/bundle.env.example` vers un fichier local non versionné
   et renseigner les variables.
3. Exécuter `make check`.
4. Valider puis déployer le bundle avec le Databricks CLI.
5. Exécuter les migrations et appliquer les privilèges minimaux comme indiqué
   dans le guide.
6. Lancer `python tools/preflight.py`, puis réaliser la recette décrite.

## Documentation

- [Guide de déploiement](docs/GUIDE_DEPLOIEMENT.md)
- [Architecture et exploitation](docs/ARCHITECTURE.md)
- [Guide ADMIN_METIER](docs/GUIDE_ADMIN_METIER.md)
- [Développement local](docs/DEVELOPPEMENT_LOCAL.md)
- [Rapport de vérification](docs/RAPPORT_VERIFICATION.md)
- [Changements détaillés](docs/CHANGEMENTS_DETAILLES.md)
- [Cahier des charges d'origine](docs/CAHIER_DES_CHARGES.md)

Version : **5.0.0** — Python 3.11 — Streamlit 1.49.1 — Lakebase Autoscaling —
Declarative Automation Bundles.
