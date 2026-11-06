#!/bin/bash
set -e
REGION="us-east-1"
ACCOUNT_ID="493114794251"

echo "Creating Dead Letter Queue (DLQ)..."
aws sqs create-queue \
  --queue-name vericloud-ingest-dlq \
  --attributes MessageRetentionPeriod=1209600 \
  --region $REGION

REDRIVE_POLICY="{\"deadLetterTargetArn\":\"arn:aws:sqs:$REGION:$ACCOUNT_ID:vericloud-ingest-dlq\",\"maxReceiveCount\":\"3\"}"

echo "Creating Ingestion Queue with DLQ Binding..."
aws sqs create-queue \
  --queue-name vericloud-ingest-queue \
  --attributes "VisibilityTimeout=360,RedrivePolicy='$REDRIVE_POLICY'" \
  --region $REGION
echo "SQS Infrastructure setup completed."
