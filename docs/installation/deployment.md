# Initial Deployment

This guide covers deploying your first etcd cluster with Smallstep CA for automated certificate management.

## Prerequisites

Before starting deployment:

- [ ] Completed [Prerequisites](../getting-started/prerequisites.md)
- [ ] Created [Inventory](inventory.md)
- [ ] Configured [AWS KMS](kms-setup.md) (optional but recommended)
- [ ] Created encrypted vault file with secrets

## Deployment Steps

### 1. Verify Prerequisites

```bash
# Test Ansible connectivity
ansible all -i inventory.ini -m ping

# Verify sudo access
ansible all -i inventory.ini -m shell -a "sudo whoami" -b

# Check Python version
ansible all -i inventory.ini -m shell -a "python3 --version"
```

### 2. Configure Secrets

Create and encrypt vault file:

```bash
# Copy example
cp group_vars/all/vault.yml.example group_vars/all/vault.yml

# Edit with your secrets
vi group_vars/all/vault.yml

# Encrypt
ansible-vault encrypt group_vars/all/vault.yml

# Save password
echo "your-vault-password" > ~/.vault-pass
chmod 600 ~/.vault-pass
```

Required secrets:
```yaml
step_ca_password: "secure-password"
step_provisioner_password: "secure-password"
step_ca_backup_s3_bucket: "your-org-etcd-backups"
step_ca_backup_kms_key_id: "alias/etcd-ca-backup"
```

### 3. Deploy Cluster

```bash
ansible-playbook -i inventory.ini etcd.yaml \
  -e etcd_action=create \
  --vault-password-file ~/.vault-pass \
  -b --become-user=root
```

**What happens during deployment:**

1. **Install Dependencies** (~2 min)
   - Create etcd user
   - Download binaries (etcd, step-ca, step CLI)
   - Install to `/opt/bin/`

2. **Setup Certificate Authority** (~2 min)
   - Install step-ca on cert-manager node
   - Initialize CA with root and intermediate certificates
   - Start step-ca service on port 9000
   - Replicate CA keys to backup cert-managers (if configured)

3. **Generate Certificates** (~2 min)
   - Install step CLI on all nodes
   - Bootstrap trust with step-ca
   - Request certificates for each node (peer, server, client)
   - Configure automatic renewal timers

4. **Deploy etcd Cluster** (~3 min)
   - Create etcd configuration files
   - Create systemd service files
   - Start etcd services
   - Verify cluster health

5. **Configure Backups** (~1 min)
   - Setup automated backup scripts
   - Configure cron jobs
   - Setup log rotation

**Total deployment time:** ~10 minutes

### 4. Monitor Deployment

Watch deployment progress:

```bash
# In another terminal
watch -n 2 'ansible etcd -i inventory.ini -m shell -a "systemctl status etcd-* | grep Active" -b'
```

## Deployment Output

Successful deployment shows:

```
PLAY RECAP ***********************************************************
etcd-k8s-1   : ok=45  changed=23  unreachable=0  failed=0  skipped=5
etcd-k8s-2   : ok=38  changed=20  unreachable=0  failed=0  skipped=8
etcd-k8s-3   : ok=38  changed=20  unreachable=0  failed=0  skipped=8
```

## Post-Deployment Verification

See [Verification Guide](verification.md) for detailed verification steps.

### Quick Health Check

```bash
# Check etcd cluster
ansible etcd[0] -i inventory.ini -m shell -a "
  etcdctl --endpoints=https://10.0.1.10:2379,https://10.0.1.11:2379,https://10.0.1.12:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  endpoint health
" -b
```

Expected output:
```
https://10.0.1.10:2379 is healthy: successfully committed proposal
https://10.0.1.11:2379 is healthy: successfully committed proposal
https://10.0.1.12:2379 is healthy: successfully committed proposal
```

## Common Deployment Scenarios

### Single-Node Development Cluster

```ini
[etcd]
etcd-dev-1 ansible_host=192.168.1.10

[etcd-cert-managers]
etcd-dev-1
```

```bash
ansible-playbook -i inventory-dev.ini etcd.yaml \
  -e etcd_action=create \
  -e etcd_cluster_name=dev \
  --vault-password-file ~/.vault-pass \
  -b
```

### Production 3-Node Cluster with HA

```ini
[etcd]
etcd-prod-1 ansible_host=10.0.1.10
etcd-prod-2 ansible_host=10.0.1.11
etcd-prod-3 ansible_host=10.0.1.12

[etcd-cert-managers]
etcd-prod-1  # Primary
etcd-prod-2  # Backup

[etcd-clients]
kube-apiserver-1 ansible_host=10.0.2.10
```

```bash
ansible-playbook -i inventory-prod.ini etcd.yaml \
  -e etcd_action=create \
  -e etcd_cluster_name=production \
  --vault-password-file ~/.vault-pass \
  -b
```

### Multi-Cluster Deployment

Deploy separate clusters for different purposes:

```bash
# Main cluster
ansible-playbook -i inventory-main.ini etcd.yaml \
  -e etcd_action=create \
  -e etcd_cluster_name=main \
  --vault-password-file ~/.vault-pass -b

# Events cluster
ansible-playbook -i inventory-events.ini etcd.yaml \
  -e etcd_action=create \
  -e etcd_cluster_name=events \
  --vault-password-file ~/.vault-pass -b
```

## Troubleshooting Deployment

### Installation Fails Partway Through

```bash
# Retry with force flag
ansible-playbook -i inventory.ini etcd.yaml \
  -e etcd_action=create \
  -e etcd_force_create=true \
  --vault-password-file ~/.vault-pass -b
```

### step-ca Won't Start

```bash
# Check logs
ansible etcd-cert-managers[0] -i inventory.ini \
  -m shell -a "journalctl -u step-ca -n 50" -b

# Verify CA files
ansible etcd-cert-managers[0] -i inventory.ini \
  -m shell -a "ls -la /etc/step-ca/secrets/" -b

# Test configuration
ansible etcd-cert-managers[0] -i inventory.ini \
  -m shell -a "/opt/bin/step-ca --dry-run /etc/step-ca/config/ca.json" -b
```

### Certificate Generation Fails

```bash
# Test connectivity to step-ca
ansible etcd -i inventory.ini \
  -m shell -a "curl -k https://10.0.1.10:9000/health" -b

# Check step-ca health
ansible etcd-cert-managers[0] -i inventory.ini \
  -m shell -a "systemctl status step-ca" -b
```

### etcd Won't Start

```bash
# Check etcd logs
ansible etcd -i inventory.ini \
  -m shell -a "journalctl -u etcd-* -n 50" -b

# Verify certificate files
ansible etcd -i inventory.ini \
  -m shell -a "ls -la /etc/etcd/ssl/" -b

# Check certificate validity
ansible etcd -i inventory.ini \
  -m shell -a "openssl verify -CAfile /etc/etcd/ssl/root_ca.crt /etc/etcd/ssl/etcd-*-peer.crt" -b
```

## Deployment Variables

### Essential Variables

```yaml
# Cluster configuration
etcd_cluster_name: default
etcd_version: v3.5.26

# Certificate authority
step_ca_port: 9000
step_cert_default_duration: "17520h"  # 2 years

# Backup configuration
etcd_backup_cron_enabled: true
ca_backup_cron_enabled: true
```

### Optional Variables

```yaml
# Performance tuning
etcd_heartbeat_interval: 250
etcd_election_timeout: 5000

# Backup retention
etcd_backup_retention_days: 90
ca_backup_retention_days: 365

# Healthcheck monitoring
backup_healthcheck_enabled: true
backup_healthcheck_url: "https://hc-ping.com/your-uuid"
```

## Next Steps

After successful deployment:

1. [Verify Installation](verification.md) - Complete verification
2. [Operations Guide](../operations/cluster-management.md) - Day-2 operations
3. [Backup & Restore](../operations/backup-restore.md) - Backup procedures
4. [Certificate Management](../certificates/overview.md) - Certificate operations

## Related Documentation

- [Prerequisites](../getting-started/prerequisites.md)
- [Inventory Setup](inventory.md)
- [AWS KMS Setup](kms-setup.md)
- [Quick Start Guide](../getting-started/quick-start.md)
