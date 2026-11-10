#!/bin/bash
# A5 — S3 upload event -> SQS (docs/interface.md sections 2, 3, 5.2)
#
# Run in the AWS Academy Learner Lab terminal (AWS CLI is already signed in):
#   bash setup_s3_event.sh            # set everything up
#   bash setup_s3_event.sh --verify   # set up, then upload a test selfie and check the queue
#
# Safe to run again: existing bucket / queues are reused, settings are re-applied.
# Bucket name (interface v1.3.1) can be overridden for a personal test account:
#   BUCKET=vericloud-raw-1009-yourname bash setup_s3_event.sh
set -euo pipefail

REGION="us-east-1"
BUCKET="${BUCKET:-vericloud-raw-1009-a}"
QUEUE="vericloud-ingest-queue"
DLQ="vericloud-ingest-dlq"
PREFIX="raw/selfie/"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

CALLER_ARN="$(aws sts get-caller-identity --query Arn --output text)"
case "$CALLER_ARN" in
  *voclabs*) ;;
  *)
    echo "!! 当前身份不是你的 Learner Lab 账号：$CALLER_ARN"
    echo "   1) 确认 Lab 左上角是绿点（Start Lab）"
    echo "   2) AWS Details -> AWS CLI: Show，复制 [default] 那几行；cat > ~/lab_creds 回车，粘贴，回车，Ctrl+D"
    echo "      然后 export AWS_SHARED_CREDENTIALS_FILE=~/lab_creds（每开一个新终端都要再 export）"
    echo "   3) aws sts get-caller-identity 的 Arn 里出现 voclabs 后再运行本脚本"
    echo "   (Set ALLOW_ANY_IDENTITY=1 to skip this check outside Learner Lab.)"
    [ "${ALLOW_ANY_IDENTITY:-}" = "1" ] || exit 1
    ;;
esac
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
echo "Account: $ACCOUNT_ID   Region: $REGION   Bucket: $BUCKET   Identity: $CALLER_ARN"

# Turn a one-line JSON document into a JSON string value (no newlines/backslashes inside).
json_str() { printf '"%s"' "$(printf '%s' "$1" | sed 's/"/\\"/g')"; }

# ---------- 1. Queues (D's settings, but with this account's ID) ----------
queue_url() { aws sqs get-queue-url --queue-name "$1" --region "$REGION" --query QueueUrl --output text 2>/dev/null || true; }

DLQ_URL="$(queue_url "$DLQ")"
if [ -z "$DLQ_URL" ]; then
  echo "[1/5] Creating DLQ $DLQ"
  DLQ_URL="$(aws sqs create-queue --queue-name "$DLQ" --region "$REGION" \
    --attributes MessageRetentionPeriod=1209600 --query QueueUrl --output text)"
else
  echo "[1/5] DLQ $DLQ already exists"
fi
DLQ_ARN="arn:aws:sqs:$REGION:$ACCOUNT_ID:$DLQ"

QUEUE_URL="$(queue_url "$QUEUE")"
REDRIVE="{\"deadLetterTargetArn\":\"$DLQ_ARN\",\"maxReceiveCount\":\"3\"}"
printf '{"VisibilityTimeout":"360","RedrivePolicy":%s}' "$(json_str "$REDRIVE")" > "$TMP/queue_attrs.json"
if [ -z "$QUEUE_URL" ]; then
  echo "      Creating queue $QUEUE (DLQ after 3 receives)"
  QUEUE_URL="$(aws sqs create-queue --queue-name "$QUEUE" --region "$REGION" \
    --attributes "file://$TMP/queue_attrs.json" --query QueueUrl --output text)"
else
  echo "      Queue $QUEUE already exists; re-applying DLQ binding"
  aws sqs set-queue-attributes --queue-url "$QUEUE_URL" --region "$REGION" \
    --attributes "file://$TMP/queue_attrs.json"
fi
QUEUE_ARN="arn:aws:sqs:$REGION:$ACCOUNT_ID:$QUEUE"

# ---------- 2. Bucket ----------
if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  echo "[2/5] Bucket $BUCKET already exists in this account"
else
  echo "[2/5] Creating bucket $BUCKET"
  if ! aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" >/dev/null; then
    echo "!! Could not create $BUCKET. If the name is taken by a teammate's account, ask them to delete it,"
    echo "   or rerun with another name: BUCKET=${BUCKET}-yourname bash $0"
    exit 1
  fi
fi

echo "      Blocking public access, default SSE-S3 encryption, raw/ lifecycle 7 days"
aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" --lifecycle-configuration \
  '{"Rules":[{"ID":"raw-7-days","Status":"Enabled","Filter":{"Prefix":"raw/"},"Expiration":{"Days":7}}]}'

# ---------- 3. Let this bucket (only) send messages to the queue ----------
echo "[3/5] Allowing S3 bucket $BUCKET to send to $QUEUE"
POLICY="{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"AllowS3SendMessage\",\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"s3.amazonaws.com\"},\"Action\":\"sqs:SendMessage\",\"Resource\":\"$QUEUE_ARN\",\"Condition\":{\"ArnLike\":{\"aws:SourceArn\":\"arn:aws:s3:::$BUCKET\"},\"StringEquals\":{\"aws:SourceAccount\":\"$ACCOUNT_ID\"}}}]}"
printf '{"Policy":%s}' "$(json_str "$POLICY")" > "$TMP/policy_attrs.json"
aws sqs set-queue-attributes --queue-url "$QUEUE_URL" --region "$REGION" \
  --attributes "file://$TMP/policy_attrs.json"

# ---------- 4. Event notification: only selfie uploads trigger the pipeline ----------
echo "[4/5] S3 event notification: ObjectCreated under $PREFIX -> $QUEUE"
cat > "$TMP/notify.json" <<EOF
{"QueueConfigurations":[{"Id":"selfie-upload-to-ingest-queue","QueueArn":"$QUEUE_ARN","Events":["s3:ObjectCreated:*"],
  "Filter":{"Key":{"FilterRules":[{"Name":"prefix","Value":"$PREFIX"}]}}}]}
EOF
aws s3api put-bucket-notification-configuration --bucket "$BUCKET" \
  --notification-configuration "file://$TMP/notify.json"

# ---------- 5. Optional check ----------
if [ "${1:-}" = "--verify" ]; then
  echo "[5/5] Uploading a test selfie and reading the queue (starter must NOT be attached yet, or it will take the message first)"
  KEY="${PREFIX}a5-check-$(date +%s).jpg"
  printf 'a5' > "$TMP/a5.jpg"
  aws s3 cp "$TMP/a5.jpg" "s3://$BUCKET/$KEY" --quiet
  FOUND=""
  for _ in 1 2 3; do
    aws sqs receive-message --queue-url "$QUEUE_URL" --region "$REGION" --max-number-of-messages 10 \
      --wait-time-seconds 10 --output json > "$TMP/msgs.json"
    if grep -q "$KEY" "$TMP/msgs.json"; then FOUND=yes; fi
    grep -q 's3:TestEvent' "$TMP/msgs.json" && echo "      (saw the s3:TestEvent message from step 4 — expected, starter skips it)"
    # delete what we read so it doesn't end up in the DLQ
    { grep -o '"ReceiptHandle": "[^"]*"' "$TMP/msgs.json" || true; } | cut -d'"' -f4 | while read -r h; do
      aws sqs delete-message --queue-url "$QUEUE_URL" --region "$REGION" --receipt-handle "$h"
    done
    [ -n "$FOUND" ] && break
  done
  aws s3 rm "s3://$BUCKET/$KEY" --quiet
  if [ -n "$FOUND" ]; then
    echo "OK: upload to $KEY produced an SQS message."
  else
    echo "!! No message for $KEY after ~30s. Check the queue policy (step 3) and notification (step 4) in the console."
    exit 1
  fi
else
  echo "[5/5] Skipped check (run with --verify to test)"
fi

echo
echo "Done. Put these in docs/interface.md section 8 (demo account):"
echo "  S3 bucket       : $BUCKET"
echo "  SQS queue URL   : $QUEUE_URL"
echo "  SQS DLQ ARN     : $DLQ_ARN"
