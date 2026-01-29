# Multi-Cluster Quick Start

Deploy multiple etcd clusters in **one command** - complete guide in 5 minutes.

## Prerequisites

- ✅ Ansible 2.9+
- ✅ Python 3.6+
- ✅ SSH access to target nodes
- ✅ AWS credentials (for backups)

## Step 1: Copy Examples (30 seconds)

```bash
# Copy example files
cp inventory/inventory-multi-cluster-example.ini inventory.ini
cp inventory/group_vars/all/multi-cluster-example.yaml group_vars/all/etcd.yaml
```

## Step 2: Customize for Your Environment (2 minutes)

Edit `inventory.ini`:

```ini
[etcd-k8s]
node1 ansible_host=YOUR_IP_1
node2 ansible_host=YOUR_IP_2
node3 ansible_host=YOUR_IP_3

[etcd-k8s-events]
node1 ansible_host=YOUR_IP_1  # Same nodes OK
node2 ansible_host=YOUR_IP_2
node3 ansible_host=YOUR_IP_3

[etcd-all:children]
etcd-k8s
etcd-k8s-events

[etcd-cert-managers-all]
node1
```

Edit `group_vars/all/etcd.yaml` (adjust S3 prefixes, ports, etc.):

```yaml
# Defaults apply to ALL clusters
etcd_backup_interval: "*/30"

# Per-cluster overrides
etcd_cluster_configs:
  k8s:
    backup:
      s3_prefix: "YOUR-ORG/k8s/"
  k8s-events:
    ports: { client: 2381, peer: 2382 }
    backup:
      interval: "*/60"
      s3_prefix: "YOUR-ORG/events/"
```

Edit `group_vars/all/vault.yml` (S3 bucket, AWS credentials):

```yaml
# Encrypt with: ansible-vault encrypt group_vars/all/vault.yml
etcd_upload_backup:
  bucket: "YOUR-S3-BUCKET"
  
aws_access_key_id: "YOUR_AWS_KEY"
aws_secret_access_key: "YOUR_AWS_SECRET"
```

## Step 3: Test Configuration (1 minute)

```bash
# Validate syntax
./scripts/test-multi-cluster.sh

# Or manually:
ansible-playbook playbooks/deploy-all-clusters.yaml --syntax-check
ansible-playbook playbooks/deploy-all-clusters.yaml -i inventory.ini -e etcd_action=create --check
```

## Step 4: Deploy All Clusters (5-10 minutes)

```bash
# Single command deploys everything!
ansible-playbook -i inventory.ini playbooks/deploy-all-clusters.yaml \
  -e etcd_action=create \
  --vault-password-file .vault-pass \
  -b
```

**What happens:**
```
Phase 1: Prepare all nodes (ONCE)
├─ Download etcd, step-ca, step-cli, awscli
├─ Create etcd user
└─ Install shared step-ca

Phase 2: Deploy each cluster (Sequential)
├─ Deploy k8s cluster (ports 2379/2380)
│  ├─ Generate k8s-specific certificates
│  ├─ Start etcd-k8s-* services
│  └─ Setup k8s backup cron (*/30)
└─ Deploy k8s-events cluster (ports 2381/2382)
   ├─ Generate events-specific certificates
   ├─ Start etcd-k8s-events-* services
   └─ Setup events backup cron (*/60)

Phase 3: Summary
└─ Show completion status
```

## Step 5: Verify Deployment (1 minute)

```bash
# Check all clusters healthy
ansible-playbook -i inventory.ini playbooks/etcd-health-all-clusters.yaml
```

**Expected output:**
```
╔════════════════════════════════════════════════════════════════╗
║           MULTI-CLUSTER HEALTH SUMMARY                        ║
╠════════════════════════════════════════════════════════════════╣
║ Cluster: k8s                 Status: ✅ HEALTHY
║ Cluster: k8s-events          Status: ✅ HEALTHY
╠════════════════════════════════════════════════════════════════╣
║ Overall: ✅ All clusters healthy
╚════════════════════════════════════════════════════════════════╝
```

**Additional verification:**

```bash
# Services running
ansible etcd-all -i inventory.ini -m shell -a 'systemctl status etcd-*' -b

# Backup cron jobs
ansible etcd-all -i inventory.ini -m shell -a 'crontab -l | grep etcd-backup' -b

# Certificates
ansible etcd-all -i inventory.ini -m shell -a 'ls -1 /etc/etcd/ssl/etcd-*-peer.crt' -b
```

## Checklist

After deployment, verify:

- [ ] All clusters show as HEALTHY in health check
- [ ] Each node runs N etcd services (N = cluster count)
- [ ] Each cluster has separate data directory (`/var/lib/etcd/etcd-CLUSTERNAME-*`)
- [ ] Backup cron jobs created per cluster (check `crontab -l`)
- [ ] Certificates include cluster name (`etcd-k8s-1`, `etcd-events-1`)
- [ ] Only one step-ca running (on first cert-manager)
- [ ] Each cluster accessible on its specific ports

## Common Issues

### "Cluster not found in inventory"

**Error:** `❌ Cluster 'k8s' configured in etcd_cluster_configs but no inventory group!`

**Fix:** Add `[etcd-k8s]` group to inventory.ini

### "etcd-all group not found"

**Error:** `❌ Inventory missing [etcd-all] aggregate group!`

**Fix:** Add to inventory:
```ini
[etcd-all:children]
etcd-k8s
etcd-k8s-events
```

### Port conflicts

**Symptom:** etcd service fails to start with "address already in use"

**Fix:** Ensure each cluster uses different ports in `etcd_cluster_configs`

### Backup cron not created

**Symptom:** `crontab -l` shows no etcd-backup entries

**Fix:** Check `deploy-single-cluster.yml` includes backup cron role

## Next Steps

1. **Configure monitoring:** Add healthcheck URLs to cluster configs
2. **Test backups:** Wait for first cron run, verify S3 uploads
3. **Test restore:** Practice disaster recovery procedures
4. **Scale:** Add more clusters as needed

## Time Savings

**Before (separate deployments):**
- Cluster 1: 5-7 minutes
- Cluster 2: 5-7 minutes  
- Cluster 3: 5-7 minutes
- **Total: 15-21 minutes** + manual coordination

**After (unified deployment):**
- All clusters: **8-12 minutes**
- **Savings: 40-50%** + automatic coordination

## See Also

- [Multi-Cluster Configuration](../advanced/multi-cluster-config.md) - All configuration options
- [Unified Deployment Guide](../advanced/unified-multi-cluster.md) - Detailed architecture
- [Implementation TODO](../../todos/multicluster.md) - What was built
