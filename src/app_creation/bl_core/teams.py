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


def _mentions(destinataires: list[dict]) -> tuple[str, list[dict]]:
    """Construit le texte des mentions et les entités Teams associées.

    `destinataires` : [{"nom": "Prénom Nom", "email": "prenom.nom@…"}, …].
    Les entrées sans e-mail sont affichées en texte simple (pas de mention).
    """
    jetons, entites = [], []
    for destinataire in destinataires:
        nom = (destinataire.get("nom") or destinataire.get("code") or "").strip()
        email = (destinataire.get("email") or "").strip()
        if not nom:
            continue
        if email:
            jetons.append(f"<at>{nom}</at>")
            entites.append({
                "type": "mention",
                "text": f"<at>{nom}</at>",
                "mentioned": {"id": email, "name": nom},
            })
        else:
            jetons.append(nom)
    return " ".join(jetons), entites


def carte_nouvelle_reception(numero_bl: str, fournisseur: str, quai: str,
                             date_reception, plage_horaire: str, statut_libelle: str,
                             nb_pages: int, saisi_par: str,
                             destinataires: list[dict]) -> dict:
    """Carte adaptative « nouvelle réception », avec mentions des gestionnaires."""
    texte_mentions, entites = _mentions(destinataires)
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
    # Enveloppe attendue par le flux Teams « Workflows ».
    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": carte,
        }],
    }


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
