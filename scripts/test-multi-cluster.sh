#!/bin/bash
# Test script for unified multi-cluster deployment
# Usage: ./scripts/test-multi-cluster.sh

set -e

echo "════════════════════════════════════════════════════════════════"
echo "Multi-Cluster Deployment Test"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Check prerequisites
echo "1. Checking prerequisites..."

if [ ! -f "inventory/inventory-multi-cluster-example.ini" ]; then
    echo "❌ Example inventory not found"
    echo "   Copy: cp inventory/inventory-multi-cluster-example.ini inventory-test.ini"
    exit 1
fi

if [ ! -f "inventory/group_vars/all/multi-cluster-example.yaml" ]; then
    echo "❌ Example config not found"
    echo "   Copy: cp inventory/group_vars/all/multi-cluster-example.yaml group_vars/all/etcd-test.yaml"
    exit 1
fi

echo "✅ Prerequisites OK"
echo ""

# Validate inventory
echo "2. Validating inventory structure..."
ansible-inventory -i inventory-test.ini --graph | grep -q "etcd-all" || {
    echo "❌ Inventory missing [etcd-all] group"
    exit 1
}
echo "✅ Inventory structure OK"
echo ""

# Check syntax
echo "3. Checking playbook syntax..."
ansible-playbook playbooks/deploy-all-clusters.yaml --syntax-check || {
    echo "❌ Syntax check failed"
    exit 1
}
echo "✅ Syntax OK"
echo ""

# Dry run (check mode)
echo "4. Running dry-run deployment (check mode)..."
ansible-playbook -i inventory-test.ini playbooks/deploy-all-clusters.yaml \
    -e etcd_action=create \
    --check \
    -v || {
    echo "❌ Dry-run failed"
    exit 1
}
echo "✅ Dry-run OK"
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "✅ All pre-deployment checks passed!"
echo ""
echo "Ready to deploy for real:"
echo ""
echo "  ansible-playbook -i inventory-test.ini \\"
echo "    playbooks/deploy-all-clusters.yaml \\"
echo "    -e etcd_action=create -b"
echo ""
echo "After deployment, verify with:"
echo ""
echo "  ansible-playbook -i inventory-test.ini \\"
echo "    playbooks/etcd-health-all-clusters.yaml"
echo ""
echo "════════════════════════════════════════════════════════════════"
