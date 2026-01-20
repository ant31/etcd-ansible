# Preparing Inventory

The inventory file defines your etcd cluster topology and which nodes perform specific roles.

## Required Groups

### `[etcd]` - Cluster Member Nodes

Nodes that run the etcd service and participate in the cluster.

```ini
[etcd]
etcd-k8s-1 ansible_host=10.0.1.10
etcd-k8s-2 ansible_host=10.0.1.11
etcd-k8s-3 ansible_host=10.0.1.12
```

**Requirements:**
- Odd number of nodes (3, 5, 7) for quorum
- All nodes should have reliable network connectivity
- Low latency between nodes (< 10ms recommended)

### `[etcd-cert-managers]` - Certificate Authority Nodes

Nodes that run step-ca and hold CA private keys.

```ini
[etcd-cert-managers]
etcd-k8s-1  # Primary cert-manager (step-ca running)
etcd-k8s-2  # Backup cert-manager (CA keys replicated, step-ca stopped)
```

**Best Practices:**
- **Development**: Use 1 cert-manager (first etcd node)
- **Production**: Use 2+ cert-managers for redundancy
- **High Availability**: Primary runs step-ca, backups have replicated keys

### `[etcd-clients]` - Client Nodes (Optional)

Nodes that need client certificates to connect to etcd but don't run etcd themselves.

```ini
[etcd-clients]
kube-apiserver-1 ansible_host=10.0.2.10
kube-apiserver-2 ansible_host=10.0.2.11
app-server-1 ansible_host=10.0.2.20
```

**Use Cases:**
- Kubernetes API servers connecting to etcd
- Application servers that read/write to etcd
- Monitoring systems
- Backup/restore tools

## Example Inventories

### Small Development Cluster

```ini
# inventory-dev.ini
[etcd]
etcd-dev-1 ansible_host=192.168.1.10

[etcd-cert-managers]
etcd-dev-1

[etcd-all:children]
etcd
```

**Characteristics:**
- Single node (no HA)
- Good for testing and development
- Simple setup

### Production 3-Node Cluster

```ini
# inventory-prod.ini
[etcd]
etcd-prod-1 ansible_host=10.0.1.10
etcd-prod-2 ansible_host=10.0.1.11
etcd-prod-3 ansible_host=10.0.1.12

[etcd-cert-managers]
etcd-prod-1  # Primary
etcd-prod-2  # Backup

[etcd-all:children]
etcd
```

**Characteristics:**
- 3 nodes (1 node failure tolerance)
- HA certificate management
- Recommended for small production

### Large Production 5-Node Cluster with Clients

```ini
# inventory-large.ini
[etcd]
etcd-1 ansible_host=10.0.1.10
etcd-2 ansible_host=10.0.1.11
etcd-3 ansible_host=10.0.1.12
etcd-4 ansible_host=10.0.1.13
etcd-5 ansible_host=10.0.1.14

[etcd-clients]
k8s-master-1 ansible_host=10.0.2.10
k8s-master-2 ansible_host=10.0.2.11
k8s-master-3 ansible_host=10.0.2.12

[etcd-cert-managers]
etcd-1  # Primary
etcd-2  # Backup
etcd-3  # Backup

[etcd-all:children]
etcd
etcd-clients
```

**Characteristics:**
- 5 nodes (2 node failure tolerance)
- Multiple backup cert-managers
- Kubernetes integration
- Enterprise-grade HA

## Host Variables

### Common Host Variables

```ini
[etcd]
etcd-k8s-1 ansible_host=10.0.1.10 etcd_member_index=1
etcd-k8s-2 ansible_host=10.0.1.11 etcd_member_index=2
etcd-k8s-3 ansible_host=10.0.1.12 etcd_member_index=3

[etcd:vars]
ansible_user=ubuntu
ansible_become=yes
ansible_python_interpreter=/usr/bin/python3
```

**Available Host Variables:**
- `etcd_member_index`: Custom index number (default: auto-assigned)
- `etcd_member_name`: Custom member name (default: etcd-{cluster}-{index})
- `ansible_host`: IP address or hostname
- `ansible_user`: SSH user
- `ansible_port`: SSH port (default: 22)

### Custom Member Names

```ini
[etcd]
primary ansible_host=10.0.1.10 etcd_member_name=etcd-primary
secondary ansible_host=10.0.1.11 etcd_member_name=etcd-secondary
tertiary ansible_host=10.0.1.12 etcd_member_name=etcd-tertiary
```

## Group Variables

### Cluster Configuration

Create `group_vars/etcd.yml`:

```yaml
# Cluster settings
etcd_cluster_name: production
etcd_version: v3.5.26

# Ports
etcd_ports:
  client: 2379
  peer: 2380

# Performance tuning
etcd_heartbeat_interval: 250
etcd_election_timeout: 5000

# Backup settings
etcd_backup: yes
etcd_backup_retention_days: 90
```

### Certificate Settings

Create `group_vars/all/certs.yml`:

```yaml
# Smallstep CA
step_version: "0.25.2"
step_ca_version: "0.25.2"
step_ca_port: 9000

# Certificate lifetimes
step_cert_default_duration: "17520h"  # 2 years
step_cert_max_duration: "26280h"      # 3 years
```

### Sensitive Variables (Encrypted)

Create `group_vars/all/vault.yml` (encrypted with ansible-vault):

```yaml
# Generate with: openssl rand -base64 32
step_ca_password: "CHANGE_ME"
step_provisioner_password: "CHANGE_ME"

# AWS configuration
step_ca_backup_s3_bucket: "my-org-etcd-backups"
step_ca_backup_kms_key_id: "alias/etcd-ca-backup"
```

Encrypt the file:

```bash
ansible-vault encrypt group_vars/all/vault.yml
```

## Multi-Environment Inventories

### Separate Inventories per Environment

```
inventories/
├── dev/
│   ├── inventory.ini
│   └── group_vars/
│       └── all/
│           ├── vars.yml
│           └── vault.yml
├── staging/
│   ├── inventory.ini
│   └── group_vars/
│       └── all/
│           ├── vars.yml
│           └── vault.yml
└── prod/
    ├── inventory.ini
    └── group_vars/
        └── all/
            ├── vars.yml
            └── vault.yml
```

**Usage:**

```bash
# Deploy to dev
ansible-playbook -i inventories/dev/inventory.ini etcd.yaml -e etcd_action=create

# Deploy to prod
ansible-playbook -i inventories/prod/inventory.ini etcd.yaml -e etcd_action=create
```

### Single Inventory with Environment Groups

```ini
# inventory-all.ini
[etcd-dev]
etcd-dev-1 ansible_host=192.168.1.10

[etcd-staging]
etcd-stg-1 ansible_host=10.1.1.10
etcd-stg-2 ansible_host=10.1.1.11
etcd-stg-3 ansible_host=10.1.1.12

[etcd-prod]
etcd-prod-1 ansible_host=10.0.1.10
etcd-prod-2 ansible_host=10.0.1.11
etcd-prod-3 ansible_host=10.0.1.12

# Aggregate groups
[etcd:children]
etcd-dev
etcd-staging
etcd-prod

[etcd-dev:vars]
etcd_cluster_name=dev
etcd_backup_retention_days=30

[etcd-staging:vars]
etcd_cluster_name=staging
etcd_backup_retention_days=60

[etcd-prod:vars]
etcd_cluster_name=production
etcd_backup_retention_days=90
```

**Usage with limits:**

```bash
# Deploy only prod
ansible-playbook -i inventory-all.ini etcd.yaml --limit=etcd-prod -e etcd_action=create
```

## Network Topology Considerations

### Same Datacenter (Recommended)

```ini
# All nodes in same DC, low latency
[etcd]
etcd-dc1-1 ansible_host=10.0.1.10  # Rack A
etcd-dc1-2 ansible_host=10.0.1.11  # Rack B
etcd-dc1-3 ansible_host=10.0.1.12  # Rack C
```

**Benefits:**
- Low latency (< 1ms)
- High throughput
- Simple network configuration

### Multi-Datacenter (Advanced)

```ini
# Nodes across DCs - only if latency < 10ms
[etcd]
etcd-dc1-1 ansible_host=10.0.1.10  # DC1
etcd-dc1-2 ansible_host=10.0.1.11  # DC1
etcd-dc2-1 ansible_host=10.1.1.10  # DC2
etcd-dc2-2 ansible_host=10.1.1.11  # DC2
etcd-dc3-1 ansible_host=10.2.1.10  # DC3
```

**Requirements:**
- Latency < 10ms between DCs
- Stable network connectivity
- 5+ nodes for quorum across DCs

!!! warning "Network Latency"
    etcd is very sensitive to network latency. Keep all nodes in the same datacenter unless you have very low inter-DC latency (< 10ms).

## Validation

### Test Connectivity

```bash
# Ping all hosts
ansible all -i inventory.ini -m ping

# Test sudo access
ansible all -i inventory.ini -m shell -a "sudo whoami" -b

# Check Python version
ansible all -i inventory.ini -m shell -a "python3 --version"
```

### Verify Groups

```bash
# List etcd members
ansible etcd -i inventory.ini --list-hosts

# List cert-managers
ansible etcd-cert-managers -i inventory.ini --list-hosts

# List all etcd-related hosts
ansible etcd-all -i inventory.ini --list-hosts
```

### Validate Variables

```bash
# Show host variables
ansible-inventory -i inventory.ini --host etcd-k8s-1

# Show group variables
ansible-inventory -i inventory.ini --graph --vars

# Check vault encryption
ansible-vault view group_vars/all/vault.yml
```

## Troubleshooting

### SSH Connection Issues

```bash
# Test SSH directly
ssh -i ~/.ssh/id_rsa user@etcd-k8s-1

# Test with verbose output
ansible all -i inventory.ini -m ping -vvv

# Check SSH config
cat ~/.ssh/config
```

### Group Not Found

```
ERROR! 'etcd-cert-managers' is not a valid group name
```

**Solution:** Check group names in inventory match exactly (case-sensitive).

### Host Not Reachable

```bash
# Check network connectivity
ping etcd-k8s-1

# Check DNS resolution
nslookup etcd-k8s-1

# Use IP address instead
[etcd]
etcd-k8s-1 ansible_host=10.0.1.10
```

## Best Practices

1. **Use meaningful hostnames** - Name nodes descriptively (e.g., `etcd-prod-1`)
2. **Document your topology** - Add comments to inventory explaining the setup
3. **Version control** - Keep inventory in git (but not vault passwords!)
4. **Separate secrets** - Use ansible-vault for sensitive data
5. **Test before production** - Validate inventory with dev environment first
6. **Backup inventory** - Keep copies of production inventory secure
7. **Use consistent naming** - Follow naming conventions across environments
8. **Document special configs** - Comment any non-standard settings

## Next Steps

- [AWS KMS Setup](kms-setup.md) - Configure encrypted backups
- [Initial Deployment](deployment.md) - Deploy your first cluster
- [Verification](verification.md) - Verify the deployment
