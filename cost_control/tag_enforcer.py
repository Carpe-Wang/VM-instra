#!/usr/bin/env python3
"""
Tag Enforcement - MANDATORY COST CONTROL
Required tags: AutoDelete, CostCenter, MaxHours
Auto-terminate untagged resources after 2 hours
Zero tolerance policy
"""

import boto3
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Set

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TagEnforcer:
    """
    STRICT TAG ENFORCEMENT
    No tags = No resources
    Auto-terminate violators
    """
    
    def __init__(self):
        self.ec2 = boto3.client('ec2')
        self.events = boto3.client('events')
        self.lambda_client = boto3.client('lambda')
        
        # REQUIRED TAGS - MANDATORY
        self.REQUIRED_TAGS = {
            'AutoDelete': 'true|false',  # Must be true or false
            'CostCenter': 'string',       # Cost allocation
            'MaxHours': 'number',         # Maximum runtime hours
            'Environment': 'dev|staging|prod',  # Environment type
            'Owner': 'email'              # Owner email
        }
        
        # ENFORCEMENT SETTINGS
        self.GRACE_PERIOD_HOURS = 2  # 2 hours before termination
        self.CHECK_INTERVAL_MINUTES = 15  # Check every 15 minutes
        
    def enforce_all_tags(self) -> Dict:
        """
        Enforce tags on ALL resources
        Terminate violators after grace period
        Cost impact: SAVES $100-1000/month by killing untagged resources
        """
        results = {
            'instances_tagged': 0,
            'instances_terminated': 0,
            'volumes_tagged': 0,
            'volumes_deleted': 0,
            'violations_found': 0,
            'estimated_monthly_savings': 0.0
        }
        
        # Check instances
        instance_result = self.enforce_instance_tags()
        results['instances_tagged'] = instance_result['tagged']
        results['instances_terminated'] = instance_result['terminated']
        results['estimated_monthly_savings'] += instance_result['savings']
        
        # Check volumes
        volume_result = self.enforce_volume_tags()
        results['volumes_tagged'] = volume_result['tagged']
        results['volumes_deleted'] = volume_result['deleted']
        results['estimated_monthly_savings'] += volume_result['savings']
        
        # Check snapshots
        snapshot_result = self.enforce_snapshot_tags()
        results['estimated_monthly_savings'] += snapshot_result['savings']
        
        # Total violations
        results['violations_found'] = (
            instance_result['violations'] + 
            volume_result['violations'] + 
            snapshot_result['violations']
        )
        
        logger.info(f"TAG ENFORCEMENT COMPLETE: {results['violations_found']} violations, ${results['estimated_monthly_savings']:.2f}/month saved")
        return results
        
    def enforce_instance_tags(self) -> Dict:
        """
        Enforce tags on EC2 instances
        Terminate untagged after grace period
        """
        tagged = 0
        terminated = 0
        violations = 0
        monthly_savings = 0.0
        
        try:
            response = self.ec2.describe_instances(
                Filters=[{'Name': 'instance-state-name', 'Values': ['running', 'pending', 'stopping', 'stopped']}]
            )
            
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    instance_id = instance['InstanceId']
                    tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                    
                    # Check for violations
                    missing_tags = self.get_missing_tags(tags)
                    
                    if missing_tags:
                        violations += 1
                        launch_time = instance['LaunchTime']
                        hours_running = (datetime.utcnow() - launch_time.replace(tzinfo=None)).total_seconds() / 3600
                        
                        if hours_running > self.GRACE_PERIOD_HOURS:
                            # TERMINATE - Grace period expired
                            logger.critical(f"TERMINATING UNTAGGED: {instance_id} (missing: {missing_tags})")
                            
                            # Calculate savings
                            instance_type = instance['InstanceType']
                            hourly_cost = self.get_instance_cost(instance_type)
                            monthly_savings += hourly_cost * 24 * 30
                            
                            self.ec2.terminate_instances(InstanceIds=[instance_id])
                            terminated += 1
                            
                        else:
                            # Add warning tag and set deletion timer
                            remaining_hours = self.GRACE_PERIOD_HOURS - hours_running
                            logger.warning(f"VIOLATION: {instance_id} missing tags: {missing_tags}. Terminating in {remaining_hours:.1f} hours")
                            
                            # Add warning tags
                            self.ec2.create_tags(
                                Resources=[instance_id],
                                Tags=[
                                    {'Key': 'VIOLATION', 'Value': 'MISSING_TAGS'},
                                    {'Key': 'TERMINATION_TIME', 'Value': (datetime.utcnow() + timedelta(hours=remaining_hours)).isoformat()},
                                    {'Key': 'AutoDelete', 'Value': 'true'},  # Force auto-delete
                                ]
                            )
                            tagged += 1
                    else:
                        # Check MaxHours tag
                        if 'MaxHours' in tags:
                            max_hours = float(tags['MaxHours'])
                            launch_time = instance['LaunchTime']
                            hours_running = (datetime.utcnow() - launch_time.replace(tzinfo=None)).total_seconds() / 3600
                            
                            if hours_running > max_hours:
                                # Exceeded max hours - TERMINATE
                                logger.warning(f"MAX HOURS EXCEEDED: {instance_id} ran {hours_running:.1f} hours (max: {max_hours})")
                                
                                # Calculate savings
                                instance_type = instance['InstanceType']
                                hourly_cost = self.get_instance_cost(instance_type)
                                monthly_savings += hourly_cost * 24 * 30
                                
                                self.ec2.terminate_instances(InstanceIds=[instance_id])
                                terminated += 1
                                
                        # Check AutoDelete tag
                        if tags.get('AutoDelete') == 'true':
                            # Check if instance should be deleted based on schedule
                            if self.should_auto_delete(tags):
                                logger.info(f"AUTO-DELETING: {instance_id}")
                                self.ec2.terminate_instances(InstanceIds=[instance_id])
                                terminated += 1
                                
        except Exception as e:
            logger.error(f"Failed to enforce instance tags: {e}")
            
        return {
            'tagged': tagged,
            'terminated': terminated,
            'violations': violations,
            'savings': monthly_savings
        }
        
    def enforce_volume_tags(self) -> Dict:
        """
        Enforce tags on EBS volumes
        Delete untagged volumes
        """
        tagged = 0
        deleted = 0
        violations = 0
        monthly_savings = 0.0
        
        try:
            response = self.ec2.describe_volumes()
            
            for volume in response['Volumes']:
                volume_id = volume['VolumeId']
                tags = {tag['Key']: tag['Value'] for tag in volume.get('Tags', [])}
                
                # Check for violations
                missing_tags = self.get_missing_tags(tags)
                
                if missing_tags:
                    violations += 1
                    
                    # If unattached and untagged - DELETE
                    if volume['State'] == 'available':
                        logger.warning(f"DELETING UNTAGGED VOLUME: {volume_id}")
                        
                        # Calculate savings
                        size_gb = volume['Size']
                        monthly_savings += size_gb * 0.10  # $0.10/GB/month
                        
                        self.ec2.delete_volume(VolumeId=volume_id)
                        deleted += 1
                    else:
                        # Add warning tags
                        self.ec2.create_tags(
                            Resources=[volume_id],
                            Tags=[
                                {'Key': 'VIOLATION', 'Value': 'MISSING_TAGS'},
                                {'Key': 'AutoDelete', 'Value': 'true'}
                            ]
                        )
                        tagged += 1
                        
        except Exception as e:
            logger.error(f"Failed to enforce volume tags: {e}")
            
        return {
            'tagged': tagged,
            'deleted': deleted,
            'violations': violations,
            'savings': monthly_savings
        }
        
    def enforce_snapshot_tags(self) -> Dict:
        """
        Enforce tags on snapshots
        Delete old untagged snapshots
        """
        deleted = 0
        violations = 0
        monthly_savings = 0.0
        
        try:
            response = self.ec2.describe_snapshots(OwnerIds=['self'])
            cutoff_date = datetime.utcnow() - timedelta(days=7)
            
            for snapshot in response['Snapshots']:
                snapshot_id = snapshot['SnapshotId']
                tags = {tag['Key']: tag['Value'] for tag in snapshot.get('Tags', [])}
                
                # Check for violations
                missing_tags = self.get_missing_tags(tags)
                
                if missing_tags:
                    violations += 1
                    
                    # If old and untagged - DELETE
                    if snapshot['StartTime'].replace(tzinfo=None) < cutoff_date:
                        logger.warning(f"DELETING UNTAGGED SNAPSHOT: {snapshot_id}")
                        
                        # Calculate savings
                        size_gb = snapshot.get('VolumeSize', 0)
                        monthly_savings += size_gb * 0.05  # $0.05/GB/month
                        
                        self.ec2.delete_snapshot(SnapshotId=snapshot_id)
                        deleted += 1
                        
        except Exception as e:
            logger.error(f"Failed to enforce snapshot tags: {e}")
            
        return {
            'deleted': deleted,
            'violations': violations,
            'savings': monthly_savings
        }
        
    def get_missing_tags(self, current_tags: Dict) -> List[str]:
        """
        Get list of missing required tags
        """
        missing = []
        for required_tag in self.REQUIRED_TAGS:
            if required_tag not in current_tags:
                missing.append(required_tag)
        return missing
        
    def should_auto_delete(self, tags: Dict) -> bool:
        """
        Check if resource should be auto-deleted based on tags
        """
        # Check environment
        if tags.get('Environment') == 'prod':
            return False  # Never auto-delete production
            
        # Check if it's after hours for dev/staging
        current_hour = datetime.utcnow().hour
        if tags.get('Environment') in ['dev', 'staging']:
            if current_hour >= 19 or current_hour < 7:  # 7 PM to 7 AM
                return True
                
        # Check if it's weekend for non-prod
        if datetime.utcnow().weekday() >= 5:  # Saturday or Sunday
            if tags.get('Environment') != 'prod':
                return True
                
        return False
        
    def get_instance_cost(self, instance_type: str) -> float:
        """
        Get hourly cost for instance type
        """
        costs = {
            'm5.2xlarge': 0.384,
            'm5.xlarge': 0.192,
            't3.large': 0.0832,
            't3.medium': 0.0416,
        }
        return costs.get(instance_type, 0.10)
        
    def create_enforcement_lambda(self) -> Dict:
        """
        Create Lambda function for automated enforcement
        """
        lambda_code = '''
import json
from tag_enforcer import TagEnforcer

def lambda_handler(event, context):
    enforcer = TagEnforcer()
    result = enforcer.enforce_all_tags()
    return {
        'statusCode': 200,
        'body': json.dumps(result)
    }
'''
        
        # Create Lambda function
        function_name = 'tag-enforcement'
        
        try:
            response = self.lambda_client.create_function(
                FunctionName=function_name,
                Runtime='python3.9',
                Role='arn:aws:iam::account:role/lambda-role',
                Handler='lambda_function.lambda_handler',
                Code={'ZipFile': lambda_code.encode()},
                Timeout=60,
                MemorySize=256
            )
            
            # Create EventBridge rule to run every 15 minutes
            rule_name = 'tag-enforcement-schedule'
            self.events.put_rule(
                Name=rule_name,
                ScheduleExpression='rate(15 minutes)',
                State='ENABLED'
            )
            
            # Add Lambda permission
            self.lambda_client.add_permission(
                FunctionName=function_name,
                StatementId='EventBridgeInvoke',
                Action='lambda:InvokeFunction',
                Principal='events.amazonaws.com',
                SourceArn=f'arn:aws:events:us-east-1:account:rule/{rule_name}'
            )
            
            # Set Lambda as target
            self.events.put_targets(
                Rule=rule_name,
                Targets=[{
                    'Id': '1',
                    'Arn': response['FunctionArn']
                }]
            )
            
            logger.info(f"Created enforcement Lambda: {function_name}")
            return {'status': 'created', 'function': function_name}
            
        except Exception as e:
            logger.error(f"Failed to create Lambda: {e}")
            return {'status': 'failed', 'error': str(e)}

def lambda_handler(event, context):
    """
    Lambda entry point
    """
    enforcer = TagEnforcer()
    result = enforcer.enforce_all_tags()
    
    return {
        'statusCode': 200,
        'body': json.dumps(result)
    }

if __name__ == "__main__":
    enforcer = TagEnforcer()
    
    print("=" * 60)
    print("TAG ENFORCEMENT - MANDATORY COMPLIANCE")
    print("=" * 60)
    print(f"Required Tags: {list(enforcer.REQUIRED_TAGS.keys())}")
    print(f"Grace Period: {enforcer.GRACE_PERIOD_HOURS} hours")
    print("=" * 60)
    
    result = enforcer.enforce_all_tags()
    
    print("\nENFORCEMENT RESULTS:")
    print(f"Violations Found: {result['violations_found']}")
    print(f"Instances Tagged: {result['instances_tagged']}")
    print(f"Instances Terminated: {result['instances_terminated']}")
    print(f"Volumes Tagged: {result['volumes_tagged']}")
    print(f"Volumes Deleted: {result['volumes_deleted']}")
    print(f"Estimated Monthly Savings: ${result['estimated_monthly_savings']:.2f}")