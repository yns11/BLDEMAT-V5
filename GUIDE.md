# BLDEMAT — Guide de déploiement et de fonctionnement

Solution de dématérialisation des bordereaux de livraison (BL) : deux
applications Databricks (Streamlit), une base Lakebase (PostgreSQL managé),
deux jobs, et des notifications Microsoft Teams envoyées en temps réel.

**Principe de configuration** : *tout* est dans les deux fichiers `app.yaml`.
Pas de bundle, pas de secret scope, pas de valeur en dur dans le code.

---

# 1. Vue d'ensemble

```
   Smartphone/PC                                  Teams (canal « Récep BL »)
        │                                                    ▲
        ▼                                                    │ carte
┌──────────────────────┐   pages + métadonnées   ┌────────────┴─────────┐
│ App CRÉATION DE BL   │────────────────────────▶│                      │
│ (opérateurs au quai) │                         │      LAKEBASE        │
└──────────────────────┘                         │  (PostgreSQL managé) │
        ▲ IA vision                              │   schéma bl_demat    │
        │                                        │                      │
┌───────┴──────────────┐                         │                      │
│ Endpoint model       │   ┌─────────────────────┤                      │
│ serving (Claude)     │   │  App ADMINISTRATION │                      │
└──────────────────────┘   │  (appros, ADV,      │                      │
                           │   finance, admins)  └──────────┬───────────┘
                           └──────────┬─────────────────────┘
                                      │                     ▲
                                      ▼ carte Teams         │ jobs quotidiens
                              Teams (EDI NOK → OK)   ┌──────┴──────────────┐
                                                     │ sync_referentiels   │
                                                     │ maintenance         │
                                                     └─────────────────────┘
```

| Composant | Rôle |
|---|---|
| **App Création** | Saisie au quai : type d'opération → scan → champs pré-remplis par IA → validation. Notifie Teams à chaque **nouvelle réception**. |
| **App Administration** | Pilotage (tableau de bord, KPI), vues BL/DESADV/Rapprochement, référentiels, rôles. Notifie Teams au **passage EDI NOK → OK**. |
| **Lakebase** | Métadonnées **et** images (BYTEA) dans le schéma `bl_demat`. |
| **Model serving** | Modèle vision qui lit les BL scannés (optionnel). |
| **Jobs** | Synchronisation ERP quotidienne + maintenance. |

---

# 2. Déploiement pas à pas

## Étape 1 — Créer le projet Lakebase

Databricks ▸ **Compute / Database (Lakebase)** ▸ *Create project*, par exemple
`demat-bl`. Noter le **PGHOST** (onglet Connection details) : il servira aux jobs.

## Étape 2 — Créer le schéma et les tables

Ouvrir l'**éditeur SQL du projet Lakebase** (⚠️ pas l'éditeur SQL Spark) sur la
branche `production`, puis exécuter :

| Cas | Fichier(s) à exécuter, dans l'ordre |
|---|---|
| Installation neuve | `sql/migrations/V001__baseline_professionnelle.sql` |
| Installation existante (déjà en V001) | `V002__notifications_directes.sql` puis `V003__mention_teams_id.sql` |

Les scripts sont **idempotents** (ré-exécutables sans risque) et utilisent
directement le schéma `bl_demat` : rien à remplacer. Pour un autre nom de
schéma, faire un rechercher/remplacer de `bl_demat` et aligner `BL_PG_SCHEMA`
dans les deux `app.yaml`.

## Étape 3 — Créer les deux applications

Compute ▸ **Apps** ▸ *Create app* (app personnalisée), deux fois :
`bl-creation` et `bl-administration`.

Sur **chaque** app, onglet **Edit ▸ Resources ▸ + Add resource** :

| Ressource | Paramètres | Sur quelle app |
|---|---|---|
| **Database** | projet Lakebase, branche `production`, base `databricks_postgres`, permission **Can connect and create**, clé **`postgres`** | les deux |
| **Serving endpoint** | le modèle vision (ex. `databricks-claude-opus-4-8`), permission **Can query** | Création uniquement |

> Les variables `PGHOST`, `PGDATABASE`, `PGUSER`… sont alors injectées
> automatiquement : **ne pas** les écrire dans `app.yaml`.

## Étape 4 — Déployer le code

Déployer le dossier `src/app_creation` sur l'app Création et
`src/app_administration` sur l'app Administration (chaque dossier est
autonome : il embarque sa copie de `bl_core`).

> Après toute modification de `shared/bl_core`, resynchroniser les copies :
> `cp shared/bl_core/*.py src/app_creation/bl_core/` (idem administration).

## Étape 5 — Accorder les droits SQL

Récupérer le **client ID du service principal** de chaque app (page de l'app ▸
onglet *Authorization*), puis dans l'éditeur SQL Lakebase :

```sql
-- App Création
GRANT USAGE ON SCHEMA bl_demat TO "<SP_APP_CREATION>";
GRANT SELECT, INSERT ON bl_demat.suivi_bl, bl_demat.pieces_jointes_bl,
  bl_demat.audit_bl, bl_demat.qualite_extraction, bl_demat.notifications
  TO "<SP_APP_CREATION>";
GRANT UPDATE ON bl_demat.suivi_bl, bl_demat.notifications TO "<SP_APP_CREATION>";
GRANT SELECT ON bl_demat.base_tiers, bl_demat.base_desadv, bl_demat.quais,
  bl_demat.pla, bl_demat.adresses, bl_demat.sites_logistiques,
  bl_demat.portefeuilles, bl_demat.gestionnaires, bl_demat.roles_utilisateurs
  TO "<SP_APP_CREATION>";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA bl_demat TO "<SP_APP_CREATION>";

-- App Administration (CRUD complet)
GRANT USAGE ON SCHEMA bl_demat TO "<SP_APP_ADMINISTRATION>";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA bl_demat
  TO "<SP_APP_ADMINISTRATION>";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA bl_demat
  TO "<SP_APP_ADMINISTRATION>";
```

## Étape 6 — Créer le flux Teams (notifications)

1. Dans Teams, ouvrir le **canal** cible (ex. « Récep BL ») ▸ **+** ▸
   application **Workflows** ▸ modèle **« Envoyez des alertes webhook à un
   canal »** (*Post to a channel when a webhook request is received*).
2. Valider ; Teams affiche une **URL de webhook** : la copier.
3. La coller dans les `app.yaml` :
   - `BL_TEAMS_WEBHOOK_RECEPTION` (app Création),
   - `BL_TEAMS_WEBHOOK_EDI` (app Administration).
   La **même URL** peut servir aux deux (même canal).
4. **Ajouter au canal tous les gestionnaires** susceptibles d'être mentionnés :
   une mention ne notifie que si la personne est membre.

### Rendre les mentions cliquables

**Point clé** : écrire soi-même `msteams.entities` dans une carte envoyée par
Power Automate **ne fonctionne pas** — le Flow bot rejette la carte avec
« One or more mention entity could not be found in card text », ou affiche le
nom sans le rendre cliquable. La seule méthode fiable est l'action Teams
**« Obtenir un jeton @mention pour un utilisateur »** : elle prend l'**e-mail**
de la personne (surtout pas son AAD Object ID) et renvoie un jeton que le
Flow bot transforme lui-même en vraie mention.

L'application est déjà prête pour cela (`BL_TEAMS_MENTION_MODE=flow`) : elle
envoie, à la racine de la charge utile, un tableau `mentions` avec les
e-mails des gestionnaires, et place le marqueur `{{MENTIONS}}` dans la carte.
**Il reste à faire remplacer ce marqueur par le flux** — sans toucher au
schéma du déclencheur.

#### Modification du flux (5 actions à ajouter)

Power Automate ▸ Mes flux ▸ *Envoyer des alertes webhook à …* ▸ **Modifier**.

1. **Après le déclencheur**, ajouter *Initialiser une variable* :
   - Nom : `JetonsMentions` · Type : **Chaîne** · Valeur : *(vide)*

2. Ajouter *Appliquer à chacun* :
   - Entrée (mode expression) : `triggerBody()?['mentions']`
   > Le schéma du déclencheur n'a pas besoin de déclarer `mentions` : une
   > expression lit toujours le corps **brut** de la requête.

3. **Dans** cette boucle, ajouter l'action Teams
   **« Obtenir un jeton @mention pour un utilisateur »** :
   - *Utilisateur* : `item()` (l'e-mail courant)

4. Toujours dans la boucle, ajouter *Ajouter à la variable chaîne* :
   - Nom : `JetonsMentions`
   - Valeur : la sortie de l'action précédente (**@mention token**), suivie
     d'un espace

5. Dans l'action **« Publier une carte dans un chat ou un canal »** déjà
   présente, remplacer le contenu du champ *Corps du message* par
   l'expression :

   ```
   json(replace(string(item()?['content']), '{{MENTIONS}}', variables('JetonsMentions')))
   ```

   > Dans la branche « si les pièces jointes sont nulles », l'expression
   > équivalente est :
   > `json(replace(string(variables('Body')), '{{MENTIONS}}', variables('JetonsMentions')))`

6. **Enregistrer**, créer un BL de test : le nom du gestionnaire doit
   maintenant apparaître en mention cliquable, et la personne reçoit une
   notification Teams.

#### Vérifier / diagnostiquer

App Administration ▸ **Gestion ▸ Gestionnaires** ▸ **🧪 Tester les mentions
Teams** : la carte de test publie quatre lignes — la n° 1 utilise la méthode
« Flow bot » (celle ci-dessus), les n° 2 à 4 les identifiants écrits par
l'application. **Seule la ligne réellement cliquable compte.** En principe
c'est la n° 1 une fois le flux modifié.

Rappels :

- L'action exige l'**e-mail** ; le champ *Teams ID* du référentiel ne sert
  qu'au mode `entities`, à ne conserver que s'il fonctionne chez vous.
- Seuls les blocs **TextBlock** et **FactSet** affichent une mention dans une
  carte adaptative.
- La personne doit être **membre de l'équipe/du canal**.
- Si vous ne pouvez pas modifier le flux du tout : passer
  `BL_TEAMS_MENTION_MODE` à `texte` — les gestionnaires sont alors cités en
  clair, sans notification personnelle.

## Étape 7 — Renseigner les `app.yaml`

Un extrait des variables à ajuster (le reste a des valeurs par défaut saines) :

| Variable | App | Valeur |
|---|---|---|
| `BL_ENVIRONMENT` | les deux | `prod` |
| `BL_RBAC_MODE` | les deux | `strict` |
| `BL_BOOTSTRAP_ADMINS` | les deux | votre e-mail (secours) |
| `BL_PG_SCHEMA` | les deux | `bl_demat` |
| `BL_LLM_ENDPOINT` | Création | nom de l'endpoint, ou vide pour désactiver l'IA |
| `BL_TEAMS_WEBHOOK_RECEPTION` | Création | URL du flux Teams |
| `BL_TEAMS_WEBHOOK_EDI` | Administration | URL du flux Teams |

Puis **Deploy**.

## Étape 8 — Paramétrer les accès et le référentiel

1. Page de chaque app ▸ **Permissions** ▸ ajouter les utilisateurs/groupes
   (**Can use**). C'est le 1ᵉʳ niveau : qui peut *ouvrir* l'app.
2. Ouvrir l'app Administration (vous êtes admin via `BL_BOOTSTRAP_ADMINS`) ▸
   **Gestion ▸ Rôles** : attribuer les rôles (voir §4). **S'attribuer
   ADMIN_METIER en premier**, puis vider `BL_BOOTSTRAP_ADMINS` et redéployer.
3. **Gestion ▸ Gestionnaires** : renseigner pour chacun le **nom affiché** et
   l'**e-mail Microsoft 365** (indispensable aux mentions Teams).
4. **Gestion ▸ Portefeuilles** : associer chaque gestionnaire à ses
   fournisseurs — c'est ce lien qui détermine **qui est mentionné**.
5. **Gestion ▸ PLA** : quai par fournisseur (pré-remplissage automatique).

## Étape 9 — Créer les jobs (facultatif mais recommandé)

Lakeflow Jobs ▸ *Create job* ▸ tâche **Python script** sur **serverless**,
pour `jobs/sync_referentiels_erp.py` (quotidien, 05h30) et
`jobs/maintenance.py` (quotidien, 04h00). Détails, paramètres et dépendances :
`jobs/README.md`.

---

# 3. Fonctionnement des notifications

## 3.1 Nouvelle réception → carte adaptative avec mentions

```
Opérateur valide un BL de type « Nouvelle réception »
        │
        ├─▶ 1. BL + pages enregistrés dans Lakebase       (transaction)
        ├─▶ 2. Ligne écrite dans « notifications »        (trace, fait foi)
        ├─▶ 3. Gestionnaires du portefeuille du fournisseur → e-mails
        └─▶ 4. POST de la carte adaptative au flux Teams  (best effort)
                 └─ succès → envoyee = true
                 └─ échec  → erreur_envoi renseignée, BL conservé
```

La carte affiche : numéro de BL, fournisseur, quai, date + plage horaire,
état, nombre de pages, auteur de la saisie, et **@mentionne** les
gestionnaires concernés.

**Règle importante** : une indisponibilité de Teams **n'annule jamais**
l'enregistrement du BL. L'opérateur voit un avertissement, et la trace reste
consultable dans **Gestion ▸ Notifications** (colonne « Erreur »).

Seules les **nouvelles réceptions** déclenchent cette carte (ni expéditions,
ni archivages).

## 3.2 Passage EDI NOK → OK → MessageCard + commentaire

Depuis l'app Administration, deux chemins :
- **fiche BL** (bouton ✏️ Modifier) en basculant l'état sur OK ;
- **action de masse** (bouton ✅ Passer à OK) sur une sélection.

Dans les deux cas, un champ **« Commentaire pour la notification Teams
(facultatif) »** apparaît dans la fenêtre de confirmation. Son contenu est
ajouté à la carte, sous la ligne « Par ». Le format de carte historique est
conservé.

## 3.3 Sans notification configurée

Si l'URL de webhook est vide, tout fonctionne normalement : les événements
sont journalisés en base, simplement pas publiés dans Teams.

---

# 4. Rôles et droits (RBAC)

| Rôle | App Création | App Administration |
|---|---|---|
| **LOG** | Nouvelle réception, nouvelle expédition | — |
| **APPROS** | Archivage réception | BL réception (modification) ; DESADV achat, Rapprochement achat, Notifications (lecture) |
| **ADV** | Archivage expédition | BL expédition (modification) ; DESADV vente, Rapprochement vente, Notifications (lecture) |
| **FINANCE** | — | BL et rapprochements (lecture) |
| **ADMIN_METIER** | Toutes | Toutes, y compris le module Gestion |

- Les vues sans droit sont **masquées** ; en lecture seule, les actions
  d'écriture disparaissent.
- La matrice est dans `shared/bl_core/rbac.py` (versionnée avec le code) ; les
  **affectations** sont en base (Gestion ▸ Rôles).
- `BL_RBAC_MODE=strict` : aucun rôle = aucun accès. Le mode `disabled` est
  refusé en `prod`.

---

# 5. Exploitation courante

| Situation | Où regarder / que faire |
|---|---|
| Une notification n'est pas arrivée | Gestion ▸ **Notifications** : colonne « Envoyée » et « Erreur ». Une erreur réseau ou HTTP y est explicite. |
| Une mention n'est pas cliquable | Voir « Rendre les mentions cliquables » (§2.6) : schéma du déclencheur, puis Teams ID (AAD Object ID) dans Gestion ▸ Gestionnaires, puis appartenance au canal. |
| Personne n'est mentionné | Le fournisseur n'a pas de gestionnaire dans Gestion ▸ **Portefeuilles**. |
| L'IA ne pré-remplit plus | `BL_LLM_ENDPOINT` vide, ou ressource *Serving endpoint* absente / sans « Can query ». Le détail de l'erreur est affiché à l'étape 3. |
| « Ressource Lakebase absente » | La ressource Database n'est pas attachée à l'app (clé `postgres`). |
| Erreur de droits SQL | Rejouer les GRANT de l'étape 5 avec les bons client ID. |
| Un utilisateur ne voit rien | Aucun rôle attribué (Gestion ▸ Rôles). |

**Sauvegarde** : tout est dans Lakebase (métadonnées + images). S'appuyer sur
les sauvegardes/branches du projet Lakebase.

---

# 6. Structure du dépôt

```
shared/bl_core/          code partagé (source de vérité)
  config.py              configuration validée (lue depuis app.yaml)
  database.py            pool PostgreSQL + transactions
  repository.py          accès aux données métier
  teams.py               cartes Teams (adaptative + MessageCard)
  notifications.py       trace en base puis envoi (best effort)
  rbac.py                matrice des droits
  extraction.py          extraction IA des BL scannés
  images.py, pdf_bl.py, ui.py, validation.py, identity.py
src/app_creation/        app + copie de bl_core + app.yaml + requirements.txt
src/app_administration/  idem
sql/migrations/          V001 (installation neuve), V002 (mise à niveau)
jobs/                    sync ERP, maintenance, common.py + README
```
