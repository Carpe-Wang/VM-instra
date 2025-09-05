#!/usr/bin/env python3
"""
Right-Sizing Automation - CPU/MEMORY OPTIMIZATION
Analyze usage hourly
Auto-downgrade oversized instances
Report savings weekly
"""

import boto3
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from statistics import mean, median

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RightSizer:
    """
    AUTOMATIC RIGHT-SIZING
    Downgrade oversized instances
    Maximize resource efficiency
    """
    
    def __init__(self):
        self.ec2 = boto3.client('ec2')
        self.cloudwatch = boto3.client('cloudwatch')
        self.ce = boto3.client('ce')  # Cost Explorer
        
        # UTILIZATION THRESHOLDS
        self.CPU_UNDERUTILIZED = 20  # < 20% CPU = oversized
        self.CPU_OVERUTILIZED = 80   # > 80% CPU = undersized
        self.MEMORY_UNDERUTILIZED = 30  # < 30% memory = oversized
        self.MEMORY_OVERUTILIZED = 85   # > 85% memory = undersized
        
        # DOWNGRADE MAPPING
        self.DOWNGRADE_MAP = {
            'm5.2xlarge': 'm5.xlarge',  # 8 vCPU -> 4 vCPU
            'm5.xlarge': 'm5.large',     # 4 vCPU -> 2 vCPU
            'm5.large': 't3.large',      # 2 vCPU -> 2 vCPU (burstable)
            't3.xlarge': 't3.large',     # 4 vCPU -> 2 vCPU
            't3.large': 't3.medium',     # 2 vCPU -> 2 vCPU (less memory)
            't2.xlarge': 't2.large',     # 4 vCPU -> 2 vCPU
            't2.large': 't2.medium',     # 2 vCPU -> 2 vCPU
            'c5.xlarge': 'c5.large',     # 4 vCPU -> 2 vCPU
            'c5.large': 't3.large',      # 2 vCPU -> 2 vCPU (cheaper)
        }
        
        # UPGRADE MAPPING (for overutilized)
        self.UPGRADE_MAP = {
            't3.medium': 't3.large',     # 2 vCPU -> 2 vCPU (more memory)
            't3.large': 't3.xlarge',     # 2 vCPU -> 4 vCPU
            't2.medium': 't2.large',     # 2 vCPU -> 2 vCPU
            't2.large': 't2.xlarge',     # 2 vCPU -> 4 vCPU
            'm5.large': 'm5.xlarge',     # 2 vCPU -> 4 vCPU
            'm5.xlarge': 'm5.2xlarge',   # 4 vCPU -> 8 vCPU
        }
        
        # Instance specifications
        self.INSTANCE_SPECS = {
            'm5.2xlarge': {'vcpu': 8, 'memory': 32, 'cost': 0.384},
            'm5.xlarge': {'vcpu': 4, 'memory': 16, 'cost': 0.192},
            'm5.large': {'vcpu': 2, 'memory': 8, 'cost': 0.096},
            't3.xlarge': {'vcpu': 4, 'memory': 16, 'cost': 0.1664},
            't3.large': {'vcpu': 2, 'memory': 8, 'cost': 0.0832},
            't3.medium': {'vcpu': 2, 'memory': 4, 'cost': 0.0416},
            't2.xlarge': {'vcpu': 4, 'memory': 16, 'cost': 0.1856},
            't2.large': {'vcpu': 2, 'memory': 8, 'cost': 0.0928},
            't2.medium': {'vcpu': 2, 'memory': 4, 'cost': 0.0464},
        }
        
    def analyze_all_instances(self) -> Dict:
        """
        Analyze all instances for right-sizing opportunities
        Cost impact: SAVES 30-50% on oversized instances
        """
        results = {
            'analyzed': 0,
            'recommendations': [],
            'auto_resized': [],
            'potential_monthly_savings': 0.0,
            'actual_monthly_savings': 0.0
        }
        
        try:
            # Get all running instances
            response = self.ec2.describe_instances(
                Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
            )
            
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    instance_id = instance['InstanceId']
                    instance_type = instance['InstanceType']
                    
                    # Skip if not in our known types
                    if instance_type not in self.INSTANCE_SPECS:
                        continue
                        
                    results['analyzed'] += 1
                    
                    # Analyze utilization
                    utilization = self.analyze_instance_utilization(instance_id)
                    
                    if not utilization:
                        continue
                        
                    # Get recommendation
                    recommendation = self.get_sizing_recommendation(
                        instance_id, instance_type, utilization
                    )
                    
                    if recommendation:
                        results['recommendations'].append(recommendation)
                        results['potential_monthly_savings'] += recommendation['monthly_savings']
                        
                        # Auto-resize if confidence is high
                        if recommendation['confidence'] >= 0.9 and recommendation['action'] == 'DOWNGRADE':
                            success = self.resize_instance(
                                instance_id,
                                instance_type,
                                recommendation['new_type']
                            )
                            
                            if success:
                                results['auto_resized'].append({
                                    'instance_id': instance_id,
                                    'old_type': instance_type,
                                    'new_type': recommendation['new_type'],
                                    'monthly_savings': recommendation['monthly_savings']
                                })
                                results['actual_monthly_savings'] += recommendation['monthly_savings']
                                
        except Exception as e:
            logger.error(f"Failed to analyze instances: {e}")
            
        # Generate weekly report
        self.generate_weekly_report(results)
        
        return results
        
    def analyze_instance_utilization(self, instance_id: str) -> Optional[Dict]:
        """
        Analyze CPU and memory utilization for an instance
        """
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=7)  # 7 days of data
            
            # Get CPU utilization
            cpu_response = self.cloudwatch.get_metric_statistics(
                Namespace='AWS/EC2',
                MetricName='CPUUtilization',
                Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=3600,  # 1 hour intervals
                Statistics=['Average', 'Maximum']
            )
            
            if not cpu_response['Datapoints']:
                logger.warning(f"No CPU data for {instance_id}")
                return None
                
            # Calculate CPU statistics
            cpu_averages = [dp['Average'] for dp in cpu_response['Datapoints']]
            cpu_maximums = [dp['Maximum'] for dp in cpu_response['Datapoints']]
            
            cpu_stats = {
                'mean': mean(cpu_averages),
                'median': median(cpu_averages),
                'p95': sorted(cpu_averages)[int(len(cpu_averages) * 0.95)] if len(cpu_averages) > 20 else max(cpu_averages),
                'max': max(cpu_maximums),
                'samples': len(cpu_averages)
            }
            
            # Get memory utilization (if CloudWatch agent installed)
            memory_stats = self.get_memory_utilization(instance_id, start_time, end_time)
            
            # Get network utilization
            network_stats = self.get_network_utilization(instance_id, start_time, end_time)
            
            return {
                'cpu': cpu_stats,
                'memory': memory_stats,
                'network': network_stats,
                'analysis_period_days': 7
            }
            
        except Exception as e:
            logger.error(f"Failed to analyze utilization for {instance_id}: {e}")
            return None
            
    def get_memory_utilization(self, instance_id: str, start_time: datetime, end_time: datetime) -> Dict:
        """
        Get memory utilization (requires CloudWatch agent)
        """
        try:
            response = self.cloudwatch.get_metric_statistics(
                Namespace='CWAgent',
                MetricName='mem_used_percent',
                Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=3600,
                Statistics=['Average', 'Maximum']
            )
            
            if response['Datapoints']:
                mem_averages = [dp['Average'] for dp in response['Datapoints']]
                mem_maximums = [dp['Maximum'] for dp in response['Datapoints']]
                
                return {
                    'mean': mean(mem_averages),
                    'median': median(mem_averages),
                    'max': max(mem_maximums),
                    'samples': len(mem_averages)
                }
        except:
            pass
            
        # Return estimated values if no data
        return {
            'mean': 50,  # Assume 50% if no data
            'median': 50,
            'max': 70,
            'samples': 0
        }
        
    def get_network_utilization(self, instance_id: str, start_time: datetime, end_time: datetime) -> Dict:
        """
        Get network utilization
        """
        try:
            # Network In
            in_response = self.cloudwatch.get_metric_statistics(
                Namespace='AWS/EC2',
                MetricName='NetworkIn',
                Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=3600,
                Statistics=['Average', 'Maximum']
            )
            
            # Network Out
            out_response = self.cloudwatch.get_metric_statistics(
                Namespace='AWS/EC2',
                MetricName='NetworkOut',
                Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=3600,
                Statistics=['Average', 'Maximum']
            )
            
            if in_response['Datapoints'] and out_response['Datapoints']:
                in_avg = mean([dp['Average'] for dp in in_response['Datapoints']])
                out_avg = mean([dp['Average'] for dp in out_response['Datapoints']])
                
                return {
                    'in_mbps': (in_avg * 8) / (1024 * 1024),  # Convert to Mbps
                    'out_mbps': (out_avg * 8) / (1024 * 1024),
                    'total_mbps': ((in_avg + out_avg) * 8) / (1024 * 1024)
                }
        except:
            pass
            
        return {'in_mbps': 0, 'out_mbps': 0, 'total_mbps': 0}
        
    def get_sizing_recommendation(self, instance_id: str, current_type: str, utilization: Dict) -> Optional[Dict]:
        """
        Generate sizing recommendation based on utilization
        """
        cpu_avg = utilization['cpu']['mean']
        cpu_max = utilization['cpu']['max']
        mem_avg = utilization['memory']['mean']
        mem_max = utilization['memory']['max']
        
        current_spec = self.INSTANCE_SPECS.get(current_type)
        if not current_spec:
            return None
            
        recommendation = None
        confidence = 0.0
        reason = []
        
        # Check for UNDERUTILIZATION
        if cpu_avg < self.CPU_UNDERUTILIZED and cpu_max < 50:
            if current_type in self.DOWNGRADE_MAP:
                new_type = self.DOWNGRADE_MAP[current_type]
                new_spec = self.INSTANCE_SPECS.get(new_type)
                
                if new_spec:
                    # Calculate if new type can handle the load
                    cpu_headroom = (new_spec['vcpu'] / current_spec['vcpu']) * 100
                    
                    if cpu_max < cpu_headroom * 0.8:  # 80% of new capacity
                        recommendation = {
                            'action': 'DOWNGRADE',
                            'instance_id': instance_id,
                            'current_type': current_type,
                            'new_type': new_type,
                            'reason': f"CPU underutilized: avg={cpu_avg:.1f}%, max={cpu_max:.1f}%",
                            'current_cost': current_spec['cost'],
                            'new_cost': new_spec['cost'],
                            'hourly_savings': current_spec['cost'] - new_spec['cost'],
                            'monthly_savings': (current_spec['cost'] - new_spec['cost']) * 24 * 30,
                            'confidence': 0.95 if cpu_max < 30 else 0.85
                        }
                        
        # Check for OVERUTILIZATION
        elif cpu_avg > self.CPU_OVERUTILIZED or cpu_max > 95:
            if current_type in self.UPGRADE_MAP:
                new_type = self.UPGRADE_MAP[current_type]
                new_spec = self.INSTANCE_SPECS.get(new_type)
                
                if new_spec:
                    recommendation = {
                        'action': 'UPGRADE',
                        'instance_id': instance_id,
                        'current_type': current_type,
                        'new_type': new_type,
                        'reason': f"CPU overutilized: avg={cpu_avg:.1f}%, max={cpu_max:.1f}%",
                        'current_cost': current_spec['cost'],
                        'new_cost': new_spec['cost'],
                        'hourly_increase': new_spec['cost'] - current_spec['cost'],
                        'monthly_increase': (new_spec['cost'] - current_spec['cost']) * 24 * 30,
                        'confidence': 0.90
                    }
                    
        # Check memory if we have data
        if utilization['memory']['samples'] > 0:
            if mem_avg < self.MEMORY_UNDERUTILIZED and not recommendation:
                # Suggest smaller memory instance
                if current_type == 't3.large':
                    recommendation = {
                        'action': 'DOWNGRADE',
                        'instance_id': instance_id,
                        'current_type': current_type,
                        'new_type': 't3.medium',
                        'reason': f"Memory underutilized: avg={mem_avg:.1f}%",
                        'current_cost': current_spec['cost'],
                        'new_cost': self.INSTANCE_SPECS['t3.medium']['cost'],
                        'hourly_savings': current_spec['cost'] - self.INSTANCE_SPECS['t3.medium']['cost'],
                        'monthly_savings': (current_spec['cost'] - self.INSTANCE_SPECS['t3.medium']['cost']) * 24 * 30,
                        'confidence': 0.80
                    }
                    
        return recommendation
        
    def resize_instance(self, instance_id: str, old_type: str, new_type: str) -> bool:
        """
        Resize an instance to new type
        """
        try:
            logger.info(f"RESIZING: {instance_id} from {old_type} to {new_type}")
            
            # Stop the instance
            self.ec2.stop_instances(InstanceIds=[instance_id])
            
            # Wait for stop
            waiter = self.ec2.get_waiter('instance_stopped')
            waiter.wait(
                InstanceIds=[instance_id],
                WaiterConfig={'Delay': 5, 'MaxAttempts': 60}
            )
            
            # Modify instance type
            self.ec2.modify_instance_attribute(
                InstanceId=instance_id,
                InstanceType={'Value': new_type}
            )
            
            # Tag the resize
            self.ec2.create_tags(
                Resources=[instance_id],
                Tags=[
                    {'Key': 'LastResize', 'Value': datetime.utcnow().isoformat()},
                    {'Key': 'ResizeFrom', 'Value': old_type},
                    {'Key': 'ResizeTo', 'Value': new_type},
                    {'Key': 'ResizeReason', 'Value': 'auto-rightsizing'}
                ]
            )
            
            # Start the instance
            self.ec2.start_instances(InstanceIds=[instance_id])
            
            logger.info(f"RESIZED SUCCESSFULLY: {instance_id} -> {new_type}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to resize {instance_id}: {e}")
            return False
            
    def generate_weekly_report(self, results: Dict):
        """
        Generate weekly rightsizing report
        """
        report = {
            'report_date': datetime.utcnow().isoformat(),
            'instances_analyzed': results['analyzed'],
            'recommendations_count': len(results['recommendations']),
            'auto_resized_count': len(results['auto_resized']),
            'potential_monthly_savings': results['potential_monthly_savings'],
            'actual_monthly_savings': results['actual_monthly_savings'],
            'top_recommendations': []
        }
        
        # Sort recommendations by savings
        if results['recommendations']:
            sorted_recs = sorted(
                results['recommendations'],
                key=lambda x: x.get('monthly_savings', 0),
                reverse=True
            )
            
            report['top_recommendations'] = sorted_recs[:10]
            
        # Log report
        logger.info("=" * 60)
        logger.info("WEEKLY RIGHTSIZING REPORT")
        logger.info("=" * 60)
        logger.info(f"Instances analyzed: {report['instances_analyzed']}")
        logger.info(f"Recommendations: {report['recommendations_count']}")
        logger.info(f"Auto-resized: {report['auto_resized_count']}")
        logger.info(f"Potential savings: ${report['potential_monthly_savings']:.2f}/month")
        logger.info(f"Actual savings: ${report['actual_monthly_savings']:.2f}/month")
        
        if report['top_recommendations']:
            logger.info("\nTOP RECOMMENDATIONS:")
            for rec in report['top_recommendations'][:5]:
                logger.info(f"  - {rec['instance_id']}: {rec['current_type']} -> {rec['new_type']} (${rec['monthly_savings']:.2f}/month)")
                
        # Save report to file
        with open(f"rightsizing_report_{datetime.utcnow().strftime('%Y%m%d')}.json", 'w') as f:
            json.dump(report, f, indent=2, default=str)
            
        return report

def lambda_handler(event, context):
    """
    Lambda entry point for hourly analysis
    """
    rightsizer = RightSizer()
    results = rightsizer.analyze_all_instances()
    
    return {
        'statusCode': 200,
        'body': json.dumps(results, default=str)
    }

if __name__ == "__main__":
    rightsizer = RightSizer()
    
    print("=" * 60)
    print("RIGHT-SIZING ANALYSIS - RESOURCE OPTIMIZATION")
    print("=" * 60)
    
    print("\nANALYZING ALL INSTANCES...")
    results = rightsizer.analyze_all_instances()
    
    print(f"\nANALYSIS COMPLETE:")
    print(f"Instances analyzed: {results['analyzed']}")
    print(f"Recommendations: {len(results['recommendations'])}")
    print(f"Auto-resized: {len(results['auto_resized'])}")
    print(f"Potential monthly savings: ${results['potential_monthly_savings']:.2f}")
    print(f"Actual monthly savings: ${results['actual_monthly_savings']:.2f}")
    
    if results['recommendations']:
        print("\nTOP RECOMMENDATIONS:")
        for rec in results['recommendations'][:5]:
            print(f"\n  Instance: {rec['instance_id']}")
            print(f"  Action: {rec['action']}")
            print(f"  Current: {rec['current_type']} (${rec['current_cost']:.4f}/hr)")
            print(f"  Recommended: {rec['new_type']} (${rec.get('new_cost', 0):.4f}/hr)")
            print(f"  Reason: {rec['reason']}")
            print(f"  Savings: ${rec.get('monthly_savings', 0):.2f}/month")
            print(f"  Confidence: {rec['confidence']*100:.0f}%")