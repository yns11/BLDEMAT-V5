# Rapport de vérification de la livraison

Date : 25 juillet 2026  
Version : 5.0.0

## Contrôles réussis

| Contrôle | Résultat |
|---|---|
| résolution des dépendances épinglées | OK |
| parsing/compilation de tous les Python | OK |
| Ruff | aucune erreur |
| Pytest | 24/24 réussis |
| traitement JPEG | réussi |
| génération PDF | réussie |
| signature Files API SDK 0.89.0 | compatible |
| synchronisation bit à bit de `bl_core` | OK |
| YAML sans clé dupliquée | OK |
| ordre des migrations et checksums | OK |
| contrôle des manifests et valeurs codées | OK |
| Databricks CLI 1.9.0, champs de bundle reconnus | OK |
| App Création, rendu bootstrap Streamlit | aucune exception |
| App Administration, panne DB simulée | erreur gérée, aucune exception UI |
| construction ZIP, CRC et chemins dupliqués | OK, 83 fichiers |

## Contrôles dépendants de l'environnement

Ils doivent être exécutés avec les ressources réelles :

- `databricks bundle validate` authentifié ;
- migrations sur une branche Lakebase de recette ;
- application des GRANT aux vrais rôles ;
- écriture/lecture réelle dans le Volume ;
- appel réel de l'endpoint vision ;
- lecture des vues ERP et validation du mapping ;
- secrets et webhooks ;
- test de charge, restauration et bascule ;
- recette des cinq rôles avec comptes réels.

Le guide de déploiement décrit ces contrôles et leurs critères.
