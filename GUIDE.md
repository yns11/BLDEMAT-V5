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
**« Obtenir un jeton @mention pour un utilisateur »** : elle renvoie un jeton
que le Flow bot transforme lui-même en vraie mention.

Cette action **échoue si la personne n'est pas membre de l'équipe**, et son
échec fait échouer tout le flux — donc aussi la notification. Le flux
ci-dessous évite ce piège : il **liste les membres réels de l'équipe** et ne
demande un jeton que pour ceux qui figurent dans les e-mails envoyés par
l'application. Un gestionnaire absent du canal est simplement ignoré ; la
carte part quand même.

L'application est déjà prête (`BL_TEAMS_MENTION_MODE=flow`) : elle envoie, à
la racine de la charge utile, un tableau `mentions` contenant les e-mails des
gestionnaires **en minuscules**, et place le marqueur `{{MENTIONS}}` dans la
carte, à l'endroit exact où les mentions doivent apparaître :

```json
{
  "type": "message",
  "mentions": ["marie.durand@emotors.com", "paul.martin@emotors.com"],
  "attachments": [{ "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": { "...": "… Gestionnaire(s) : {{MENTIONS}} …" } }]
}
```

`mentions` est **toujours** présent — vide pour la MessageCard « EDI NOK →
OK » ou pour une réception sans gestionnaire.

#### Convention préalable : renommer les actions

Les expressions référencent les actions par leur nom, apostrophes doublées et
espaces remplacés par `_` : `body('Répertorier_les_membres_de_l''équipe')` est
illisible et source d'erreurs. **Renommez chaque action ajoutée** (⋯ ▸
*Renommer*) avec les noms ASCII utilisés ci-dessous. Toutes les expressions du
guide en dépendent.

#### Modification du flux (6 actions à ajouter)

Power Automate ▸ Mes flux ▸ *Envoyer des alertes webhook à …* ▸ **Modifier**.
Les actions 1 à 5 se placent **après le déclencheur et avant** l'action
« Publier une carte dans un chat ou un canal » (donc avant la boucle sur les
pièces jointes, si le modèle en comporte une).

**1. Initialiser une variable** — nom `JetonsMentions`

| Champ | Valeur |
|---|---|
| Nom | `JetonsMentions` |
| Type | **Chaîne** |
| Valeur | *(vide)* |

**2. Teams ▸ « Répertorier les membres de l'équipe »** — renommer `Membres`

| Champ | Valeur |
|---|---|
| Équipe | l'équipe qui contient le canal de notification |

> Sortie utile : `body('Membres')?['value']`, un tableau d'objets contenant
> `displayName`, `userPrincipalName`, `email`, `userId`. Faites un premier
> **Test** du flux et regardez la sortie brute de cette action pour confirmer
> les noms de champs de votre tenant — les expressions ci-dessous utilisent un
> `coalesce` qui accepte `userPrincipalName` **ou** `email`, ce qui couvre les
> deux cas.

**3. « Filtrer un tableau »** — renommer `Gestionnaires`

| Champ | Valeur |
|---|---|
| De | `body('Membres')?['value']` |

Condition : basculer en **mode avancé** (bouton *Modifier en mode avancé*) et
coller :

```
@contains(
  coalesce(triggerBody()?['mentions'], createArray()),
  toLower(coalesce(item()?['userPrincipalName'], item()?['email'], ''))
)
```

> Ne garde que les membres de l'équipe dont l'e-mail figure dans la charge
> utile. `toLower` est indispensable : `contains` est sensible à la casse et
> Teams renvoie souvent l'UPN avec des majuscules. C'est pour cette raison que
> l'application envoie les e-mails déjà en minuscules.
>
> Le `coalesce` sur `triggerBody()?['mentions']` évite l'erreur *« expression
> … is of type 'Null' »* sur les charges sans mentions.

**4. « Appliquer à chacun »** — renommer `PourChaqueGestionnaire`

| Champ | Valeur |
|---|---|
| Sélectionner une sortie | `body('Gestionnaires')` |

> La sortie d'un *Filtrer un tableau* **est** le tableau : pas de `?['value']`
> ici. Un tableau vide fait simplement zéro itération.

**5a. Dans la boucle — Teams ▸ « Obtenir un jeton @mention pour un
utilisateur »** — renommer `Jeton`

| Champ | Valeur |
|---|---|
| Utilisateur | `coalesce(item()?['userPrincipalName'], item()?['email'])` |

**5b. Toujours dans la boucle — « Ajouter à la variable chaîne »**

| Champ | Valeur |
|---|---|
| Nom | `JetonsMentions` |
| Valeur | `concat(outputs('Jeton')?['body/atMention'], ' ')` |

> L'espace final sépare les mentions successives.

**6. Dans « Publier une carte dans un chat ou un canal »**, remplacer le
contenu du champ *Corps du message* (carte adaptative) par :

```
json(replace(string(item()?['content']), '{{MENTIONS}}', trim(variables('JetonsMentions'))))
```

> `item()` désigne ici la pièce jointe courante, dans la boucle du modèle
> d'origine. Si votre flux passe l'objet complet, l'équivalent direct est :
> `json(replace(string(triggerOutputs()?['body/attachments'][0]?['content']), '{{MENTIONS}}', trim(variables('JetonsMentions'))))`
>
> Dans la branche « si les pièces jointes sont nulles » (MessageCard EDI) :
> `json(replace(string(variables('Body')), '{{MENTIONS}}', trim(variables('JetonsMentions'))))`
> — cette carte ne contient pas le marqueur, le `replace` est donc sans effet.

**7. Enregistrer**, puis créer une réception de test : le nom du gestionnaire
doit apparaître en mention cliquable et la personne reçoit une notification
Teams personnelle.

#### Ordre final du flux

```
Déclencheur : requête webhook Teams
├─ Initialiser JetonsMentions (chaîne, vide)
├─ Membres            → Répertorier les membres de l'équipe
├─ Gestionnaires      → Filtrer un tableau (membres ∩ mentions)
├─ PourChaqueGestionnaire (sur body('Gestionnaires'))
│   ├─ Jeton          → Obtenir un jeton @mention
│   └─ Ajouter à JetonsMentions : concat(jeton, ' ')
└─ Publier une carte  → {{MENTIONS}} remplacé par JetonsMentions
```

#### Vérifier / diagnostiquer

App Administration ▸ **Gestion ▸ Gestionnaires** ▸ **🧪 Tester les mentions
Teams** : la carte de test publie quatre lignes — la n° 1 utilise la méthode
« Flow bot » (celle ci-dessus), les n° 2 à 4 les identifiants écrits par
l'application. **Seule la ligne réellement cliquable compte.** En principe
c'est la n° 1 une fois le flux modifié.

Points d'attention :

- L'e-mail saisi dans Gestion ▸ Gestionnaires doit être celui du **compte
  Microsoft 365** (UPN), pas un alias.
- La personne doit être **membre de l'équipe** ; sinon elle est filtrée
  silencieusement (pas de mention, mais pas d'échec non plus).
- « Répertorier les membres de l'équipe » est **paginée** : sur une grande
  équipe, activer *Paramètres ▸ Pagination* de l'action et monter le seuil,
  sinon un gestionnaire au-delà de la première page ne serait jamais trouvé.
- Seuls les blocs **TextBlock** et **FactSet** affichent une mention dans une
  carte adaptative.
- Si le marqueur reste vide, la ligne affiche « Gestionnaire(s) : » sans nom.
  Pour un repli explicite, remplacer `trim(variables('JetonsMentions'))` par
  `if(empty(trim(variables('JetonsMentions'))), '—', trim(variables('JetonsMentions')))`.
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
| Une mention n'est pas cliquable | Voir « Rendre les mentions cliquables » : le flux doit produire les jetons (action « Obtenir un jeton @mention »), l'e-mail doit être renseigné dans Gestion ▸ Gestionnaires, et la personne être membre du canal. |
| Le flux échoue : *'foreach' expression … is of type 'Null'* | Une expression boucle directement sur `triggerBody()?['mentions']`. L'envelopper dans `coalesce(…, createArray())` : certaines cartes (EDI NOK → OK, réception sans gestionnaire) n'ont pas de mentions. |
| Le flux échoue sur *Obtenir un jeton @mention* | La personne n'est pas membre de l'équipe. Le filtre `Gestionnaires` doit s'intercaler avant la boucle (voir « Rendre les mentions cliquables ») pour l'écarter au lieu de faire échouer le flux. |
| Un gestionnaire n'est jamais mentionné | Son e-mail dans Gestion ▸ Gestionnaires n'est pas son UPN Microsoft 365, ou il dépasse la première page de « Répertorier les membres de l'équipe » (activer la pagination de l'action). |
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
