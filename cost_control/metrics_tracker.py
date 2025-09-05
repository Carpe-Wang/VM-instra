#!/usr/bin/env python3
"""
Metrics Tracker - COMPREHENSIVE COST TRACKING
Track and report DAILY on all cost metrics
Calculate savings, project costs, alert on anomalies
Zero tolerance for untracked expenses
"""

import boto3
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import pandas as pd
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MetricsTracker:
    """
    COMPREHENSIVE METRICS TRACKING
    Every dollar, every instance, every hour
    Complete cost visibility
    """
    
    def __init__(self):
        self.ec2 = boto3.client('ec2')
        self.ce = boto3.client('ce')  # Cost Explorer
        self.cloudwatch = boto3.client('cloudwatch')
        self.sns = boto3.client('sns')
        
        # Metrics to track
        self.METRICS = {
            'total_aws_spend': 'Total AWS spend across all services',
            'cost_per_instance_hour': 'Average cost per instance hour',
            'spot_savings_percentage': 'Percentage saved using spot instances',
            'idle_resource_waste': 'Cost of idle/unused resources',
            'projected_monthly_cost': 'Projected cost for current month',
            'budget_utilization': 'Percentage of budget used',
            'cost_per_environment': 'Cost breakdown by environment',
            'cost_per_service': 'Cost breakdown by AWS service',
            'instance_efficiency': 'CPU/memory utilization vs cost',
            'savings_achieved': 'Total savings from optimization'
        }
        
        # Cost targets
        self.DAILY_TARGET = 100  # $100/day target
        self.MONTHLY_TARGET = 3000  # $3,000/month target
        
    def track_all_metrics(self) -> Dict:
        """
        Track all cost metrics and report
        """
        report_date = datetime.utcnow()
        
        report = {
            'report_date': report_date.isoformat(),
            'metrics': {},
            'alerts': [],
            'recommendations': [],
            'daily_summary': None,
            'weekly_trend': None,
            'monthly_projection': None
        }
        
        # 1. Total AWS Spend
        report['metrics']['total_aws_spend'] = self.track_total_spend()
        
        # 2. Cost per Instance Hour
        report['metrics']['cost_per_instance_hour'] = self.track_instance_costs()
        
        # 3. Spot Savings
        report['metrics']['spot_savings'] = self.track_spot_savings()
        
        # 4. Idle Resource Waste
        report['metrics']['idle_waste'] = self.track_idle_waste()
        
        # 5. Projected Monthly Cost
        report['metrics']['monthly_projection'] = self.project_monthly_cost()
        
        # 6. Budget Utilization
        report['metrics']['budget_utilization'] = self.track_budget_utilization()
        
        # 7. Cost by Environment
        report['metrics']['environment_costs'] = self.track_environment_costs()
        
        # 8. Cost by Service
        report['metrics']['service_costs'] = self.track_service_costs()
        
        # 9. Instance Efficiency
        report['metrics']['instance_efficiency'] = self.track_instance_efficiency()
        
        # 10. Savings Achieved
        report['metrics']['savings_achieved'] = self.track_savings_achieved()
        
        # Generate summaries
        report['daily_summary'] = self.generate_daily_summary(report['metrics'])
        report['weekly_trend'] = self.analyze_weekly_trend()
        report['monthly_projection'] = self.project_month_end()
        
        # Check for alerts
        report['alerts'] = self.check_alerts(report['metrics'])
        
        # Generate recommendations
        report['recommendations'] = self.generate_recommendations(report['metrics'])
        
        # Publish to CloudWatch
        self.publish_metrics(report['metrics'])
        
        # Send daily report
        self.send_daily_report(report)
        
        return report
        
    def track_total_spend(self) -> Dict:
        """
        Track total AWS spend
        """
        try:
            today = datetime.utcnow().date()
            yesterday = today - timedelta(days=1)
            week_ago = today - timedelta(days=7)
            month_ago = today - timedelta(days=30)
            
            # Today's spend
            today_spend = self.get_cost_for_period(today, today + timedelta(days=1))
            
            # Yesterday's spend
            yesterday_spend = self.get_cost_for_period(yesterday, today)
            
            # Last 7 days
            week_spend = self.get_cost_for_period(week_ago, today)
            
            # Last 30 days
            month_spend = self.get_cost_for_period(month_ago, today)
            
            return {
                'today': today_spend,
                'yesterday': yesterday_spend,
                'last_7_days': week_spend,
                'last_30_days': month_spend,
                'daily_average': month_spend / 30,
                'vs_target': {
                    'daily': today_spend - self.DAILY_TARGET,
                    'monthly': month_spend - self.MONTHLY_TARGET
                }
            }
        except Exception as e:
            logger.error(f"Failed to track total spend: {e}")
            return {}
            
    def track_instance_costs(self) -> Dict:
        """
        Track cost per instance hour
        """
        try:
            instances = self.ec2.describe_instances(
                Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
            )
            
            total_hourly_cost = 0
            instance_count = 0
            instance_details = []
            
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    instance_count += 1
                    instance_type = instance['InstanceType']
                    is_spot = instance.get('InstanceLifecycle') == 'spot'
                    
                    # Get hourly cost
                    hourly_cost = self.get_instance_hourly_cost(instance_type, is_spot)
                    total_hourly_cost += hourly_cost
                    
                    # Calculate total cost since launch
                    launch_time = instance['LaunchTime']
                    hours_running = (datetime.utcnow() - launch_time.replace(tzinfo=None)).total_seconds() / 3600
                    total_cost = hourly_cost * hours_running
                    
                    instance_details.append({
                        'instance_id': instance['InstanceId'],
                        'type': instance_type,
                        'is_spot': is_spot,
                        'hourly_cost': hourly_cost,
                        'hours_running': hours_running,
                        'total_cost': total_cost
                    })
                    
            # Sort by cost
            instance_details.sort(key=lambda x: x['total_cost'], reverse=True)
            
            return {
                'total_instances': instance_count,
                'total_hourly_cost': total_hourly_cost,
                'average_hourly_cost': total_hourly_cost / instance_count if instance_count > 0 else 0,
                'projected_daily_cost': total_hourly_cost * 24,
                'projected_monthly_cost': total_hourly_cost * 24 * 30,
                'top_5_expensive': instance_details[:5],
                'cost_distribution': {
                    'spot': sum(i['hourly_cost'] for i in instance_details if i['is_spot']),
                    'on_demand': sum(i['hourly_cost'] for i in instance_details if not i['is_spot'])
                }
            }
        except Exception as e:
            logger.error(f"Failed to track instance costs: {e}")
            return {}
            
    def track_spot_savings(self) -> Dict:
        """
        Track savings from spot instances
        """
        try:
            instances = self.ec2.describe_instances(
                Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
            )
            
            spot_cost = 0
            on_demand_equivalent = 0
            spot_count = 0
            on_demand_count = 0
            
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    instance_type = instance['InstanceType']
                    is_spot = instance.get('InstanceLifecycle') == 'spot'
                    
                    on_demand_price = self.get_instance_hourly_cost(instance_type, False)
                    
                    if is_spot:
                        spot_count += 1
                        actual_price = on_demand_price * 0.3  # Assume 70% savings
                        spot_cost += actual_price
                        on_demand_equivalent += on_demand_price
                    else:
                        on_demand_count += 1
                        
            savings = on_demand_equivalent - spot_cost if on_demand_equivalent > 0 else 0
            savings_percentage = (savings / on_demand_equivalent * 100) if on_demand_equivalent > 0 else 0
            
            return {
                'spot_instances': spot_count,
                'on_demand_instances': on_demand_count,
                'spot_percentage': (spot_count / (spot_count + on_demand_count) * 100) if (spot_count + on_demand_count) > 0 else 0,
                'hourly_spot_cost': spot_cost,
                'hourly_on_demand_equivalent': on_demand_equivalent,
                'hourly_savings': savings,
                'daily_savings': savings * 24,
                'monthly_savings': savings * 24 * 30,
                'savings_percentage': savings_percentage
            }
        except Exception as e:
            logger.error(f"Failed to track spot savings: {e}")
            return {}
            
    def track_idle_waste(self) -> Dict:
        """
        Track cost of idle resources
        """
        idle_cost = 0
        idle_resources = []
        
        try:
            # Check for idle instances
            instances = self.ec2.describe_instances(
                Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
            )
            
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    instance_id = instance['InstanceId']
                    instance_type = instance['InstanceType']
                    
                    # Check CPU utilization
                    cpu_util = self.get_instance_cpu_utilization(instance_id)
                    
                    if cpu_util < 5:  # Less than 5% CPU = idle
                        hourly_cost = self.get_instance_hourly_cost(instance_type, instance.get('InstanceLifecycle') == 'spot')
                        idle_cost += hourly_cost
                        idle_resources.append({
                            'type': 'instance',
                            'id': instance_id,
                            'instance_type': instance_type,
                            'cpu_utilization': cpu_util,
                            'hourly_cost': hourly_cost
                        })
                        
            # Check for unattached volumes
            volumes = self.ec2.describe_volumes(
                Filters=[{'Name': 'status', 'Values': ['available']}]
            )
            
            for volume in volumes['Volumes']:
                size_gb = volume['Size']
                monthly_cost = size_gb * 0.10  # $0.10/GB/month
                hourly_cost = monthly_cost / (30 * 24)
                idle_cost += hourly_cost
                idle_resources.append({
                    'type': 'volume',
                    'id': volume['VolumeId'],
                    'size_gb': size_gb,
                    'hourly_cost': hourly_cost
                })
                
            return {
                'idle_resources_count': len(idle_resources),
                'hourly_waste': idle_cost,
                'daily_waste': idle_cost * 24,
                'monthly_waste': idle_cost * 24 * 30,
                'top_5_idle': sorted(idle_resources, key=lambda x: x['hourly_cost'], reverse=True)[:5]
            }
        except Exception as e:
            logger.error(f"Failed to track idle waste: {e}")
            return {}
            
    def project_monthly_cost(self) -> Dict:
        """
        Project monthly cost based on current run rate
        """
        try:
            today = datetime.utcnow().date()
            month_start = today.replace(day=1)
            days_in_month = 30
            days_elapsed = (today - month_start).days + 1
            days_remaining = days_in_month - days_elapsed
            
            # Get cost so far this month
            month_to_date = self.get_cost_for_period(month_start, today + timedelta(days=1))
            
            # Calculate daily average
            daily_average = month_to_date / days_elapsed if days_elapsed > 0 else 0
            
            # Project month end
            projected_total = month_to_date + (daily_average * days_remaining)
            
            # Get last 7 days trend
            week_ago = today - timedelta(days=7)
            last_week_cost = self.get_cost_for_period(week_ago, today)
            recent_daily_average = last_week_cost / 7
            
            # Trend-adjusted projection
            trend_projection = month_to_date + (recent_daily_average * days_remaining)
            
            return {
                'month_to_date': month_to_date,
                'days_elapsed': days_elapsed,
                'days_remaining': days_remaining,
                'daily_average': daily_average,
                'recent_daily_average': recent_daily_average,
                'projected_total': projected_total,
                'trend_projection': trend_projection,
                'vs_budget': projected_total - self.MONTHLY_TARGET,
                'on_track': projected_total <= self.MONTHLY_TARGET
            }
        except Exception as e:
            logger.error(f"Failed to project monthly cost: {e}")
            return {}
            
    def track_budget_utilization(self) -> Dict:
        """
        Track budget utilization
        """
        try:
            today = datetime.utcnow().date()
            month_start = today.replace(day=1)
            
            # Daily budget utilization
            today_spend = self.get_cost_for_period(today, today + timedelta(days=1))
            daily_utilization = (today_spend / self.DAILY_TARGET * 100) if self.DAILY_TARGET > 0 else 0
            
            # Monthly budget utilization
            month_spend = self.get_cost_for_period(month_start, today + timedelta(days=1))
            monthly_utilization = (month_spend / self.MONTHLY_TARGET * 100) if self.MONTHLY_TARGET > 0 else 0
            
            # Days until budget exhausted at current rate
            daily_rate = today_spend
            if daily_rate > 0:
                days_until_exhausted = (self.MONTHLY_TARGET - month_spend) / daily_rate
            else:
                days_until_exhausted = float('inf')
                
            return {
                'daily': {
                    'budget': self.DAILY_TARGET,
                    'spent': today_spend,
                    'utilization': daily_utilization,
                    'remaining': self.DAILY_TARGET - today_spend
                },
                'monthly': {
                    'budget': self.MONTHLY_TARGET,
                    'spent': month_spend,
                    'utilization': monthly_utilization,
                    'remaining': self.MONTHLY_TARGET - month_spend
                },
                'days_until_budget_exhausted': days_until_exhausted,
                'alert_level': self.get_alert_level(monthly_utilization)
            }
        except Exception as e:
            logger.error(f"Failed to track budget utilization: {e}")
            return {}
            
    def track_environment_costs(self) -> List[Dict]:
        """
        Track costs by environment
        """
        try:
            instances = self.ec2.describe_instances()
            
            env_costs = defaultdict(lambda: {'count': 0, 'hourly_cost': 0, 'instances': []})
            
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    if instance['State']['Name'] in ['running', 'stopped']:
                        tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                        env = tags.get('Environment', 'unknown')
                        instance_type = instance['InstanceType']
                        is_spot = instance.get('InstanceLifecycle') == 'spot'
                        
                        hourly_cost = 0
                        if instance['State']['Name'] == 'running':
                            hourly_cost = self.get_instance_hourly_cost(instance_type, is_spot)
                            
                        env_costs[env]['count'] += 1
                        env_costs[env]['hourly_cost'] += hourly_cost
                        env_costs[env]['instances'].append({
                            'id': instance['InstanceId'],
                            'type': instance_type,
                            'state': instance['State']['Name'],
                            'hourly_cost': hourly_cost
                        })
                        
            # Convert to list and calculate totals
            result = []
            for env, data in env_costs.items():
                result.append({
                    'environment': env,
                    'instance_count': data['count'],
                    'hourly_cost': data['hourly_cost'],
                    'daily_cost': data['hourly_cost'] * 24,
                    'monthly_cost': data['hourly_cost'] * 24 * 30,
                    'top_instances': sorted(data['instances'], key=lambda x: x['hourly_cost'], reverse=True)[:3]
                })
                
            return sorted(result, key=lambda x: x['monthly_cost'], reverse=True)
            
        except Exception as e:
            logger.error(f"Failed to track environment costs: {e}")
            return []
            
    def track_service_costs(self) -> List[Dict]:
        """
        Track costs by AWS service
        """
        try:
            today = datetime.utcnow().date()
            month_start = today.replace(day=1)
            
            response = self.ce.get_cost_and_usage(
                TimePeriod={
                    'Start': month_start.isoformat(),
                    'End': (today + timedelta(days=1)).isoformat()
                },
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
            )
            
            services = []
            if response['ResultsByTime']:
                total_cost = 0
                for group in response['ResultsByTime'][0].get('Groups', []):
                    service = group['Keys'][0]
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])
                    total_cost += cost
                    
                    if cost > 0.01:
                        services.append({
                            'service': service,
                            'monthly_cost': cost,
                            'daily_average': cost / (today.day),
                            'percentage': 0  # Will calculate after
                        })
                        
                # Calculate percentages
                for service in services:
                    service['percentage'] = (service['monthly_cost'] / total_cost * 100) if total_cost > 0 else 0
                    
            return sorted(services, key=lambda x: x['monthly_cost'], reverse=True)
            
        except Exception as e:
            logger.error(f"Failed to track service costs: {e}")
            return []
            
    def track_instance_efficiency(self) -> Dict:
        """
        Track instance efficiency (utilization vs cost)
        """
        try:
            instances = self.ec2.describe_instances(
                Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
            )
            
            efficient = []
            inefficient = []
            total_efficiency_score = 0
            instance_count = 0
            
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    instance_id = instance['InstanceId']
                    instance_type = instance['InstanceType']
                    is_spot = instance.get('InstanceLifecycle') == 'spot'
                    
                    # Get utilization
                    cpu_util = self.get_instance_cpu_utilization(instance_id)
                    
                    # Get cost
                    hourly_cost = self.get_instance_hourly_cost(instance_type, is_spot)
                    
                    # Calculate efficiency score (0-100)
                    # High utilization + low cost = high efficiency
                    if hourly_cost > 0:
                        efficiency_score = (cpu_util / hourly_cost) * 10  # Normalize to 0-100
                        efficiency_score = min(100, efficiency_score)  # Cap at 100
                    else:
                        efficiency_score = 100
                        
                    instance_count += 1
                    total_efficiency_score += efficiency_score
                    
                    instance_data = {
                        'instance_id': instance_id,
                        'type': instance_type,
                        'cpu_utilization': cpu_util,
                        'hourly_cost': hourly_cost,
                        'efficiency_score': efficiency_score
                    }
                    
                    if efficiency_score < 30:
                        inefficient.append(instance_data)
                    elif efficiency_score > 70:
                        efficient.append(instance_data)
                        
            average_efficiency = total_efficiency_score / instance_count if instance_count > 0 else 0
            
            return {
                'average_efficiency': average_efficiency,
                'efficient_instances': len(efficient),
                'inefficient_instances': len(inefficient),
                'total_instances': instance_count,
                'top_5_efficient': sorted(efficient, key=lambda x: x['efficiency_score'], reverse=True)[:5],
                'top_5_inefficient': sorted(inefficient, key=lambda x: x['efficiency_score'])[:5]
            }
        except Exception as e:
            logger.error(f"Failed to track instance efficiency: {e}")
            return {}
            
    def track_savings_achieved(self) -> Dict:
        """
        Track total savings from optimization efforts
        """
        try:
            # Calculate baseline (if all instances were m5.2xlarge on-demand)
            instances = self.ec2.describe_instances(
                Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
            )
            
            instance_count = sum(len(r['Instances']) for r in instances['Reservations'])
            baseline_hourly = instance_count * 0.384  # m5.2xlarge cost
            
            # Get actual current cost
            actual_hourly = 0
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    instance_type = instance['InstanceType']
                    is_spot = instance.get('InstanceLifecycle') == 'spot'
                    actual_hourly += self.get_instance_hourly_cost(instance_type, is_spot)
                    
            # Calculate savings
            hourly_savings = baseline_hourly - actual_hourly
            daily_savings = hourly_savings * 24
            monthly_savings = daily_savings * 30
            annual_savings = daily_savings * 365
            
            # Get historical comparison (30 days ago)
            month_ago = datetime.utcnow().date() - timedelta(days=30)
            historical_daily = self.get_cost_for_period(month_ago, month_ago + timedelta(days=1))
            current_daily = self.get_cost_for_period(datetime.utcnow().date(), datetime.utcnow().date() + timedelta(days=1))
            historical_savings = historical_daily - current_daily if historical_daily > current_daily else 0
            
            return {
                'baseline_hourly_cost': baseline_hourly,
                'actual_hourly_cost': actual_hourly,
                'hourly_savings': hourly_savings,
                'daily_savings': daily_savings,
                'monthly_savings': monthly_savings,
                'annual_savings': annual_savings,
                'savings_percentage': (hourly_savings / baseline_hourly * 100) if baseline_hourly > 0 else 0,
                'vs_30_days_ago': {
                    'then': historical_daily,
                    'now': current_daily,
                    'savings': historical_savings,
                    'percentage': (historical_savings / historical_daily * 100) if historical_daily > 0 else 0
                }
            }
        except Exception as e:
            logger.error(f"Failed to track savings achieved: {e}")
            return {}
            
    def get_cost_for_period(self, start_date, end_date) -> float:
        """
        Get total cost for a period
        """
        try:
            response = self.ce.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.isoformat() if hasattr(start_date, 'isoformat') else str(start_date),
                    'End': end_date.isoformat() if hasattr(end_date, 'isoformat') else str(end_date)
                },
                Granularity='DAILY',
                Metrics=['UnblendedCost']
            )
            
            total = sum(float(day['Total']['UnblendedCost']['Amount']) for day in response['ResultsByTime'])
            return total
        except Exception as e:
            logger.error(f"Failed to get cost for period: {e}")
            return 0.0
            
    def get_instance_hourly_cost(self, instance_type: str, is_spot: bool) -> float:
        """
        Get hourly cost for instance type
        """
        on_demand_costs = {
            'm5.2xlarge': 0.384,
            'm5.xlarge': 0.192,
            'm5.large': 0.096,
            't3.xlarge': 0.1664,
            't3.large': 0.0832,
            't3.medium': 0.0416,
            't3a.large': 0.0752,
            't3a.medium': 0.0376,
            't2.large': 0.0928,
            't2.medium': 0.0464
        }
        
        cost = on_demand_costs.get(instance_type, 0.10)
        if is_spot:
            cost *= 0.3  # Assume 70% savings for spot
        return cost
        
    def get_instance_cpu_utilization(self, instance_id: str) -> float:
        """
        Get average CPU utilization for last hour
        """
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=1)
            
            response = self.cloudwatch.get_metric_statistics(
                Namespace='AWS/EC2',
                MetricName='CPUUtilization',
                Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,
                Statistics=['Average']
            )
            
            if response['Datapoints']:
                return sum(dp['Average'] for dp in response['Datapoints']) / len(response['Datapoints'])
            return 0.0
        except:
            return 0.0
            
    def get_alert_level(self, utilization: float) -> str:
        """
        Get alert level based on utilization
        """
        if utilization >= 90:
            return 'CRITICAL'
        elif utilization >= 80:
            return 'HIGH'
        elif utilization >= 70:
            return 'MEDIUM'
        elif utilization >= 50:
            return 'LOW'
        return 'NORMAL'
        
    def generate_daily_summary(self, metrics: Dict) -> Dict:
        """
        Generate daily summary
        """
        return {
            'total_spend_today': metrics.get('total_aws_spend', {}).get('today', 0),
            'vs_target': metrics.get('total_aws_spend', {}).get('vs_target', {}).get('daily', 0),
            'running_instances': metrics.get('cost_per_instance_hour', {}).get('total_instances', 0),
            'spot_savings': metrics.get('spot_savings', {}).get('daily_savings', 0),
            'idle_waste': metrics.get('idle_waste', {}).get('daily_waste', 0),
            'efficiency_score': metrics.get('instance_efficiency', {}).get('average_efficiency', 0)
        }
        
    def analyze_weekly_trend(self) -> Dict:
        """
        Analyze weekly spending trend
        """
        try:
            today = datetime.utcnow().date()
            week_costs = []
            
            for i in range(7):
                date = today - timedelta(days=i)
                cost = self.get_cost_for_period(date, date + timedelta(days=1))
                week_costs.append({'date': date.isoformat(), 'cost': cost})
                
            # Calculate trend
            if len(week_costs) >= 2:
                trend = 'increasing' if week_costs[0]['cost'] > week_costs[-1]['cost'] else 'decreasing'
            else:
                trend = 'stable'
                
            return {
                'daily_costs': week_costs,
                'average': sum(d['cost'] for d in week_costs) / len(week_costs) if week_costs else 0,
                'trend': trend
            }
        except Exception as e:
            logger.error(f"Failed to analyze weekly trend: {e}")
            return {}
            
    def project_month_end(self) -> Dict:
        """
        Project month end costs
        """
        projection = self.project_monthly_cost()
        return {
            'projected_total': projection.get('projected_total', 0),
            'vs_budget': projection.get('vs_budget', 0),
            'on_track': projection.get('on_track', False),
            'action_needed': projection.get('projected_total', 0) > self.MONTHLY_TARGET
        }
        
    def check_alerts(self, metrics: Dict) -> List[Dict]:
        """
        Check for alert conditions
        """
        alerts = []
        
        # Budget alerts
        budget = metrics.get('budget_utilization', {})
        if budget.get('daily', {}).get('utilization', 0) > 100:
            alerts.append({
                'level': 'CRITICAL',
                'type': 'BUDGET_BREACH',
                'message': f"Daily budget exceeded: ${budget['daily']['spent']:.2f} > ${self.DAILY_TARGET}"
            })
            
        # Idle resource alerts
        idle = metrics.get('idle_waste', {})
        if idle.get('daily_waste', 0) > 50:
            alerts.append({
                'level': 'HIGH',
                'type': 'IDLE_RESOURCES',
                'message': f"High idle resource cost: ${idle['daily_waste']:.2f}/day"
            })
            
        # Efficiency alerts
        efficiency = metrics.get('instance_efficiency', {})
        if efficiency.get('average_efficiency', 100) < 30:
            alerts.append({
                'level': 'MEDIUM',
                'type': 'LOW_EFFICIENCY',
                'message': f"Low instance efficiency: {efficiency['average_efficiency']:.1f}%"
            })
            
        return alerts
        
    def generate_recommendations(self, metrics: Dict) -> List[Dict]:
        """
        Generate cost optimization recommendations
        """
        recommendations = []
        
        # Spot instance recommendations
        spot = metrics.get('spot_savings', {})
        if spot.get('spot_percentage', 0) < 100:
            on_demand = spot.get('on_demand_instances', 0)
            potential_savings = on_demand * 0.0832 * 0.7 * 24 * 30  # Assume t3.large
            recommendations.append({
                'action': 'CONVERT_TO_SPOT',
                'priority': 'HIGH',
                'description': f"Convert {on_demand} on-demand instances to spot",
                'potential_savings': potential_savings
            })
            
        # Idle resource recommendations
        idle = metrics.get('idle_waste', {})
        if idle.get('idle_resources_count', 0) > 0:
            recommendations.append({
                'action': 'TERMINATE_IDLE',
                'priority': 'HIGH',
                'description': f"Terminate {idle['idle_resources_count']} idle resources",
                'potential_savings': idle.get('monthly_waste', 0)
            })
            
        # Efficiency recommendations
        efficiency = metrics.get('instance_efficiency', {})
        if efficiency.get('inefficient_instances', 0) > 0:
            recommendations.append({
                'action': 'RIGHTSIZE_INSTANCES',
                'priority': 'MEDIUM',
                'description': f"Rightsize {efficiency['inefficient_instances']} inefficient instances",
                'potential_savings': efficiency['inefficient_instances'] * 20  # Estimate $20/month per instance
            })
            
        return sorted(recommendations, key=lambda x: x.get('potential_savings', 0), reverse=True)
        
    def publish_metrics(self, metrics: Dict):
        """
        Publish metrics to CloudWatch
        """
        try:
            metric_data = []
            
            # Total spend
            if 'total_aws_spend' in metrics:
                metric_data.append({
                    'MetricName': 'TotalDailySpend',
                    'Value': metrics['total_aws_spend'].get('today', 0),
                    'Unit': 'None'
                })
                
            # Spot savings
            if 'spot_savings' in metrics:
                metric_data.append({
                    'MetricName': 'SpotSavingsPercentage',
                    'Value': metrics['spot_savings'].get('savings_percentage', 0),
                    'Unit': 'Percent'
                })
                
            # Budget utilization
            if 'budget_utilization' in metrics:
                metric_data.append({
                    'MetricName': 'MonthlyBudgetUtilization',
                    'Value': metrics['budget_utilization'].get('monthly', {}).get('utilization', 0),
                    'Unit': 'Percent'
                })
                
            if metric_data:
                self.cloudwatch.put_metric_data(
                    Namespace='CostControl/Metrics',
                    MetricData=metric_data
                )
                
        except Exception as e:
            logger.error(f"Failed to publish metrics: {e}")
            
    def send_daily_report(self, report: Dict):
        """
        Send daily report via email/SNS
        """
        try:
            summary = report.get('daily_summary', {})
            
            message = f"""
            DAILY COST REPORT - {report['report_date']}
            
            Today's Spend: ${summary.get('total_spend_today', 0):.2f}
            vs Target: ${summary.get('vs_target', 0):.2f}
            
            Running Instances: {summary.get('running_instances', 0)}
            Spot Savings: ${summary.get('spot_savings', 0):.2f}
            Idle Waste: ${summary.get('idle_waste', 0):.2f}
            
            Efficiency Score: {summary.get('efficiency_score', 0):.1f}%
            
            Alerts: {len(report.get('alerts', []))}
            Recommendations: {len(report.get('recommendations', []))}
            """
            
            # Log the report
            logger.info(message)
            
            # Save to file
            with open(f"daily_report_{datetime.utcnow().strftime('%Y%m%d')}.json", 'w') as f:
                json.dump(report, f, indent=2, default=str)
                
        except Exception as e:
            logger.error(f"Failed to send daily report: {e}")

def lambda_handler(event, context):
    """
    Lambda entry point for daily metrics tracking
    """
    tracker = MetricsTracker()
    report = tracker.track_all_metrics()
    
    return {
        'statusCode': 200,
        'body': json.dumps(report, default=str)
    }

if __name__ == "__main__":
    tracker = MetricsTracker()
    
    print("=" * 60)
    print("METRICS TRACKER - COMPREHENSIVE COST ANALYSIS")
    print("=" * 60)
    
    report = tracker.track_all_metrics()
    
    print("\nDAILY SUMMARY:")
    summary = report.get('daily_summary', {})
    print(f"Today's Spend: ${summary.get('total_spend_today', 0):.2f}")
    print(f"vs Target: ${summary.get('vs_target', 0):+.2f}")
    print(f"Running Instances: {summary.get('running_instances', 0)}")
    print(f"Spot Savings: ${summary.get('spot_savings', 0):.2f}")
    print(f"Idle Waste: ${summary.get('idle_waste', 0):.2f}")
    print(f"Efficiency Score: {summary.get('efficiency_score', 0):.1f}%")
    
    if report.get('alerts'):
        print(f"\nALERTS ({len(report['alerts'])}):")
        for alert in report['alerts']:
            print(f"  [{alert['level']}] {alert['message']}")
            
    if report.get('recommendations'):
        print(f"\nRECOMMENDATIONS:")
        for rec in report['recommendations'][:3]:
            print(f"  - {rec['description']}")
            print(f"    Potential Savings: ${rec.get('potential_savings', 0):.2f}/month")