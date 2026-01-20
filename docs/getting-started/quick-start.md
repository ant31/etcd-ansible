# Quick Start Guide

Get your first etcd cluster running in 15 minutes!

## Prerequisites Check

Before starting, ensure you have:

- [ ] 3 Linux servers (Ubuntu 20.04+ recommended)
- [ ] Ansible 2.9+ installed on your laptop
- [ ] SSH access to all servers with sudo privileges
- [ ] AWS account for S3 backups (optional but recommended)
- [ ] AWS CLI installed and configured

## Step 1: Clone Repository

```bash
git clone https://github.com/your-org/etcd-ansible.git
cd etcd-ansible
```

## Step 2: Create Inventory

Create `inventory.ini`:

```bash
cp inventory-example.ini inventory.ini
```

Edit with your server IPs:

```ini
[etcd]
etcd-k8s-1 ansible_host=10.0.1.10
etcd-k8s-2 ansible_host=10.0.1.11
etcd-k8s-3 ansible_host=10.0.1.12

[etcd-cert-managers]
etcd-k8s-1  # This node runs step-ca
```

## Step 3: Setup AWS KMS (Optional but Recommended)

Create KMS key for backup encryption:

```bash
# Create KMS key
aws kms create-key --description "etcd CA backup encryption"

# Note the KeyId from output, then create alias
aws kms create-alias \
  --alias-name alias/etcd-ca-backup \
  --target-key-id <KEY_ID_FROM_ABOVE>
```

Or use the automated playbook:

```bash
ansible-playbook playbooks/setup-kms.yaml
```

## Step 4: Configure Secrets

Create vault file:

```bash
cp group_vars/all/vault.yml.example group_vars/all/vault.yml
```

Edit `group_vars/all/vault.yml`:

```yaml
# Generate strong passwords:
# openssl rand -base64 32

step_ca_password: "your-secure-ca-password"
step_provisioner_password: "your-secure-provisioner-password"

# S3 bucket for backups
step_ca_backup_s3_bucket: "your-org-etcd-backups"

# KMS key for encryption
step_ca_backup_kms_key_id: "alias/etcd-ca-backup"
```

Encrypt the vault:

```bash
ansible-vault encrypt group_vars/all/vault.yml
# Enter a vault password when prompted

# Save vault password to file (don't commit to git!)
echo "your-vault-password" > ~/.vault-pass
chmod 600 ~/.vault-pass
```

## Step 5: Deploy Cluster

```bash
ansible-playbook -i inventory.ini etcd.yaml \
  -e etcd_action=create \
  --vault-password-file ~/.vault-pass \
  -b --become-user=root
```

This will:

1. ✅ Install step-ca on etcd-k8s-1
2. ✅ Initialize CA with root and intermediate certificates
3. ✅ Install step CLI on all nodes
4. ✅ Generate 2-year certificates for all nodes
5. ✅ Configure automatic certificate renewal
6. ✅ Deploy etcd cluster
7. ✅ Configure automated backups

**Deployment time**: ~5-10 minutes

## Step 6: Verify Installation

### Check cluster health

```bash
# SSH to any etcd node
ssh etcd-k8s-1

# Check etcd cluster
sudo etcdctl \
  --endpoints=https://etcd-k8s-1:2379,https://etcd-k8s-2:2379,https://etcd-k8s-3:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  endpoint health
```

Expected output:
```
https://etcd-k8s-1:2379 is healthy: successfully committed proposal
https://etcd-k8s-2:2379 is healthy: successfully committed proposal
https://etcd-k8s-3:2379 is healthy: successfully committed proposal
```

### Check step-ca status

```bash
# On cert-manager node (etcd-k8s-1)
sudo systemctl status step-ca

# Test health endpoint
curl -k https://localhost:9000/health
```

Expected output:
```json
{"status":"ok"}
```

### Check certificate expiration

```bash
# View certificate details
sudo step certificate inspect /etc/etcd/ssl/etcd-k8s-1-peer.crt
```

Look for:
```
    Not Before: 2026-01-20 15:30:00 +0000 UTC
    Not After: 2028-01-20 15:30:00 +0000 UTC  # 2 years
```

### Check automatic renewal timers

```bash
# List renewal timers
sudo systemctl list-timers 'step-renew-*'
```

Expected output:
```
NEXT                         LEFT          LAST  PASSED  UNIT
Tue 2026-01-21 03:00:00 UTC  11h left      -     -       step-renew-etcd-k8s-1-peer.timer
Tue 2026-01-21 03:00:00 UTC  11h left      -     -       step-renew-etcd-k8s-1-server.timer
Tue 2026-01-21 03:00:00 UTC  11h left      -     -       step-renew-etcd-k8s-1-client.timer
```

## Step 7: Test Cluster Operations

### Write data to etcd

```bash
# Write a key
sudo etcdctl \
  --endpoints=https://etcd-k8s-1:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  put /test/key "hello world"
```

### Read data from etcd

```bash
# Read the key
sudo etcdctl \
  --endpoints=https://etcd-k8s-2:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  get /test/key
```

Expected output:
```
/test/key
hello world
```

### Check cluster members

```bash
sudo etcdctl \
  --endpoints=https://etcd-k8s-1:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  member list
```

## Step 8: Verify Automated Backups

Check if automated backups are configured:

```bash
# SSH to cert-manager node
ssh etcd-k8s-1

# Check backup cron jobs
sudo crontab -l | grep backup

# Check backup logs
sudo tail -f /var/log/etcd-backups/ca-backup.log
sudo tail -f /var/log/etcd-backups/etcd-backup.log
```

## Congratulations! 🎉

You now have a production-ready etcd cluster with:

- ✅ Automated certificate management
- ✅ 2-year certificates with automatic renewal
- ✅ Encrypted backups to S3
- ✅ High availability setup
- ✅ Zero-downtime operations ready

## Next Steps

Now that you have a running cluster:

1. **Integrate with Applications**: [Integration Examples](../playbooks/integration.md)
2. **Setup Monitoring**: [Health Checks](../operations/health-checks.md)
3. **Configure High Availability**: [HA Setup Guide](../advanced/ha-setup.md)
4. **Learn Operations**: [Operations Guide](../operations/cluster-management.md)
5. **Understand Certificates**: [Certificate Management](../certificates/overview.md)

## Common Issues

### Issue: SSH connection fails

```bash
# Test SSH connectivity
ansible all -i inventory.ini -m ping

# If fails, check SSH keys:
ssh-copy-id -i ~/.ssh/id_rsa.pub etcd-k8s-1
```

### Issue: Ansible vault password error

```bash
# Verify vault password file exists
cat ~/.vault-pass

# Or use interactive mode:
ansible-playbook ... --ask-vault-pass
```

### Issue: KMS access denied

```bash
# Verify KMS key exists
aws kms describe-key --key-id alias/etcd-ca-backup

# Verify IAM permissions
aws kms encrypt \
  --key-id alias/etcd-ca-backup \
  --plaintext "test" \
  --query CiphertextBlob
```

### Issue: step-ca won't start

```bash
# Check step-ca logs
sudo journalctl -u step-ca -n 100

# Verify CA files exist
sudo ls -la /etc/step-ca/secrets/

# Test configuration
sudo /opt/bin/step-ca --dry-run /etc/step-ca/config/ca.json
```

## Getting Help

- **Documentation**: Read the full [Operations Guide](../operations/cluster-management.md)
- **Troubleshooting**: Check [Common Issues](../troubleshooting/common-issues.md)
- **FAQ**: Visit [FAQ](../reference/faq.md)
- **GitHub Issues**: Report bugs or ask questions

## Cleanup (Optional)

To remove the test cluster:

```bash
ansible-playbook -i inventory.ini etcd.yaml \
  -e etcd_delete_cluster=true \
  -b --become-user=root
```

!!! warning "Destructive Operation"
    This will permanently delete all etcd data and certificates!
