#!/usr/bin/env bash
# Provision Microsoft Foundry for Gegenpress, and print the two env vars
# the code needs.
#
#   bash scripts/azure_setup.sh
#
# Needs Azure CLI 2.80+ and `az login` first. Override any default with an
# environment variable, e.g. LOCATION=westeurope bash scripts/azure_setup.sh
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-gegenpress-rg}"
LOCATION="${LOCATION:-eastus}"
# Must be globally unique: this becomes a hostname.
ACCOUNT="${ACCOUNT:-gegenpress-$(head -c4 /dev/urandom | od -An -tx1 | tr -d ' \n')}"
PROJECT="${PROJECT:-gegenpress}"
MODEL="${MODEL:-gpt-5-mini}"
MODEL_VERSION="${MODEL_VERSION:-2025-08-07}"
CAPACITY="${CAPACITY:-10}"

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

command -v az >/dev/null || { echo "Azure CLI not found: https://aka.ms/InstallAzureCLI"; exit 1; }
az account show >/dev/null 2>&1 || { echo "Not logged in. Run: az login"; exit 1; }

say "Subscription"
az account show --query '{name:name, id:id}' -o tsv

say "Resource group: $RESOURCE_GROUP ($LOCATION)"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" -o none

say "Foundry resource: $ACCOUNT"
# --assign-identity is required or project creation fails.
# --allow-project-management cannot be changed after creation.
az cognitiveservices account create \
  --name "$ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --kind AIServices \
  --sku S0 \
  --location "$LOCATION" \
  --custom-domain "$ACCOUNT" \
  --assign-identity \
  --allow-project-management true \
  --yes -o none

say "Project: $PROJECT"
az cognitiveservices account project create \
  --name "$ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --project-name "$PROJECT" \
  --location "$LOCATION" -o none

say "Deploying model: $MODEL"
if ! az cognitiveservices account deployment create \
  --name "$ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --deployment-name "$MODEL" \
  --model-name "$MODEL" \
  --model-version "$MODEL_VERSION" \
  --model-format OpenAI \
  --sku-capacity "$CAPACITY" \
  --sku-name GlobalStandard -o none 2>/tmp/gegenpress_model_err; then
    echo
    echo "Model deployment failed. Most likely the model or version is not"
    echo "available in $LOCATION, or your subscription has no quota."
    echo
    sed 's/^/  /' /tmp/gegenpress_model_err
    echo
    echo "What is available here:"
    az cognitiveservices model list --location "$LOCATION" \
      --query "[?kind=='AIServices'].{model:model.name, version:model.version}" -o table | head -25
    echo
    echo "Then re-run with, for example:  MODEL=<name> MODEL_VERSION=<version> bash $0"
    exit 1
fi

ENDPOINT=$(az cognitiveservices account project show \
  --name "$ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --project-name "$PROJECT" \
  --query 'properties.endpoints."AI Foundry API"' -o tsv)

say "Done"
cat <<EOF

Add these to your shell, then re-run the pipeline:

  export FOUNDRY_PROJECT_ENDPOINT="$ENDPOINT"
  export FOUNDRY_MODEL="$MODEL"

  pip install agent-framework azure-identity
  PYTHONPATH=src python3 -m gegenpress desk --foundry

Written to .env.foundry as well (gitignored -- do not commit it).

Resource group "$RESOURCE_GROUP" holds everything. To remove it all:
  az group delete --name "$RESOURCE_GROUP" --yes --no-wait
EOF

cat > .env.foundry <<EOF
export FOUNDRY_PROJECT_ENDPOINT="$ENDPOINT"
export FOUNDRY_MODEL="$MODEL"
EOF
