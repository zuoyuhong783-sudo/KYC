#!/bin/bash
# A6 — deploy the processing pipeline into the demo account in one go:
#   SNS topic + email, vericloud-face, vericloud-ocr (needs Docker, see step 3),
#   vericloud-kyc-workflow, vericloud-starter + SQS trigger, vericloud-notify + stream trigger.
# Prerequisites already done: A5 (bucket + queues), the table, setup_api.sh.
#
# Run in the Learner Lab terminal, from the repo:
#   EMAIL=you@example.com bash infrastructure/deploy_all.sh
# EMAIL gets the result mails; confirm the subscription mail AWS sends you.
# Safe to run again (creates what is missing, updates the rest).
set -euo pipefail

REGION="us-east-1"
BUCKET="${BUCKET:-vericloud-raw-1009-a}"
TABLE="vericloud-kyc-table"
QUEUE="vericloud-ingest-queue"
TOPIC="vericloud-kyc-topic"
SM="vericloud-kyc-workflow"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

CALLER_ARN="$(aws sts get-caller-identity --query Arn --output text)"
case "$CALLER_ARN" in
  *voclabs*) ;;
  *)
    echo "!! 当前身份不是你的 Learner Lab 账号：$CALLER_ARN"
    echo "   AWS Details -> AWS CLI: Show，复制 [default] 那几行；cat > ~/lab_creds 回车，粘贴，回车，Ctrl+D"
    echo "   然后 export AWS_SHARED_CREDENTIALS_FILE=~/lab_creds 再运行本脚本"
    [ "${ALLOW_ANY_IDENTITY:-}" = "1" ] || exit 1
    ;;
esac
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ROLE_ARN="$(aws iam get-role --role-name LabRole --query Role.Arn --output text)"
SM_ARN="arn:aws:states:$REGION:$ACCOUNT_ID:stateMachine:$SM"
echo "Account $ACCOUNT_ID  bucket $BUCKET"

# ---------- helpers ----------
wait_ready() {  # polling instead of `aws lambda wait`: the Lab CLI is old
  for _ in $(seq 1 60); do
    st="$(aws lambda get-function-configuration --function-name "$1" --region "$REGION" \
      --query '[State, LastUpdateStatus]' --output text 2>/dev/null || true)"
    case "$st" in *Pending*|*InProgress*) sleep 2 ;; *) return 0 ;; esac
  done
}
exists_fn() { aws lambda get-function --function-name "$1" --region "$REGION" >/dev/null 2>&1; }

# deploy_zip <name> <zip> <timeout> <memory> <env "Variables={...}" or "">
deploy_zip() {
  local name="$1" zip="$2" timeout="$3" mem="$4" env="$5"
  local envarg=(); [ -n "$env" ] && envarg=(--environment "$env")
  if exists_fn "$name"; then
    wait_ready "$name"
    aws lambda update-function-code --function-name "$name" --region "$REGION" --zip-file "fileb://$zip" >/dev/null
    wait_ready "$name"
    aws lambda update-function-configuration --function-name "$name" --region "$REGION" \
      --timeout "$timeout" --memory-size "$mem" ${envarg[@]+"${envarg[@]}"} >/dev/null
  else
    aws lambda create-function --function-name "$name" --region "$REGION" --runtime python3.12 \
      --handler handler.lambda_handler --role "$ROLE_ARN" --zip-file "fileb://$zip" \
      --timeout "$timeout" --memory-size "$mem" ${envarg[@]+"${envarg[@]}"} >/dev/null
  fi
  wait_ready "$name"
}

# zip_dir <src dir> <out zip> [extra dir whose contents go to the zip root]
zip_dir() {
  python3 - "$1" "$2" "${3:-}" <<'PY'
import os, sys, zipfile
src, out, extra = sys.argv[1], sys.argv[2], sys.argv[3]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for name in os.listdir(src):
        if name.endswith(".py") and not name.startswith("test_"):
            z.write(os.path.join(src, name), name)
    if extra:
        for root, _, files in os.walk(extra):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, extra))
PY
}

# map_source <function> <event source arn> [extra args...]: create the trigger once
map_source() {
  local fn="$1" src="$2"; shift 2
  local n
  n="$(aws lambda list-event-source-mappings --function-name "$fn" --event-source-arn "$src" \
    --region "$REGION" --query 'length(EventSourceMappings)' --output text)"
  if [ "$n" = "0" ]; then
    aws lambda create-event-source-mapping --function-name "$fn" --event-source-arn "$src" \
      --region "$REGION" --batch-size 1 "$@" >/dev/null
    echo "      trigger created"
  else
    echo "      trigger already there"
  fi
}

# ---------- 1. SNS topic for result mails ----------
echo "[1/6] SNS topic $TOPIC"
TOPIC_ARN="$(aws sns create-topic --name "$TOPIC" --region "$REGION" --query TopicArn --output text)"
if [ -n "${EMAIL:-}" ]; then
  subs="$(aws sns list-subscriptions-by-topic --topic-arn "$TOPIC_ARN" --region "$REGION" \
    --query "Subscriptions[?Endpoint=='$EMAIL'] | length(@)" --output text)"
  if [ "$subs" = "0" ]; then
    aws sns subscribe --topic-arn "$TOPIC_ARN" --protocol email --notification-endpoint "$EMAIL" --region "$REGION" >/dev/null
    echo "      subscription mail sent to $EMAIL -> open it and click Confirm subscription"
  else
    echo "      $EMAIL already subscribed"
  fi
else
  echo "      (no EMAIL given: results still work, but no mail is sent. Rerun with EMAIL=... to add one)"
fi

# ---------- 2. vericloud-face ----------
echo "[2/6] vericloud-face"
zip_dir "$HERE/lambda/face" "$TMP/face.zip"
deploy_zip vericloud-face "$TMP/face.zip" 30 256 ""

# ---------- 3. vericloud-ocr (container image) ----------
echo "[3/6] vericloud-ocr"
OCR_IMAGE="${OCR_IMAGE_URI:-}"
if [ -z "$OCR_IMAGE" ] && command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  REPO="vericloud-ocr"
  aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" >/dev/null 2>&1 || \
    aws ecr create-repository --repository-name "$REPO" --region "$REGION" >/dev/null
  REG="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
  aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REG" >/dev/null
  OCR_IMAGE="$REG/$REPO:latest"
  docker build -t "$OCR_IMAGE" "$HERE/lambda/ocr"
  docker push "$OCR_IMAGE"
fi
if [ -n "$OCR_IMAGE" ]; then
  if exists_fn vericloud-ocr; then
    wait_ready vericloud-ocr
    aws lambda update-function-code --function-name vericloud-ocr --region "$REGION" --image-uri "$OCR_IMAGE" >/dev/null
    wait_ready vericloud-ocr
    aws lambda update-function-configuration --function-name vericloud-ocr --region "$REGION" --timeout 60 --memory-size 1536 >/dev/null
  else
    aws lambda create-function --function-name vericloud-ocr --region "$REGION" --package-type Image \
      --code "ImageUri=$OCR_IMAGE" --role "$ROLE_ARN" --timeout 60 --memory-size 1536 >/dev/null
  fi
  wait_ready vericloud-ocr
  echo "      deployed from $OCR_IMAGE"
elif exists_fn vericloud-ocr; then
  echo "      no Docker here; keeping the vericloud-ocr that is already deployed"
else
  echo "      !! SKIPPED: no Docker in this terminal and no OCR_IMAGE_URI given."
  echo "         Everything else still deploys. Until OCR exists every application ends as FAIL / ocr_failed."
fi

# ---------- 4. state machine ----------
echo "[4/6] $SM"
DEF="file://$HERE/stepfunctions/stepfunctions/kyc_workflow.asl.json"
if aws stepfunctions describe-state-machine --state-machine-arn "$SM_ARN" --region "$REGION" >/dev/null 2>&1; then
  aws stepfunctions update-state-machine --state-machine-arn "$SM_ARN" --definition "$DEF" --role-arn "$ROLE_ARN" --region "$REGION" >/dev/null
else
  aws stepfunctions create-state-machine --name "$SM" --definition "$DEF" --role-arn "$ROLE_ARN" --type STANDARD --region "$REGION" >/dev/null
fi

# ---------- 5. vericloud-starter + SQS trigger ----------
echo "[5/6] vericloud-starter (+ Pillow) and SQS trigger"
python3 -m pip --version >/dev/null 2>&1 || { echo "!! pip is missing in this terminal: run  python3 -m ensurepip --user  and rerun"; exit 1; }
python3 -m pip install --quiet --target "$TMP/starter_pkg" --platform manylinux2014_x86_64 \
  --python-version 3.12 --implementation cp --abi cp312 --only-binary=:all: --ignore-requires-python "Pillow>=10,<13"
zip_dir "$HERE/lambda/starter" "$TMP/starter.zip" "$TMP/starter_pkg"
deploy_zip vericloud-starter "$TMP/starter.zip" 60 512 "Variables={STATE_MACHINE_ARN=$SM_ARN}"
map_source vericloud-starter "arn:aws:sqs:$REGION:$ACCOUNT_ID:$QUEUE"

# ---------- 6. vericloud-notify + stream trigger ----------
echo "[6/6] vericloud-notify and DynamoDB stream trigger"
zip_dir "$HERE/lambda/notify" "$TMP/notify.zip"
deploy_zip vericloud-notify "$TMP/notify.zip" 30 128 "Variables={SNS_TOPIC_ARN=$TOPIC_ARN}"
STREAM_ARN="$(aws dynamodb describe-table --table-name "$TABLE" --region "$REGION" --query Table.LatestStreamArn --output text)"
map_source vericloud-notify "$STREAM_ARN" --starting-position LATEST

echo
echo "Done. Deployed in $ACCOUNT_ID:"
for f in vericloud-face vericloud-ocr vericloud-starter vericloud-notify vericloud-api; do
  printf '  %-20s %s\n' "$f" "$(exists_fn "$f" && echo ok || echo MISSING)"
done
echo "  $SM   ok"
echo "  topic                $TOPIC_ARN"
echo
API="$(aws apigatewayv2 get-apis --region "$REGION" --query "Items[?Name=='vericloud-api'].ApiEndpoint | [0]" --output text)"
echo "Try it: on your PC put this line in frontend/dist/config.js, then open index.html:"
echo "  const VERICLOUD_API = '$API';"
echo "Or watch: Step Functions console -> $SM -> Executions."
