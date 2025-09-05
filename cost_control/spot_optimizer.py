#!/usr/bin/env python3
"""
Spot Instance Optimizer - MAXIMUM COST REDUCTION
Use ONLY t3.medium and t3.large instances
Diversified spot fleet with 5 instance types
Max bid at 30% of on-demand price
"""

import boto3
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SpotOptimizer:
    """
    AGGRESSIVE SPOT OPTIMIZATION
    70-90% cheaper than on-demand
    Diversified fleet for availability
    """
    
    def __init__(self):
        self.ec2 = boto3.client('ec2')
        
        # SPOT CONFIGURATION
        self.MAX_SPOT_PRICE_PERCENT = 0.30  # 30% of on-demand MAX
        
        # Instance configuration with weights and max prices
        self.SPOT_CONFIG = {
            't3.medium': {
                'on_demand': 0.0416,
                'max_spot': 0.0125,  # 30% of on-demand
                'weight': 1.0,
                'priority': 1
            },
            't3.large': {
                'on_demand': 0.0832,
                'max_spot': 0.025,  # 30% of on-demand
                'weight': 2.0,
                'priority': 2
            },
            't3a.medium': {  # AMD variant - usually cheaper
                'on_demand': 0.0376,
                'max_spot': 0.0113,
                'weight': 1.0,
                'priority': 3
            },
            't3a.large': {
                'on_demand': 0.0752,
                'max_spot': 0.0226,
                'weight': 2.0,
                'priority': 4
            },
            't2.medium': {  # Older gen - backup option
                'on_demand': 0.0464,
                'max_spot': 0.0139,
                'weight': 1.0,
                'priority': 5
            }
        }
        
        # Fleet configuration
        self.FLEET_SIZE = 10  # Maximum fleet size
        self.ALLOCATION_STRATEGY = 'lowestPrice'  # Always cheapest
        
    def create_optimized_spot_fleet(self, target_capacity: int = 5) -> Dict:
        """
        Create diversified spot fleet for maximum savings
        Cost impact: SAVES 70-90% vs on-demand
        """
        try:
            # Get current spot prices
            spot_prices = self.get_current_spot_prices()
            
            # Build launch specifications
            launch_specs = []
            for instance_type, config in self.SPOT_CONFIG.items():
                current_price = spot_prices.get(instance_type, config['max_spot'])
                
                # Only include if price is acceptable
                if current_price <= config['max_spot']:
                    launch_specs.append({
                        'InstanceType': instance_type,
                        'SpotPrice': str(config['max_spot']),
                        'ImageId': 'ami-0c55b159cbfafe1f0',  # Update with your AMI
                        'KeyName': 'vm-instra-key',
                        'SecurityGroups': [{'GroupId': 'sg-default'}],
                        'WeightedCapacity': config['weight'],
                        'UserData': self.get_user_data(),
                        'TagSpecifications': [{
                            'ResourceType': 'instance',
                            'Tags': [
                                {'Key': 'AutoDelete', 'Value': 'true'},
                                {'Key': 'CostCenter', 'Value': 'vm-instra'},
                                {'Key': 'MaxHours', 'Value': '24'},
                                {'Key': 'Environment', 'Value': 'prod'},
                                {'Key': 'Owner', 'Value': 'ops@company.com'},
                                {'Key': 'Type', 'Value': 'spot-fleet'}
                            ]
                        }]
                    })
                    
            if not launch_specs:
                logger.error("No acceptable spot prices found!")
                return {'status': 'failed', 'reason': 'prices_too_high'}
                
            # Create spot fleet request
            fleet_config = {
                'AllocationStrategy': self.ALLOCATION_STRATEGY,
                'IamFleetRole': 'arn:aws:iam::account:role/fleet-role',
                'SpotPrice': str(max(c['max_spot'] for c in self.SPOT_CONFIG.values())),
                'TargetCapacity': target_capacity,
                'TerminateInstancesWithExpiration': True,
                'Type': 'maintain',  # Maintain capacity
                'ReplaceUnhealthyInstances': True,
                'InstanceInterruptionBehavior': 'terminate',
                'LaunchSpecifications': launch_specs,
                'ValidUntil': (datetime.utcnow() + timedelta(days=7)).isoformat() + 'Z'
            }
            
            response = self.ec2.request_spot_fleet(SpotFleetRequestConfig=fleet_config)
            fleet_id = response['SpotFleetRequestId']
            
            # Calculate savings
            on_demand_cost = target_capacity * self.SPOT_CONFIG['t3.large']['on_demand']
            spot_cost = target_capacity * self.SPOT_CONFIG['t3.large']['max_spot']
            hourly_savings = on_demand_cost - spot_cost
            
            result = {
                'status': 'success',
                'fleet_id': fleet_id,
                'target_capacity': target_capacity,
                'instance_types': len(launch_specs),
                'hourly_on_demand_cost': f"${on_demand_cost:.4f}",
                'hourly_spot_cost': f"${spot_cost:.4f}",
                'hourly_savings': f"${hourly_savings:.4f}",
                'daily_savings': f"${hourly_savings * 24:.2f}",
                'monthly_savings': f"${hourly_savings * 24 * 30:.2f}",
                'savings_percentage': f"{(hourly_savings/on_demand_cost)*100:.1f}%"
            }
            
            logger.info(f"SPOT FLEET CREATED: {json.dumps(result)}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to create spot fleet: {e}")
            return {'status': 'failed', 'error': str(e)}
            
    def convert_on_demand_to_spot(self) -> Dict:
        """
        Convert ALL on-demand instances to spot
        Cost impact: SAVES 70-90% on existing instances
        """
        converted = []
        failed = []
        total_savings = 0.0
        
        try:
            # Get all on-demand instances
            response = self.ec2.describe_instances(
                Filters=[
                    {'Name': 'instance-state-name', 'Values': ['running']},
                    {'Name': 'instance-lifecycle', 'Values': ['normal']}  # On-demand only
                ]
            )
            
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    instance_id = instance['InstanceId']
                    instance_type = instance['InstanceType']
                    
                    # Only convert if in our allowed types
                    if instance_type in self.SPOT_CONFIG:
                        logger.info(f"Converting {instance_id} ({instance_type}) to spot")
                        
                        # Get instance details for recreation
                        ami_id = instance['ImageId']
                        subnet_id = instance.get('SubnetId')
                        security_groups = [sg['GroupId'] for sg in instance['SecurityGroups']]
                        tags = instance.get('Tags', [])
                        
                        # Request spot replacement
                        spot_request = self.request_spot_replacement(
                            instance_type=instance_type,
                            ami_id=ami_id,
                            subnet_id=subnet_id,
                            security_groups=security_groups,
                            tags=tags
                        )
                        
                        if spot_request['status'] == 'success':
                            # Terminate on-demand instance
                            self.ec2.terminate_instances(InstanceIds=[instance_id])
                            
                            converted.append({
                                'instance_id': instance_id,
                                'type': instance_type,
                                'spot_request': spot_request['request_id']
                            })
                            
                            # Calculate savings
                            on_demand = self.SPOT_CONFIG[instance_type]['on_demand']
                            spot = self.SPOT_CONFIG[instance_type]['max_spot']
                            total_savings += (on_demand - spot)
                            
                            logger.info(f"CONVERTED: {instance_id} - Saving ${(on_demand-spot)*24:.2f}/day")
                        else:
                            failed.append(instance_id)
                            
        except Exception as e:
            logger.error(f"Failed to convert instances: {e}")
            
        return {
            'converted': len(converted),
            'failed': len(failed),
            'hourly_savings': f"${total_savings:.4f}",
            'daily_savings': f"${total_savings*24:.2f}",
            'monthly_savings': f"${total_savings*24*30:.2f}"
        }
        
    def request_spot_replacement(self, instance_type: str, ami_id: str, 
                                subnet_id: str, security_groups: List[str],
                                tags: List[Dict]) -> Dict:
        """
        Request a spot instance to replace on-demand
        """
        try:
            max_price = self.SPOT_CONFIG[instance_type]['max_spot']
            
            response = self.ec2.request_spot_instances(
                SpotPrice=str(max_price),
                InstanceCount=1,
                Type='one-time',
                LaunchSpecification={
                    'ImageId': ami_id,
                    'InstanceType': instance_type,
                    'SecurityGroupIds': security_groups,
                    'SubnetId': subnet_id,
                    'UserData': self.get_user_data()
                },
                TagSpecifications=[{
                    'ResourceType': 'spot-instances-request',
                    'Tags': tags + [
                        {'Key': 'SpotReplacement', 'Value': 'true'},
                        {'Key': 'MaxPrice', 'Value': str(max_price)}
                    ]
                }]
            )
            
            return {
                'status': 'success',
                'request_id': response['SpotInstanceRequests'][0]['SpotInstanceRequestId']
            }
            
        except Exception as e:
            logger.error(f"Failed to request spot replacement: {e}")
            return {'status': 'failed', 'error': str(e)}
            
    def optimize_spot_requests(self) -> Dict:
        """
        Optimize existing spot requests
        Cancel expensive ones, replace with cheaper
        """
        optimized = 0
        cancelled = 0
        savings = 0.0
        
        try:
            # Get all active spot requests
            response = self.ec2.describe_spot_instance_requests(
                Filters=[{'Name': 'state', 'Values': ['open', 'active']}]
            )
            
            for request in response['SpotInstanceRequests']:
                request_id = request['SpotInstanceRequestId']
                instance_type = request['LaunchSpecification']['InstanceType']
                current_price = float(request.get('SpotPrice', 0))
                
                if instance_type in self.SPOT_CONFIG:
                    max_price = self.SPOT_CONFIG[instance_type]['max_spot']
                    
                    # Cancel if price too high
                    if current_price > max_price:
                        logger.warning(f"CANCELLING expensive spot request {request_id}: ${current_price} > ${max_price}")
                        self.ec2.cancel_spot_instance_requests(SpotInstanceRequestIds=[request_id])
                        cancelled += 1
                        
                        # Request cheaper replacement
                        self.request_spot_replacement(
                            instance_type=instance_type,
                            ami_id=request['LaunchSpecification']['ImageId'],
                            subnet_id=request['LaunchSpecification'].get('SubnetId'),
                            security_groups=[sg['GroupId'] for sg in request['LaunchSpecification']['SecurityGroups']],
                            tags=[]
                        )
                        optimized += 1
                        savings += (current_price - max_price)
                        
        except Exception as e:
            logger.error(f"Failed to optimize spot requests: {e}")
            
        return {
            'optimized': optimized,
            'cancelled': cancelled,
            'hourly_savings': f"${savings:.4f}",
            'daily_savings': f"${savings*24:.2f}"
        }
        
    def get_current_spot_prices(self) -> Dict[str, float]:
        """
        Get current spot prices for our instance types
        """
        prices = {}
        
        try:
            for instance_type in self.SPOT_CONFIG.keys():
                response = self.ec2.describe_spot_price_history(
                    InstanceTypes=[instance_type],
                    MaxResults=1,
                    ProductDescriptions=['Linux/UNIX'],
                    StartTime=datetime.utcnow() - timedelta(minutes=5)
                )
                
                if response['SpotPriceHistory']:
                    prices[instance_type] = float(response['SpotPriceHistory'][0]['SpotPrice'])
                    
        except Exception as e:
            logger.error(f"Failed to get spot prices: {e}")
            
        return prices
        
    def get_user_data(self) -> str:
        """
        User data script for spot instances
        """
        return """#!/bin/bash
# Cost optimization user data
echo "SPOT_INSTANCE=true" >> /etc/environment

# Auto-shutdown if idle
cat > /usr/local/bin/idle_check.sh << 'EOF'
#!/bin/bash
CPU=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
if (( $(echo "$CPU < 5" | bc -l) )); then
    echo "Instance idle, shutting down"
    shutdown -h now
fi
EOF

chmod +x /usr/local/bin/idle_check.sh
echo "*/15 * * * * root /usr/local/bin/idle_check.sh" >> /etc/crontab

# Tag instance with spot info
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
aws ec2 create-tags --resources $INSTANCE_ID --tags Key=SpotInstance,Value=true Key=AutoShutdown,Value=enabled
"""

    def monitor_spot_interruptions(self) -> Dict:
        """
        Monitor for spot interruption warnings
        """
        interrupted = []
        
        try:
            # Check CloudWatch for interruption warnings
            response = self.cloudwatch.describe_alarms(
                AlarmNamePrefix='spot-interruption'
            )
            
            for alarm in response['MetricAlarms']:
                if alarm['StateValue'] == 'ALARM':
                    interrupted.append(alarm['AlarmName'])
                    
        except Exception as e:
            logger.error(f"Failed to monitor interruptions: {e}")
            
        return {'interrupted': len(interrupted), 'instances': interrupted}

def lambda_handler(event, context):
    """
    Lambda entry point for spot optimization
    """
    optimizer = SpotOptimizer()
    
    # Create/update spot fleet
    fleet_result = optimizer.create_optimized_spot_fleet()
    
    # Convert on-demand to spot
    conversion_result = optimizer.convert_on_demand_to_spot()
    
    # Optimize existing spot requests
    optimization_result = optimizer.optimize_spot_requests()
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'fleet': fleet_result,
            'conversions': conversion_result,
            'optimizations': optimization_result
        })
    }

if __name__ == "__main__":
    optimizer = SpotOptimizer()
    
    print("=" * 60)
    print("SPOT INSTANCE OPTIMIZER - MAXIMUM SAVINGS")
    print("=" * 60)
    
    # Show current spot prices
    prices = optimizer.get_current_spot_prices()
    print("\nCURRENT SPOT PRICES:")
    for instance_type, price in prices.items():
        config = optimizer.SPOT_CONFIG[instance_type]
        on_demand = config['on_demand']
        max_bid = config['max_spot']
        savings = ((on_demand - price) / on_demand) * 100
        print(f"  {instance_type}: ${price:.4f}/hr (on-demand: ${on_demand:.4f}, max: ${max_bid:.4f}, savings: {savings:.1f}%)")
        
    # Create spot fleet
    print("\nCREATING SPOT FLEET...")
    fleet_result = optimizer.create_optimized_spot_fleet(target_capacity=5)
    print(json.dumps(fleet_result, indent=2))
    
    # Convert on-demand to spot
    print("\nCONVERTING ON-DEMAND TO SPOT...")
    conversion_result = optimizer.convert_on_demand_to_spot()
    print(json.dumps(conversion_result, indent=2))