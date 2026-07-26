-- BLDEMAT V5 Professional - modèle PostgreSQL de référence.
-- Le token {{schema}} est remplacé par tools/migrate.py après validation.

CREATE SCHEMA IF NOT EXISTS {{schema}};
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS {{schema}}.base_tiers (
  name                TEXT PRIMARY KEY,
  type_tiers          TEXT NOT NULL CHECK (type_tiers IN ('FOURNISSEUR', 'CLIENT')),
  source_donnee       TEXT NOT NULL DEFAULT 'MANUEL' CHECK (source_donnee IN ('ERP', 'MANUEL')),
  source_key          TEXT,
  actif               BOOLEAN NOT NULL DEFAULT true,
  last_seen_at        TIMESTAMPTZ,
  cree_le             TIMESTAMPTZ NOT NULL DEFAULT now(),
  modifie_le          TIMESTAMPTZ NOT NULL DEFAULT now(),
  version             INTEGER NOT NULL DEFAULT 1 CHECK (version > 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_base_tiers_source
  ON {{schema}}.base_tiers (type_tiers, source_key)
  WHERE source_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS {{schema}}.gestionnaires (
  code_gestionnaire   TEXT PRIMARY KEY,
  actif               BOOLEAN NOT NULL DEFAULT true,
  cree_le             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS {{schema}}.quais (
  code_quai           TEXT PRIMARY KEY,
  actif               BOOLEAN NOT NULL DEFAULT true,
  cree_le             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS {{schema}}.adresses (
  adresse             TEXT PRIMARY KEY,
  actif               BOOLEAN NOT NULL DEFAULT true,
  cree_le             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS {{schema}}.portefeuilles (
  code_gestionnaire   TEXT NOT NULL
    REFERENCES {{schema}}.gestionnaires (code_gestionnaire) ON UPDATE CASCADE,
  nom_fournisseur     TEXT NOT NULL
    REFERENCES {{schema}}.base_tiers (name) ON UPDATE CASCADE,
  PRIMARY KEY (code_gestionnaire, nom_fournisseur)
);

CREATE TABLE IF NOT EXISTS {{schema}}.sites_logistiques (
  entite              TEXT NOT NULL
    REFERENCES {{schema}}.base_tiers (name) ON UPDATE CASCADE,
  adresse             TEXT NOT NULL
    REFERENCES {{schema}}.adresses (adresse) ON UPDATE CASCADE,
  PRIMARY KEY (entite, adresse)
);

CREATE TABLE IF NOT EXISTS {{schema}}.pla (
  nom_fournisseur     TEXT PRIMARY KEY
    REFERENCES {{schema}}.base_tiers (name) ON UPDATE CASCADE,
  code_quai           TEXT NOT NULL
    REFERENCES {{schema}}.quais (code_quai) ON UPDATE CASCADE,
  jours_livraison     TEXT,
  frequence_livraison TEXT,
  version             INTEGER NOT NULL DEFAULT 1 CHECK (version > 0)
);

CREATE TABLE IF NOT EXISTS {{schema}}.roles_utilisateurs (
  utilisateur         TEXT NOT NULL CHECK (utilisateur = lower(utilisateur)),
  role                TEXT NOT NULL CHECK (
    role IN ('LOG', 'APPROS', 'ADV', 'FINANCE', 'ADMIN_METIER')
  ),
  attribue_par        TEXT,
  attribue_le         TIMESTAMPTZ NOT NULL DEFAULT now(),
  expire_le           TIMESTAMPTZ,
  PRIMARY KEY (utilisateur, role),
  CHECK (expire_le IS NULL OR expire_le > attribue_le)
);

CREATE TABLE IF NOT EXISTS {{schema}}.base_desadv (
  numero_bl           TEXT NOT NULL,
  nom_fournisseur     TEXT NOT NULL
    REFERENCES {{schema}}.base_tiers (name) ON UPDATE CASCADE,
  sens                TEXT NOT NULL CHECK (sens IN ('ACHAT', 'VENTE')),
  issuedatetime       TIMESTAMPTZ,
  integrationdate     DATE,
  statut_edi          TEXT CHECK (statut_edi IS NULL OR statut_edi IN ('OK', 'EDI NOK')),
  source_donnee       TEXT NOT NULL DEFAULT 'MANUEL' CHECK (source_donnee IN ('ERP', 'MANUEL')),
  source_key          TEXT,
  actif               BOOLEAN NOT NULL DEFAULT true,
  last_seen_at        TIMESTAMPTZ,
  payload_hash        TEXT,
  version             INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
  PRIMARY KEY (numero_bl, sens)
);
CREATE INDEX IF NOT EXISTS idx_desadv_tiers
  ON {{schema}}.base_desadv (sens, nom_fournisseur, integrationdate DESC);

CREATE TABLE IF NOT EXISTS {{schema}}.suivi_bl (
  id_bl               TEXT PRIMARY KEY,
  numero_bl           TEXT NOT NULL CHECK (length(btrim(numero_bl)) BETWEEN 1 AND 80),
  date_reception      DATE,
  plage_horaire       TEXT,
  nom_fournisseur     TEXT
    REFERENCES {{schema}}.base_tiers (name) ON UPDATE CASCADE,
  quai_reception      TEXT
    REFERENCES {{schema}}.quais (code_quai) ON UPDATE CASCADE,
  statut_bl           TEXT CHECK (statut_bl IS NULL OR statut_bl IN ('0', '1')),
  comment_bl          TEXT CHECK (comment_bl IS NULL OR length(comment_bl) <= 2000),
  saisie_par          TEXT NOT NULL,
  saisie_le           TIMESTAMPTZ NOT NULL DEFAULT now(),
  modifie_par         TEXT,
  modifie_le          TIMESTAMPTZ,
  type_operation      TEXT NOT NULL CHECK (
    type_operation IN ('RECEPTION', 'EXPEDITION',
                       'ARCHIVAGE_RECEPTION', 'ARCHIVAGE_EXPEDITION')
  ),
  sens                TEXT GENERATED ALWAYS AS (
    CASE
      WHEN type_operation IN ('RECEPTION', 'ARCHIVAGE_RECEPTION') THEN 'ACHAT'
      ELSE 'VENTE'
    END
  ) STORED,
  source_donnee       TEXT NOT NULL DEFAULT 'MANUEL' CHECK (source_donnee IN ('ERP', 'MANUEL')),
  document_statut     TEXT NOT NULL DEFAULT 'BROUILLON'
    CHECK (document_statut IN ('BROUILLON', 'COMPLET', 'ERREUR')),
  est_supprime        BOOLEAN NOT NULL DEFAULT false,
  supprime_par        TEXT,
  supprime_le         TIMESTAMPTZ,
  desadv_rapproche    BOOLEAN NOT NULL DEFAULT false,
  desadv_rapproche_le TIMESTAMPTZ,
  version             INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
  CHECK (
    (est_supprime = false AND supprime_par IS NULL AND supprime_le IS NULL)
    OR
    (est_supprime = true AND supprime_par IS NOT NULL AND supprime_le IS NOT NULL)
  )
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_suivi_bl_numero_sens
  ON {{schema}}.suivi_bl (upper(numero_bl), sens);
CREATE INDEX IF NOT EXISTS idx_suivi_bl_saisie
  ON {{schema}}.suivi_bl (saisie_le DESC);
CREATE INDEX IF NOT EXISTS idx_suivi_bl_date
  ON {{schema}}.suivi_bl (sens, date_reception DESC);
CREATE INDEX IF NOT EXISTS idx_suivi_bl_tiers
  ON {{schema}}.suivi_bl (nom_fournisseur, date_reception DESC);

CREATE TABLE IF NOT EXISTS {{schema}}.pieces_jointes_bl (
  id_photo            TEXT PRIMARY KEY,
  id_bl               TEXT NOT NULL
    REFERENCES {{schema}}.suivi_bl (id_bl) ON DELETE RESTRICT,
  contenu             BYTEA,
  storage_uri         TEXT,
  sha256              TEXT NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  taille_octets       BIGINT NOT NULL CHECK (taille_octets > 0),
  content_type        TEXT NOT NULL DEFAULT 'image/jpeg',
  index_page          INTEGER NOT NULL CHECK (index_page >= 0),
  cree_le             TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (id_bl, index_page),
  CHECK ((contenu IS NOT NULL) <> (storage_uri IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_pieces_id_bl
  ON {{schema}}.pieces_jointes_bl (id_bl, index_page);

CREATE TABLE IF NOT EXISTS {{schema}}.audit_bl (
  id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id_bl               TEXT NOT NULL,
  evenement           TEXT NOT NULL,
  champ               TEXT,
  valeur_avant        TEXT,
  valeur_apres        TEXT,
  modifie_par         TEXT NOT NULL,
  modifie_le          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_bl_id
  ON {{schema}}.audit_bl (id_bl, modifie_le DESC);

CREATE TABLE IF NOT EXISTS {{schema}}.audit_evenements (
  id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  categorie           TEXT NOT NULL,
  action              TEXT NOT NULL,
  cible               TEXT,
  acteur              TEXT NOT NULL,
  details             JSONB NOT NULL DEFAULT '{}'::jsonb,
  cree_le             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_evenements
  ON {{schema}}.audit_evenements (cree_le DESC, categorie);

CREATE TABLE IF NOT EXISTS {{schema}}.qualite_extraction (
  id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  cree_le             TIMESTAMPTZ NOT NULL DEFAULT now(),
  utilisateur         TEXT,
  numero_bl           TEXT,
  champ               TEXT NOT NULL,
  valeur_ia           TEXT,
  valeur_validee      TEXT,
  identique           BOOLEAN NOT NULL,
  modele_endpoint     TEXT,
  prompt_version      TEXT,
  score_confiance     NUMERIC(5,4)
    CHECK (score_confiance IS NULL OR score_confiance BETWEEN 0 AND 1)
);
CREATE INDEX IF NOT EXISTS idx_qualite_champ
  ON {{schema}}.qualite_extraction (champ, cree_le DESC);

CREATE TABLE IF NOT EXISTS {{schema}}.ecrans_utilisateur (
  utilisateur         TEXT NOT NULL,
  vue                 TEXT NOT NULL,
  nom                 TEXT NOT NULL,
  est_defaut          BOOLEAN NOT NULL DEFAULT false,
  etat                TEXT NOT NULL,
  modifie_le          TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (utilisateur, vue, nom)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ecran_defaut
  ON {{schema}}.ecrans_utilisateur (lower(utilisateur), vue)
  WHERE est_defaut = true;

CREATE TABLE IF NOT EXISTS {{schema}}.notifications (
  id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_key           TEXT NOT NULL UNIQUE,
  type_notif          TEXT NOT NULL,
  numero_bl           TEXT,
  message             TEXT NOT NULL,
  cree_le             TIMESTAMPTZ NOT NULL DEFAULT now(),
  cree_par            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS {{schema}}.notification_canaux (
  code                TEXT PRIMARY KEY CHECK (code ~ '^[A-Z0-9_]+$'),
  actif               BOOLEAN NOT NULL DEFAULT false,
  type_canal          TEXT NOT NULL CHECK (type_canal IN ('TEAMS', 'POWER_AUTOMATE')),
  secret_scope        TEXT,
  secret_key          TEXT,
  timeout_secondes    INTEGER NOT NULL DEFAULT 20 CHECK (timeout_secondes BETWEEN 1 AND 120),
  modifie_le          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS {{schema}}.notification_livraisons (
  notification_id     BIGINT NOT NULL
    REFERENCES {{schema}}.notifications (id) ON DELETE CASCADE,
  canal               TEXT NOT NULL
    REFERENCES {{schema}}.notification_canaux (code),
  statut              TEXT NOT NULL CHECK (
    statut IN ('EN_ATTENTE', 'EN_COURS', 'ENVOYEE', 'ECHEC', 'DEAD_LETTER')
  ),
  tentatives          INTEGER NOT NULL DEFAULT 0 CHECK (tentatives >= 0),
  prochaine_tentative_le TIMESTAMPTZ,
  verrouille_jusqua   TIMESTAMPTZ,
  envoyee_le          TIMESTAMPTZ,
  derniere_erreur     TEXT,
  idempotency_key     TEXT GENERATED ALWAYS AS
    (notification_id::text || ':' || canal) STORED,
  PRIMARY KEY (notification_id, canal)
);
CREATE INDEX IF NOT EXISTS idx_notification_livraisons_a_envoyer
  ON {{schema}}.notification_livraisons (statut, prochaine_tentative_le)
  WHERE statut IN ('EN_ATTENTE', 'ECHEC');

CREATE TABLE IF NOT EXISTS {{schema}}.job_executions (
  id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_name            TEXT NOT NULL,
  run_id              TEXT,
  statut              TEXT NOT NULL CHECK (statut IN ('STARTED', 'SUCCEEDED', 'FAILED')),
  started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at         TIMESTAMPTZ,
  metrics             JSONB NOT NULL DEFAULT '{}'::jsonb,
  erreur              TEXT
);
CREATE INDEX IF NOT EXISTS idx_job_executions
  ON {{schema}}.job_executions (job_name, started_at DESC);

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

INSERT INTO {{schema}}.quais (code_quai)
VALUES ('B15'), ('B06EST'), ('B06NORD'), ('B02NORD'), ('AUTRE')
ON CONFLICT DO NOTHING;

INSERT INTO {{schema}}.notification_canaux
  (code, actif, type_canal, secret_scope, secret_key)
VALUES
  ('TEAMS', false, 'TEAMS', 'bldemat', 'teams-webhook-url'),
  ('POWER_AUTOMATE', false, 'POWER_AUTOMATE', 'bldemat', 'power-automate-url')
ON CONFLICT (code) DO NOTHING;
