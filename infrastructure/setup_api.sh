#!/bin/bash
# Frontend backend: deploy lambda/api as vericloud-api behind an API Gateway HTTP API,
# allow browser PUTs on the bucket (S3 CORS), and point frontend/dist/config.js at it.
#
# Run in the Learner Lab terminal, from the repo:
#   bash infrastructure/setup_api.sh
# Safe to run again (updates code and settings).
set -euo pipefail

REGION="us-east-1"
FN="vericloud-api"
BUCKET="${BUCKET:-vericloud-raw-1009-a}"
TABLE="vericloud-kyc-table"
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
ROLE_ARN="$(aws iam get-role --role-name LabRole --query Role.Arn --output text)"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"

# Wait until the function is no longer being created/updated. A polling loop instead of
# `aws lambda wait`, because the Learner Lab CLI is old and lacks some waiters.
wait_ready() {
  for _ in $(seq 1 45); do
    st="$(aws lambda get-function-configuration --function-name "$FN" --region "$REGION"       --query '[State, LastUpdateStatus]' --output text 2>/dev/null || true)"
    case "$st" in *Pending*|*InProgress*) sleep 2 ;; *) return 0 ;; esac
  done
}

# ---------- 1. Lambda function ----------
( cd "$HERE/lambda/api" && python3 -c "import zipfile; z=zipfile.ZipFile('$TMP/api.zip','w'); z.write('handler.py'); z.close()" )
ENV="Variables={BUCKET=$BUCKET,TABLE=$TABLE,URL_TTL=300}"
if aws lambda get-function --function-name "$FN" --region "$REGION" >/dev/null 2>&1; then
  echo "[1/4] Updating $FN"
  wait_ready
  aws lambda update-function-code --function-name "$FN" --region "$REGION" --zip-file "fileb://$TMP/api.zip" >/dev/null
  wait_ready
  aws lambda update-function-configuration --function-name "$FN" --region "$REGION"     --environment "$ENV" --timeout 10 --memory-size 256 >/dev/null
  wait_ready
else
  echo "[1/4] Creating $FN"
  aws lambda create-function --function-name "$FN" --region "$REGION" --runtime python3.12     --handler handler.lambda_handler --role "$ROLE_ARN" --zip-file "fileb://$TMP/api.zip"     --environment "$ENV" --timeout 10 --memory-size 256 >/dev/null
  wait_ready
fi
FN_ARN="arn:aws:lambda:$REGION:$ACCOUNT_ID:function:$FN"

# ---------- 2. Public HTTPS endpoint: API Gateway HTTP API with CORS ----------
# (Lambda function URLs would be simpler, but the Learner Lab CLI is too old to create them.)
cat > "$TMP/cors.json" <<'JSON'
{"AllowOrigins":["*"],"AllowMethods":["GET","POST"],"AllowHeaders":["content-type"],"MaxAge":300}
JSON
API_ID="$(aws apigatewayv2 get-apis --region "$REGION" --query "Items[?Name=='$FN'].ApiId | [0]" --output text)"
if [ -n "$API_ID" ] && [ "$API_ID" != "None" ]; then
  echo "[2/4] HTTP API $FN exists ($API_ID); re-applying CORS"
  aws apigatewayv2 update-api --api-id "$API_ID" --region "$REGION" --cors-configuration "file://$TMP/cors.json" >/dev/null
else
  echo "[2/4] Creating HTTP API $FN"
  # Quick create: one $default route -> the Lambda, $default stage with auto-deploy, payload format 2.0.
  API_ID="$(aws apigatewayv2 create-api --name "$FN" --region "$REGION" --protocol-type HTTP     --target "$FN_ARN" --cors-configuration "file://$TMP/cors.json" --query ApiId --output text)"
fi
aws lambda add-permission --function-name "$FN" --region "$REGION" --statement-id apigw-invoke   --action lambda:InvokeFunction --principal apigateway.amazonaws.com   --source-arn "arn:aws:execute-api:$REGION:$ACCOUNT_ID:$API_ID/*" >/dev/null 2>&1 || true
API_URL="$(aws apigatewayv2 get-api --api-id "$API_ID" --region "$REGION" --query ApiEndpoint --output text)"
API_URL="${API_URL%/}"

# ---------- 3. Let the browser PUT to the bucket ----------
echo "[3/4] S3 CORS on $BUCKET: PUT from the frontend"
aws s3api put-bucket-cors --bucket "$BUCKET" --cors-configuration \
  '{"CORSRules":[{"AllowedOrigins":["*"],"AllowedMethods":["PUT"],"AllowedHeaders":["*"],"ExposeHeaders":["ETag"],"MaxAgeSeconds":300}]}'

# ---------- 4. Point the frontend at the API ----------
CFG="$HERE/frontend/dist/config.js"
if [ -f "$CFG" ]; then
  sed -i "s#^const VERICLOUD_API = .*#const VERICLOUD_API = '$API_URL';#" "$CFG"
  echo "[4/4] Wrote the API URL into frontend/dist/config.js"
else
  echo "[4/4] frontend/dist/config.js not found; set VERICLOUD_API there by hand"
fi

echo
echo "Quick check (expect 404 {\"status\": \"PENDING\"}):"
curl -s "$API_URL/applications/00000000-0000-4000-8000-000000000000"; echo
echo
echo "API URL: $API_URL"
echo "Do not post this URL publicly: anyone who has it can request upload links."
