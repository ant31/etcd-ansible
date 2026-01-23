# Etcd Smallstep CA Integration

This role integrates Smallstep CA (step-ca) for automated certificate management in etcd clusters.

## Features

- **Automated CA Setup**: Deploys step-ca on the cert-manager node
- **Long-Lived Certificates**: Default 2-year certificate lifetime for manual renewal planning
- **Automatic Renewal**: Systemd timers renew certificates at 2/3 of their lifetime (~487 days)
- **Zero-Downtime Renewal**: Certificates are renewed without restarting etcd
- **Modern Security**: Industry-standard PKI with ACME protocol support
- **No Manual Distribution**: Certificates are fetched directly from step-ca

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Cert-Manager Node (etcd-k8s-1)                          │
│                                                          │
│ ┌─────────────────────────────────────────────────┐    │
│ │ step-ca (port 9000)                             │    │
│ │ - Root CA                                       │    │
│ │ - Intermediate CA                               │    │
│ │ - Certificate Provisioner                       │    │
│ │ - ACME server                                   │    │
│ └─────────────────────────────────────────────────┘    │
│                                                          │
│ /etc/step-ca/                                           │
│ ├── config/ca.json                                      │
│ ├── certs/root_ca.crt                                   │
│ ├── secrets/root_ca_key                                 │
│ └── db/ (certificate database)                          │
└─────────────────────────────────────────────────────────┘
                         │
                         │ HTTPS (port 9000)
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ etcd-k8s-2   │  │ etcd-k8s-3   │  │ app-server   │
│              │  │              │  │              │
│ step-cli     │  │ step-cli     │  │ step-cli     │
│ + systemd    │  │ + systemd    │  │ + systemd    │
│   timers     │  │   timers     │  │   timers     │
│              │  │              │  │              │
│ Auto-renew:  │  │ Auto-renew:  │  │ Auto-renew:  │
│ - peer.crt   │  │ - peer.crt   │  │ - client.crt │
│ - server.crt │  │ - server.crt │  │              │
│ - client.crt │  │ - client.crt │  │              │
└──────────────┘  └──────────────┘  └──────────────┘
```

## Quick Start

### 1. Inventory Configuration

```ini
[etcd]
etcd-k8s-1 ansible_host=10.0.1.10
etcd-k8s-2 ansible_host=10.0.1.11
etcd-k8s-3 ansible_host=10.0.1.12

[etcd-clients]
app-server ansible_host=10.0.2.50

[etcd-cert-managers]
etcd-k8s-1  # This node will run step-ca
```

### 2. Deploy with Smallstep

```bash
ansible-playbook -i inventory.ini playbooks/etcd-smallstep.yaml -e etcd_action=create
```

This will:
1. Install step-ca on etcd-k8s-1
2. Initialize the CA with a root and intermediate certificate
3. Install step-cli on all nodes
4. Generate initial certificates for all nodes
5. Configure automatic renewal via systemd timers
6. Deploy the etcd cluster

### 3. Verify Installation

On the cert-manager node:
```bash
# Check step-ca status
systemctl status step-ca

# View CA health
curl -k https://localhost:9000/health

# List certificates
step ca certificate list
```

On etcd nodes:
```bash
# Check certificate details
step certificate inspect /etc/etcd/ssl/etcd-k8s-1-peer.crt

# Check renewal timer status
systemctl list-timers step-renew-*

# Manually renew a certificate
systemctl start step-renew-etcd-k8s-1-peer.service
```

## Configuration Variables

### CA Configuration

```yaml
# Smallstep versions
step_version: "0.25.2"
step_ca_version: "0.25.2"

# CA naming and network
step_ca_name: "etcd-{{ etcd_cluster_name }}-ca"
step_ca_dns: "{{ hostvars[groups[etcd_certmanagers_group][0]]['ansible_fqdn'] }}"
step_ca_url: "https://{{ step_ca_dns }}:9000"
step_ca_port: 9000

# Certificate lifetimes
step_cert_default_duration: "17520h"  # 2 years (730 days)
step_cert_max_duration: "26280h"      # 3 years
step_cert_min_duration: "1h"

# Renewal period (when to renew)
step_cert_renew_period: "11688h"  # ~487 days (2/3 of 2 years)
```

### Security Best Practices

**IMPORTANT**: In production, store passwords in ansible-vault:

```yaml
# group_vars/all/vault.yml (encrypted with ansible-vault)
step_ca_password: "your-secure-ca-password"
step_provisioner_password: "your-secure-provisioner-password"
```

Encrypt the vault file:
```bash
ansible-vault encrypt group_vars/all/vault.yml
```

Run playbook with vault:
```bash
ansible-playbook -i inventory.ini playbooks/etcd-smallstep.yaml --ask-vault-pass
```

## Certificate Renewal

Certificates are automatically renewed by systemd timers. Three timers are created per etcd node:

1. `step-renew-etcd-k8s-1-peer.timer` - Renews peer certificate
2. `step-renew-etcd-k8s-1-server.timer` - Renews server certificate
3. `step-renew-etcd-k8s-1-client.timer` - Renews client certificate

### Renewal Schedule

- **When**: Daily at 3:00 AM (with 1-hour random delay)
- **Trigger**: Renews if certificate has less than 1/3 of lifetime remaining (~243 days for 2-year certs)
- **Post-Renewal**: Automatically reloads etcd service (for peer/server certs)

### Manual Renewal

Force renewal of a certificate:
```bash
# Renew peer certificate
systemctl start step-renew-etcd-k8s-1-peer.service

# Renew all certificates
systemctl start step-renew-etcd-k8s-1-peer.service
systemctl start step-renew-etcd-k8s-1-server.service
systemctl start step-renew-etcd-k8s-1-client.service
```

## Troubleshooting

### Check step-ca logs
```bash
journalctl -u step-ca -f
```

### Check renewal service logs
```bash
journalctl -u step-renew-etcd-k8s-1-peer.service
```

### Verify certificate expiration
```bash
step certificate inspect /etc/etcd/ssl/etcd-k8s-1-peer.crt --format json | jq '.validity'
```

### Test renewal without applying
```bash
step ca renew --dry-run /etc/etcd/ssl/etcd-k8s-1-peer.crt /etc/etcd/ssl/etcd-k8s-1-peer.key
```

### Manually issue a new certificate
```bash
step ca certificate \
  "etcd-k8s-1" \
  /tmp/test.crt \
  /tmp/test.key \
  --provisioner="etcd-provisioner" \
  --ca-url="https://localhost:9000" \
  --root="/etc/etcd/ssl/root_ca.crt"
```

## Adding New Nodes

To add a new etcd node to an existing cluster:

1. Add the node to inventory:
```ini
[etcd]
etcd-k8s-1
etcd-k8s-2
etcd-k8s-3
etcd-k8s-4  # NEW NODE
```

2. Run the playbook with limit:
```bash
ansible-playbook -i inventory.ini playbooks/etcd-smallstep.yaml --limit=etcd-k8s-4
```

The new node will:
- Install step-cli
- Bootstrap connection to existing step-ca
- Generate its certificates
- Configure automatic renewal
- Join the etcd cluster

## Migration from cfssl

To migrate an existing cluster from cfssl to Smallstep:

1. **Create a backup**:
```bash
ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=backup
```

2. **Deploy step-ca** (cert-manager only):
```bash
ansible-playbook -i inventory.ini playbooks/etcd-smallstep.yaml --tags=step-ca --limit=etcd-cert-managers
```

3. **Migrate nodes one by one**:
```bash
# For each node:
ansible-playbook -i inventory.ini playbooks/etcd-smallstep.yaml --limit=etcd-k8s-2
# Wait for node to rejoin cluster
# Then continue with next node
```

4. **Verify cluster health**:
```bash
etcdctl --endpoints=https://etcd-k8s-1:2379,https://etcd-k8s-2:2379,https://etcd-k8s-3:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  endpoint health
```

## High Availability Setup

### Configure Multiple Cert-Managers

```ini
# inventory.ini
[etcd-cert-managers]
etcd-k8s-1  # Primary - step-ca will run here
etcd-k8s-2  # Backup - CA keys replicated, step-ca installed but stopped
```

Deploy with CA key replication:

```bash
# Initial deployment - replication happens automatically
ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=create

# Manual replication (if adding new backup cert-manager later)
ansible-playbook -i inventory.ini playbooks/replicate-ca.yaml
```

**Automatic replication during deployment (only if multiple cert-managers):**
1. Installs step-ca on primary cert-manager (starts service)
2. Creates encrypted backup of CA keys to S3 (aws-kms or symmetric)
3. Restores CA on backup cert-managers from encrypted S3 backup
4. Verifies CA fingerprints match across all cert-managers
5. Keeps step-ca stopped on backups (ready for failover)

**Note:** Replication is **automatically skipped** if only one cert-manager is configured in inventory.

**Encryption Options:**
- **aws-kms** (recommended): AWS KMS client-side encryption with key rotation support
- **symmetric**: OpenSSL AES-256-CBC encryption with password from ansible-vault
- **none**: No encryption (not recommended for production)

**Security Benefits:**
- ✅ CA keys transmitted encrypted (aws-kms or symmetric)
- ✅ Backup/restore tested during deployment
- ✅ Same process used for disaster recovery
- ✅ No plaintext CA keys in Ansible memory
- ✅ Manual replication uses same secure method

### Manual Failover Procedure

If primary cert-manager fails:

```bash
# 1. Verify primary is down
curl -k https://etcd-k8s-1:9000/health

# 2. Activate step-ca on backup
ssh etcd-k8s-2
systemctl start step-ca

# 3. Update step_ca_url in inventory
# Change step_ca_dns to etcd-k8s-2

# 4. Verify failover
curl -k https://etcd-k8s-2:9000/health
```

## Backup and Recovery

### Automated Daily Backup

**Setup cron for automated backups:**

```bash
# Add to crontab on Ansible controller or automation server
# Using AWS KMS encryption
0 2 * * * cd /opt/etcd-ansible && /usr/bin/ansible-playbook -i inventory.ini playbooks/backup-ca.yaml >> /var/log/step-ca-backup.log 2>&1

# Or using symmetric encryption with vault password file
0 2 * * * cd /opt/etcd-ansible && /usr/bin/ansible-playbook -i inventory.ini playbooks/backup-ca.yaml --vault-password-file /etc/ansible/.vault-pass >> /var/log/step-ca-backup.log 2>&1
```

**Backup retention policy (run weekly):**

```bash
# Delete backups older than 90 days
0 3 * * 0 aws s3 ls s3://etcd-backups/step-ca/ --recursive | awk '{print $4}' | while read file; do DAYS=$(( ($(date +%s) - $(date -d "$(echo $file | grep -oP '\d{4}-\d{2}-\d{2}')" +%s)) / 86400 )); if [ $DAYS -gt 90 ]; then aws s3 rm "s3://etcd-backups/$file"; fi; done
```

### Manual Backup

**Option 1: AWS KMS (Recommended)**

```bash
# Configure in group_vars/all/vault.yml (encrypted)
step_ca_backup_encryption_method: aws-kms
step_ca_backup_kms_key_id: alias/etcd-ca-backup
step_ca_backup_s3_bucket: etcd-backups

# Run backup
ansible-playbook -i inventory.ini playbooks/backup-ca.yaml --vault-password-file ~/.vault-pass
```

**Option 2: Symmetric Encryption**

```bash
# Configure in group_vars/all/vault.yml (encrypted with ansible-vault)
step_ca_backup_encryption_method: symmetric
step_ca_backup_password: "your-very-secure-password-from-password-manager"
step_ca_backup_s3_bucket: etcd-backups

# Run backup
ansible-playbook -i inventory.ini playbooks/backup-ca.yaml --vault-password-file ~/.vault-pass
```

**Option 3: Manual Shell Commands**

```bash
# With AWS KMS
tar czf /tmp/ca-backup.tar.gz /etc/step-ca/secrets /etc/step-ca/config
aws kms encrypt --key-id alias/etcd-ca-backup \
  --plaintext fileb:///tmp/ca-backup.tar.gz \
  --output text --query CiphertextBlob | base64 -d > /tmp/ca-backup.tar.gz.kms
aws s3 cp /tmp/ca-backup.tar.gz.kms s3://backups/step-ca/

# With symmetric encryption
tar czf /tmp/ca-backup.tar.gz /etc/step-ca/secrets /etc/step-ca/config
openssl enc -aes-256-cbc -salt -pbkdf2 -iter 100000 \
  -in /tmp/ca-backup.tar.gz -out /tmp/ca-backup.tar.gz.enc \
  -pass pass:YOUR_PASSWORD
aws s3 cp /tmp/ca-backup.tar.gz.enc s3://backups/step-ca/
```

### Restore from Backup

**Using Ansible (Recommended)**

```bash
# Restore from latest backup
ansible-playbook -i inventory.ini playbooks/restore-ca-from-backup.yaml \
  -e target_node=etcd-k8s-1 \
  --vault-password-file ~/.vault-pass

# Restore specific backup
ansible-playbook -i inventory.ini playbooks/restore-ca-from-backup.yaml \
  -e target_node=etcd-k8s-1 \
  -e step_ca_restore_file=step-ca/2026/01/step-ca-backup-2026-01-20.tar.gz.kms \
  --vault-password-file ~/.vault-pass
```

**Manual Shell Commands**

```bash
# From AWS KMS encrypted backup
aws s3 cp s3://backups/step-ca/ca-backup.tar.gz.kms /tmp/
aws kms decrypt --ciphertext-blob fileb:///tmp/ca-backup.tar.gz.kms \
  --output text --query Plaintext | base64 -d | tar xzf - -C /
chmod 0400 /etc/step-ca/secrets/*
systemctl restart step-ca

# From symmetric encrypted backup
aws s3 cp s3://backups/step-ca/ca-backup.tar.gz.enc /tmp/
openssl enc -aes-256-cbc -d -pbkdf2 -iter 100000 \
  -in /tmp/ca-backup.tar.gz.enc -out /tmp/ca-backup.tar.gz \
  -pass pass:YOUR_PASSWORD
tar xzf /tmp/ca-backup.tar.gz -C /
chmod 0400 /etc/step-ca/secrets/*
systemctl restart step-ca
```

## Disaster Recovery Scenarios

### Scenario 1: Primary Cert-Manager Node Fails

**RTO:** 5-10 minutes  
**Impact:** Certificate issuance blocked (renewal will retry automatically)

**Recovery:**
1. Activate step-ca on backup node (see Manual Failover above)
2. Update DNS/inventory to point to backup
3. Verify health

### Scenario 2: CA Keys Corrupted/Lost

**RTO:** 10-30 minutes  
**Impact:** Cannot issue new certificates

**Recovery:**
1. Stop step-ca: `systemctl stop step-ca`
2. Restore from backup (see above) or copy from backup cert-manager
3. Verify files and permissions
4. Start step-ca: `systemctl start step-ca`

### Scenario 3: Complete Cluster Disaster

**RTO:** 1-2 hours  
**Impact:** Full cluster rebuild needed

**Recovery:**
1. Restore CA keys from encrypted backup
2. Redeploy etcd cluster
3. Restore etcd data (separate backup)
4. Verify all nodes can request certificates

## Benefits over cfssl

1. **Automated Renewal**: Certificates renew automatically without manual intervention
2. **Modern Architecture**: Built-in ACME support, webhooks, and integrations
3. **Configurable Lifetime**: Default 2 years (configurable from 1 hour to 3 years)
4. **Zero Trust**: Nodes fetch certificates on-demand instead of pre-distribution
5. **Monitoring**: Built-in health checks and metrics
6. **Extensible**: Easy to add ACME clients, OIDC providers, etc.

## References

- [Smallstep Documentation](https://smallstep.com/docs/)
- [step-ca GitHub](https://github.com/smallstep/certificates)
- [step CLI GitHub](https://github.com/smallstep/cli)
- [Best Practices Guide](https://smallstep.com/docs/step-ca/certificate-authority-server-production)
