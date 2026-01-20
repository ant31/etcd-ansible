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
# Initial deployment
ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=create

# This automatically:
# 1. Installs step-ca on etcd-k8s-1 (starts service)
# 2. Installs step-ca on etcd-k8s-2 (service stopped)
# 3. Replicates CA keys to etcd-k8s-2
```

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

Create cron job to backup CA keys daily:

```bash
# On cert-manager node or via Ansible
0 2 * * * /usr/local/bin/backup-step-ca.sh
```

```bash
#!/bin/bash
# /usr/local/bin/backup-step-ca.sh
DATE=$(date +%Y-%m-%d)
tar czf /tmp/step-ca-backup-${DATE}.tar.gz /etc/step-ca/secrets /etc/step-ca/config
gpg --encrypt --recipient admin@example.com /tmp/step-ca-backup-${DATE}.tar.gz
aws s3 cp /tmp/step-ca-backup-${DATE}.tar.gz.gpg s3://backups/step-ca/
rm -f /tmp/step-ca-backup-${DATE}.tar.gz*
```

### Manual Backup

```bash
# On cert-manager node
tar czf step-ca-backup.tar.gz /etc/step-ca/secrets /etc/step-ca/config
gpg --encrypt --recipient admin@example.com step-ca-backup.tar.gz
aws s3 cp step-ca-backup.tar.gz.gpg s3://backups/step-ca/
```

### Restore from Backup

```bash
# Download backup
aws s3 cp s3://backups/step-ca/step-ca-backup.tar.gz.gpg .

# Decrypt and extract
gpg --decrypt step-ca-backup.tar.gz.gpg | tar xzf - -C /

# Fix permissions
chmod 0400 /etc/step-ca/secrets/*
chown -R root:root /etc/step-ca/

# Restart step-ca
systemctl restart step-ca

# Verify
curl -k https://localhost:9000/health
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
