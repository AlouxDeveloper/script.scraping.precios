#!/usr/bin/env bash
# Conexión BigLake a Vertex AI para el entity resolution vectorial.
#
# BigQuery no llama por su cuenta a un modelo de embeddings: necesita una
# conexión CLOUD_RESOURCE que le dé una identidad con permiso sobre Vertex AI.
# El modelo remoto emb_gemini (03_modelo_emb_gemini.sql) se declara contra esta
# conexión y AI.GENERATE_EMBEDDING la usa en cada llamada.
#
# Se corre a mano una sola vez, desde la raíz del repo:
#   bash transform/entity_resolution/sql/02_conexion_vertex.sh
#
# La conexión va en US, la misma multi-región que los datasets y los buckets:
# una conexión regional no puede usarse desde un dataset multi-región.
#
# Es una conexión aparte de la que ya existe (precios_biglake, declarada en
# load/config/gcp.yml), que le da a las external tables de precios_bronce
# acceso de lectura a GCS. Reusarla obligaría a ampliarle el alcance a Vertex
# AI; una conexión dedicada mantiene chico el radio de cada identidad.

set -euo pipefail

PROYECTO="scenic-firefly-473823-f7"
REGION="US"
CONEXION="vertex"

# Idempotente: si la conexión ya existe, bq mk falla y el script continúa.
bq mk --connection \
    --location="${REGION}" \
    --project_id="${PROYECTO}" \
    --connection_type=CLOUD_RESOURCE \
    "${CONEXION}" || echo "La conexión ya existe, se continúa."

bq show --format=prettyjson --connection "${PROYECTO}.${REGION}.${CONEXION}"

# Google genera el service account al crear la conexión; no se elige, se lee.
CUENTA=$(bq show --format=prettyjson \
    --connection "${PROYECTO}.${REGION}.${CONEXION}" \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['cloudResource']['serviceAccountId'])")

echo "Service account de la conexión: ${CUENTA}"

gcloud projects add-iam-policy-binding "${PROYECTO}" \
    --member="serviceAccount:${CUENTA}" \
    --role="roles/aiplatform.user" \
    --condition=None

# Verificación: la cuenta debe aparecer con roles/aiplatform.user.
gcloud projects get-iam-policy "${PROYECTO}" \
    --flatten="bindings[].members" \
    --filter="bindings.role:roles/aiplatform.user AND bindings.members:${CUENTA}" \
    --format="table(bindings.role, bindings.members)"
