"""Notifications Microsoft Teams envoyées directement par les applications.

Deux formats, deux usages :

* **Carte adaptative** (`carte_nouvelle_reception`) — nouvelle réception. Elle
  **mentionne** (`@`) les gestionnaires du portefeuille du fournisseur, ce qui
  les notifie personnellement dans le canal. Une mention se compose d'un jeton
  ``<at>Nom</at>`` dans le texte ET d'une entrée dans ``msteams.entities``
  portant l'adresse e-mail (UPN) de la personne.
* **MessageCard** (`carte_passage_ok`) — passage EDI NOK → OK, format
  historique conservé, enrichi du commentaire éventuel du gestionnaire.

L'envoi est **direct** (aucun job) et **best effort** : une indisponibilité de
Teams ne doit jamais empêcher l'enregistrement d'un BL. L'appelant reçoit
(succès, message d'erreur) et journalise le résultat en base.

Prérequis côté Teams : un flux « Workflows » du canal, déclencheur
« Lorsqu'une requête webhook Teams est reçue », publiant la carte reçue. Les
personnes mentionnées doivent être membres de l'équipe/du canal.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from .config import get_settings

logger = logging.getLogger("bl.teams")

_VERT = "43B02A"
_BLEU = "0F62A6"


def _poster(url: str, charge: dict) -> tuple[bool, str]:
    """POST JSON vers un webhook Teams. Renvoie (succès, message)."""
    if not url:
        return False, "Aucun webhook Teams configuré."
    requete = urllib.request.Request(
        url,
        data=json.dumps(charge).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(requete, timeout=get_settings().teams_timeout_s) as reponse:
            if 200 <= reponse.status < 300:
                return True, "OK"
            return False, f"HTTP {reponse.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} : {exc.reason}"
    except Exception as exc:                       # réseau, DNS, timeout…
        return False, f"{type(exc).__name__} : {exc}"


# Marqueur remplacé par le flux Power Automate (mode « flow ») par les jetons
# de mention produits par l'action « Obtenir un jeton @mention pour un
# utilisateur ». Ne jamais le modifier sans adapter le flux.
MARQUEUR_MENTIONS = "{{MENTIONS}}"


def _mentions(destinataires: list[dict]) -> tuple[str, list[dict], list[str]]:
    """Prépare la mention des destinataires selon `BL_TEAMS_MENTION_MODE`.

    Renvoie (texte à insérer, entités msteams, e-mails à mentionner) :

    * **flow** (recommandé) — le texte est le marqueur `{{MENTIONS}}` et les
      e-mails sont joints à la charge utile. Le flux appelle « Obtenir un
      jeton @mention pour un utilisateur » pour chacun et remplace le
      marqueur : c'est le **Flow bot** qui pose les entités, seule méthode
      fiable (écrire soi-même `msteams.entities` est rejeté avec
      « One or more mention entity could not be found in card text »).
      L'action exige l'**e-mail** de la personne, pas son AAD Object ID.
    * **entities** — l'app écrit elle-même `msteams.entities` (fonctionne sur
      certains tenants seulement) ; utilise teams_id s'il est renseigné.
    * **texte** — noms en clair, aucune mention.
    """
    mode = get_settings().teams_mention_mode
    noms, entites, emails = [], [], []
    for destinataire in destinataires:
        nom = (destinataire.get("nom") or destinataire.get("code") or "").strip()
        email = (destinataire.get("email") or "").strip()
        if not nom:
            continue
        if mode == "flow":
            if email:
                emails.append(email)
            else:
                noms.append(nom)          # sans e-mail : simple citation
            continue
        if mode == "entities":
            identifiant = (destinataire.get("teams_id") or "").strip() or email
            if identifiant:
                noms.append(f"<at>{nom}</at>")
                entites.append({
                    "type": "mention",
                    "text": f"<at>{nom}</at>",
                    "mentioned": {"id": identifiant, "name": nom},
                })
            else:
                noms.append(nom)
            continue
        noms.append(nom)                  # mode « texte »

    if mode == "flow" and emails:
        # Le marqueur précède les éventuels noms non mentionnables.
        texte = " ".join([MARQUEUR_MENTIONS] + noms)
    else:
        texte = " ".join(noms)
    return texte, entites, emails


def carte_nouvelle_reception(numero_bl: str, fournisseur: str, quai: str,
                             date_reception, plage_horaire: str, statut_libelle: str,
                             nb_pages: int, saisi_par: str,
                             destinataires: list[dict]) -> dict:
    """Carte adaptative « nouvelle réception », avec mentions des gestionnaires."""
    texte_mentions, entites, emails = _mentions(destinataires)
    faits = [
        {"title": "Fournisseur", "value": fournisseur or "—"},
        {"title": "Quai", "value": quai or "—"},
        {"title": "Réception", "value": f"{date_reception or '—'} · {plage_horaire or '—'}"},
        {"title": "État", "value": statut_libelle},
        {"title": "Pages", "value": str(nb_pages)},
        {"title": "Saisi par", "value": saisi_par or "—"},
    ]
    corps = [
        {
            "type": "TextBlock",
            "text": f"📥 Nouvelle réception — BL {numero_bl}",
            "weight": "Bolder",
            "size": "Large",
            "color": "Good",
            "wrap": True,
        },
        {"type": "FactSet", "facts": faits},
    ]
    if texte_mentions:
        corps.append({
            "type": "TextBlock",
            "text": f"Gestionnaire(s) : {texte_mentions}",
            "wrap": True,
        })
    carte = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": corps,
    }
    if entites:
        carte["msteams"] = {"entities": entites}
    # Enveloppe attendue par le flux Teams « Workflows ». En mode « flow »,
    # « mentions » porte les e-mails que le flux transforme en jetons.
    charge = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": carte,
        }],
    }
    if emails:
        charge["mentions"] = emails
    return charge


def carte_test_mentions(nom: str, email: str = "", teams_id: str = "",
                        upn: str = "") -> dict:
    """Carte de diagnostic : compare, en une seule publication, la méthode
    « flow » (jeton produit par le Flow bot) et les identifiants écrits par
    l'application (`msteams.entities`).

    La ligne qui devient réellement cliquable indique la voie à retenir :
    normalement la première (mode `flow`, après modification du flux) ; les
    suivantes ne fonctionnent que sur certains tenants.
    """
    corps = [{
        "type": "TextBlock",
        "text": "🧪 Test des mentions Teams",
        "weight": "Bolder", "size": "Large", "wrap": True,
    }, {
        "type": "TextBlock",
        "text": ("Repérez la ligne dont le nom est réellement cliquable "
                 "(fond bleuté) : elle indique la méthode à retenir."),
        "wrap": True, "isSubtle": True,
    }]
    charge_mentions = []
    if email:
        corps.append({
            "type": "TextBlock",
            "text": f"**1. Flow bot (jeton du flux)** : {MARQUEUR_MENTIONS}",
            "wrap": True,
        })
        charge_mentions.append(email)
    else:
        corps.append({"type": "TextBlock",
                      "text": "**1. Flow bot (jeton du flux)** : (e-mail non renseigné)",
                      "wrap": True})

    entites = []
    for index, (libelle, identifiant) in enumerate(
            (("2. msteams.entities avec l'e-mail", email),
             ("3. msteams.entities avec le Teams ID", teams_id),
             ("4. msteams.entities avec l'UPN interne", upn)), start=2):
        if not identifiant:
            corps.append({"type": "TextBlock",
                          "text": f"**{libelle}** : (non renseigné)", "wrap": True})
            continue
        # Jeton rendu unique : sans cela Teams ne peut pas rattacher chaque
        # entité à son occurrence dans le texte.
        jeton = f"{nom} [{index}]"
        corps.append({"type": "TextBlock",
                      "text": f"**{libelle}** : <at>{jeton}</at>", "wrap": True})
        entites.append({
            "type": "mention",
            "text": f"<at>{jeton}</at>",
            "mentioned": {"id": identifiant, "name": jeton},
        })
    carte = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": corps,
    }
    if entites:
        carte["msteams"] = {"entities": entites}
    charge = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": carte,
        }],
    }
    if charge_mentions:
        charge["mentions"] = charge_mentions
    return charge


def carte_passage_ok(numero_bl: str, message: str, cree_par: str,
                     quand: str, commentaire: str = "") -> dict:
    """MessageCard « EDI NOK → OK » — structure historique, plus le
    commentaire facultatif laissé par le gestionnaire."""
    faits = [
        {"name": "Type", "value": "EDI_NOK_OK"},
        {"name": "Quand", "value": quand},
        {"name": "Par", "value": cree_par or "—"},
    ]
    if commentaire:
        faits.append({"name": "Commentaire", "value": commentaire})
    return {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": _VERT,
        "summary": f"BL {numero_bl} passé de EDI NOK à OK",
        "sections": [{
            "activityTitle": f"✅ BL {numero_bl} passé de EDI NOK à OK",
            "text": message,
            "facts": faits,
        }],
    }


def envoyer_nouvelle_reception(**kwargs) -> tuple[bool, str]:
    return _poster(get_settings().teams_webhook_reception,
                   carte_nouvelle_reception(**kwargs))


def envoyer_passage_ok(**kwargs) -> tuple[bool, str]:
    return _poster(get_settings().teams_webhook_edi, carte_passage_ok(**kwargs))


def envoyer_test_mentions(**kwargs) -> tuple[bool, str]:
    """Publie la carte de diagnostic sur le canal des réceptions (ou, à
    défaut, sur celui des passages à OK)."""
    parametres = get_settings()
    url = parametres.teams_webhook_reception or parametres.teams_webhook_edi
    return _poster(url, carte_test_mentions(**kwargs))
