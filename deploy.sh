#!/bin/bash
# --------------------------------------------------------------------------
# Déploiement sur Google Cloud Run (Phase 3)
#
# Prérequis :
#   - gcloud CLI installé et authentifié : gcloud auth login / gcloud init
#   - Projet GCP créé AVEC BILLING ACTIVÉ (carte requise, mais le free tier
#     couvre largement ce projet — configurez une alerte budget par sécurité)
#   - Un cluster Qdrant Cloud (free tier 1GB) — https://cloud.qdrant.io
#     -> Cloud Run ne peut pas atteindre un Qdrant local (localhost)
#   - data/finances.db généré (python src/create_sqlite_db.py)
#   - .gcloudignore présent à la racine, et NE DOIT PAS exclure
#     data/finances.db (nécessaire au Dockerfile)
#
# Usage :
#   chmod +x deploy.sh
#   ./deploy.sh
# --------------------------------------------------------------------------

set -e

# ----- À adapter -----
PROJECT_ID="ton-projet-gcp"
REGION="europe-west1"
SERVICE_NAME="enterprise-agent"
GOOGLE_API_KEY_VALUE="ta_cle_gemini"
QDRANT_URL_VALUE="https://xxxxx.cloud.qdrant.io:6333"   # inclure le port :6333
QDRANT_API_KEY_VALUE="ta_cle_qdrant"
# ----------------------

echo "Configuration du projet GCP : $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

echo "Activation des APIs nécessaires..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com

# --------------------------------------------------------------------------
# IAM : sur un projet GCP fraîchement créé, le compte de service Cloud Build
# (PROJECT_NUMBER-compute@developer.gserviceaccount.com) manque souvent ces
# rôles, ce qui fait échouer le premier déploiement avec des erreurs
# "storage.objects.get" ou "logging.logEntries.create". On les ajoute de
# manière idempotente (sans erreur si déjà présents).
# --------------------------------------------------------------------------

echo "Vérification des permissions IAM du compte de service Cloud Build..."
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for ROLE in \
  "roles/logging.logWriter" \
  "roles/storage.admin" \
  "roles/artifactregistry.writer" \
  "roles/cloudbuild.builds.builder"
do
  echo "  - $ROLE"
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="$ROLE" \
    --condition=None \
    --quiet > /dev/null
done

echo "Build + déploiement sur Cloud Run (via Cloud Build, pas besoin de Docker local)..."
gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --set-env-vars "GOOGLE_API_KEY=$GOOGLE_API_KEY_VALUE,QDRANT_URL=$QDRANT_URL_VALUE,QDRANT_API_KEY=$QDRANT_API_KEY_VALUE"

echo ""
echo "✅ Déploiement terminé."
echo "Récupère l'URL avec :"
echo "  gcloud run services describe $SERVICE_NAME --region $REGION --format='value(status.url)'"
echo ""
echo "Teste avec :"
echo '  curl https://YOUR-URL.run.app/'