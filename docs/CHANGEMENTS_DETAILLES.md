# Changements détaillés — V4 vers V5 Professional

## 1. Synthèse

La V4 démontrait correctement les parcours fonctionnels mais restait fragile
pour une production durable : contrôle d'accès ouvert en cas d'erreur,
écritures fragmentées, images en base, jobs difficilement rejouables, secrets
potentiellement exposés, absence de migrations versionnées, de tests et de
pipeline CI/CD.

La V5 conserve les fonctions utiles et remplace les zones à risque par un
socle industrialisé.

## 2. Sécurité et identités

| V4 | V5 Professional | Effet |
|---|---|---|
| table de rôles vide = accès complet | RBAC strict, table vide = zéro droit | suppression du fail-open |
| erreur RBAC susceptible d'ouvrir l'accès | erreur = contexte indisponible et blocage | sécurité par défaut |
| identité locale implicite | SSO obligatoire ; `BL_LOCAL_USER` explicite en local | traçabilité fiable |
| contrôle surtout visuel | gardes serveur avant les actions sensibles | appel direct refusé |
| aucun bootstrap encadré | liste explicite `BL_BOOTSTRAP_ADMINS` | initialisation contrôlée |
| suppression possible du dernier admin | au moins un ADMIN_METIER obligatoire | anti-verrouillage métier |
| rôles sans expiration | colonne `expire_le` | accès temporaire |
| privilèges larges/non automatisés | script de GRANT par principal | moindre privilège |
| endpoints/contacts dans la configuration | variables de bundle et secrets | aucune valeur d'environnement en Git |
| jeton/reconnexion ad hoc | pool thread-safe et rotation avant expiration | stabilité Lakebase |
| brouillon persistant en localStorage | sessionStorage isolé par utilisateur | exposition locale réduite |
| prompt vision sans frontière forte | document déclaré non fiable, instructions embarquées ignorées | réduction du prompt injection |

Fichiers principaux : `rbac.py`, `identity.py`, `config.py`,
`grant_privileges.py`, `databricks.yml`.

## 3. Transactions et intégrité

| V4 | V5 Professional | Effet |
|---|---|---|
| connexion globale fragile | `ConnectionPool` psycopg | concurrence et recyclage |
| opérations multi-requêtes séparées | transactions atomiques | pas d'état partiel logique |
| audit « best effort » | audit dans la transaction métier | mutation non auditée impossible |
| dernier clic gagnant | verrouillage optimiste par `version` | conflits visibles |
| numéro unique global | unicité insensible à la casse par sens | achat/vente corrects |
| pages sans unicité d'index | `(id_bl,index_page)` unique | reprise idempotente |
| BL visible avant toutes ses pages | `BROUILLON` puis `COMPLET` | document incomplet masqué |
| restauration peu contrainte | cohérence suppression/auteur/date | historique cohérent |
| contrôle métier surtout UI | normalisation et validation dans le service | défense en profondeur |
| CRUD référentiel requête par requête | diff transactionnel + audit générique | cohérence de masse |
| données ERP éditables comme les autres | provenance et blocage des mutations ERP | source de vérité respectée |

Fichiers : `database.py`, `repository.py`, `validation.py`, migrations SQL.

## 4. Stockage documentaire

- Nouveau backend `VolumeStore` utilisant l'API Files du SDK Databricks.
- URI, SHA-256, taille, type MIME et index conservés en Lakebase.
- Écriture compensée si l'insertion SQL échoue.
- Vérification de l'empreinte à chaque téléchargement.
- Repli `database` réservé au local et compatibilité de lecture des anciens
  `BYTEA`.
- Limites configurables par page, document, nombre de pages et dimension.
- Réordonnancement et suppression de pages avant validation.
- Compression JPEG bornée et formats mobiles HEIC/HEIF supportés.

Fichiers : `storage.py`, `images.py`, `validation.py`, App Création.

## 5. Application Création

- Entête de contexte utilisateur/environnement/rôles.
- Parcours en stepper accessible.
- Opérations filtrées par rôles puis revérifiées avant écriture.
- Maximum de pages et taille totale affichés et contrôlés.
- Pages réordonnables/supprimables.
- Analyse de toutes les pages par lots de quatre, sans pages silencieusement
  ignorées.
- Fusion déterministe des résultats par lot.
- Rapprochement tiers par code stable avant le nom.
- Rapprochement BL exact ou inclusion seulement, sans fuzzy dangereux.
- Endpoint IA optionnel ; saisie manuelle toujours disponible.
- Valeurs IA journalisées seulement après une finalisation réussie.
- Création en deux phases `BROUILLON`/pages/`COMPLET`.
- Reprise des pages déjà enregistrées.
- Brouillon navigateur nettoyé après succès.
- Messages d'erreur compréhensibles.
- CSS mobile, cibles tactiles, focus visible et réduction des animations.

## 6. Application Administration

- Contexte global et arrêt en cas d'indisponibilité RBAC.
- Navigation filtrée par rôle.
- Tableau de bord Achat/Vente/Tous.
- Gestionnaire limité au contexte achat.
- DESADV chargés selon le bon sens.
- KPI BL et DESADV séparés afin d'éviter des dénominateurs incohérents.
- Heatmaps d'activité, évolution des NOK et top tiers.
- Documents `BROUILLON` exclus des vues opérationnelles.
- Pagination et sélection de colonnes.
- Écrans/filtres enregistrables.
- Fiche, suppression, restauration et passage à OK sous confirmation.
- Verrouillage optimiste sur toutes les mutations BL.
- Visionneuse avec contrôle d'intégrité des images.
- Export PDF.
- Audit détaillé par BL.
- Rapprochements achat et vente.
- Référentiels manuels sous contrôle de clés étrangères.
- Refus de modification d'une donnée ERP.
- Protection du dernier administrateur métier.
- Qualité IA par champ, modèle et version de prompt.
- État détaillé des livraisons de notifications.

## 7. Données et migrations

### Baseline V001

- 15 objets métier structurés avec types, contraintes, clés et index.
- provenance `ERP` / `MANUEL`, activité, horodatages et versions ;
- suppression logique cohérente ;
- statut documentaire ;
- stockage hybride Volume/BYTEA ;
- audits BL et génériques ;
- qualité IA ;
- écrans utilisateur ;
- outbox multi-canal ;
- exécutions de jobs ;
- vue de rapprochement.

### Upgrade V002

- migration additive depuis le schéma V4 ;
- aucun effacement de donnée ;
- ajout des colonnes de provenance, activité et version ;
- calcul SHA-256 des anciennes images ;
- nouvel index d'unicité par sens ;
- clé d'événement rétroalimentée ;
- recréation des clés étrangères tiers avec `ON UPDATE CASCADE` ;
- création autonome des nouveaux objets.

### Moteur de migration

- tri strict des versions ;
- verrou advisory pour empêcher deux migrations simultanées ;
- table `schema_migrations` ;
- checksum SHA-256 ;
- transaction par migration ;
- détection et baseline d'un schéma V4.

## 8. Synchronisation ERP

| V4 | V5 Professional |
|---|---|
| notebook et configuration séparés | tâche Python paramétrée par bundle |
| `collect()` global possible | `toLocalIterator()` et lots de 1 000 |
| statut d'appariement seulement mis à vrai | recalcul complet vrai/faux |
| suppression/écrasement sans provenance | `source_key`, `last_seen_at`, `actif` |
| pas de garde snapshot | arrêt si fournisseurs ou clients vides |
| état de job dispersé | `job_executions` + métriques JSON |
| pas de staging historisé | tables Delta append par `run_id` |
| données incomplètes | toutes les dates/statuts DESADV utiles |
| DESADV vente sans adaptateur | adaptateur vente optionnel, désactivé tant que le mapping ERP n'est pas validé |
| noms ERP instables | upsert par clé ERP stable et cascade des renommages |
| risque SQL de paramètre | validation des identifiants catalogue/schéma |

## 9. Notifications

- Modèle outbox événement + livraison par canal.
- Clé d'événement unique et clé de livraison idempotente.
- Canaux activables séparément.
- URL lue depuis Databricks Secrets.
- Claim concurrent avec `SKIP LOCKED`.
- Verrou de cinq minutes et récupération des verrous expirés.
- Timeout HTTP.
- Backoff exponentiel plafonné.
- Nombre maximal de tentatives.
- Statut `DEAD_LETTER`.
- Historique de la dernière erreur.
- Métriques d'exécution.

## 10. Déploiement et exploitation

- Bundle unique pour apps et jobs.
- Cibles `dev`, `rec`, `prod`.
- Paramètres d'environnement externalisés.
- Ressources Lakebase, Volume et Model Serving déclarées.
- Groupes `CAN_USE` et administrateurs `CAN_MANAGE`.
- Jobs exécutés par service principal et concurrence limitée à un run.
- Maintenance quotidienne des brouillons interrompus et jobs orphelins.
- Dépendances Python épinglées.
- Outils `migrate`, `grant_privileges`, `preflight`,
  `validate_release` et `sync_shared`.
- `Makefile` pour un contrôle reproductible.
- Logs structurés des jobs.
- Guide de déploiement, architecture et runbook ADMIN_METIER.

## 11. Qualité logicielle

- `pyproject.toml` et configuration Ruff.
- 24 tests unitaires initiaux couvrant :
  - configuration sécurisée ;
  - limites documentaires ;
  - normalisation des BL ;
  - rapprochement IA ;
  - fusion multi-lots ;
  - prompt injection ;
  - RBAC fail-closed ;
  - bootstrap ;
  - garde serveur ;
  - idempotence de payload notification.
  - traitement et compression d'image ;
  - export PDF ;
  - cloisonnement des URI de Volume.
- Workflow GitHub Actions :
  - installation déterministe ;
  - synchronisation du cœur ;
  - lint ;
  - tests ;
  - contrôle du paquet ;
  - validation structurelle du bundle.
- Contrôle de synchronisation bit à bit des copies `bl_core`.
- Analyse syntaxique de tous les fichiers Python.
- Validation YAML et séquence de migrations.
- Détection de valeurs d'environnement codées en dur.

## 12. UX et accessibilité

- Design system commun et jetons CSS.
- Stepper explicite dans le parcours de création.
- Barre de contexte et environnement visibles.
- Cibles tactiles d'au moins 44 px.
- Mise en page responsive mobile.
- Focus clavier visible.
- Respect de `prefers-reduced-motion`.
- Confirmations avant mutations.
- Erreurs actionnables et conflits explicites.
- Limites documentaires annoncées avant l'envoi.
- Séparation des KPI BL et DESADV.

## 13. Éléments supprimés ou remplacés

- Scripts SQL historiques non ordonnés : remplacés par `sql/migrations`.
- Ancien job de notifications « marque envoyé » : remplacé par l'outbox.
- Anciens notebooks/jobs JSON : remplacés par tâches Python et bundle.
- Configuration email/webhook codée : remplacée par secrets.
- LocalStorage persistant des images : remplacé par sessionStorage.
- Hypothèse « table RBAC vide = accès complet » : supprimée.
- Stockage par défaut des nouvelles images en `BYTEA` : remplacé par Volume.

## 14. Actions dépendantes de l'entreprise

Le code ne peut pas décider seul des éléments suivants :

- mapping final des tables et colonnes ERP ;
- groupes et personnes réelles ;
- endpoint vision et politique d'usage des données ;
- webhooks/flux et destinataires ;
- RPO, RTO, rétention et purge légale ;
- classification des données et exigences SSI ;
- dimensionnement et seuils d'alerte ;
- migration massive des images historiques ;
- valeur probante et signature électronique éventuelles.

Ces points sont listés comme prérequis de production, et non masqués comme des
fonctions déjà acquises.

## 15. Vérifications réalisées sur cette livraison

- parsing de tous les fichiers Python ;
- lint Ruff sans erreur ;
- 24 tests réussis ;
- YAML lisible ;
- migrations ordonnées ;
- cœur partagé synchronisé dans les deux apps ;
- absence de contact ou URL d'environnement codés dans les manifests ;
- archive reconstruite depuis la source contrôlée.
