-- Migration additive pour une base V4 existante. Aucune donnée n'est supprimée.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE {{schema}}.base_tiers
  ADD COLUMN IF NOT EXISTS source_donnee TEXT NOT NULL DEFAULT 'MANUEL',
  ADD COLUMN IF NOT EXISTS source_key TEXT,
  ADD COLUMN IF NOT EXISTS actif BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS cree_le TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS modifie_le TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

ALTER TABLE {{schema}}.base_desadv
  ADD COLUMN IF NOT EXISTS source_donnee TEXT NOT NULL DEFAULT 'MANUEL',
  ADD COLUMN IF NOT EXISTS source_key TEXT,
  ADD COLUMN IF NOT EXISTS actif BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS payload_hash TEXT,
  ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

ALTER TABLE {{schema}}.gestionnaires
  ADD COLUMN IF NOT EXISTS actif BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS cree_le TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE {{schema}}.quais
  ADD COLUMN IF NOT EXISTS actif BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS cree_le TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE {{schema}}.adresses
  ADD COLUMN IF NOT EXISTS actif BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS cree_le TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE {{schema}}.roles_utilisateurs
  ADD COLUMN IF NOT EXISTS attribue_par TEXT,
  ADD COLUMN IF NOT EXISTS attribue_le TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS expire_le TIMESTAMPTZ;

ALTER TABLE {{schema}}.suivi_bl
  ADD COLUMN IF NOT EXISTS source_donnee TEXT NOT NULL DEFAULT 'MANUEL',
  ADD COLUMN IF NOT EXISTS document_statut TEXT NOT NULL DEFAULT 'COMPLET',
  ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

ALTER TABLE {{schema}}.suivi_bl
  ADD COLUMN IF NOT EXISTS sens TEXT GENERATED ALWAYS AS (
    CASE
      WHEN type_operation IN ('RECEPTION', 'ARCHIVAGE_RECEPTION') THEN 'ACHAT'
      ELSE 'VENTE'
    END
  ) STORED;

DROP INDEX IF EXISTS {{schema}}.uniq_suivi_bl_numero;
CREATE UNIQUE INDEX IF NOT EXISTS uq_suivi_bl_numero_sens
  ON {{schema}}.suivi_bl (upper(numero_bl), sens);

ALTER TABLE {{schema}}.pieces_jointes_bl
  ALTER COLUMN contenu DROP NOT NULL,
  ADD COLUMN IF NOT EXISTS storage_uri TEXT,
  ADD COLUMN IF NOT EXISTS sha256 TEXT,
  ADD COLUMN IF NOT EXISTS taille_octets BIGINT,
  ADD COLUMN IF NOT EXISTS content_type TEXT NOT NULL DEFAULT 'image/jpeg',
  ADD COLUMN IF NOT EXISTS cree_le TIMESTAMPTZ NOT NULL DEFAULT now();

UPDATE {{schema}}.pieces_jointes_bl
SET sha256 = encode(digest(contenu, 'sha256'), 'hex'),
    taille_octets = octet_length(contenu)
WHERE contenu IS NOT NULL AND (sha256 IS NULL OR taille_octets IS NULL);

CREATE UNIQUE INDEX IF NOT EXISTS uq_pieces_bl_page
  ON {{schema}}.pieces_jointes_bl (id_bl, index_page);

ALTER TABLE {{schema}}.qualite_extraction
  ADD COLUMN IF NOT EXISTS modele_endpoint TEXT,
  ADD COLUMN IF NOT EXISTS prompt_version TEXT,
  ADD COLUMN IF NOT EXISTS score_confiance NUMERIC(5,4);

ALTER TABLE {{schema}}.notifications
  ADD COLUMN IF NOT EXISTS event_key TEXT;
UPDATE {{schema}}.notifications
SET event_key = encode(
  digest(coalesce(type_notif, '') || '|' || coalesce(numero_bl, '') || '|' || id::text, 'sha256'),
  'hex'
)
WHERE event_key IS NULL;
ALTER TABLE {{schema}}.notifications
  ALTER COLUMN event_key SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_event_key
  ON {{schema}}.notifications (event_key);

-- Les renommages ERP d'un tiers doivent se propager aux tables V4 qui
-- utilisent encore son nom comme clé étrangère.
ALTER TABLE {{schema}}.portefeuilles
  DROP CONSTRAINT IF EXISTS portefeuilles_nom_fournisseur_fkey;
ALTER TABLE {{schema}}.portefeuilles
  ADD CONSTRAINT portefeuilles_nom_fournisseur_fkey
  FOREIGN KEY (nom_fournisseur) REFERENCES {{schema}}.base_tiers (name)
  ON UPDATE CASCADE ON DELETE RESTRICT;

ALTER TABLE {{schema}}.sites_logistiques
  DROP CONSTRAINT IF EXISTS sites_logistiques_entite_fkey;
ALTER TABLE {{schema}}.sites_logistiques
  ADD CONSTRAINT sites_logistiques_entite_fkey
  FOREIGN KEY (entite) REFERENCES {{schema}}.base_tiers (name)
  ON UPDATE CASCADE ON DELETE RESTRICT;

ALTER TABLE {{schema}}.pla
  DROP CONSTRAINT IF EXISTS pla_nom_fournisseur_fkey;
ALTER TABLE {{schema}}.pla
  ADD CONSTRAINT pla_nom_fournisseur_fkey
  FOREIGN KEY (nom_fournisseur) REFERENCES {{schema}}.base_tiers (name)
  ON UPDATE CASCADE ON DELETE RESTRICT;

-- Les nouveaux objets sont également déclarés dans V001. Les CREATE IF NOT
-- EXISTS ci-dessous rendent cette migration autonome sur une base V4.
CREATE TABLE IF NOT EXISTS {{schema}}.audit_evenements (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  categorie TEXT NOT NULL,
  action TEXT NOT NULL,
  cible TEXT,
  acteur TEXT NOT NULL,
  details JSONB NOT NULL DEFAULT '{}'::jsonb,
  cree_le TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS {{schema}}.notification_canaux (
  code TEXT PRIMARY KEY,
  actif BOOLEAN NOT NULL DEFAULT false,
  type_canal TEXT NOT NULL,
  secret_scope TEXT,
  secret_key TEXT,
  timeout_secondes INTEGER NOT NULL DEFAULT 20,
  modifie_le TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS {{schema}}.notification_livraisons (
  notification_id BIGINT NOT NULL REFERENCES {{schema}}.notifications (id) ON DELETE CASCADE,
  canal TEXT NOT NULL REFERENCES {{schema}}.notification_canaux (code),
  statut TEXT NOT NULL,
  tentatives INTEGER NOT NULL DEFAULT 0,
  prochaine_tentative_le TIMESTAMPTZ,
  verrouille_jusqua TIMESTAMPTZ,
  envoyee_le TIMESTAMPTZ,
  derniere_erreur TEXT,
  idempotency_key TEXT GENERATED ALWAYS AS (notification_id::text || ':' || canal) STORED,
  PRIMARY KEY (notification_id, canal)
);

CREATE TABLE IF NOT EXISTS {{schema}}.job_executions (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_name TEXT NOT NULL,
  run_id TEXT,
  statut TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
  erreur TEXT
);

INSERT INTO {{schema}}.notification_canaux
  (code, actif, type_canal, secret_scope, secret_key)
VALUES
  ('TEAMS', false, 'TEAMS', 'bldemat', 'teams-webhook-url'),
  ('POWER_AUTOMATE', false, 'POWER_AUTOMATE', 'bldemat', 'power-automate-url')
ON CONFLICT (code) DO NOTHING;

CREATE OR REPLACE VIEW {{schema}}.v_rapprochement_bl_desadv AS
SELECT
  b.id_bl,
  b.numero_bl,
  b.sens,
  b.nom_fournisseur AS tiers_bl,
  d.nom_fournisseur AS tiers_desadv,
  b.date_reception,
  d.integrationdate,
  (d.numero_bl IS NOT NULL) AS rapproche,
  (d.numero_bl IS NOT NULL AND d.nom_fournisseur IS DISTINCT FROM b.nom_fournisseur)
    AS tiers_different
FROM {{schema}}.suivi_bl b
LEFT JOIN {{schema}}.base_desadv d
  ON upper(d.numero_bl) = upper(b.numero_bl)
 AND d.sens = b.sens
 AND d.actif = true
WHERE b.est_supprime = false
  AND b.document_statut = 'COMPLET';
