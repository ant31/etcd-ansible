# Certificate Architecture - Smallstep CA

**Last Updated**: 2026-01-20  
**Implementation**: Smallstep CA (step-ca)  
**Status**: Production-ready

## Quick Reference

### File Locations

**On step-ca node (cert-manager):**
```
/etc/step-ca/
├── config/ca.json              # CA configuration
├── certs/root_ca.crt           # Root CA (public)
├── secrets/root_ca_key         # Root CA key (PRIVATE)
├── certs/intermediate_ca.crt   # Intermediate CA (public)
├── secrets/intermediate_ca_key # Intermediate CA key (PRIVATE)
├── secrets/password            # CA password (PRIVATE)
└── db/                         # Certificate database

/opt/bin/
├── step-ca                     # CA server binary
└── step                        # CLI tool
```

**On each etcd/client node:**
```
/etc/etcd/ssl/
├── etcd-k8s-X-peer.crt         # Peer certificate (public)
├── etcd-k8s-X-peer.key         # Peer private key (PRIVATE)
├── etcd-k8s-X-server.crt       # Server certificate (public)
├── etcd-k8s-X-server.key       # Server private key (PRIVATE)
├── etcd-k8s-X-client.crt       # Client certificate (public)
├── etcd-k8s-X-client.key       # Client private key (PRIVATE)
├── root_ca.crt                 # Root CA (public)
├── peer-ca.crt → root_ca.crt   # Symlink for compatibility
└── client-ca.crt → root_ca.crt # Symlink for compatibility

/opt/bin/
└── step                        # CLI tool
```

### Certificate Lifecycle

| Certificate Type | Lifetime | Renewal Trigger | Auto-Renewal |
|------------------|----------|-----------------|--------------|
| Root CA | 10 years | Manual | No |
| Intermediate CA | 10 years | Manual | No |
| Peer Certificate | 2 years | 487 days (2/3) | Yes (systemd timer) |
| Server Certificate | 2 years | 487 days (2/3) | Yes (systemd timer) |
| Client Certificate | 2 years | 487 days (2/3) | Yes (systemd timer) |

### Service Endpoints

- **step-ca**: `https://<cert-manager-node>:9000`
- **Health check**: `https://<cert-manager-node>:9000/health`

### Systemd Units

**On step-ca node:**
- `step-ca.service` - CA server

**On each etcd node:**
- `step-renew-<etcd-name>-peer.service` - Peer cert renewal
- `step-renew-<etcd-name>-peer.timer` - Peer cert renewal timer
- `step-renew-<etcd-name>-server.service` - Server cert renewal
- `step-renew-<etcd-name>-server.timer` - Server cert renewal timer
- `step-renew-<etcd-name>-client.service` - Client cert renewal
- `step-renew-<etcd-name>-client.timer` - Client cert renewal timer

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Cert-Manager Node (First etcd node)                     │
│                                                          │
│  ┌────────────────────────────────────────────────┐    │
│  │ step-ca (systemd service)                      │    │
│  │ - Listens on port 9000 (HTTPS)                 │    │
│  │ - Issues certificates via REST API             │    │
│  │ - Stores CA keys in /etc/step-ca/secrets/      │    │
│  │ - Certificate database in /etc/step-ca/db/     │    │
│  └────────────────────────────────────────────────┘    │
│                                                          │
│  etcd process also runs here                            │
└─────────────────────────────────────────────────────────┘
                         │
                         │ HTTPS (port 9000)
                         │ Certificate requests
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ etcd node 2  │  │ etcd node 3  │  │ client node  │
│              │  │              │  │              │
│ step CLI     │  │ step CLI     │  │ step CLI     │
│ + timers     │  │ + timers     │  │ + timer      │
│              │  │              │  │              │
│ Requests     │  │ Requests     │  │ Requests     │
│ certs from   │  │ certs from   │  │ certs from   │
│ step-ca      │  │ step-ca      │  │ step-ca      │
└──────────────┘  └──────────────┘  └──────────────┘
```

## Security Properties

### Private Key Security

✅ **Private keys NEVER leave their origin node**
- step-ca generates key pairs locally using `step ca certificate`
- Private key is written directly to node's filesystem
- Only the certificate (public part) comes from step-ca

✅ **CA keys never leave cert-manager node**
- Root and intermediate CA keys in `/etc/step-ca/secrets/`
- File permissions: 0400 (read-only by root)
- Can be backed up encrypted to other nodes for redundancy

✅ **No credentials in Ansible**
- Ansible never sees private keys
- Passwords stored in ansible-vault (encrypted)
- Communication over SSH (encrypted)

### Certificate Issuance Flow

1. Node runs: `step ca certificate <name> <cert-path> <key-path>`
2. step CLI generates key pair locally
3. step CLI sends certificate request to step-ca via HTTPS
4. step-ca validates request and signs certificate
5. step-ca returns signed certificate to node
6. step CLI saves certificate and key locally

**Security**: Only the certificate request and signed certificate traverse the network (both public data).

## Deployment

### Initial Deployment

```bash
# Deploy entire cluster with Smallstep certs
ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=create
```

This will:
1. Install step-ca on cert-manager node
2. Initialize CA with root and intermediate certificates
3. Install step CLI on all nodes
4. Request and install certificates for all nodes
5. Configure automatic renewal
6. Deploy etcd cluster

### Adding a New Node

```bash
# Add node to inventory first
# Then run limited to new node
ansible-playbook -i inventory.ini etcd.yaml --limit=new-node-name
```

The new node will:
1. Install step CLI
2. Bootstrap trust with step-ca
3. Request its certificates
4. Configure automatic renewal
5. Join the etcd cluster

## Operations

### Check Certificate Status

```bash
# On any node, check certificate expiration
step certificate inspect /etc/etcd/ssl/etcd-k8s-1-peer.crt

# Check renewal timer status
systemctl list-timers 'step-renew-*'
```

### Manual Certificate Renewal

```bash
# Force renewal of a specific certificate
systemctl start step-renew-etcd-k8s-1-peer.service

# Check renewal logs
journalctl -u step-renew-etcd-k8s-1-peer.service
```

### Check step-ca Health

```bash
# On cert-manager node
systemctl status step-ca

# Via API
curl -k https://localhost:9000/health
```

### Backup CA Keys

```bash
# On cert-manager node
tar czf step-ca-backup.tar.gz /etc/step-ca/secrets /etc/step-ca/config

# Encrypt
gpg --encrypt --recipient admin@example.com step-ca-backup.tar.gz

# Store securely (e.g., S3)
aws s3 cp step-ca-backup.tar.gz.gpg s3://backups/step-ca/
```

## Configuration

### Change Certificate Lifetime

Edit `roles/etcd3/certs/smallstep/defaults/main.yml`:

```yaml
# Certificate settings
step_cert_default_duration: "17520h"  # 2 years (current default)
step_cert_max_duration: "26280h"      # 3 years
step_cert_min_duration: "1h"
```

Then re-run deployment for new certificates.

### Disable Automatic Renewal

```bash
# On specific node
systemctl disable --now step-renew-etcd-k8s-1-peer.timer
systemctl disable --now step-renew-etcd-k8s-1-server.timer
systemctl disable --now step-renew-etcd-k8s-1-client.timer
```

### Change Renewal Schedule

Edit timer files in `/etc/systemd/system/step-renew-*.timer`:

```ini
[Timer]
# Change from daily at 3 AM to weekly on Sunday at 2 AM
OnCalendar=Sun *-*-* 02:00:00
```

Then reload systemd: `systemctl daemon-reload`

## High Availability (HA) Configuration

### Current Limitation

**Smallstep CA does NOT support active-active clustering** - you cannot run multiple step-ca instances sharing the same database. Each step-ca instance needs its own state.

### Recommended HA Architecture: Active-Passive

```
┌─────────────────────────────────────────────────────────┐
│ Primary Cert-Manager (etcd-k8s-1)                       │
│ - step-ca RUNNING (active)                              │
│ - CA keys in /etc/step-ca/secrets/                      │
│ - Handles all certificate requests                      │
└─────────────────────────────────────────────────────────┘
                         │
                         │ CA keys replicated
                         ▼
┌─────────────────────────────────────────────────────────┐
│ Backup Cert-Manager (etcd-k8s-2)                        │
│ - step-ca INSTALLED but STOPPED (passive)               │
│ - Same CA keys replicated from primary                  │
│ - Ready for manual failover                             │
└─────────────────────────────────────────────────────────┘
```

### Setup HA Configuration

**1. Configure multiple cert-managers in inventory:**

```ini
[etcd]
etcd-k8s-1 ansible_host=10.0.1.10
etcd-k8s-2 ansible_host=10.0.1.11
etcd-k8s-3 ansible_host=10.0.1.12

[etcd-cert-managers]
etcd-k8s-1  # Primary cert-manager
etcd-k8s-2  # Backup cert-manager
```

**2. Deploy with CA key replication:**

```bash
# Deploy step-ca on primary
ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=create

# Replicate CA keys to backup
ansible-playbook -i inventory.ini playbooks/replicate-ca.yaml
```

### Disaster Recovery Procedures

#### Scenario 1: Primary Cert-Manager Node Fails

**Symptoms:**
- step-ca not responding on primary (etcd-k8s-1)
- Certificate requests failing
- Health check fails: `curl -k https://etcd-k8s-1:9000/health`

**Recovery Steps:**

```bash
# 1. Verify primary is down
curl -k https://etcd-k8s-1:9000/health
# Expected: Connection refused or timeout

# 2. Activate step-ca on backup node (etcd-k8s-2)
ssh etcd-k8s-2
systemctl start step-ca
systemctl status step-ca

# 3. Update DNS or load balancer to point to backup
# Update inventory to make etcd-k8s-2 the primary cert-manager

# 4. Verify step-ca is working
curl -k https://etcd-k8s-2:9000/health
# Expected: {"status":"ok"}

# 5. Test certificate issuance
step ca certificate test-cert /tmp/test.crt /tmp/test.key \
  --ca-url https://etcd-k8s-2:9000 \
  --root /etc/etcd/ssl/root_ca.crt
```

**Time to Recovery:** ~5-10 minutes (manual failover)

#### Scenario 2: CA Keys Lost/Corrupted

**Symptoms:**
- step-ca won't start
- CA key files missing or corrupted
- Error: "failed to load CA"

**Recovery Steps:**

```bash
# 1. Stop step-ca service
systemctl stop step-ca

# 2. Restore from backup (if available from another cert-manager)
ansible-playbook -i inventory.ini playbooks/restore-ca.yaml \
  -e source_node=etcd-k8s-2 \
  -e target_node=etcd-k8s-1

# 3. Or restore from encrypted offsite backup
aws s3 cp s3://backups/step-ca/ca-backup.tar.gz.gpg /tmp/
gpg --decrypt /tmp/ca-backup.tar.gz.gpg | tar xzf - -C /

# 4. Verify CA files
ls -la /etc/step-ca/secrets/
# Should show: root_ca_key, intermediate_ca_key, password

# 5. Set correct permissions
chmod 0400 /etc/step-ca/secrets/*_key
chmod 0400 /etc/step-ca/secrets/password
chown -R root:root /etc/step-ca/secrets/

# 6. Restart step-ca
systemctl start step-ca
systemctl status step-ca

# 7. Verify health
curl -k https://localhost:9000/health
```

**Time to Recovery:** ~10-30 minutes (depending on backup location)

#### Scenario 3: Complete Cluster Disaster

**Symptoms:**
- All etcd nodes lost
- All cert-managers destroyed
- Need to rebuild from scratch

**Prerequisites:**
- Encrypted CA backup in S3/offsite storage
- Etcd data backups
- Inventory and configuration in git

**Recovery Steps:**

```bash
# 1. Rebuild infrastructure
# Provision new servers with same IPs/hostnames if possible

# 2. Clone configuration repository
git clone https://github.com/your-org/etcd-ansible.git

# 3. Restore CA keys first (before deploying etcd)
ansible-playbook -i inventory.ini playbooks/restore-ca-from-backup.yaml

# 4. Deploy etcd cluster with existing CA
ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=create

# 5. Restore etcd data if needed
ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=restore
```

**Time to Recovery:** ~1-2 hours (full rebuild)

### Backup and Recovery

#### Automated Backup Strategy

**Daily Backup to S3:**

```yaml
# playbooks/backup-ca-daily.yaml
- hosts: etcd-cert-managers[0]  # Primary only
  tasks:
    - name: Create CA backup
      archive:
        path:
          - /etc/step-ca/secrets
          - /etc/step-ca/config
        dest: /tmp/step-ca-backup-{{ ansible_date_time.date }}.tar.gz

    - name: Encrypt backup
      command: |
        gpg --encrypt --recipient admin@example.com \
        /tmp/step-ca-backup-{{ ansible_date_time.date }}.tar.gz

    - name: Upload to S3
      aws_s3:
        bucket: etcd-backups
        object: "step-ca/{{ ansible_date_time.year }}/{{ ansible_date_time.month }}/ca-backup-{{ ansible_date_time.date }}.tar.gz.gpg"
        src: "/tmp/step-ca-backup-{{ ansible_date_time.date }}.tar.gz.gpg"
        encrypt: yes

    - name: Cleanup local backup
      file:
        path: "{{ item }}"
        state: absent
      loop:
        - "/tmp/step-ca-backup-{{ ansible_date_time.date }}.tar.gz"
        - "/tmp/step-ca-backup-{{ ansible_date_time.date }}.tar.gz.gpg"
```

**Add to cron:**
```bash
# Run daily at 2 AM
0 2 * * * cd /path/to/etcd-ansible && ansible-playbook -i inventory.ini playbooks/backup-ca-daily.yaml
```

#### Manual Backup

```bash
# On any cert-manager node
tar czf step-ca-backup.tar.gz /etc/step-ca/secrets /etc/step-ca/config

# Encrypt backup
gpg --encrypt --recipient admin@example.com step-ca-backup.tar.gz

# Store securely (e.g., S3)
aws s3 cp step-ca-backup.tar.gz.gpg s3://backups/step-ca/
```

#### Restore CA Keys

```bash
# Download backup
aws s3 cp s3://backups/step-ca/step-ca-backup.tar.gz.gpg .

# Decrypt
gpg --decrypt step-ca-backup.tar.gz.gpg > step-ca-backup.tar.gz

# Extract
tar xzf step-ca-backup.tar.gz -C /

# Fix permissions
chmod 0400 /etc/step-ca/secrets/*
chown -R root:root /etc/step-ca/

# Restart step-ca
systemctl restart step-ca
```

### Health Monitoring

#### Automated Health Checks

```bash
# Add to monitoring system (Prometheus, Nagios, etc.)

# Check step-ca health endpoint
*/5 * * * * curl -sf https://etcd-k8s-1:9000/health || echo "step-ca down" | mail -s "ALERT: step-ca down" admin@example.com

# Check CA certificate expiration
0 0 * * * step certificate inspect /etc/step-ca/certs/root_ca.crt --format json | jq -r '.validity.end' | xargs -I {} echo "CA expires: {}"
```

#### Manual Health Check

```bash
# Check step-ca status
systemctl status step-ca

# Check health endpoint
curl -k https://localhost:9000/health

# Check CA cert expiration
step certificate inspect /etc/step-ca/certs/root_ca.crt

# Check database
ls -lh /etc/step-ca/db/

# Check recent certificate issuances
journalctl -u step-ca -n 100 | grep "Signing certificate"
```

### Limitations and Trade-offs

**Current Implementation:**
- ✅ Single step-ca instance (simple, no split-brain risk)
- ✅ Manual failover (controlled, tested procedure)
- ✅ CA keys replicated to backup nodes
- ❌ No automatic failover (~5-10 min downtime during DR)
- ❌ Cannot issue certificates during failover
- ⚠️ Certificate renewal will retry automatically (built into systemd timers)

**Why Not Active-Active?**
- Smallstep CA database is not designed for concurrent writes
- Risk of certificate serial number conflicts
- Complex state synchronization required
- Our use case (etcd certificates, 2-year lifetime) doesn't require active-active

**Why Not Load Balancer?**
- Can't round-robin to multiple step-ca instances (database conflicts)
- Load balancer would only provide DNS failover (same as manual)
- Adds complexity without significant benefit for our use case

### Recovery Time Objectives (RTO)

| Scenario | RTO | RPO | Notes |
|----------|-----|-----|-------|
| Primary node failure | 5-10 min | 0 | Manual failover to backup |
| CA key corruption | 10-30 min | Last backup | Restore from backup node or S3 |
| Complete disaster | 1-2 hours | Last etcd backup | Full rebuild required |
| CA certificate expiration | Planned | N/A | 10-year CA cert lifetime |

### Best Practices

1. **Always maintain 2+ cert-managers** with replicated CA keys
2. **Test failover procedure quarterly** to ensure it works
3. **Backup CA keys daily** to encrypted offsite storage
4. **Monitor CA certificate expiration** (10-year default is safe)
5. **Document your specific DR procedures** based on your environment
6. **Keep inventory and configs in version control**
7. **Test restore procedure** at least annually

## Troubleshooting

### Certificate Request Fails

**Symptom**: `step ca certificate` command fails

**Check**:
1. Is step-ca running? `systemctl status step-ca`
2. Can node reach step-ca? `curl -k https://<cert-manager>:9000/health`
3. Are provisioner credentials correct?
4. Check step-ca logs: `journalctl -u step-ca -n 100`

### Certificate Renewal Fails

**Symptom**: Timer runs but certificate not renewed

**Check**:
1. Check renewal service logs: `journalctl -u step-renew-<name>.service`
2. Verify certificate is eligible for renewal (< 1/3 lifetime remaining)
3. Check step-ca is reachable
4. Verify provisioner credentials

### etcd Won't Start After Certificate Update

**Symptom**: etcd fails to start after certificate renewal

**Check**:
1. Verify certificate file permissions (0644 for .crt, 0400 for .key)
2. Verify certificate ownership (should be `etcd` user)
3. Verify certificate validity: `step certificate verify /etc/etcd/ssl/etcd-k8s-1-peer.crt --roots /etc/etcd/ssl/root_ca.crt`
4. Check etcd logs: `journalctl -u etcd-<cluster-name>-<index>`

## Migration

### From Old cfssl Setup

If you have an existing cluster with cfssl-based certificates:

1. **Backup everything**:
   ```bash
   ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=backup
   ```

2. **Deploy step-ca on cert-manager** (doesn't affect running cluster):
   ```bash
   ansible-playbook -i inventory.ini etcd.yaml --tags=step-ca --limit=<cert-manager-node>
   ```

3. **Migrate one node at a time**:
   ```bash
   # For each non-cert-manager node
   ansible-playbook -i inventory.ini etcd.yaml --limit=etcd-k8s-2
   # Wait for node to rejoin cluster with new certs
   # Verify cluster health
   # Continue with next node
   ```

4. **Migrate cert-manager last**:
   ```bash
   ansible-playbook -i inventory.ini etcd.yaml --limit=<cert-manager-node>
   ```

5. **Clean up old certificates**:
   ```bash
   # On each node, after verifying new certs work
   rm -f /etc/etcd/ssl/*.pem
   ```

## References

- [Smallstep Documentation](https://smallstep.com/docs/)
- [step-ca Production Guide](https://smallstep.com/docs/step-ca/certificate-authority-server-production)
- [Role README](roles/etcd3/certs/smallstep/README.md)
- [Workflow Documentation](csr_workflow_clarification.md)
