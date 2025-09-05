#!/usr/bin/env python3
"""
Scheduled Operations - AUTOMATIC COST CONTROL
Auto-stop all dev/staging at 7 PM
Weekend shutdown for non-production
Holiday calendar integration
"""

import boto3
import json
import logging
from datetime import datetime, timedelta, time
from typing import List, Dict, Set
import pytz

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CostScheduler:
    """
    AUTOMATED SCHEDULE-BASED COST CONTROL
    Stop instances outside business hours
    Save 60%+ on non-production resources
    """
    
    def __init__(self):
        self.ec2 = boto3.client('ec2')
        self.events = boto3.client('events')
        self.lambda_client = boto3.client('lambda')
        
        # SCHEDULE CONFIGURATION
        self.BUSINESS_START = time(7, 0)  # 7:00 AM
        self.BUSINESS_END = time(19, 0)   # 7:00 PM
        self.TIMEZONE = pytz.timezone('US/Eastern')
        
        # HOLIDAYS 2024-2025 (US Federal)
        self.HOLIDAYS = [
            '2024-01-01',  # New Year's Day
            '2024-01-15',  # MLK Day
            '2024-02-19',  # Presidents Day
            '2024-05-27',  # Memorial Day
            '2024-07-04',  # Independence Day
            '2024-09-02',  # Labor Day
            '2024-11-28',  # Thanksgiving
            '2024-12-25',  # Christmas
            '2025-01-01',  # New Year's Day
            '2025-01-20',  # MLK Day
            '2025-02-17',  # Presidents Day
            '2025-05-26',  # Memorial Day
            '2025-07-04',  # Independence Day
            '2025-09-01',  # Labor Day
            '2025-11-27',  # Thanksgiving
            '2025-12-25',  # Christmas
        ]
        
        # Environment shutdown rules
        self.SHUTDOWN_RULES = {
            'dev': {
                'weekdays': self.BUSINESS_END,  # Stop at 7 PM
                'weekends': True,  # Shut down on weekends
                'holidays': True,  # Shut down on holidays
            },
            'staging': {
                'weekdays': self.BUSINESS_END,  # Stop at 7 PM
                'weekends': True,  # Shut down on weekends
                'holidays': True,  # Shut down on holidays
            },
            'test': {
                'weekdays': self.BUSINESS_END,  # Stop at 7 PM
                'weekends': True,  # Shut down on weekends
                'holidays': True,  # Shut down on holidays
            },
            'prod': {
                'weekdays': None,  # Never auto-stop
                'weekends': False,  # Keep running
                'holidays': False,  # Keep running
            }
        }
        
    def execute_schedule(self) -> Dict:
        """
        Execute scheduled operations based on current time
        Cost impact: SAVES 60%+ on non-production costs
        """
        now = datetime.now(self.TIMEZONE)
        current_time = now.time()
        is_weekend = now.weekday() >= 5  # Saturday = 5, Sunday = 6
        is_holiday = now.strftime('%Y-%m-%d') in self.HOLIDAYS
        
        results = {
            'timestamp': now.isoformat(),
            'is_business_hours': self.is_business_hours(now),
            'is_weekend': is_weekend,
            'is_holiday': is_holiday,
            'stopped_instances': [],
            'started_instances': [],
            'scheduled_stops': [],
            'estimated_savings': 0.0
        }
        
        logger.info(f"Executing schedule: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        
        # Get all instances with environment tags
        instances = self.get_instances_by_environment()
        
        for env, instance_list in instances.items():
            rules = self.SHUTDOWN_RULES.get(env, {})
            
            # Skip production unless explicitly configured
            if env == 'prod':
                continue
                
            for instance in instance_list:
                instance_id = instance['InstanceId']
                instance_type = instance['InstanceType']
                state = instance['State']['Name']
                
                should_stop = self.should_stop_instance(env, now, rules)
                should_start = self.should_start_instance(env, now, rules)
                
                if should_stop and state == 'running':
                    # Stop the instance
                    self.stop_instance(instance_id, f"Scheduled stop - {env}")
                    results['stopped_instances'].append({
                        'instance_id': instance_id,
                        'environment': env,
                        'type': instance_type,
                        'reason': 'scheduled_shutdown'
                    })
                    
                    # Calculate savings
                    hourly_cost = self.get_instance_cost(instance_type)
                    hours_until_start = self.hours_until_business_start(now)
                    results['estimated_savings'] += hourly_cost * hours_until_start
                    
                elif should_start and state == 'stopped':
                    # Only start if auto-stopped (check tags)
                    tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                    if tags.get('AutoStopped') == 'true':
                        self.start_instance(instance_id, f"Scheduled start - {env}")
                        results['started_instances'].append({
                            'instance_id': instance_id,
                            'environment': env,
                            'type': instance_type,
                            'reason': 'scheduled_start'
                        })
                        
        # Schedule future stops
        results['scheduled_stops'] = self.get_scheduled_stops(instances)
        
        # Create CloudWatch events for next actions
        self.create_scheduled_events()
        
        logger.info(f"Schedule execution complete: {len(results['stopped_instances'])} stopped, {len(results['started_instances'])} started")
        logger.info(f"Estimated savings: ${results['estimated_savings']:.2f}")
        
        return results
        
    def should_stop_instance(self, env: str, now: datetime, rules: Dict) -> bool:
        """
        Determine if instance should be stopped
        """
        current_time = now.time()
        is_weekend = now.weekday() >= 5
        is_holiday = now.strftime('%Y-%m-%d') in self.HOLIDAYS
        
        # Check holiday rule
        if is_holiday and rules.get('holidays'):
            return True
            
        # Check weekend rule
        if is_weekend and rules.get('weekends'):
            return True
            
        # Check weekday time rule
        if not is_weekend and not is_holiday:
            stop_time = rules.get('weekdays')
            if stop_time and current_time >= stop_time:
                return True
                
        return False
        
    def should_start_instance(self, env: str, now: datetime, rules: Dict) -> bool:
        """
        Determine if instance should be started
        """
        current_time = now.time()
        is_weekend = now.weekday() >= 5
        is_holiday = now.strftime('%Y-%m-%d') in self.HOLIDAYS
        
        # Don't start on weekends if weekend shutdown is enabled
        if is_weekend and rules.get('weekends'):
            return False
            
        # Don't start on holidays if holiday shutdown is enabled
        if is_holiday and rules.get('holidays'):
            return False
            
        # Start at business hours on weekdays
        if not is_weekend and not is_holiday:
            if self.BUSINESS_START <= current_time < self.BUSINESS_END:
                return True
                
        return False
        
    def get_instances_by_environment(self) -> Dict[str, List]:
        """
        Get instances grouped by environment
        """
        environments = {}
        
        try:
            response = self.ec2.describe_instances(
                Filters=[
                    {'Name': 'instance-state-name', 'Values': ['running', 'stopped']}
                ]
            )
            
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                    env = tags.get('Environment', 'unknown').lower()
                    
                    if env not in environments:
                        environments[env] = []
                        
                    environments[env].append(instance)
                    
        except Exception as e:
            logger.error(f"Failed to get instances: {e}")
            
        return environments
        
    def stop_instance(self, instance_id: str, reason: str):
        """
        Stop instance and tag it
        """
        try:
            # Stop the instance
            self.ec2.stop_instances(InstanceIds=[instance_id])
            
            # Tag it as auto-stopped
            self.ec2.create_tags(
                Resources=[instance_id],
                Tags=[
                    {'Key': 'AutoStopped', 'Value': 'true'},
                    {'Key': 'StopReason', 'Value': reason},
                    {'Key': 'StopTime', 'Value': datetime.utcnow().isoformat()}
                ]
            )
            
            logger.info(f"STOPPED: {instance_id} - {reason}")
            
        except Exception as e:
            logger.error(f"Failed to stop {instance_id}: {e}")
            
    def start_instance(self, instance_id: str, reason: str):
        """
        Start instance and update tags
        """
        try:
            # Start the instance
            self.ec2.start_instances(InstanceIds=[instance_id])
            
            # Update tags
            self.ec2.create_tags(
                Resources=[instance_id],
                Tags=[
                    {'Key': 'AutoStopped', 'Value': 'false'},
                    {'Key': 'StartReason', 'Value': reason},
                    {'Key': 'StartTime', 'Value': datetime.utcnow().isoformat()}
                ]
            )
            
            logger.info(f"STARTED: {instance_id} - {reason}")
            
        except Exception as e:
            logger.error(f"Failed to start {instance_id}: {e}")
            
    def is_business_hours(self, now: datetime) -> bool:
        """
        Check if current time is within business hours
        """
        current_time = now.time()
        is_weekend = now.weekday() >= 5
        is_holiday = now.strftime('%Y-%m-%d') in self.HOLIDAYS
        
        if is_weekend or is_holiday:
            return False
            
        return self.BUSINESS_START <= current_time < self.BUSINESS_END
        
    def hours_until_business_start(self, now: datetime) -> float:
        """
        Calculate hours until next business start
        """
        # If it's currently business hours, return 0
        if self.is_business_hours(now):
            return 0
            
        # Find next business day
        next_day = now + timedelta(days=1)
        while next_day.weekday() >= 5 or next_day.strftime('%Y-%m-%d') in self.HOLIDAYS:
            next_day += timedelta(days=1)
            
        # Calculate hours until business start
        next_start = datetime.combine(next_day.date(), self.BUSINESS_START)
        next_start = self.TIMEZONE.localize(next_start)
        
        delta = next_start - now
        return delta.total_seconds() / 3600
        
    def get_scheduled_stops(self, instances: Dict[str, List]) -> List[Dict]:
        """
        Get list of instances scheduled to stop
        """
        scheduled = []
        now = datetime.now(self.TIMEZONE)
        
        for env, instance_list in instances.items():
            if env == 'prod':
                continue
                
            rules = self.SHUTDOWN_RULES.get(env, {})
            stop_time = rules.get('weekdays')
            
            if stop_time:
                for instance in instance_list:
                    if instance['State']['Name'] == 'running':
                        scheduled.append({
                            'instance_id': instance['InstanceId'],
                            'environment': env,
                            'stop_time': stop_time.strftime('%H:%M'),
                            'type': instance['InstanceType']
                        })
                        
        return scheduled
        
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
        
    def create_scheduled_events(self):
        """
        Create CloudWatch Events for scheduled actions
        """
        try:
            # Create rule for evening shutdown (7 PM EST)
            self.events.put_rule(
                Name='evening-shutdown',
                ScheduleExpression='cron(0 23 * * ? *)',  # 7 PM EST = 23:00 UTC
                State='ENABLED',
                Description='Stop dev/staging instances at 7 PM EST'
            )
            
            # Create rule for morning startup (7 AM EST)
            self.events.put_rule(
                Name='morning-startup',
                ScheduleExpression='cron(0 11 ? * MON-FRI *)',  # 7 AM EST = 11:00 UTC, weekdays only
                State='ENABLED',
                Description='Start dev/staging instances at 7 AM EST on weekdays'
            )
            
            # Create rule for weekend shutdown
            self.events.put_rule(
                Name='weekend-shutdown',
                ScheduleExpression='cron(0 0 ? * SAT *)',  # Saturday midnight
                State='ENABLED',
                Description='Ensure all non-prod instances are stopped on weekends'
            )
            
            logger.info("Scheduled events created/updated")
            
        except Exception as e:
            logger.error(f"Failed to create scheduled events: {e}")
            
    def generate_savings_report(self) -> Dict:
        """
        Calculate savings from scheduling
        """
        # Assume 12 hours/day * 5 days/week operation for dev/staging
        # vs 24/7 operation
        
        instances = self.get_instances_by_environment()
        
        total_instances = 0
        total_hourly_cost = 0.0
        
        for env, instance_list in instances.items():
            if env in ['dev', 'staging', 'test']:
                for instance in instance_list:
                    total_instances += 1
                    total_hourly_cost += self.get_instance_cost(instance['InstanceType'])
                    
        # Calculate savings
        # Current: 24 hours * 7 days = 168 hours/week
        # Optimized: 12 hours * 5 days = 60 hours/week
        # Savings: 108 hours/week = 64%
        
        weekly_current = total_hourly_cost * 168
        weekly_optimized = total_hourly_cost * 60
        weekly_savings = weekly_current - weekly_optimized
        
        return {
            'non_prod_instances': total_instances,
            'hourly_cost': total_hourly_cost,
            'weekly_cost_current': weekly_current,
            'weekly_cost_optimized': weekly_optimized,
            'weekly_savings': weekly_savings,
            'monthly_savings': weekly_savings * 4.33,
            'annual_savings': weekly_savings * 52,
            'savings_percentage': 64
        }

def lambda_handler(event, context):
    """
    Lambda entry point for scheduled execution
    """
    scheduler = CostScheduler()
    result = scheduler.execute_schedule()
    
    return {
        'statusCode': 200,
        'body': json.dumps(result, default=str)
    }

if __name__ == "__main__":
    scheduler = CostScheduler()
    
    print("=" * 60)
    print("COST SCHEDULER - AUTOMATED SHUTDOWN/STARTUP")
    print("=" * 60)
    
    now = datetime.now(scheduler.TIMEZONE)
    print(f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Business hours: {scheduler.BUSINESS_START} - {scheduler.BUSINESS_END}")
    print(f"Is business hours: {scheduler.is_business_hours(now)}")
    print(f"Is weekend: {now.weekday() >= 5}")
    print(f"Is holiday: {now.strftime('%Y-%m-%d') in scheduler.HOLIDAYS}")
    
    print("\nEXECUTING SCHEDULE...")
    result = scheduler.execute_schedule()
    
    print(f"\nRESULTS:")
    print(f"Stopped instances: {len(result['stopped_instances'])}")
    print(f"Started instances: {len(result['started_instances'])}")
    print(f"Estimated savings: ${result['estimated_savings']:.2f}")
    
    if result['scheduled_stops']:
        print(f"\nSCHEDULED STOPS:")
        for stop in result['scheduled_stops']:
            print(f"  - {stop['instance_id']} ({stop['environment']}) at {stop['stop_time']}")
            
    print("\nSAVINGS PROJECTION:")
    savings = scheduler.generate_savings_report()
    print(f"Non-prod instances: {savings['non_prod_instances']}")
    print(f"Current weekly cost: ${savings['weekly_cost_current']:.2f}")
    print(f"Optimized weekly cost: ${savings['weekly_cost_optimized']:.2f}")
    print(f"Weekly savings: ${savings['weekly_savings']:.2f}")
    print(f"Monthly savings: ${savings['monthly_savings']:.2f}")
    print(f"Annual savings: ${savings['annual_savings']:.2f}")
    print(f"Savings percentage: {savings['savings_percentage']}%")