#!/bin/bash
# E4/E5 (A on behalf of E): CloudWatch dashboard + three alarms, as in docs/e_monitoring_spec.md.
#   EMAIL=you@example.com bash infrastructure/setup_monitoring.sh
# Creates/updates: SNS topic vericloud-ops-alarm (+ email subscription), dashboard
# vericloud-dashboard, alarms vericloud-worker-errors / -dlq-not-empty / -workflow-failed.
# Safe to run again.
set -euo pipefail
REGION="us-east-1"
TABLE="vericloud-kyc-table"; Q="vericloud-ingest-queue"; DLQ="vericloud-ingest-dlq"; SM="vericloud-kyc-workflow"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

CALLER_ARN="$(aws sts get-caller-identity --query Arn --output text)"
case "$CALLER_ARN" in *voclabs*) ;; *)
  echo "!! 当前身份不是你的 Learner Lab 账号：$CALLER_ARN"
  echo "   先 export AWS_SHARED_CREDENTIALS_FILE=~/lab_creds（里面是 AWS Details 的 [default] 几行）"
  [ "${ALLOW_ANY_IDENTITY:-}" = "1" ] || exit 1;; esac
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
SM_ARN="arn:aws:states:$REGION:$ACCOUNT_ID:stateMachine:$SM"

echo "[1/3] SNS topic vericloud-ops-alarm"
TOPIC_ARN="$(aws sns create-topic --name vericloud-ops-alarm --region "$REGION" --query TopicArn --output text)"
if [ -n "${EMAIL:-}" ]; then
  n="$(aws sns list-subscriptions-by-topic --topic-arn "$TOPIC_ARN" --region "$REGION" --query "Subscriptions[?Endpoint=='$EMAIL'] | length(@)" --output text)"
  if [ "$n" = "0" ]; then
    aws sns subscribe --topic-arn "$TOPIC_ARN" --protocol email --notification-endpoint "$EMAIL" --region "$REGION" >/dev/null
    echo "      confirmation mail sent to $EMAIL -> click Confirm subscription"
  fi
fi

echo "[2/3] Dashboard vericloud-dashboard"
python3 - "$REGION" "$SM_ARN" > "$TMP/dash.json" <<'PY'
import json, sys
region, sm = sys.argv[1], sys.argv[2]
fns = ["vericloud-starter", "vericloud-ocr", "vericloud-face", "vericloud-notify"]
def w(title, metrics, x, y, stat="Sum", width=8, view="timeSeries"):
    return {"type": "metric", "x": x, "y": y, "width": width, "height": 6,
            "properties": {"title": title, "region": region, "stat": stat, "period": 60, "view": view, "metrics": metrics}}
lam = lambda m, stat=None: [["AWS/Lambda", m, "FunctionName", f] + ([{"stat": stat}] if stat else []) for f in fns]
widgets = [
    w("Invocations", lam("Invocations"), 0, 0, width=12),
    w("Concurrency (max)", lam("ConcurrentExecutions"), 12, 0, stat="Maximum", width=12),
    w("Duration p90 / p99 (ms)", [["AWS/Lambda", "Duration", "FunctionName", f, {"stat": s, "label": f"{f[10:]} {s}"}]
                                  for f in ("vericloud-ocr", "vericloud-face") for s in ("p90", "p99")], 0, 6),
    w("Errors and throttles", lam("Errors") + lam("Throttles"), 8, 6),
    w("DynamoDB throttles / user errors", [["AWS/DynamoDB", "ThrottledRequests", "TableName", "vericloud-kyc-table"],
                                           ["AWS/DynamoDB", "UserErrors"]], 16, 6),
    w("Ingest queue (visible)", [["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", "vericloud-ingest-queue", {"stat": "Maximum"}],
                                 ["AWS/SQS", "ApproximateNumberOfMessagesNotVisible", "QueueName", "vericloud-ingest-queue", {"stat": "Maximum"}]], 0, 12, stat="Maximum"),
    w("Dead-letter queue (visible)", [["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", "vericloud-ingest-dlq", {"stat": "Maximum"}]], 8, 12, stat="Maximum"),
    w("Workflow executions", [["AWS/States", "ExecutionsSucceeded", "StateMachineArn", sm], ["AWS/States", "ExecutionsFailed", "StateMachineArn", sm],
                              ["AWS/States", "ExecutionsStarted", "StateMachineArn", sm]], 16, 12),
]
print(json.dumps({"widgets": widgets}))
PY
aws cloudwatch put-dashboard --dashboard-name vericloud-dashboard --dashboard-body "file://$TMP/dash.json" --region "$REGION" >/dev/null

echo "[3/3] Alarms -> vericloud-ops-alarm"
# Starter errors are expected (bad files are rejected on purpose), so only the three workers count.
cat > "$TMP/worker.json" <<EOF
[{"Id":"total","Expression":"ocr+face+notify","Label":"Worker errors","ReturnData":true},
 {"Id":"ocr","MetricStat":{"Metric":{"Namespace":"AWS/Lambda","MetricName":"Errors","Dimensions":[{"Name":"FunctionName","Value":"vericloud-ocr"}]},"Period":300,"Stat":"Sum"},"ReturnData":false},
 {"Id":"face","MetricStat":{"Metric":{"Namespace":"AWS/Lambda","MetricName":"Errors","Dimensions":[{"Name":"FunctionName","Value":"vericloud-face"}]},"Period":300,"Stat":"Sum"},"ReturnData":false},
 {"Id":"notify","MetricStat":{"Metric":{"Namespace":"AWS/Lambda","MetricName":"Errors","Dimensions":[{"Name":"FunctionName","Value":"vericloud-notify"}]},"Period":300,"Stat":"Sum"},"ReturnData":false}]
EOF
aws cloudwatch put-metric-alarm --region "$REGION" --alarm-name vericloud-worker-errors \
  --alarm-description "OCR / face / notify errors (starter excluded: rejecting bad files is expected)" \
  --metrics "file://$TMP/worker.json" --comparison-operator GreaterThanThreshold --threshold 5 \
  --evaluation-periods 1 --treat-missing-data notBreaching --alarm-actions "$TOPIC_ARN"
aws cloudwatch put-metric-alarm --region "$REGION" --alarm-name vericloud-dlq-not-empty \
  --alarm-description "An application was quarantined in the dead-letter queue" \
  --namespace AWS/SQS --metric-name ApproximateNumberOfMessagesVisible --dimensions Name=QueueName,Value="$DLQ" \
  --statistic Maximum --period 300 --evaluation-periods 1 --threshold 0 --comparison-operator GreaterThanThreshold \
  --treat-missing-data notBreaching --alarm-actions "$TOPIC_ARN"
aws cloudwatch put-metric-alarm --region "$REGION" --alarm-name vericloud-workflow-failed \
  --alarm-description "A workflow execution failed before writing its row" \
  --namespace AWS/States --metric-name ExecutionsFailed --dimensions Name=StateMachineArn,Value="$SM_ARN" \
  --statistic Sum --period 300 --evaluation-periods 1 --threshold 0 --comparison-operator GreaterThanThreshold \
  --treat-missing-data notBreaching --alarm-actions "$TOPIC_ARN"

echo
echo "Done. Console: CloudWatch -> Dashboards -> vericloud-dashboard ; CloudWatch -> Alarms (3)."
