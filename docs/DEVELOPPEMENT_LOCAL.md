# Développement local

Le mode local utilise PostgreSQL 17 et stocke temporairement les images en
base. Il ne reproduit pas les permissions et ressources Databricks.

```bash
docker compose up -d
cp deployment/local.env.example deployment/local.env
set -a
source deployment/local.env
set +a

python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

python tools/migrate.py
python tools/preflight.py
streamlit run src/app_creation/app.py
```

Dans un second terminal, avec les mêmes variables :

```bash
streamlit run src/app_administration/app.py --server.port 8502
```

Arrêt :

```bash
docker compose down
```

La commande `docker compose down -v` efface la base locale ; ne l'utiliser
qu'en connaissance de cause.
