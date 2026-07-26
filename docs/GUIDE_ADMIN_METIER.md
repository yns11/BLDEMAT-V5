# Guide ADMIN_METIER

## 1. Mission

L'ADMIN_METIER garantit la qualité fonctionnelle de BLDEMAT :

- attribuer les rôles applicatifs ;
- maintenir les référentiels manuels ;
- surveiller les flux BL, DESADV, IA et notifications ;
- traiter les anomalies et conflits ;
- préserver la traçabilité ;
- escalader les incidents techniques.

Il n'administre ni les secrets, ni les service principals, ni les ressources
Databricks : ces responsabilités restent techniques.

## 2. Matrice des rôles

| Rôle | Création | Administration |
|---|---|---|
| `LOG` | nouvelles réceptions et expéditions | aucune |
| `APPROS` | archivage réception | BL réception en modification, DESADV/rapprochement achat en lecture |
| `ADV` | archivage expédition | BL expédition en modification, DESADV/rapprochement vente en lecture |
| `FINANCE` | aucune | BL et rapprochements en lecture |
| `ADMIN_METIER` | toutes opérations | toutes vues et modifications |

Les rôles sont cumulables. Appliquer le principe du moindre privilège.

## 3. Prise en main

La barre de contexte affiche :

- l'utilisateur SSO ;
- l'environnement (`dev`, `rec`, `prod`) ;
- les rôles actifs.

Vérifier cet encart avant toute opération sensible. Une erreur « contrôle des
droits indisponible » bloque volontairement l'outil : ne pas contourner, ouvrir
un incident.

## 4. Tableau de bord

Choisir le périmètre Achat, Vente ou Tous. Les filtres de période et de tiers
s'appliquent aux KPI ; le gestionnaire s'applique au portefeuille achat.

Interprétation :

- **BL (période)** : documents complets, actifs ;
- **Réceptions / Expéditions** : opérations nouvelles ;
- **RECEPTIONS NOK** : statut métier saisi NOK ;
- **DESADV NOK** : erreur du message EDI ;
- **deltas** : comparaison à la période précédente de même durée.

Ne pas additionner automatiquement un NOK BL et un NOK DESADV : ce sont deux
contrôles distincts sur des populations potentiellement différentes.

## 5. Gérer les BL

Les vues Achat et Vente permettent :

- recherche multicritère et pagination ;
- consultation des pages ;
- export PDF ;
- modification de la fiche ;
- passage de NOK à OK ;
- suppression logique et restauration ;
- consultation de l'historique.

Une confirmation est toujours demandée. Si un message indique qu'un autre
utilisateur a modifié le BL, fermer la boîte, rafraîchir et réévaluer la
modification. Ne jamais essayer de « forcer » une ancienne valeur.

La suppression est logique : le BL et ses images restent disponibles pour
restauration et audit.

## 6. Rapprochement BL / DESADV

Deux listes sont présentées :

- BL sans DESADV ;
- DESADV sans BL.

Vérifier en priorité :

- casse, espaces ou préfixes du numéro ;
- sens Achat/Vente ;
- tiers ;
- fraîcheur du job ERP ;
- éventuelle suppression logique du BL.

Corriger une donnée ERP dans l'ERP, jamais dans BLDEMAT. Le référentiel bloque
la modification et la suppression d'une ligne de provenance `ERP`.

## 7. Référentiels

Les référentiels manuels couvrent gestionnaires, portefeuilles, quais,
adresses, sites et PLA.

Bonnes pratiques :

- préparer la modification et vérifier les dépendances ;
- éviter les doublons de libellé ;
- utiliser des codes stables ;
- renseigner le PLA pour fiabiliser le quai proposé ;
- confirmer la grille seulement après relecture ;
- contrôler l'audit après un changement de masse.

Une valeur encore utilisée par un BL ou un autre référentiel ne peut pas être
supprimée.

## 8. Rôles

Les identifiants sont les emails Databricks en minuscules. Une ligne =
un utilisateur + un rôle. Une date d'expiration peut être gérée en base pour
les droits temporaires.

Règles :

- toujours conserver au moins deux ADMIN_METIER ;
- revue mensuelle des attributions ;
- supprimer les droits à la fin d'une mission ;
- ne pas utiliser de compte partagé ;
- tester avec un compte de chaque rôle après une évolution.

Le dernier ADMIN_METIER est protégé par l'application.

## 9. Qualité IA

La vue compare, champ par champ, la valeur proposée et la valeur validée.

Surveiller :

- taux de correction du numéro ;
- taux de correction du tiers ;
- dates/statuts manuscrits ;
- changement après évolution du prompt ou du modèle ;
- fournisseurs ou formats de BL particulièrement dégradés.

Une baisse durable doit déclencher une analyse d'échantillons et, si besoin,
une modification du prompt en recette. Ne jamais auto-valider uniquement sur
la sortie IA.

## 10. Notifications

La vue montre l'événement et l'état de chaque canal :

- `EN_ATTENTE` : prêt ;
- `EN_COURS` : verrouillé par un job ;
- `ENVOYEE` : succès ;
- `ECHEC` : prochaine tentative planifiée ;
- `DEAD_LETTER` : nombre maximal de tentatives atteint.

Pour une dead-letter :

1. noter le BL, le canal et la dernière erreur ;
2. vérifier si le destinataire a déjà reçu l'information ;
3. ouvrir un incident à l'exploitation ;
4. ne pas recréer manuellement le même événement sans analyse de doublon ;
5. demander un rejeu contrôlé après correction.

## 11. Rituels

### Chaque jour ouvré

- fraîcheur du dernier job ERP ;
- volumes BL et anomalies ;
- notifications en échec/dead-letter ;
- BL brouillons anciens signalés par l'exploitation.

### Chaque semaine

- écarts BL/DESADV ;
- qualité IA ;
- anomalies récurrentes par tiers ;
- nouveaux référentiels et PLA.

### Chaque mois

- revue des rôles ;
- échantillon d'audits ;
- capacité Volume/Lakebase ;
- incidents et actions préventives ;
- validation des contacts et procédures.

## 12. Incidents

| Symptôme | Action métier | Escalade |
|---|---|---|
| aucune vue disponible | vérifier le rôle | ADMIN_METIER sécurité |
| RBAC indisponible | arrêter les opérations | exploitation immédiate |
| IA indisponible | continuer en manuel | exploitation si durable |
| images inaccessibles | noter le BL, ne pas supprimer | stockage/Databricks |
| ERP non rafraîchi | ne pas corriger les lignes ERP | équipe data |
| conflit de modification | rafraîchir et comparer | aucune si résolu |
| dead-letter | contrôler le doublon | exploitation intégration |
| incohérence d'audit | geler la modification | SSI + exploitation |

Toujours communiquer l'environnement, l'heure, l'utilisateur, le numéro de BL,
l'action et une capture sans donnée sensible inutile.
