#!/bin/bash
# Frontend backend: deploy lambda/api as vericloud-api behind a Lambda function URL,
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

# ---------- 1. Lambda function ----------
( cd "$HERE/lambda/api" && python3 -c "import zipfile; z=zipfile.ZipFile('$TMP/api.zip','w'); z.write('handler.py'); z.close()" )
ENV="Variables={BUCKET=$BUCKET,TABLE=$TABLE,URL_TTL=300}"
if aws lambda get-function --function-name "$FN" --region "$REGION" >/dev/null 2>&1; then
  echo "[1/4] Updating $FN"
  aws lambda update-function-code --function-name "$FN" --region "$REGION" --zip-file "fileb://$TMP/api.zip" >/dev/null
  aws lambda wait function-updated --function-name "$FN" --region "$REGION"
  aws lambda update-function-configuration --function-name "$FN" --region "$REGION" \
    --environment "$ENV" --timeout 10 --memory-size 256 >/dev/null
  aws lambda wait function-updated --function-name "$FN" --region "$REGION"
else
  echo "[1/4] Creating $FN"
  aws lambda create-function --function-name "$FN" --region "$REGION" --runtime python3.12 \
    --handler handler.lambda_handler --role "$ROLE_ARN" --zip-file "fileb://$TMP/api.zip" \
    --environment "$ENV" --timeout 10 --memory-size 256 >/dev/null
  aws lambda wait function-active --function-name "$FN" --region "$REGION"
fi

# ---------- 2. Public function URL with CORS ----------
CORS='{"AllowOrigins":["*"],"AllowMethods":["GET","POST"],"AllowHeaders":["content-type"],"MaxAge":300}'
if aws lambda get-function-url-config --function-name "$FN" --region "$REGION" >/dev/null 2>&1; then
  echo "[2/4] Function URL exists; re-applying CORS"
  aws lambda update-function-url-config --function-name "$FN" --region "$REGION" --cors "$CORS" >/dev/null
else
  echo "[2/4] Creating function URL"
  aws lambda create-function-url-config --function-name "$FN" --region "$REGION" \
    --auth-type NONE --cors "$CORS" >/dev/null
fi
# Public URLs need both permissions (the second one is required for URLs created since late 2025).
aws lambda add-permission --function-name "$FN" --region "$REGION" --statement-id public-url \
  --action lambda:InvokeFunctionUrl --principal '*' --function-url-auth-type NONE >/dev/null 2>&1 || true
if ! aws lambda add-permission --function-name "$FN" --region "$REGION" --statement-id public-url-invoke \
  --action lambda:InvokeFunction --principal '*' --invoked-via-function-url >/dev/null 2>"$TMP/perm.err"; then
  grep -q ResourceConflictException "$TMP/perm.err" || {
    echo "   (note) second permission not added: $(head -c 200 "$TMP/perm.err")"
    echo "   If the quick check below returns Forbidden, add it in the console:"
    echo "   Lambda -> $FN -> Configuration -> Permissions -> Resource-based policy -> Add: lambda:InvokeFunction, principal *"
  }
fi
API_URL="$(aws lambda get-function-url-config --function-name "$FN" --region "$REGION" --query FunctionUrl --output text)"
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
