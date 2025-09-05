#!/usr/bin/env python3
"""
Cost Dashboard - REAL-TIME COST TRACKING
Track every dollar spent
Detect cost anomalies > 20% increase
Daily/weekly/monthly reports
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

class CostDashboard:
    """
    REAL-TIME COST MONITORING
    Track, analyze, alert on costs
    Zero tolerance for waste
    """
    
    def __init__(self):
        self.ce = boto3.client('ce')  # Cost Explorer
        self.ec2 = boto3.client('ec2')
        self.cloudwatch = boto3.client('cloudwatch')
        self.sns = boto3.client('sns')
        
        # ANOMALY THRESHOLDS
        self.ANOMALY_THRESHOLD = 0.20  # 20% increase triggers alert
        self.DAILY_BUDGET = 500  # $500/day maximum
        self.HOURLY_BUDGET = 20.83  # $500/24
        
        # Instance costs (per hour)
        self.INSTANCE_COSTS = {
            'm5.2xlarge': 0.384,
            'm5.xlarge': 0.192,
            'm5.large': 0.096,
            't3.large': 0.0832,
            't3.medium': 0.0416,
            't3a.large': 0.0752,
            't3a.medium': 0.0376,
            't2.large': 0.0928,
            't2.medium': 0.0464
        }
        
    def generate_cost_report(self) -> Dict:
        """
        Generate comprehensive cost report
        Real-time + historical analysis
        """
        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'real_time': self.get_real_time_costs(),
            'daily': self.get_daily_costs(),
            'weekly': self.get_weekly_costs(),
            'monthly': self.get_monthly_costs(),
            'by_service': self.get_costs_by_service(),
            'by_instance': self.get_costs_by_instance(),
            'anomalies': self.detect_anomalies(),
            'forecast': self.forecast_costs(),
            'recommendations': self.get_cost_recommendations()
        }
        
        # Check for budget violations
        if report['real_time']['current_daily_spend'] > self.DAILY_BUDGET:
            logger.critical(f"BUDGET VIOLATION: ${report['real_time']['current_daily_spend']:.2f} > ${self.DAILY_BUDGET}")
            self.trigger_emergency_shutdown()
            
        return report
        
    def get_real_time_costs(self) -> Dict:
        """
        Get current running costs
        """
        try:
            # Get running instances
            response = self.ec2.describe_instances(
                Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
            )
            
            total_hourly = 0.0
            instance_costs = []
            
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    instance_type = instance['InstanceType']
                    hourly_cost = self.INSTANCE_COSTS.get(instance_type, 0.10)
                    
                    # Check if spot
                    is_spot = instance.get('InstanceLifecycle') == 'spot'
                    if is_spot:
                        hourly_cost *= 0.3  # Assume 70% savings
                        
                    total_hourly += hourly_cost
                    
                    # Calculate runtime
                    launch_time = instance['LaunchTime']
                    runtime_hours = (datetime.utcnow() - launch_time.replace(tzinfo=None)).total_seconds() / 3600
                    
                    instance_costs.append({
                        'instance_id': instance['InstanceId'],
                        'type': instance_type,
                        'hourly_cost': hourly_cost,
                        'runtime_hours': runtime_hours,
                        'total_cost': hourly_cost * runtime_hours,
                        'is_spot': is_spot
                    })
                    
            # Sort by cost
            instance_costs.sort(key=lambda x: x['total_cost'], reverse=True)
            
            # Get today's actual spend from Cost Explorer
            today = datetime.utcnow().date()
            ce_response = self.ce.get_cost_and_usage(
                TimePeriod={
                    'Start': today.isoformat(),
                    'End': (today + timedelta(days=1)).isoformat()
                },
                Granularity='DAILY',
                Metrics=['UnblendedCost']
            )
            
            current_daily_spend = float(ce_response['ResultsByTime'][0]['Total']['UnblendedCost']['Amount'])
            
            return {
                'current_hourly_rate': total_hourly,
                'current_daily_rate': total_hourly * 24,
                'current_monthly_rate': total_hourly * 24 * 30,
                'current_daily_spend': current_daily_spend,
                'budget_utilization': (current_daily_spend / self.DAILY_BUDGET) * 100,
                'running_instances': len(instance_costs),
                'top_5_expensive': instance_costs[:5],
                'spot_vs_ondemand': {
                    'spot_count': sum(1 for i in instance_costs if i['is_spot']),
                    'ondemand_count': sum(1 for i in instance_costs if not i['is_spot']),
                    'spot_cost': sum(i['hourly_cost'] for i in instance_costs if i['is_spot']),
                    'ondemand_cost': sum(i['hourly_cost'] for i in instance_costs if not i['is_spot'])
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get real-time costs: {e}")
            return {}
            
    def get_daily_costs(self) -> Dict:
        """
        Get last 7 days of costs
        """
        try:
            end_date = datetime.utcnow().date()
            start_date = end_date - timedelta(days=7)
            
            response = self.ce.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.isoformat(),
                    'End': end_date.isoformat()
                },
                Granularity='DAILY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
            )
            
            daily_costs = []
            for day in response['ResultsByTime']:
                date = day['TimePeriod']['Start']
                total = float(day['Total']['UnblendedCost']['Amount'])
                
                services = {}
                for group in day.get('Groups', []):
                    service = group['Keys'][0]
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])
                    if cost > 0.01:  # Filter out tiny costs
                        services[service] = cost
                        
                daily_costs.append({
                    'date': date,
                    'total': total,
                    'services': services,
                    'over_budget': total > self.DAILY_BUDGET
                })
                
            # Calculate averages
            avg_daily = sum(d['total'] for d in daily_costs) / len(daily_costs) if daily_costs else 0
            
            return {
                'daily_costs': daily_costs,
                'average_daily': avg_daily,
                'total_7_days': sum(d['total'] for d in daily_costs),
                'days_over_budget': sum(1 for d in daily_costs if d['over_budget'])
            }
            
        except Exception as e:
            logger.error(f"Failed to get daily costs: {e}")
            return {}
            
    def get_weekly_costs(self) -> Dict:
        """
        Get last 4 weeks of costs
        """
        try:
            end_date = datetime.utcnow().date()
            start_date = end_date - timedelta(weeks=4)
            
            response = self.ce.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.isoformat(),
                    'End': end_date.isoformat()
                },
                Granularity='WEEKLY',
                Metrics=['UnblendedCost']
            )
            
            weekly_costs = []
            for week in response['ResultsByTime']:
                start = week['TimePeriod']['Start']
                total = float(week['Total']['UnblendedCost']['Amount'])
                
                weekly_costs.append({
                    'week_start': start,
                    'total': total,
                    'daily_average': total / 7
                })
                
            return {
                'weekly_costs': weekly_costs,
                'average_weekly': sum(w['total'] for w in weekly_costs) / len(weekly_costs) if weekly_costs else 0
            }
            
        except Exception as e:
            logger.error(f"Failed to get weekly costs: {e}")
            return {}
            
    def get_monthly_costs(self) -> Dict:
        """
        Get last 3 months of costs
        """
        try:
            end_date = datetime.utcnow().date().replace(day=1)
            start_date = (end_date - timedelta(days=90)).replace(day=1)
            
            response = self.ce.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.isoformat(),
                    'End': end_date.isoformat()
                },
                Granularity='MONTHLY',
                Metrics=['UnblendedCost']
            )
            
            monthly_costs = []
            for month in response['ResultsByTime']:
                start = month['TimePeriod']['Start']
                total = float(month['Total']['UnblendedCost']['Amount'])
                
                monthly_costs.append({
                    'month': start,
                    'total': total,
                    'daily_average': total / 30
                })
                
            # Calculate trend
            if len(monthly_costs) >= 2:
                trend = ((monthly_costs[-1]['total'] - monthly_costs[-2]['total']) / monthly_costs[-2]['total']) * 100
            else:
                trend = 0
                
            return {
                'monthly_costs': monthly_costs,
                'average_monthly': sum(m['total'] for m in monthly_costs) / len(monthly_costs) if monthly_costs else 0,
                'trend_percentage': trend
            }
            
        except Exception as e:
            logger.error(f"Failed to get monthly costs: {e}")
            return {}
            
    def get_costs_by_service(self) -> List[Dict]:
        """
        Break down costs by AWS service
        """
        try:
            end_date = datetime.utcnow().date()
            start_date = end_date - timedelta(days=30)
            
            response = self.ce.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.isoformat(),
                    'End': end_date.isoformat()
                },
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
            )
            
            service_costs = []
            if response['ResultsByTime']:
                for group in response['ResultsByTime'][0].get('Groups', []):
                    service = group['Keys'][0]
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])
                    
                    if cost > 0.01:
                        service_costs.append({
                            'service': service,
                            'monthly_cost': cost,
                            'daily_average': cost / 30,
                            'percentage': 0  # Will calculate after
                        })
                        
            # Calculate percentages
            total = sum(s['monthly_cost'] for s in service_costs)
            for s in service_costs:
                s['percentage'] = (s['monthly_cost'] / total * 100) if total > 0 else 0
                
            # Sort by cost
            service_costs.sort(key=lambda x: x['monthly_cost'], reverse=True)
            
            return service_costs
            
        except Exception as e:
            logger.error(f"Failed to get costs by service: {e}")
            return []
            
    def get_costs_by_instance(self) -> List[Dict]:
        """
        Get costs per instance with recommendations
        """
        instance_costs = []
        
        try:
            response = self.ec2.describe_instances()
            
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    if instance['State']['Name'] != 'terminated':
                        instance_id = instance['InstanceId']
                        instance_type = instance['InstanceType']
                        state = instance['State']['Name']
                        
                        # Get tags
                        tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                        
                        # Calculate costs
                        hourly_cost = self.INSTANCE_COSTS.get(instance_type, 0.10)
                        is_spot = instance.get('InstanceLifecycle') == 'spot'
                        if is_spot:
                            hourly_cost *= 0.3
                            
                        # Calculate runtime
                        if state == 'running':
                            launch_time = instance['LaunchTime']
                            runtime_hours = (datetime.utcnow() - launch_time.replace(tzinfo=None)).total_seconds() / 3600
                        else:
                            runtime_hours = 0
                            
                        total_cost = hourly_cost * runtime_hours
                        
                        instance_costs.append({
                            'instance_id': instance_id,
                            'type': instance_type,
                            'state': state,
                            'is_spot': is_spot,
                            'hourly_cost': hourly_cost,
                            'runtime_hours': runtime_hours,
                            'total_cost': total_cost,
                            'daily_cost': hourly_cost * 24 if state == 'running' else 0,
                            'monthly_cost': hourly_cost * 24 * 30 if state == 'running' else 0,
                            'environment': tags.get('Environment', 'unknown'),
                            'owner': tags.get('Owner', 'unknown')
                        })
                        
            # Sort by total cost
            instance_costs.sort(key=lambda x: x['total_cost'], reverse=True)
            
        except Exception as e:
            logger.error(f"Failed to get instance costs: {e}")
            
        return instance_costs
        
    def detect_anomalies(self) -> List[Dict]:
        """
        Detect cost anomalies (> 20% increase)
        """
        anomalies = []
        
        try:
            # Compare today vs yesterday
            today = datetime.utcnow().date()
            yesterday = today - timedelta(days=1)
            
            response = self.ce.get_cost_and_usage(
                TimePeriod={
                    'Start': yesterday.isoformat(),
                    'End': (today + timedelta(days=1)).isoformat()
                },
                Granularity='DAILY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
            )
            
            if len(response['ResultsByTime']) >= 2:
                yesterday_costs = {}
                today_costs = {}
                
                # Parse yesterday's costs
                for group in response['ResultsByTime'][0].get('Groups', []):
                    service = group['Keys'][0]
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])
                    yesterday_costs[service] = cost
                    
                # Parse today's costs
                for group in response['ResultsByTime'][1].get('Groups', []):
                    service = group['Keys'][0]
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])
                    today_costs[service] = cost
                    
                # Check for anomalies
                for service, today_cost in today_costs.items():
                    yesterday_cost = yesterday_costs.get(service, 0)
                    
                    if yesterday_cost > 0:
                        increase = ((today_cost - yesterday_cost) / yesterday_cost)
                        
                        if increase > self.ANOMALY_THRESHOLD:
                            anomalies.append({
                                'service': service,
                                'yesterday_cost': yesterday_cost,
                                'today_cost': today_cost,
                                'increase_percentage': increase * 100,
                                'additional_cost': today_cost - yesterday_cost,
                                'severity': 'CRITICAL' if increase > 0.5 else 'WARNING'
                            })
                            
                            logger.warning(f"ANOMALY DETECTED: {service} increased {increase*100:.1f}%")
                            
        except Exception as e:
            logger.error(f"Failed to detect anomalies: {e}")
            
        return anomalies
        
    def forecast_costs(self) -> Dict:
        """
        Forecast future costs based on trends
        """
        try:
            # Get last 30 days
            end_date = datetime.utcnow().date()
            start_date = end_date - timedelta(days=30)
            
            response = self.ce.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.isoformat(),
                    'End': end_date.isoformat()
                },
                Granularity='DAILY',
                Metrics=['UnblendedCost']
            )
            
            # Calculate average daily cost
            daily_costs = [float(day['Total']['UnblendedCost']['Amount']) for day in response['ResultsByTime']]
            avg_daily = sum(daily_costs) / len(daily_costs) if daily_costs else 0
            
            # Calculate trend (simple linear)
            if len(daily_costs) > 7:
                recent_avg = sum(daily_costs[-7:]) / 7
                older_avg = sum(daily_costs[-14:-7]) / 7
                trend_rate = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0
            else:
                trend_rate = 0
                
            # Forecast
            forecast_tomorrow = avg_daily * (1 + trend_rate)
            forecast_week = forecast_tomorrow * 7
            forecast_month = forecast_tomorrow * 30
            
            return {
                'current_daily_average': avg_daily,
                'trend_rate': trend_rate * 100,
                'forecast_tomorrow': forecast_tomorrow,
                'forecast_next_week': forecast_week,
                'forecast_next_month': forecast_month,
                'will_exceed_budget': forecast_tomorrow > self.DAILY_BUDGET
            }
            
        except Exception as e:
            logger.error(f"Failed to forecast costs: {e}")
            return {}
            
    def get_cost_recommendations(self) -> List[Dict]:
        """
        Generate cost-saving recommendations
        """
        recommendations = []
        
        try:
            # Check for expensive instance types
            response = self.ec2.describe_instances(
                Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
            )
            
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    instance_type = instance['InstanceType']
                    instance_id = instance['InstanceId']
                    is_spot = instance.get('InstanceLifecycle') == 'spot'
                    
                    # Recommend spot conversion
                    if not is_spot and instance_type in ['t3.large', 't3.medium']:
                        hourly_cost = self.INSTANCE_COSTS.get(instance_type, 0.10)
                        potential_savings = hourly_cost * 0.7  # 70% savings
                        
                        recommendations.append({
                            'type': 'CONVERT_TO_SPOT',
                            'resource': instance_id,
                            'current_cost': hourly_cost,
                            'potential_cost': hourly_cost * 0.3,
                            'monthly_savings': potential_savings * 24 * 30,
                            'priority': 'HIGH'
                        })
                        
                    # Recommend downsizing
                    if instance_type in ['m5.2xlarge', 'm5.xlarge']:
                        current_cost = self.INSTANCE_COSTS.get(instance_type, 0.384)
                        new_cost = self.INSTANCE_COSTS.get('t3.large', 0.0832)
                        
                        recommendations.append({
                            'type': 'DOWNSIZE_INSTANCE',
                            'resource': instance_id,
                            'current_type': instance_type,
                            'recommended_type': 't3.large',
                            'current_cost': current_cost,
                            'potential_cost': new_cost,
                            'monthly_savings': (current_cost - new_cost) * 24 * 30,
                            'priority': 'CRITICAL'
                        })
                        
            # Check for idle instances
            for instance in self.get_costs_by_instance():
                if instance['state'] == 'stopped' and instance['runtime_hours'] > 0:
                    recommendations.append({
                        'type': 'TERMINATE_STOPPED',
                        'resource': instance['instance_id'],
                        'reason': 'Instance stopped but not terminated',
                        'monthly_savings': 10,  # EBS costs
                        'priority': 'MEDIUM'
                    })
                    
        except Exception as e:
            logger.error(f"Failed to generate recommendations: {e}")
            
        # Sort by savings potential
        recommendations.sort(key=lambda x: x.get('monthly_savings', 0), reverse=True)
        
        return recommendations
        
    def trigger_emergency_shutdown(self):
        """
        Trigger emergency shutdown on budget breach
        """
        logger.critical("TRIGGERING EMERGENCY SHUTDOWN DUE TO BUDGET BREACH")
        
        # Import and execute emergency shutdown
        from emergency_shutdown import EmergencyShutdown
        shutdown = EmergencyShutdown()
        shutdown.kill_all_instances(reason="BUDGET_BREACH_FROM_DASHBOARD")
        
    def publish_metrics(self, report: Dict):
        """
        Publish cost metrics to CloudWatch
        """
        try:
            metrics = []
            
            # Current spend metric
            if 'real_time' in report:
                metrics.append({
                    'MetricName': 'CurrentDailySpend',
                    'Value': report['real_time'].get('current_daily_spend', 0),
                    'Unit': 'None'
                })
                
                metrics.append({
                    'MetricName': 'BudgetUtilization',
                    'Value': report['real_time'].get('budget_utilization', 0),
                    'Unit': 'Percent'
                })
                
            # Anomaly count
            if 'anomalies' in report:
                metrics.append({
                    'MetricName': 'CostAnomalies',
                    'Value': len(report['anomalies']),
                    'Unit': 'Count'
                })
                
            # Publish metrics
            if metrics:
                self.cloudwatch.put_metric_data(
                    Namespace='CostControl',
                    MetricData=metrics
                )
                
        except Exception as e:
            logger.error(f"Failed to publish metrics: {e}")

def lambda_handler(event, context):
    """
    Lambda entry point for scheduled reporting
    """
    dashboard = CostDashboard()
    report = dashboard.generate_cost_report()
    
    # Publish metrics
    dashboard.publish_metrics(report)
    
    # Send alerts for anomalies
    if report.get('anomalies'):
        # Send SNS notification
        pass
        
    return {
        'statusCode': 200,
        'body': json.dumps(report, default=str)
    }

if __name__ == "__main__":
    dashboard = CostDashboard()
    
    print("=" * 60)
    print("COST DASHBOARD - REAL-TIME MONITORING")
    print("=" * 60)
    
    report = dashboard.generate_cost_report()
    
    # Print summary
    if 'real_time' in report:
        rt = report['real_time']
        print(f"\nCURRENT STATUS:")
        print(f"  Hourly Rate: ${rt.get('current_hourly_rate', 0):.2f}")
        print(f"  Daily Rate: ${rt.get('current_daily_rate', 0):.2f}")
        print(f"  Today's Spend: ${rt.get('current_daily_spend', 0):.2f}")
        print(f"  Budget Utilization: {rt.get('budget_utilization', 0):.1f}%")
        print(f"  Running Instances: {rt.get('running_instances', 0)}")
        
    if 'anomalies' in report and report['anomalies']:
        print(f"\nANOMALIES DETECTED: {len(report['anomalies'])}")
        for anomaly in report['anomalies']:
            print(f"  - {anomaly['service']}: +{anomaly['increase_percentage']:.1f}% (${anomaly['additional_cost']:.2f})")
            
    if 'recommendations' in report and report['recommendations']:
        print(f"\nTOP RECOMMENDATIONS:")
        for rec in report['recommendations'][:5]:
            print(f"  - {rec['type']}: Save ${rec['monthly_savings']:.2f}/month")
            
    # Save report to file
    with open('cost_report.json', 'w') as f:
        json.dump(report, f, indent=2, default=str)