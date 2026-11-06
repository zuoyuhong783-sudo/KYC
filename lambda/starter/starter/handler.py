import json
import os
import boto3

sfn_client = boto3.client('stepfunctions', region_name='us-east-1')
STATE_MACHINE_ARN = "arn:aws:states:us-east-1:493114794251:stateMachine:vericloud-kyc-workflow"

def lambda_handler(event, context):
    print("Received event: " + json.dumps(event))
    
    for record in event.get('Records', []):
        body_raw = record.get('body', '{}')
        try:
            body = json.loads(body_raw)
        except Exception as e:
            print(f"Error parsing body: {e}")
            raise e
            
        app_id = body.get('application_id')
        created_at = body.get('created_at')
        
        if not app_id:
            raise ValueError("Missing application_id in SQS message")
            
        execution_input = {
            "application_id": app_id,
            "created_at": created_at,
            "id_card_image": body.get("id_card_image", {}),
            "selfie_image": body.get("selfie_image", {})
        }
        
        exec_name = f"exec-{app_id}-{int(context.get_remaining_time_in_millis())}"
        print(f"Starting execution for application {app_id}")
        
        response = sfn_client.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            name=exec_name,
            input=json.dumps(execution_input)
        )
        print(f"Execution started successfully: {response['executionArn']}")
        
    return {"statusCode": 200, "body": "OK"}
