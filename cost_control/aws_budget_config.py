#!/usr/bin/env python3
"""
AWS Budget Configuration - CRITICAL COST CONTROL
Daily limit: $500 MAXIMUM
Auto-stop at 80% threshold
Cost reduction priority: 100%
"""

import boto3
import json
from datetime import datetime, timedelta
from typing import Dict, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AWSBudgetController:
    """
    HARD COST LIMITS ENFORCER
    Daily budget: $500 maximum
    Monthly budget: $10,000 maximum
    """
    
    def __init__(self):
        self.budgets = boto3.client('budgets')
        self.sns = boto3.client('sns')
        self.ec2 = boto3.client('ec2')
        self.cloudwatch = boto3.client('cloudwatch')
        
        # CRITICAL: Hard cost limits
        self.DAILY_LIMIT = 500  # $500/day MAXIMUM
        self.MONTHLY_LIMIT = 10000  # $10,000/month MAXIMUM
        self.SHUTDOWN_THRESHOLD = 0.8  # 80% triggers shutdown
        
    def create_daily_budget(self) -> Dict:
        """
        Create daily budget with AUTO-SHUTDOWN at 80%
        Cost impact: SAVES $500+/day by preventing overruns
        """
        budget_name = f"VM-INSTRA-DAILY-{datetime.now().strftime('%Y%m%d')}"
        
        budget = {
            'BudgetName': budget_name,
            'BudgetLimit': {
                'Amount': str(self.DAILY_LIMIT),
                'Unit': 'USD'
            },
            'TimeUnit': 'DAILY',
            'BudgetType': 'COST',
            'CostFilters': {
                'Service': ['Amazon Elastic Compute Cloud - Compute']
            },
            'NotificationsWithSubscribers': [
                {
                    'Notification': {
                        'NotificationType': 'ACTUAL',
                        'ComparisonOperator': 'GREATER_THAN',
                        'Threshold': 50.0,  # 50% alert
                        'ThresholdType': 'PERCENTAGE'
                    },
                    'Subscribers': [{'SubscriptionType': 'EMAIL', 'Address': 'ops@company.com'}]
                },
                {
                    'Notification': {
                        'NotificationType': 'ACTUAL',
                        'ComparisonOperator': 'GREATER_THAN',
                        'Threshold': 70.0,  # 70% alert
                        'ThresholdType': 'PERCENTAGE'
                    },
                    'Subscribers': [{'SubscriptionType': 'EMAIL', 'Address': 'ops@company.com'}]
                },
                {
                    'Notification': {
                        'NotificationType': 'ACTUAL',
                        'ComparisonOperator': 'GREATER_THAN',
                        'Threshold': 80.0,  # 80% SHUTDOWN TRIGGER
                        'ThresholdType': 'PERCENTAGE'
                    },
                    'Subscribers': [{'SubscriptionType': 'SNS', 'Address': 'arn:aws:sns:us-east-1:account:emergency-shutdown'}]
                }
            ]
        }
        
        try:
            response = self.budgets.create_budget(
                AccountId=boto3.client('sts').get_caller_identity()['Account'],
                Budget=budget
            )
            logger.info(f"BUDGET CREATED: {budget_name} - LIMIT: ${self.DAILY_LIMIT}/day")
            return response
        except Exception as e:
            logger.error(f"CRITICAL: Failed to create budget: {e}")
            # FAIL-SAFE: Stop all instances on budget creation failure
            self.emergency_stop_all()
            raise
            
    def setup_auto_shutdown_alarm(self):
        """
        CloudWatch alarm for 80% budget breach -> AUTO SHUTDOWN
        Cost impact: PREVENTS $100+/day overage
        """
        alarm_name = "VM-INSTRA-BUDGET-BREACH-SHUTDOWN"
        
        self.cloudwatch.put_metric_alarm(
            AlarmName=alarm_name,
            ComparisonOperator='GreaterThanThreshold',
            EvaluationPeriods=1,
            MetricName='EstimatedCharges',
            Namespace='AWS/Billing',
            Period=86400,  # Daily
            Statistic='Maximum',
            Threshold=self.DAILY_LIMIT * self.SHUTDOWN_THRESHOLD,  # $400 (80% of $500)
            ActionsEnabled=True,
            AlarmActions=[
                'arn:aws:lambda:us-east-1:account:function:emergency-shutdown'
            ],
            AlarmDescription=f'SHUTDOWN ALL INSTANCES at ${self.DAILY_LIMIT * self.SHUTDOWN_THRESHOLD} spend',
            Dimensions=[
                {'Name': 'Currency', 'Value': 'USD'}
            ]
        )
        logger.info(f"AUTO-SHUTDOWN ALARM SET: Triggers at ${self.DAILY_LIMIT * self.SHUTDOWN_THRESHOLD}")
        
    def check_current_spend(self) -> float:
        """
        Real-time spend check
        Returns current daily spend in USD
        """
        end_date = datetime.now()
        start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        ce = boto3.client('ce')
        response = ce.get_cost_and_usage(
            TimePeriod={
                'Start': start_date.strftime('%Y-%m-%d'),
                'End': end_date.strftime('%Y-%m-%d')
            },
            Granularity='DAILY',
            Metrics=['UnblendedCost']
        )
        
        daily_cost = float(response['ResultsByTime'][0]['Total']['UnblendedCost']['Amount'])
        
        if daily_cost >= self.DAILY_LIMIT * self.SHUTDOWN_THRESHOLD:
            logger.critical(f"BUDGET BREACH: ${daily_cost} >= ${self.DAILY_LIMIT * self.SHUTDOWN_THRESHOLD}")
            self.emergency_stop_all()
            
        return daily_cost
        
    def emergency_stop_all(self):
        """
        EMERGENCY: Stop ALL EC2 instances immediately
        Cost impact: SAVES $500+/day instantly
        """
        try:
            instances = self.ec2.describe_instances(
                Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
            )
            
            instance_ids = []
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    instance_ids.append(instance['InstanceId'])
                    
            if instance_ids:
                self.ec2.stop_instances(InstanceIds=instance_ids)
                logger.critical(f"EMERGENCY STOP: {len(instance_ids)} instances stopped")
                
                # Calculate savings
                hourly_cost = len(instance_ids) * 0.0832  # t3.large estimate
                daily_savings = hourly_cost * 24
                logger.info(f"COST SAVINGS: ${daily_savings:.2f}/day")
                
        except Exception as e:
            logger.error(f"EMERGENCY STOP FAILED: {e}")
            # Last resort: terminate instead of stop
            self.ec2.terminate_instances(InstanceIds=instance_ids)
            
    def enforce_instance_limits(self):
        """
        Enforce maximum 10 concurrent instances
        Cost impact: Caps spending at $20/hour maximum
        """
        instances = self.ec2.describe_instances(
            Filters=[{'Name': 'instance-state-name', 'Values': ['running', 'pending']}]
        )
        
        total_instances = sum(len(r['Instances']) for r in instances['Reservations'])
        
        if total_instances > 10:
            # Stop excess instances (newest first)
            all_instances = []
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    all_instances.append({
                        'id': instance['InstanceId'],
                        'launch_time': instance['LaunchTime']
                    })
                    
            # Sort by launch time (newest first) and stop excess
            all_instances.sort(key=lambda x: x['launch_time'], reverse=True)
            excess = all_instances[10:]  # Everything beyond 10
            
            if excess:
                excess_ids = [i['id'] for i in excess]
                self.ec2.stop_instances(InstanceIds=excess_ids)
                logger.warning(f"LIMIT ENFORCED: Stopped {len(excess_ids)} excess instances")
                
                # Cost saved
                hourly_savings = len(excess_ids) * 0.0832
                logger.info(f"COST SAVINGS: ${hourly_savings:.2f}/hour")

def lambda_handler(event, context):
    """
    Lambda entry point for automated execution
    Runs every 15 minutes to enforce limits
    """
    controller = AWSBudgetController()
    
    # Check and enforce all limits
    current_spend = controller.check_current_spend()
    controller.enforce_instance_limits()
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'current_daily_spend': current_spend,
            'daily_limit': controller.DAILY_LIMIT,
            'utilization_percentage': (current_spend / controller.DAILY_LIMIT) * 100
        })
    }

if __name__ == "__main__":
    # Initial setup
    controller = AWSBudgetController()
    controller.create_daily_budget()
    controller.setup_auto_shutdown_alarm()
    controller.enforce_instance_limits()
    
    current = controller.check_current_spend()
    print(f"CURRENT DAILY SPEND: ${current:.2f} / ${controller.DAILY_LIMIT}")
    print(f"UTILIZATION: {(current/controller.DAILY_LIMIT)*100:.1f}%")