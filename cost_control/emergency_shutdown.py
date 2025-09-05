#!/usr/bin/env python3
"""
EMERGENCY KILL SWITCH - CRITICAL COST CONTROL
Terminates ALL EC2 instances on budget breach
Lambda function for CloudWatch/manual trigger
Cost priority: ABSOLUTE
"""

import boto3
import json
import logging
from datetime import datetime
from typing import List, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmergencyShutdown:
    """
    EMERGENCY KILL SWITCH
    Terminates ALL instances immediately
    No exceptions, no delays
    """
    
    def __init__(self):
        self.ec2 = boto3.client('ec2')
        self.sns = boto3.client('sns')
        self.cloudwatch = boto3.client('cloudwatch')
        
        # Cost tracking
        self.INSTANCE_COSTS = {
            'm5.2xlarge': 0.384,  # $0.384/hour - ELIMINATE
            'm5.xlarge': 0.192,   # $0.192/hour - ELIMINATE
            't3.large': 0.0832,   # $0.0832/hour - ALLOWED
            't3.medium': 0.0416   # $0.0416/hour - PREFERRED
        }
        
    def kill_all_instances(self, reason: str = "BUDGET_BREACH") -> Dict:
        """
        TERMINATE ALL EC2 INSTANCES IMMEDIATELY
        No stop, direct termination for instant cost savings
        Cost impact: SAVES $500-2000/day instantly
        """
        terminated = []
        stopped = []
        total_hourly_savings = 0.0
        
        try:
            # Get ALL instances (running, pending, stopping, stopped)
            response = self.ec2.describe_instances()
            
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    instance_id = instance['InstanceId']
                    instance_type = instance['InstanceType']
                    state = instance['State']['Name']
                    
                    # Calculate cost being saved
                    hourly_cost = self.INSTANCE_COSTS.get(instance_type, 0.1)  # Default $0.1/hour
                    total_hourly_savings += hourly_cost
                    
                    if state in ['running', 'pending']:
                        # TERMINATE immediately for instant savings
                        try:
                            self.ec2.terminate_instances(InstanceIds=[instance_id])
                            terminated.append({
                                'id': instance_id,
                                'type': instance_type,
                                'hourly_cost': hourly_cost
                            })
                            logger.critical(f"TERMINATED: {instance_id} ({instance_type}) - Saving ${hourly_cost}/hour")
                        except Exception as e:
                            # If terminate fails, force stop
                            self.ec2.stop_instances(InstanceIds=[instance_id], Force=True)
                            stopped.append(instance_id)
                            logger.error(f"FORCE STOPPED: {instance_id} - {e}")
                            
                    elif state == 'stopping':
                        # Force immediate termination
                        self.ec2.terminate_instances(InstanceIds=[instance_id])
                        terminated.append({
                            'id': instance_id,
                            'type': instance_type,
                            'hourly_cost': hourly_cost
                        })
                        
            # Delete ALL spot instance requests
            self.cancel_all_spot_requests()
            
            # Savings report
            daily_savings = total_hourly_savings * 24
            monthly_savings = daily_savings * 30
            
            result = {
                'action': 'EMERGENCY_SHUTDOWN',
                'reason': reason,
                'terminated_count': len(terminated),
                'stopped_count': len(stopped),
                'hourly_savings': f"${total_hourly_savings:.2f}",
                'daily_savings': f"${daily_savings:.2f}",
                'monthly_savings': f"${monthly_savings:.2f}",
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Send critical alert
            self.send_alert(result)
            
            # Log to CloudWatch
            self.log_shutdown_metrics(len(terminated), total_hourly_savings)
            
            logger.critical(f"EMERGENCY SHUTDOWN COMPLETE: {json.dumps(result)}")
            return result
            
        except Exception as e:
            logger.error(f"EMERGENCY SHUTDOWN ERROR: {e}")
            # Last resort: try region-wide shutdown
            return self.nuclear_option()
            
    def cancel_all_spot_requests(self):
        """
        Cancel ALL spot instance requests
        Prevents new instances from launching
        Cost impact: Prevents $100-500/day in new charges
        """
        try:
            spot_requests = self.ec2.describe_spot_instance_requests(
                Filters=[{'Name': 'state', 'Values': ['open', 'active']}]
            )
            
            request_ids = [req['SpotInstanceRequestId'] for req in spot_requests['SpotInstanceRequests']]
            
            if request_ids:
                self.ec2.cancel_spot_instance_requests(SpotInstanceRequestIds=request_ids)
                logger.info(f"CANCELLED {len(request_ids)} spot requests")
                
        except Exception as e:
            logger.error(f"Failed to cancel spot requests: {e}")
            
    def nuclear_option(self) -> Dict:
        """
        LAST RESORT: Terminate everything possible
        Used when normal termination fails
        """
        logger.critical("NUCLEAR OPTION ACTIVATED")
        
        # Try to terminate by tag
        try:
            response = self.ec2.describe_instances()
            all_ids = []
            for r in response['Reservations']:
                all_ids.extend([i['InstanceId'] for i in r['Instances']])
                
            if all_ids:
                # Batch terminate with force
                for batch in [all_ids[i:i+100] for i in range(0, len(all_ids), 100)]:
                    self.ec2.terminate_instances(InstanceIds=batch)
                    
            return {
                'action': 'NUCLEAR_SHUTDOWN',
                'instances_terminated': len(all_ids),
                'status': 'COMPLETE'
            }
        except Exception as e:
            return {'action': 'NUCLEAR_SHUTDOWN', 'status': 'FAILED', 'error': str(e)}
            
    def delete_all_volumes(self):
        """
        Delete ALL unattached EBS volumes
        Cost impact: SAVES $50-200/month per volume
        """
        try:
            volumes = self.ec2.describe_volumes(
                Filters=[{'Name': 'status', 'Values': ['available']}]
            )
            
            deleted = 0
            saved_gb = 0
            
            for volume in volumes['Volumes']:
                try:
                    self.ec2.delete_volume(VolumeId=volume['VolumeId'])
                    deleted += 1
                    saved_gb += volume['Size']
                    logger.info(f"DELETED VOLUME: {volume['VolumeId']} ({volume['Size']}GB)")
                except Exception as e:
                    logger.error(f"Failed to delete volume {volume['VolumeId']}: {e}")
                    
            # Cost saved: $0.10/GB/month
            monthly_savings = saved_gb * 0.10
            logger.info(f"DELETED {deleted} volumes, {saved_gb}GB - Saving ${monthly_savings:.2f}/month")
            
        except Exception as e:
            logger.error(f"Volume deletion failed: {e}")
            
    def send_alert(self, result: Dict):
        """
        Send emergency alert to ops team
        """
        try:
            message = f"""
            EMERGENCY SHUTDOWN EXECUTED
            
            Reason: {result['reason']}
            Instances Terminated: {result['terminated_count']}
            Hourly Savings: {result['hourly_savings']}
            Daily Savings: {result['daily_savings']}
            Monthly Savings: {result['monthly_savings']}
            
            Action Required: Review and acknowledge
            """
            
            self.sns.publish(
                TopicArn='arn:aws:sns:us-east-1:account:emergency-alerts',
                Subject='CRITICAL: Emergency Shutdown Executed',
                Message=message
            )
        except:
            pass  # Don't fail on alert errors
            
    def log_shutdown_metrics(self, instance_count: int, hourly_savings: float):
        """
        Log shutdown metrics to CloudWatch
        """
        try:
            self.cloudwatch.put_metric_data(
                Namespace='CostControl',
                MetricData=[
                    {
                        'MetricName': 'EmergencyShutdowns',
                        'Value': 1,
                        'Unit': 'Count'
                    },
                    {
                        'MetricName': 'InstancesTerminated',
                        'Value': instance_count,
                        'Unit': 'Count'
                    },
                    {
                        'MetricName': 'HourlySavings',
                        'Value': hourly_savings,
                        'Unit': 'None'
                    }
                ]
            )
        except:
            pass  # Don't fail on metrics errors

def lambda_handler(event, context):
    """
    Lambda entry point for CloudWatch/Manual triggers
    Executes IMMEDIATE shutdown
    """
    shutdown = EmergencyShutdown()
    
    # Determine trigger reason
    reason = "MANUAL_TRIGGER"
    if 'source' in event:
        if event['source'] == 'aws.budgets':
            reason = "BUDGET_BREACH"
        elif event['source'] == 'aws.cloudwatch':
            reason = "ALARM_TRIGGERED"
            
    # EXECUTE SHUTDOWN
    result = shutdown.kill_all_instances(reason)
    
    # Clean up volumes
    shutdown.delete_all_volumes()
    
    return {
        'statusCode': 200,
        'body': json.dumps(result)
    }

def manual_trigger():
    """
    Manual execution for emergency situations
    """
    print("=" * 50)
    print("EMERGENCY SHUTDOWN - MANUAL TRIGGER")
    print("=" * 50)
    
    confirm = input("Type 'SHUTDOWN' to confirm: ")
    if confirm == 'SHUTDOWN':
        shutdown = EmergencyShutdown()
        result = shutdown.kill_all_instances("MANUAL_EMERGENCY")
        shutdown.delete_all_volumes()
        print(json.dumps(result, indent=2))
    else:
        print("Shutdown cancelled")

if __name__ == "__main__":
    manual_trigger()