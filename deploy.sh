#!/bin/bash

# Enterprise Windows Infrastructure Platform Deployment Script
# Automated deployment for production environments

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PLATFORM_NAME="Enterprise Windows Infrastructure Platform"
VERSION="1.0.0"
ENVIRONMENT=${ENVIRONMENT:-"production"}

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  $PLATFORM_NAME${NC}"
echo -e "${BLUE}  Version: $VERSION${NC}"
echo -e "${BLUE}  Environment: $ENVIRONMENT${NC}"
echo -e "${BLUE}========================================${NC}"

# Function to print status messages
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is required but not installed"
        exit 1
    fi
    
    python_version=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
    if [[ $(echo "$python_version >= 3.8" | bc -l) -eq 0 ]]; then
        print_error "Python 3.8+ is required (found $python_version)"
        exit 1
    fi
    print_status "Python $python_version ✓"
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI is required but not installed"
        print_status "Install with: pip install awscli"
        exit 1
    fi
    print_status "AWS CLI ✓"
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS credentials not configured"
        print_status "Run: aws configure"
        exit 1
    fi
    print_status "AWS credentials ✓"
    
    # Check pip
    if ! command -v pip &> /dev/null; then
        print_error "pip is required but not installed"
        exit 1
    fi
    print_status "pip ✓"
}

# Install dependencies
install_dependencies() {
    print_status "Installing Python dependencies..."
    
    if [[ -f "requirements.txt" ]]; then
        pip install -r requirements.txt
        print_status "Dependencies installed ✓"
    else
        print_error "requirements.txt not found"
        exit 1
    fi
}

# Validate configuration
validate_configuration() {
    print_status "Validating configuration..."
    
    if [[ -f "enterprise_config.yaml" ]]; then
        print_status "Enterprise configuration found ✓"
        
        # Check for required configuration values
        python3 -c "
import yaml
import sys

try:
    with open('enterprise_config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Validate required sections
    required_sections = ['infrastructure', 'vm_configuration', 'security']
    for section in required_sections:
        if section not in config:
            print(f'Missing required section: {section}')
            sys.exit(1)
    
    print('Configuration validation passed ✓')
except Exception as e:
    print(f'Configuration validation failed: {e}')
    sys.exit(1)
" || exit 1
    else
        print_warning "No enterprise_config.yaml found, using defaults"
    fi
}

# Setup AWS resources
setup_aws_resources() {
    print_status "Setting up AWS resources..."
    
    # Get AWS account info
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    REGION=$(aws configure get region || echo "us-west-2")
    
    print_status "AWS Account: $ACCOUNT_ID"
    print_status "AWS Region: $REGION"
    
    # Check for required IAM permissions
    print_status "Checking IAM permissions..."
    
    # Test EC2 permissions
    if aws ec2 describe-instances --max-items 1 &> /dev/null; then
        print_status "EC2 permissions ✓"
    else
        print_error "Missing EC2 permissions"
        exit 1
    fi
    
    # Check for default VPC
    VPC_ID=$(aws ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text 2>/dev/null || echo "None")
    if [[ "$VPC_ID" != "None" && "$VPC_ID" != "" ]]; then
        print_status "Default VPC: $VPC_ID ✓"
    else
        print_warning "No default VPC found - manual VPC configuration may be required"
    fi
}

# Run pre-flight checks
run_preflight_checks() {
    print_status "Running pre-flight checks..."
    
    # Test platform components
    python3 -c "
import sys
import importlib.util

components = [
    'vm_lifecycle_manager',
    'remote_desktop_gateway', 
    'enterprise_vm_orchestrator'
]

for component in components:
    try:
        spec = importlib.util.spec_from_file_location(component, f'{component}.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        print(f'✓ {component} imports successfully')
    except Exception as e:
        print(f'✗ {component} import failed: {e}')
        sys.exit(1)
        
print('All components validated ✓')
" || exit 1
}

# Create deployment summary
create_deployment_summary() {
    print_status "Creating deployment summary..."
    
    cat > deployment_summary.txt << EOF
Enterprise Windows Infrastructure Platform Deployment
=====================================================

Deployment Date: $(date)
Environment: $ENVIRONMENT
Version: $VERSION

AWS Configuration:
- Account ID: $(aws sts get-caller-identity --query Account --output text)
- Region: $(aws configure get region || echo "us-west-2")
- Default VPC: $(aws ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text 2>/dev/null || echo "None")

Platform Components:
- VM Lifecycle Manager: vm_lifecycle_manager.py
- Remote Desktop Gateway: remote_desktop_gateway.py
- Enterprise Orchestrator: enterprise_vm_orchestrator.py
- Infrastructure SDK: windows_infrastructure_sdk.py

Configuration:
- Config File: enterprise_config.yaml
- Requirements: requirements.txt

Quick Start:
python enterprise_vm_orchestrator.py

Support:
- Documentation: README.md
- Configuration: enterprise_config.yaml
- Logs: Check CloudWatch logs (if configured)

EOF

    print_status "Deployment summary created: deployment_summary.txt"
}

# Main deployment function
main() {
    echo
    print_status "Starting deployment of $PLATFORM_NAME..."
    echo
    
    # Run all deployment steps
    check_prerequisites
    echo
    
    install_dependencies
    echo
    
    validate_configuration
    echo
    
    setup_aws_resources
    echo
    
    run_preflight_checks
    echo
    
    create_deployment_summary
    echo
    
    print_status "Deployment completed successfully! 🎉"
    echo
    print_status "Next steps:"
    print_status "1. Review deployment_summary.txt"
    print_status "2. Customize enterprise_config.yaml if needed"
    print_status "3. Run: python enterprise_vm_orchestrator.py"
    echo
    print_status "For troubleshooting, check the README.md file"
    echo
}

# Error handling
trap 'print_error "Deployment failed at line $LINENO"' ERR

# Run main deployment
main