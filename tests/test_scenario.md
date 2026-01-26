# Etcd-Ansible Test Scenarios

Comprehensive test scenarios covering all features and code paths of etcd-ansible.

**Testing Status Legend:**
- ⬜ Not tested
- ✅ Passed
- ❌ Failed
- 🔄 In Progress
- ⏭️ Skipped (not applicable)

---

## Table of Contents

1. [Prerequisites & Setup](#1-prerequisites--setup)
2. [Happy Path - Standard Operations](#2-happy-path---standard-operations)
3. [Certificate Management](#3-certificate-management)
4. [Backup & Restore](#4-backup--restore)
5. [Disaster Recovery](#5-disaster-recovery)
6. [Advanced Features](#6-advanced-features)
7. [Multi-Cluster Operations](#7-multi-cluster-operations)
8. [Service Control & Maintenance](#8-service-control--maintenance)
9. [Edge Cases & Error Handling](#9-edge-cases--error-handling)
10. [Performance & Scale](#10-performance--scale)
11. [Security Testing](#11-security-testing)

---

## 1. Prerequisites & Setup

### 1.1 AWS KMS Setup

⬜ **Test:** Setup AWS KMS key for CA backups

**Description:** Create KMS key using automated playbook

**Inventory:** N/A (runs on localhost)

**Command:**
```bash
ansible-playbook playbooks/setup-kms.yaml -e kms_key_alias=alias/etcd-ca-backup-test
```

**Expected Result:**
- KMS key created with alias `alias/etcd-ca-backup-test`
- Key policy configured
- Success message with key ID displayed

**Cleanup:**
```bash
aws kms delete-alias --alias-name alias/etcd-ca-backup-test
# Note: Schedule key deletion separately
```

---

### 1.2 Inventory Setup

⬜ **Test:** Create basic 3-node inventory

**Description:** Verify inventory configuration works correctly

**Inventory:** Create `inventory/test/inventory.ini`
```ini
[etcd]
etcd-test-1 ansible_host=10.0.1.10
etcd-test-2 ansible_host=10.0.1.11
etcd-test-3 ansible_host=10.0.1.12

[etcd-clients]
# Empty initially

[etcd-cert-managers]
etcd-test-1
```

**Command:**
```bash
ansible-inventory -i inventory/test/inventory.ini --list
```

**Expected Result:**
- All groups populated correctly
- No syntax errors

---

### 1.3 Vault Configuration

⬜ **Test:** Create and encrypt vault file

**Description:** Configure secrets with ansible-vault

**Files:** Create `inventory/group_vars/all/vault-test.yml`
```yaml
step_ca_password: "test-ca-password-$(openssl rand -base64 32)"
step_provisioner_password: "test-prov-password-$(openssl rand -base64 32)"
step_ca_backup_s3_bucket: "my-test-etcd-backups"
step_ca_backup_kms_key_id: "alias/etcd-ca-backup-test"
etcd_upload_backup:
  storage: s3
  bucket: "my-test-etcd-backups"
  prefix: "etcd/"
aws_access_key_id: "AKIAIOSFODNN7EXAMPLE"
aws_secret_access_key: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
```

**Command:**
```bash
ansible-vault encrypt inventory/group_vars/all/vault-test.yml
echo "test-vault-pass" > .vault-pass-test
chmod 600 .vault-pass-test
ansible-vault view inventory/group_vars/all/vault-test.yml --vault-password-file .vault-pass-test
```

**Expected Result:**
- File encrypted successfully
- Can decrypt and view contents

---

## 2. Happy Path - Standard Operations

### 2.1 Initial Cluster Deployment

⬜ **Test:** Deploy fresh 3-node cluster with AWS KMS encryption

**Description:** Complete cluster deployment from scratch with all default settings

**Inventory:** `inventory/test/inventory.ini` (from 1.2)

**Variables:** `inventory/group_vars/all/test-deploy.yaml`
```yaml
etcd_cluster_name: test-cluster
etcd_version: v3.5.26
etcd_backup_cron_enabled: true
ca_backup_cron_enabled: true
step_ca_backup_encryption_method: aws-kms
```

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create \
  --vault-password-file .vault-pass-test \
  -b
```

**Expected Result:**
- step-ca installed and running on etcd-test-1
- etcd cluster healthy (3 nodes)
- Certificates generated (2-year lifetime)
- Systemd renewal timers active
- Initial backups created
- Services: `etcd-test-cluster-1`, `etcd-test-cluster-2`, `etcd-test-cluster-3`

**Verification:**
```bash
# Check cluster health
make health INVENTORY=inventory/test/inventory.ini

# Check services
ansible etcd -i inventory/test/inventory.ini -m shell -a "systemctl status etcd-*" -b

# Check certificates
ansible etcd -i inventory/test/inventory.ini -m shell -a "step certificate inspect /etc/etcd/ssl/etcd-test-cluster-peer.crt | grep 'Not After'" -b

# Check cron jobs
ansible-playbook -i inventory/test/inventory.ini playbooks/verify-backup-cron.yaml
```

---

### 2.2 Health Check

[x] **Test:** Run comprehensive health check (text output)

**Description:** Verify all health check components work

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-health.yaml
```

**Expected Result:**
- Endpoint health: All healthy
- Member list: 3 members
- Database metrics displayed
- Certificate expiration shown
- step-ca health verified

---

[x] **Test:** Run health check (JSON output)

**Description:** Verify JSON output for monitoring integration

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-health.yaml -e output_format=json
```

**Expected Result:**
- Valid JSON output
- Contains: cluster_name, healthy, endpoint_health, database_size_mb

---

### 2.3 Manual Backup

[x] **Test:** Create manual etcd data backup

**Description:** Test manual backup creation and upload to S3

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=backup \
  --vault-password-file .vault-pass-test \
  -b
```

**Expected Result:**
- Snapshot created locally
- Encrypted with AWS KMS
- Uploaded to S3: `s3://bucket/etcd/test-cluster/YYYY/MM/test-cluster-*-snapshot.db.kms`
- SHA256 checksum file uploaded: `*.sha256`
- Latest pointer updated

**Verification:**
```bash
aws s3 ls s3://my-test-etcd-backups/etcd/test-cluster/ --recursive
```

---

[x] **Test:** Create manual CA backup

**Description:** Test CA backup with KMS encryption

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/backup-ca.yaml \
  --vault-password-file .vault-pass-test
```

**Expected Result:**
- CA archive created
- Encrypted with AWS KMS
- Uploaded to S3: `s3://bucket/step-ca/YYYY/MM/ca-backup-*.tar.gz.kms`
- Latest pointer updated

---

### 2.4 Upgrade Cluster

⬜ **Test:** Safe rolling upgrade to newer version

**Description:** Upgrade etcd version with automated safety checks

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/upgrade-cluster.yaml \
  -e etcd_version=v3.5.26 \
  --vault-password-file .vault-pass-test \
  -b
```

**Expected Result:**
- Pre-upgrade validation passes
- Backup created automatically
- Nodes upgraded one at a time (serial: 1)
- Health check after each node
- All nodes running new version

**Verification:**
```bash
ansible etcd -i inventory/test/inventory.ini -m shell -a "etcd --version | head -1" -b
```

---

### 2.5 Status Operations

⬜ **Test:** View cluster status

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-status.yaml -b
```

**Expected Result:**
- Table with endpoints, DB size, leader info

---

⬜ **Test:** List cluster members

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-members.yaml -b
```

**Expected Result:**
- Table showing 3 members with IDs and URLs

---

⬜ **Test:** View logs

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-logs.yaml -b
```

**Expected Result:**
- Last 50 lines of etcd logs displayed

---

### 2.6 Database Maintenance

⬜ **Test:** Compact database

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-compact.yaml -b
```

**Expected Result:**
- Database compacted to current revision
- Success message displayed

---

⬜ **Test:** Defragment database

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-defrag.yaml -b
```

**Expected Result:**
- Database defragmented
- Space reclaimed

---

## 3. Certificate Management

### 3.1 Certificate Renewal

⬜ **Test:** Manual certificate renewal (all nodes)

**Description:** Force immediate renewal of certificates

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/renew-certs.yaml -b
```

**Expected Result:**
- All renewal services triggered
- Certificates renewed (same CA)
- etcd services reloaded

**Verification:**
```bash
ansible etcd -i inventory/test/inventory.ini -m shell -a "step certificate inspect /etc/etcd/ssl/etcd-test-cluster-peer.crt | grep 'Not Before'" -b
```

---

### 3.2 Node Certificate Regeneration (Routine)

⬜ **Test:** Regenerate node certificates quarterly

**Description:** Routine certificate rotation keeping same CA

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/regenerate-node-certs.yaml -b \
  --vault-password-file .vault-pass-test
```

**Expected Result:**
- Confirmation prompt appears
- Cluster backed up
- Old node certs removed
- New certs generated from existing CA
- Rolling restart (serial: 1)
- Zero downtime
- CA unchanged

**Verification:**
```bash
# Check CA fingerprint unchanged
ansible etcd-cert-managers -i inventory/test/inventory.ini -m shell \
  -a "step certificate fingerprint /etc/step-ca/certs/root_ca.crt" -b

# Check new cert dates
ansible etcd -i inventory/test/inventory.ini -m shell \
  -a "step certificate inspect /etc/etcd/ssl/etcd-test-cluster-peer.crt | grep 'Not Before'" -b
```

---

### 3.3 CA Regeneration (Disaster Recovery)

⬜ **Test:** Complete CA regeneration with new passwords

**Description:** Full CA rebuild for disaster recovery

**Prerequisites:**
- Update `vault-test.yml` with NEW passwords
- Encrypt with ansible-vault

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/regenerate-ca.yaml -b \
  --vault-password-file .vault-pass-test
```

**Expected Result:**
- Confirmation prompt with disaster recovery warning
- Cluster backed up
- step-ca stopped
- Old CA completely deleted
- New CA initialized with new passwords
- New certificates issued
- CA replicated to backups (if configured)
- Rolling restart
- New CA fingerprint (different from before)

**Verification:**
```bash
# Verify new CA fingerprint (should be DIFFERENT)
ansible etcd-cert-managers -i inventory/test/inventory.ini -m shell \
  -a "step certificate fingerprint /etc/step-ca/certs/root_ca.crt" -b

# All certs should be brand new
ansible etcd -i inventory/test/inventory.ini -m shell \
  -a "step certificate inspect /etc/etcd/ssl/etcd-test-cluster-peer.crt" -b
```

---

### 3.4 Certificate Rotation

⬜ **Test:** Force certificate rotation (immediate)

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/rotate-certs.yaml -b
```

**Expected Result:**
- Confirmation prompt
- All renewal services started
- Certificates rotated

---

### 3.5 Certificate Expiration Check

⬜ **Test:** Check certificate expiration dates

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-health.yaml --tags certs
```

**Expected Result:**
- Shows expiration dates for all certs
- Days remaining displayed
- Warning if < 90 days
- Timer status shown

---

## 4. Backup & Restore

### 4.1 Automated Backups

⬜ **Test:** Verify automated backup cron jobs installed

**Description:** Check that cron jobs are configured correctly

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/verify-backup-cron.yaml
```

**Expected Result:**
- etcd backup cron: INSTALLED (every 30 minutes)
- CA backup cron: INSTALLED (checks every 5 minutes)
- Next run times displayed
- Log files exist

---

⬜ **Test:** Distributed backup coordination

**Description:** Verify only one node creates backup (deduplication)

**Inventory:** `inventory/test/inventory.ini` (3 nodes)

**Variables:**
```yaml
etcd_backup_distributed: true
etcd_backup_independent: false
etcd_backup_interval: "*/5"  # Every 5 minutes for testing
```

**Command:**
```bash
# Trigger backups on all nodes simultaneously
ansible etcd -i inventory/test/inventory.ini -m shell \
  -a "python3 /opt/backups/etcd-backup.py --config /opt/backups/etcd-backup-config.yaml" \
  -b
```

**Expected Result:**
- Only ONE backup created
- First node succeeds
- Other nodes skip (recent backup exists)
- Logs show "Recent backup found"

**Verification:**
```bash
# Check S3 - should see only 1 backup
aws s3 ls s3://my-test-etcd-backups/etcd/test-cluster/ --recursive | grep "$(date +%Y-%m-%d)"
```

---

⬜ **Test:** Independent backup mode (no deduplication)

**Description:** All nodes create backups independently

**Variables:**
```yaml
etcd_backup_distributed: true
etcd_backup_independent: true
etcd_backup_interval: "*/60"  # Every hour
```

**Command:**
```bash
# Redeploy with independent mode
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=deploy \
  -e etcd_backup_independent=true \
  --tags backup-cron \
  -b

# Trigger backups
ansible etcd -i inventory/test/inventory.ini -m shell \
  -a "python3 /opt/backups/etcd-backup.py --config /opt/backups/etcd-backup-config.yaml --independent" \
  -b
```

**Expected Result:**
- 3 backups created (one per node)
- No deduplication
- All nodes report success

---

### 4.2 Encryption Methods

⬜ **Test:** AWS KMS encryption (default)

**Description:** Test KMS envelope encryption

**Variables:**
```yaml
step_ca_backup_encryption_method: aws-kms
step_ca_backup_kms_key_id: alias/etcd-ca-backup-test
```

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=backup \
  --vault-password-file .vault-pass-test \
  -b
```

**Expected Result:**
- Backup encrypted with KMS envelope encryption
- File extension: `.db.kms`
- Encryption validated (test decrypt)
- Uploaded to S3

**Verification:**
```bash
# Download and decrypt manually
aws s3 cp s3://bucket/etcd/test-cluster/latest-snapshot.db.kms /tmp/test.db.kms

# Decrypt using Python script
ansible etcd[0] -i inventory/test/inventory.ini -m shell -b -a \
  "python3 /opt/backups/etcd-backup.py --config /opt/backups/etcd-backup-config.yaml \
   --decrypt --input /tmp/test.db.kms --output /tmp/test.db --encryption aws-kms"

# Verify snapshot
ansible etcd[0] -i inventory/test/inventory.ini -m shell -b -a \
  "etcdutl snapshot status /tmp/test.db"
```

---

⬜ **Test:** Symmetric encryption

**Description:** Test OpenSSL AES-256-CBC encryption

**Variables:**
```yaml
step_ca_backup_encryption_method: symmetric
step_ca_backup_password: "test-symmetric-password-123"
```

**Command:**
```bash
# Update vault.yml
ansible-vault edit inventory/group_vars/all/vault-test.yml --vault-password-file .vault-pass-test
# Add: step_ca_backup_encryption_method: symmetric

# Redeploy cron
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=deploy \
  --tags backup-cron \
  --vault-password-file .vault-pass-test \
  -b

# Create backup
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=backup \
  --vault-password-file .vault-pass-test \
  -b
```

**Expected Result:**
- Backup encrypted with OpenSSL
- File extension: `.db.enc`
- Encryption validated
- Uploaded to S3

---

⬜ **Test:** No encryption (not recommended)

**Description:** Test unencrypted backup (for air-gapped environments)

**Variables:**
```yaml
step_ca_backup_encryption_method: none
deactivate_backup_encryption: true
```

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=backup \
  -e step_ca_backup_encryption_method=none \
  -b
```

**Expected Result:**
- Backup NOT encrypted
- File extension: `.db`
- Warning message shown
- Uploaded to S3

---

### 4.3 Restore Operations

⬜ **Test:** Restore cluster from latest S3 backup

**Description:** Full cluster restore from encrypted backup

**Prerequisites:**
- At least one backup exists in S3
- Cluster running

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/restore-etcd-cluster.yaml \
  --vault-password-file .vault-pass-test
```

**Expected Result:**
- Confirmation prompt appears
- Backups downloaded and decrypted on all nodes (parallel)
- All etcd services stopped
- Data restored on all nodes
- All services started together
- Cluster healthy
- Revision bumped by 1 billion

**Verification:**
```bash
# Check cluster health
make health INVENTORY=inventory/test/inventory.ini

# Verify revision was bumped
ansible etcd[0] -i inventory/test/inventory.ini -m shell -b -a \
  "etcdctl endpoint status -w json | jq '.[0].Status.header.revision'"
```

---

⬜ **Test:** Restore from specific backup file

**Description:** Restore from specific S3 backup instead of latest

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/restore-etcd-cluster.yaml \
  -e restore_etcd_s3_file="etcd/test-cluster/2026/01/test-cluster-2026-01-20_14-30-00-snapshot.db.kms" \
  --vault-password-file .vault-pass-test
```

**Expected Result:**
- Restores from specified file
- Same process as latest restore

---

⬜ **Test:** Restore from local file

**Description:** Restore from local snapshot file

**Prerequisites:**
- Copy snapshot to all nodes: `/tmp/local-snapshot.db`

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/restore-etcd-cluster.yaml \
  -e restore_etcd_local_file="/tmp/local-snapshot.db" \
  -e restore_confirm=false
```

**Expected Result:**
- Restores from local file (no S3 download)
- Cluster restored successfully

---

⬜ **Test:** Restore CA from S3 backup

**Description:** Restore step-ca CA keys from encrypted backup

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/restore-ca-from-backup.yaml \
  -e target_node=etcd-test-1 \
  --vault-password-file .vault-pass-test
```

**Expected Result:**
- Backup downloaded from S3
- Decrypted with KMS
- CA files restored
- step-ca restarted
- Health endpoint responds

---

⬜ **Test:** Restore CA from another node

**Description:** Copy CA keys from backup cert-manager

**Prerequisites:**
- Multiple cert-managers in inventory

**Command:**
```bash
ansible-playbook -i inventory/test-ha.ini playbooks/restore-ca.yaml \
  -e source_node=etcd-test-2 \
  -e target_node=etcd-test-1
```

**Expected Result:**
- CA keys copied from source to target
- step-ca restarted on target
- Fingerprints match

---

### 4.4 Checksum Verification

⬜ **Test:** Decrypt with checksum verification

**Description:** Test checksum validation during decrypt

**Command:**
```bash
ansible etcd[0] -i inventory/test/inventory.ini -m shell -b -a \
  "python3 /opt/backups/etcd-backup.py --config /opt/backups/etcd-backup-config.yaml \
   --decrypt \
   --input /path/to/backup.db.kms \
   --output /tmp/restored.db \
   --encryption aws-kms"
```

**Expected Result:**
- Checksum file auto-detected (`.sha256`)
- Decryption successful
- Checksum verification PASSED

---

⬜ **Test:** Decrypt without verification

**Description:** Skip checksum check (faster but less safe)

**Command:**
```bash
ansible etcd[0] -i inventory/test/inventory.ini -m shell -b -a \
  "python3 /opt/backups/etcd-backup.py \
   --decrypt \
   --input /path/to/backup.db.kms \
   --output /tmp/restored.db \
   --no-verify"
```

**Expected Result:**
- Decryption successful
- Warning: "Checksum verification requested but no checksum available"
- No checksum validation

---

⬜ **Test:** Checksum mismatch detection

**Description:** Verify that corrupted backups are detected

**Setup:**
```bash
# Corrupt a backup file
aws s3 cp s3://bucket/etcd/test-cluster/latest-snapshot.db.kms /tmp/backup.kms
# Modify the file
echo "corrupted" >> /tmp/backup.kms
```

**Command:**
```bash
ansible etcd[0] -i inventory/test/inventory.ini -m shell -b -a \
  "python3 /opt/backups/etcd-backup.py \
   --decrypt \
   --input /tmp/backup.kms \
   --output /tmp/restored.db"
```

**Expected Result:**
- Decryption fails OR checksum verification fails
- Error message: "Checksum verification FAILED"

---

## 5. Disaster Recovery

### 5.1 Single Node Failure

⬜ **Test:** Node failure and recovery (etcd keeps running)

**Description:** Simulate node failure, cluster continues with quorum

**Setup:**
```bash
# Stop one node
ansible etcd[1] -i inventory/test/inventory.ini -m shell -a "systemctl stop etcd-*" -b
```

**Verification:**
```bash
# Cluster should still be healthy (2/3 quorum)
make health INVENTORY=inventory/test/inventory.ini
```

**Recovery:**
```bash
# Start node
ansible etcd[1] -i inventory/test/inventory.ini -m shell -a "systemctl start etcd-*" -b
```

**Expected Result:**
- Cluster continues with 2 nodes
- Node rejoins cluster when started
- Full health restored

---

### 5.2 Primary Cert-Manager Failure

⬜ **Test:** Cert-manager failover to backup

**Description:** Primary cert-manager fails, activate backup

**Prerequisites:**
- HA inventory with multiple cert-managers

**Inventory:** `inventory/test-ha.ini`
```ini
[etcd]
etcd-test-1 ansible_host=10.0.1.10
etcd-test-2 ansible_host=10.0.1.11
etcd-test-3 ansible_host=10.0.1.12

[etcd-cert-managers]
etcd-test-1  # Primary
etcd-test-2  # Backup
```

**Setup:**
```bash
# Stop primary cert-manager
ssh etcd-test-1 "systemctl stop step-ca"
```

**Recovery Command:**
```bash
# Activate backup
ssh etcd-test-2 "systemctl start step-ca"

# Verify
curl -k https://etcd-test-2:9000/health
```

**Expected Result:**
- step-ca starts on backup
- Health endpoint responds
- Certificates can be issued

---

### 5.3 Complete Data Loss

⬜ **Test:** Full cluster disaster recovery

**Description:** Restore cluster from complete data loss

**Setup:**
```bash
# Delete all data (simulate disaster)
ansible etcd -i inventory/test/inventory.ini -m shell \
  -a "systemctl stop etcd-*" -b

ansible etcd -i inventory/test/inventory.ini -m shell \
  -a "rm -rf /var/lib/etcd/etcd-*" -b
```

**Recovery Command:**
```bash
# Restore from backup
ansible-playbook -i inventory/test/inventory.ini playbooks/restore-etcd-cluster.yaml \
  --vault-password-file .vault-pass-test
```

**Expected Result:**
- Data restored on all nodes
- Cluster recovers
- All data intact

---

### 5.4 CA Key Loss

⬜ **Test:** Recover CA from S3 backup

**Description:** Restore CA when keys are lost/corrupted

**Setup:**
```bash
# Delete CA keys (simulate loss)
ssh etcd-test-1 "systemctl stop step-ca && rm -rf /etc/step-ca/secrets/*"
```

**Recovery Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/restore-ca-from-backup.yaml \
  -e target_node=etcd-test-1 \
  --vault-password-file .vault-pass-test
```

**Expected Result:**
- CA keys restored
- step-ca restarts
- Certificates can be issued

---

### 5.5 Quorum Loss (All Nodes Down)

⬜ **Test:** Recover from complete cluster shutdown

**Description:** Verify cluster recovers when all nodes stopped

**Setup:**
```bash
ansible etcd -i inventory/test/inventory.ini -m shell -a "systemctl stop etcd-*" -b
```

**Recovery:**
```bash
ansible etcd -i inventory/test/inventory.ini -m shell -a "systemctl start etcd-*" -b
```

**Expected Result:**
- All nodes start
- Cluster forms quorum
- Healthy state restored

---

## 6. Advanced Features

### 6.1 High Availability Setup

⬜ **Test:** Deploy with multiple cert-managers

**Description:** Verify CA replication to backup nodes

**Inventory:** `inventory/test-ha.ini`
```ini
[etcd]
etcd-ha-1 ansible_host=10.0.1.20
etcd-ha-2 ansible_host=10.0.1.21
etcd-ha-3 ansible_host=10.0.1.22

[etcd-cert-managers]
etcd-ha-1  # Primary - step-ca running
etcd-ha-2  # Backup - CA keys replicated
```

**Command:**
```bash
ansible-playbook -i inventory/test-ha.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create \
  --vault-password-file .vault-pass-test \
  -b
```

**Expected Result:**
- step-ca running on etcd-ha-1
- CA backed up to S3 (encrypted)
- CA restored on etcd-ha-2 from S3
- step-ca stopped on etcd-ha-2
- CA fingerprints match
- Success message shows replication complete

**Verification:**
```bash
# Check fingerprints match
ansible etcd-cert-managers -i inventory/test-ha.ini -m shell \
  -a "step certificate fingerprint /etc/step-ca/certs/root_ca.crt" -b

# Verify step-ca status
ansible etcd-cert-managers -i inventory/test-ha.ini -m shell \
  -a "systemctl is-active step-ca" -b
# Should be: active (etcd-ha-1), inactive (etcd-ha-2)
```

---

⬜ **Test:** Manual CA replication

**Description:** Replicate CA to backup cert-manager manually

**Prerequisites:**
- HA cluster deployed (from 6.1)

**Command:**
```bash
ansible-playbook -i inventory/test-ha.ini playbooks/replicate-ca.yaml \
  --vault-password-file .vault-pass-test
```

**Expected Result:**
- Backup created on primary
- Restored on backups via S3
- Fingerprints verified
- step-ca stopped on backups

---

### 6.2 Adding Nodes

⬜ **Test:** Add new node to existing cluster

**Description:** Scale cluster from 3 to 4 nodes

**Inventory:** Update `inventory/test/inventory.ini`
```ini
[etcd]
etcd-test-1 ansible_host=10.0.1.10
etcd-test-2 ansible_host=10.0.1.11
etcd-test-3 ansible_host=10.0.1.12
etcd-test-4 ansible_host=10.0.1.13  # NEW
```

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create \
  --limit=etcd-test-4 \
  --vault-password-file .vault-pass-test \
  -b
```

**Expected Result:**
- New node gets certificates from step-ca
- Joins cluster
- 4 members in cluster

**Verification:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-members.yaml -b
```

---

### 6.3 Client Certificates

⬜ **Test:** Deploy client certificates to non-etcd nodes

**Description:** Configure etcd clients with certificates

**Inventory:** Update `inventory/test/inventory.ini`
```ini
[etcd-clients]
app-server-1 ansible_host=10.0.2.10
app-server-2 ansible_host=10.0.2.11
```

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=deploy \
  --vault-password-file .vault-pass-test \
  -b
```

**Expected Result:**
- Client certificates generated on app-server-1 and app-server-2
- Renewal timers configured
- Can connect to etcd

**Verification:**
```bash
ansible etcd-clients -i inventory/test/inventory.ini -m shell -b -a \
  "etcdctl --endpoints=https://10.0.1.10:2379 \
   --cert=/etc/etcd/ssl/etcd-test-cluster-client.crt \
   --key=/etc/etcd/ssl/etcd-test-cluster-client.key \
   --cacert=/etc/etcd/ssl/root_ca.crt \
   endpoint health"
```

---

### 6.4 Custom Configuration

⬜ **Test:** Custom etcd configuration

**Description:** Deploy with non-default settings

**Variables:** `inventory/group_vars/all/custom-config.yaml`
```yaml
etcd_cluster_name: custom-cluster
etcd_version: v3.5.26
etcd_heartbeat_interval: 500  # Changed from 250
etcd_election_timeout: 10000  # Changed from 5000
etcd_snapshot_count: 5000  # Changed from 10000
etcd_quota_backend_bytes: "4G"
etcd_compaction_retention: "4"

# Custom ports
etcd_ports:
  client: 12379
  peer: 12380

# Custom paths
etcd_home: /opt/etcd-data
etcd_config_dir: /opt/etcd/config
```

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create \
  -e @inventory/group_vars/all/custom-config.yaml \
  -b
```

**Expected Result:**
- Cluster uses custom ports (12379/12380)
- Custom heartbeat/election timeouts
- Data in `/opt/etcd-data`

---

### 6.5 Performance Tuning

⬜ **Test:** Deploy with systemd performance tuning

**Description:** Test systemd resource limits and scheduling

**Variables:**
```yaml
etcd_systemd_nice_level: -10  # Higher priority
etcd_systemd_ionice_class: 1  # Realtime I/O
etcd_systemd_ionice_priority: 0  # Highest
etcd_systemd_memory_limit: "4G"
etcd_systemd_cpu_quota: "200%"  # 2 cores
```

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=deploy \
  -e etcd_systemd_nice_level=-10 \
  -e etcd_systemd_memory_limit=4G \
  -b
```

**Expected Result:**
- Systemd service has custom limits
- Process has higher priority

**Verification:**
```bash
ansible etcd -i inventory/test/inventory.ini -m shell -b -a \
  "systemctl show etcd-* | grep -E 'Nice|IOScheduling|MemoryLimit|CPUQuota'"
```

---

## 7. Multi-Cluster Operations

### 7.1 Multiple Independent Clusters

⬜ **Test:** Deploy two clusters on same nodes

**Description:** Run k8s and k8s-events clusters independently

**Inventory:** `inventory/test-multi.ini`
```ini
[etcd-k8s]
etcd-m1 ansible_host=10.0.1.30
etcd-m2 ansible_host=10.0.1.31
etcd-m3 ansible_host=10.0.1.32

[etcd-k8s-events]
etcd-m1 ansible_host=10.0.1.30
etcd-m2 ansible_host=10.0.1.31
etcd-m3 ansible_host=10.0.1.32

[etcd-k8s-cert-managers]
etcd-m1

[etcd-k8s-events-cert-managers]
etcd-m1

[etcd:children]
etcd-k8s
etcd-k8s-events
```

**Variables:** Create two group_vars directories
```yaml
# group_vars/etcd-k8s/etcd.yaml
etcd_cluster_name: k8s
etcd_ports:
  client: 2379
  peer: 2380

# group_vars/etcd-k8s-events/etcd.yaml
etcd_cluster_name: k8s-events
etcd_ports:
  client: 2381
  peer: 2382
```

**Command:**
```bash
ansible-playbook -i inventory/test-multi.ini playbooks/multi-cluster-example.yaml \
  -e etcd_action=create \
  --vault-password-file .vault-pass-test \
  -b
```

**Expected Result:**
- Two clusters running on same nodes
- Different ports (2379/2380 vs 2381/2382)
- Independent certificates
- Independent backups
- Services: `etcd-k8s-1`, `etcd-k8s-events-1`, etc.

**Verification:**
```bash
# Check both clusters
ansible etcd-k8s[0] -i inventory/test-multi.ini -m shell -b -a \
  "etcdctl --endpoints=https://10.0.1.30:2379 \
   --cert=/etc/etcd/ssl/etcd-k8s-client.crt \
   --key=/etc/etcd/ssl/etcd-k8s-client.key \
   --cacert=/etc/etcd/ssl/root_ca.crt \
   endpoint health"

ansible etcd-k8s-events[0] -i inventory/test-multi.ini -m shell -b -a \
  "etcdctl --endpoints=https://10.0.1.30:2381 \
   --cert=/etc/etcd/ssl/etcd-k8s-events-client.crt \
   --key=/etc/etcd/ssl/etcd-k8s-events-client.key \
   --cacert=/etc/etcd/ssl/root_ca.crt \
   endpoint health"
```

---

### 7.2 Multi-Cluster Upgrade

⬜ **Test:** Upgrade one cluster without affecting others

**Command:**
```bash
ansible-playbook -i inventory/test-multi.ini playbooks/upgrade-cluster.yaml \
  -e etcd_version=v3.5.26 \
  --limit=etcd-k8s \
  -b
```

**Expected Result:**
- Only k8s cluster upgraded
- k8s-events cluster unchanged

---

## 8. Service Control & Maintenance

### 8.1 Service Operations

⬜ **Test:** Stop all etcd services

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/stop-cluster.yaml -b
```

**Expected Result:**
- All etcd services stopped
- Cluster unavailable

---

⬜ **Test:** Start all etcd services

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/start-cluster.yaml -b
```

**Expected Result:**
- All etcd services started
- Cluster healthy

---

⬜ **Test:** Restart all etcd services

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/restart-cluster.yaml -b
```

**Expected Result:**
- All services restarted
- Brief downtime during restart
- Cluster recovers

---

### 8.2 Log Management

⬜ **Test:** View logs from all nodes

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-logs.yaml -b
```

**Expected Result:**
- Last 50 lines from each node

---

⬜ **Test:** Follow live logs

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-logs-follow.yaml -b
# Press Ctrl+C to stop
```

**Expected Result:**
- Live log stream
- Updates in real-time

---

⬜ **Test:** Clean old logs

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/clean-logs.yaml -b
```

**Expected Result:**
- Confirmation prompt
- Logs older than 7 days deleted

---

### 8.3 Cleanup Operations

⬜ **Test:** Clean old local backups

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/clean-backups.yaml -b
```

**Expected Result:**
- Confirmation prompt
- Backups older than 30 days deleted

---

⬜ **Test:** Clean certificates

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/clean-certs.yaml -b
```

**Expected Result:**
- Confirmation prompt
- All certificates deleted
- Need to regenerate

---

⬜ **Test:** Clean data directories

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/clean-data.yaml -b
```

**Expected Result:**
- Confirmation prompt
- All etcd data deleted
- Cluster destroyed

---

### 8.4 Cluster Deletion

⬜ **Test:** Delete cluster with confirmation

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_delete_cluster=true \
  -b
```

**Expected Result:**
- Confirmation prompt
- Backup created first
- Services stopped
- Data directories removed
- Config files removed

---

## 9. Edge Cases & Error Handling

### 9.1 Validation Errors

⬜ **Test:** Create cluster when data already exists (should fail)

**Description:** Verify protection against accidental recreation

**Setup:**
```bash
# Deploy cluster first
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create -b
```

**Command:**
```bash
# Try to create again
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create -b
```

**Expected Result:**
- Error: "ETCD DATA ALREADY EXISTS"
- Helpful message with options:
  - Use 'deploy' instead
  - Use force_create flag
  - Delete cluster first

---

⬜ **Test:** Force create (override protection)

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create \
  -e etcd_force_create=true \
  -b
```

**Expected Result:**
- Existing data destroyed
- New cluster created

---

⬜ **Test:** Upgrade without data directory (should fail)

**Description:** Verify upgrade validation

**Setup:**
```bash
# Remove data
ansible etcd -i inventory/test/inventory.ini -m shell \
  -a "systemctl stop etcd-* && rm -rf /var/lib/etcd/etcd-*" -b
```

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/upgrade-cluster.yaml \
  -e etcd_version=v3.5.26 -b
```

**Expected Result:**
- Error: "ETCD DATA NOT FOUND"
- Helpful message with options

---

⬜ **Test:** Version downgrade prevention

**Description:** Verify that version downgrades are blocked

**Setup:**
```bash
# Deploy with newer version
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create \
  -e etcd_version=v3.5.26 -b
```

**Command:**
```bash
# Try to downgrade
ansible-playbook -i inventory/test/inventory.ini playbooks/upgrade-cluster.yaml \
  -e etcd_version=v3.5.13 -b
```

**Expected Result:**
- Error: "VERSION DOWNGRADE NOT ALLOWED"
- Current and target versions displayed
- Options provided

---

⬜ **Test:** Insufficient disk space (should fail)

**Description:** Verify disk space validation

**Setup:**
```bash
# Fill up disk (create large file)
ansible etcd[0] -i inventory/test/inventory.ini -m shell -b -a \
  "dd if=/dev/zero of=/var/lib/etcd/fill bs=1G count=50"
```

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create -b
```

**Expected Result:**
- Error: "INSUFFICIENT DISK SPACE"
- Available and required space shown
- Cleanup recommendations

**Cleanup:**
```bash
ansible etcd[0] -i inventory/test/inventory.ini -m shell -b -a "rm -f /var/lib/etcd/fill"
```

---

⬜ **Test:** Unhealthy cluster upgrade (should fail)

**Description:** Verify upgrade blocked on unhealthy cluster

**Setup:**
```bash
# Stop 2 nodes (lose quorum)
ansible etcd[1:2] -i inventory/test/inventory.ini -m shell -a "systemctl stop etcd-*" -b
```

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/upgrade-cluster.yaml \
  -e etcd_version=v3.5.26 -b
```

**Expected Result:**
- Error: "ETCD CLUSTER IS UNHEALTHY"
- Troubleshooting steps shown
- Recovery options provided

**Recovery:**
```bash
ansible etcd -i inventory/test/inventory.ini -m shell -a "systemctl start etcd-*" -b
```

---

⬜ **Test:** Force deploy on unhealthy cluster (dangerous)

**Description:** Override health check (testing only)

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=deploy \
  -e etcd_force_deploy=true \
  -b
```

**Expected Result:**
- Deployment proceeds despite health check failure
- Warning messages shown

---

### 9.2 Certificate Errors

⬜ **Test:** step-ca not running during bootstrap

**Description:** Verify error handling when CA unreachable

**Setup:**
```bash
ssh etcd-test-1 "systemctl stop step-ca"
```

**Command:**
```bash
# Try to deploy new node
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create \
  --limit=etcd-test-2 -b
```

**Expected Result:**
- Bootstrap fails after retries
- Error message with troubleshooting steps
- Recommendations to check step-ca

**Recovery:**
```bash
ssh etcd-test-1 "systemctl start step-ca"
```

---

⬜ **Test:** Certificate renewal timer failure handling

**Description:** Verify renewal retries work

**Setup:**
```bash
# Stop step-ca temporarily
ssh etcd-test-1 "systemctl stop step-ca"

# Trigger renewal (will fail)
ansible etcd[1] -i inventory/test/inventory.ini -m shell -b -a \
  "systemctl start step-renew-etcd-test-cluster-peer.service"

# Start step-ca
ssh etcd-test-1 "systemctl start step-ca"

# Retry renewal
ansible etcd[1] -i inventory/test/inventory.ini -m shell -b -a \
  "systemctl start step-renew-etcd-test-cluster-peer.service"
```

**Expected Result:**
- First renewal fails (step-ca down)
- Second renewal succeeds (step-ca up)
- Logs show retry behavior

---

### 9.3 Backup Errors

⬜ **Test:** Backup with cluster unhealthy (offline backup)

**Description:** Test offline backup when cluster has no quorum

**Setup:**
```bash
# Stop 2 nodes (lose quorum)
ansible etcd[1:2] -i inventory/test/inventory.ini -m shell -a "systemctl stop etcd-*" -b
```

**Command:**
```bash
ansible etcd[0] -i inventory/test/inventory.ini -m shell -b -a \
  "python3 /opt/backups/etcd-backup.py --config /opt/backups/etcd-backup-config.yaml"
```

**Expected Result:**
- Health check fails
- OFFLINE backup created (from disk)
- Filename includes "offline": `*-offline-snapshot.db.kms`
- Warning about potential inconsistency
- Backup still succeeds

**Cleanup:**
```bash
ansible etcd -i inventory/test/inventory.ini -m shell -a "systemctl start etcd-*" -b
```

---

⬜ **Test:** Backup with online-only mode (should fail)

**Description:** Verify --online-only flag aborts on unhealthy cluster

**Setup:**
```bash
# Stop 2 nodes
ansible etcd[1:2] -i inventory/test/inventory.ini -m shell -a "systemctl stop etcd-*" -b
```

**Command:**
```bash
ansible etcd[0] -i inventory/test/inventory.ini -m shell -b -a \
  "python3 /opt/backups/etcd-backup.py \
   --config /opt/backups/etcd-backup-config.yaml \
   --online-only"
```

**Expected Result:**
- Health check fails
- Backup ABORTED
- Error: "Etcd cluster is unhealthy, aborting backup (--online-only mode)"
- Healthcheck ping with 'cluster-unhealthy' status

**Cleanup:**
```bash
ansible etcd -i inventory/test/inventory.ini -m shell -a "systemctl start etcd-*" -b
```

---

⬜ **Test:** S3 upload failure handling

**Description:** Verify backup fails gracefully when S3 unavailable

**Setup:**
```bash
# Use invalid S3 bucket
ansible-vault edit inventory/group_vars/all/vault-test.yml
# Change bucket to: "nonexistent-bucket-12345"
```

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=backup \
  --vault-password-file .vault-pass-test -b
```

**Expected Result:**
- Snapshot created locally
- S3 upload fails
- Error: "Failed to upload backup to S3"
- Local files cleaned up
- Healthcheck ping with 'failure' status

---

⬜ **Test:** Encryption validation failure

**Description:** Verify that corrupt encrypted files are detected

**Setup:**
```bash
# Manually create corrupt backup
ansible etcd[0] -i inventory/test/inventory.ini -m shell -b -a \
  "echo 'corrupt data' > /tmp/corrupt.db.kms"
```

**Command:**
```bash
ansible etcd[0] -i inventory/test/inventory.ini -m shell -b -a \
  "python3 /opt/backups/etcd-backup.py \
   --decrypt \
   --input /tmp/corrupt.db.kms \
   --output /tmp/out.db"
```

**Expected Result:**
- Decryption fails
- Error message with details

---

### 9.4 Restore Errors

⬜ **Test:** Restore with invalid snapshot file

**Description:** Verify snapshot validation catches corrupt files

**Setup:**
```bash
# Create corrupt snapshot
echo "invalid snapshot data" > /tmp/corrupt-snapshot.db
```

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/restore-etcd-cluster.yaml \
  -e restore_etcd_local_file=/tmp/corrupt-snapshot.db \
  -e restore_confirm=false
```

**Expected Result:**
- Snapshot validation fails
- Error: "SNAPSHOT FILE IS INVALID OR CORRUPTED"
- Detailed troubleshooting steps
- Cluster unchanged

---

⬜ **Test:** Restore with missing parameters

**Description:** Verify validation when parameters missing

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/restore-ca.yaml
```

**Expected Result:**
- Error: "source_node and target_node must be specified"

---

## 10. Performance & Scale

### 10.1 Large Cluster

⬜ **Test:** Deploy 5-node cluster

**Description:** Test with larger cluster size

**Inventory:** `inventory/test-large.ini`
```ini
[etcd]
etcd-large-1 ansible_host=10.0.1.40
etcd-large-2 ansible_host=10.0.1.41
etcd-large-3 ansible_host=10.0.1.42
etcd-large-4 ansible_host=10.0.1.43
etcd-large-5 ansible_host=10.0.1.44

[etcd-cert-managers]
etcd-large-1
etcd-large-2  # Backup
```

**Command:**
```bash
ansible-playbook -i inventory/test-large.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create \
  --vault-password-file .vault-pass-test \
  -b
```

**Expected Result:**
- 5-node cluster healthy
- CA replicated to backup
- All nodes have certificates

---

⬜ **Test:** Distributed backups with 5 nodes

**Description:** Verify backup coordination at scale

**Variables:**
```yaml
etcd_backup_distributed: true
etcd_backup_interval: "*/10"  # Every 10 minutes
```

**Expected Result:**
- Backups staggered across 10-minute interval
- Offsets: 0, 2, 4, 6, 8 minutes
- Only one backup per 10-minute window

**Verification:**
```bash
# Check cron schedules
ansible etcd -i inventory/test-large.ini -m shell -b -a \
  "crontab -l -u root | grep etcd-backup"

# Expected output shows different minute offsets per node
```

---

### 10.2 High Frequency Backups

⬜ **Test:** Independent mode with high frequency

**Description:** Multiple backups per interval

**Variables:**
```yaml
etcd_backup_distributed: true
etcd_backup_independent: true
etcd_backup_interval: "*/60"  # Base: 60 minutes
```

**Setup:**
```bash
ansible-playbook -i inventory/test-large.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=deploy \
  -e etcd_backup_independent=true \
  --tags backup-cron -b
```

**Expected Result:**
- All 5 nodes create backups independently
- Node schedule: 0, 12, 24, 36, 48 minutes
- Result: Backup every 12 minutes (different node)

---

### 10.3 Database Growth

⬜ **Test:** Large database backup and restore

**Description:** Test with multi-GB database

**Setup:**
```bash
# Populate etcd with data
for i in {1..100000}; do
  etcdctl put "test/key-$i" "value-$i-$(head -c 1024 /dev/urandom | base64)"
done
```

**Command:**
```bash
# Backup large DB
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=backup -b

# Restore
ansible-playbook -i inventory/test/inventory.ini playbooks/restore-etcd-cluster.yaml \
  -e restore_confirm=false
```

**Expected Result:**
- Backup completes (may take several minutes)
- Encryption validation succeeds
- Restore completes
- All data intact

**Verification:**
```bash
etcdctl get "test/key-50000"
```

---

## 11. Security Testing

### 11.1 File Permissions

⬜ **Test:** Verify CA key permissions

**Description:** Ensure CA private keys are protected

**Command:**
```bash
ansible etcd-cert-managers -i inventory/test/inventory.ini -m shell -b -a \
  "stat -c '%a %U:%G' /etc/step-ca/secrets/*_key"
```

**Expected Result:**
- Permissions: 400 (read-only by owner)
- Owner: root:root

---

⬜ **Test:** Verify node certificate permissions

**Description:** Ensure node private keys are protected

**Command:**
```bash
ansible etcd -i inventory/test/inventory.ini -m shell -b -a \
  "stat -c '%a %U:%G' /etc/etcd/ssl/*.key"
```

**Expected Result:**
- Permissions: 400
- Owner: etcd:etcd

---

### 11.2 Encryption Validation

⬜ **Test:** KMS encryption roundtrip

**Description:** Verify encrypt → decrypt → verify cycle

**Command:**
```bash
# Create backup
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=backup -b

# Decrypt with verification
ansible etcd[0] -i inventory/test/inventory.ini -m shell -b -a \
  "python3 /opt/backups/etcd-backup.py \
   --decrypt \
   --input /opt/backups/etcd/test-cluster/YYYY/MM/backup.db.kms \
   --output /tmp/verified.db"
```

**Expected Result:**
- Checksum auto-detected from .sha256 file
- Decryption successful
- Checksum verification PASSED

---

⬜ **Test:** Symmetric encryption roundtrip

**Description:** Verify OpenSSL encryption works correctly

**Variables:**
```yaml
step_ca_backup_encryption_method: symmetric
```

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/backup-ca.yaml \
  --vault-password-file .vault-pass-test

# Verify on cert-manager
ansible etcd-cert-managers[0] -i inventory/test/inventory.ini -m shell -b -a \
  "python3 /opt/backups/ca-backup-check.py \
   --config /opt/backups/ca-backup-config.yaml \
   --decrypt \
   --input /tmp/ca-backup.tar.gz.enc \
   --output /tmp/ca-restored.tar.gz"
```

**Expected Result:**
- Encryption with OpenSSL succeeds
- Decryption succeeds
- Checksum matches

---

### 11.3 Vault Integration

⬜ **Test:** Deploy with encrypted vault

**Description:** Verify ansible-vault integration works

**Setup:**
```bash
# Ensure vault is encrypted
ansible-vault encrypt inventory/group_vars/all/vault-test.yml \
  --vault-password-file .vault-pass-test
```

**Command:**
```bash
# Deploy with vault
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create \
  --vault-password-file .vault-pass-test \
  -b
```

**Expected Result:**
- Vault decrypted automatically
- Secrets available
- Deployment succeeds

---

⬜ **Test:** Wrong vault password (should fail)

**Command:**
```bash
echo "wrong-password" > .vault-pass-wrong

ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create \
  --vault-password-file .vault-pass-wrong \
  -b
```

**Expected Result:**
- Error: "Decryption failed"
- Deployment aborted

---

## 12. Makefile Integration

### 12.1 Basic Commands

⬜ **Test:** Make create

**Command:**
```bash
make create INVENTORY=inventory/test/inventory.ini VAULT_PASS_FILE=.vault-pass-test
```

**Expected Result:**
- Same as ansible-playbook create

---

⬜ **Test:** Make upgrade

**Command:**
```bash
make upgrade INVENTORY=inventory/test/inventory.ini VAULT_PASS_FILE=.vault-pass-test
```

**Expected Result:**
- Prompts for version or uses variable
- Safe rolling upgrade

---

⬜ **Test:** Make health

**Command:**
```bash
make health INVENTORY=inventory/test/inventory.ini
```

**Expected Result:**
- Health check runs
- Text output displayed

---

⬜ **Test:** Make with tags

**Command:**
```bash
make deploy INVENTORY=inventory/test/inventory.ini TAGS=etcd,certs
```

**Expected Result:**
- Only etcd and certs tasks run
- Other tasks skipped

---

⬜ **Test:** Make with groups limit

**Command:**
```bash
make health INVENTORY=inventory/test/inventory.ini GROUPS=etcd[0]
```

**Expected Result:**
- Only first etcd node targeted

---

### 12.2 Certificate Management via Make

⬜ **Test:** Make check-certs

**Command:**
```bash
make check-certs INVENTORY=inventory/test/inventory.ini
```

**Expected Result:**
- Certificate expiration shown

---

⬜ **Test:** Make renew-certs

**Command:**
```bash
make renew-certs INVENTORY=inventory/test/inventory.ini
```

**Expected Result:**
- Certificates renewed

---

⬜ **Test:** Make regenerate-node-certs

**Command:**
```bash
make regenerate-node-certs INVENTORY=inventory/test/inventory.ini VAULT_PASS_FILE=.vault-pass-test
```

**Expected Result:**
- Node certs regenerated
- Confirmation prompt

---

⬜ **Test:** Make regenerate-ca

**Command:**
```bash
make regenerate-ca INVENTORY=inventory/test/inventory.ini VAULT_PASS_FILE=.vault-pass-test
```

**Expected Result:**
- Disaster recovery warning
- Full CA regeneration

---

## 13. Different OS Families

### 13.1 Ubuntu/Debian

⬜ **Test:** Deploy on Ubuntu 22.04

**Inventory:**
```ini
[etcd]
ubuntu-node ansible_host=10.0.1.50 ansible_os_family=Debian
```

**Command:**
```bash
ansible-playbook -i inventory/test-ubuntu.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create -b
```

**Expected Result:**
- etcd user created
- All paths correct for Debian

---

### 13.2 RHEL/CentOS

⬜ **Test:** Deploy on RHEL 8

**Inventory:**
```ini
[etcd]
rhel-node ansible_host=10.0.1.60 ansible_os_family=RedHat
```

**Command:**
```bash
ansible-playbook -i inventory/test-rhel.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create -b
```

**Expected Result:**
- Works on RedHat family
- Correct package manager used

---

### 13.3 CoreOS/Container Linux

⬜ **Test:** Deploy on CoreOS

**Inventory:**
```ini
[etcd]
coreos-node ansible_host=10.0.1.70 ansible_os_family=CoreOS
```

**Command:**
```bash
ansible-playbook -i inventory/test-coreos.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create -b
```

**Expected Result:**
- User creation skipped (CoreOS has etcd user)
- Deployment succeeds

---

## 14. Integration Testing

### 14.1 Kubernetes Integration

⬜ **Test:** Use etcd3/facts role to populate K8s variables

**Description:** Verify facts role provides correct variables for K8s

**Playbook:** Create `test-k8s-integration.yaml`
```yaml
- hosts: kube-master
  roles:
    - etcd3/facts
  tasks:
    - name: Display etcd connection info
      debug:
        msg: |
          Endpoints: {{ etcd_access_addresses }}
          Cert: {{ etcd_cert_paths.client.cert }}
          Key: {{ etcd_cert_paths.client.key }}
          CA: {{ etcd_cert_paths.client.ca }}
```

**Command:**
```bash
ansible-playbook test-k8s-integration.yaml -i inventory/test/inventory.ini
```

**Expected Result:**
- All variables populated
- Ready for kube-apiserver config

---

### 14.2 Monitoring Integration

⬜ **Test:** Healthcheck ping integration

**Description:** Test deadman monitoring

**Variables:**
```yaml
backup_healthcheck_enabled: true
backup_healthcheck_url: "https://hc-ping.com/test-uuid"
ca_backup_healthcheck_url: "https://hc-ping.com/test-ca-uuid"
```

**Command:**
```bash
# Deploy with healthcheck
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=deploy \
  -e backup_healthcheck_enabled=true \
  -e backup_healthcheck_url="https://hc-ping.com/test-uuid" \
  --tags backup-cron -b

# Trigger backup
ansible etcd[0] -i inventory/test/inventory.ini -m shell -b -a \
  "python3 /opt/backups/etcd-backup.py --config /opt/backups/etcd-backup-config.yaml"
```

**Expected Result:**
- Backup completes
- Healthcheck ping sent
- Monitoring service receives ping

---

## 15. Dry Run & Validation

### 15.1 Dry Run Mode

⬜ **Test:** Backup dry run

**Command:**
```bash
ansible etcd[0] -i inventory/test/inventory.ini -m shell -b -a \
  "python3 /opt/backups/etcd-backup.py \
   --config /opt/backups/etcd-backup-config.yaml \
   --dry-run"
```

**Expected Result:**
- Shows what would be done
- No actual changes
- No S3 upload

---

⬜ **Test:** CA backup dry run

**Command:**
```bash
ansible etcd-cert-managers[0] -i inventory/test/inventory.ini -m shell -b -a \
  "python3 /opt/backups/ca-backup-check.py \
   --config /opt/backups/ca-backup-config.yaml \
   --dry-run"
```

**Expected Result:**
- Shows what would be done
- No files created
- No S3 upload

---

### 15.2 Check Mode

⬜ **Test:** Ansible check mode (dry run)

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=deploy \
  --check \
  -b
```

**Expected Result:**
- Shows changes that would be made
- No actual changes
- Some tasks may fail (expected in check mode)

---

## 16. Concurrent Operations

### 16.1 Parallel Deployment

⬜ **Test:** Deploy with strategy: free

**Description:** Test parallel task execution

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create \
  -e strategy=free \
  -b
```

**Expected Result:**
- Tasks run in parallel where possible
- Deployment faster
- Still succeeds

---

### 16.2 Serial Upgrade

⬜ **Test:** Verify serial: 1 during upgrade

**Description:** Ensure one-by-one upgrade

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/upgrade-cluster.yaml \
  -e etcd_version=v3.5.26 \
  -vv \
  -b
```

**Expected Result:**
- Verbose output shows serial execution
- Only 1 node upgrading at a time
- Health check between nodes

---

## 17. Configuration Variations

### 17.1 Custom Certificate Duration

⬜ **Test:** Deploy with 1-year certificates

**Description:** Test custom certificate lifetime

**Variables:**
```yaml
step_cert_default_duration: "8760h"  # 1 year
step_cert_renew_period: "5840h"  # 2/3 of 1 year
```

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create \
  -e step_cert_default_duration=8760h \
  -b
```

**Expected Result:**
- Certificates valid for 1 year
- Renewal at ~243 days

**Verification:**
```bash
ansible etcd[0] -i inventory/test/inventory.ini -m shell -b -a \
  "step certificate inspect /etc/etcd/ssl/etcd-test-cluster-peer.crt | grep validity"
```

---

### 17.2 Disable Automated Backups

⬜ **Test:** Deploy without automated backups

**Description:** Test with cron disabled

**Variables:**
```yaml
etcd_backup_cron_enabled: false
ca_backup_cron_enabled: false
```

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create \
  -e etcd_backup_cron_enabled=false \
  -e ca_backup_cron_enabled=false \
  -b
```

**Expected Result:**
- No cron jobs created
- Manual backups still work

**Verification:**
```bash
ansible etcd -i inventory/test/inventory.ini -m shell -b -a "crontab -l -u root | grep backup || echo 'No backup cron'"
```

---

### 17.3 step-ca Runtime Limit

⬜ **Test:** step-ca auto-shutdown after timeout

**Description:** Verify step-ca stops after configured runtime

**Variables:**
```yaml
step_ca_runtime_minutes: 5  # 5 minutes for testing
```

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=deploy \
  -e step_ca_runtime_minutes=5 \
  --tags step-ca -b

# Wait 6 minutes
sleep 360

# Check status
ansible etcd-cert-managers -i inventory/test/inventory.ini -m shell -b -a \
  "systemctl is-active step-ca"
```

**Expected Result:**
- step-ca starts
- After 5 minutes: step-ca stops automatically
- Status: inactive (RuntimeMaxSec reached)

**Restart:**
```bash
ansible etcd-cert-managers[0] -i inventory/test/inventory.ini -m shell -b -a \
  "systemctl start step-ca"
```

---

⬜ **Test:** step-ca infinite runtime

**Variables:**
```yaml
step_ca_runtime_minutes: 0  # Infinite
```

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e step_ca_runtime_minutes=0 \
  --tags step-ca -b
```

**Expected Result:**
- step-ca runs indefinitely
- No RuntimeMaxSec in systemd service

---

## 18. Force Operations (Use with Caution)

### 18.1 Force Create

⬜ **Test:** Force create destroys existing data

**Setup:**
```bash
# Deploy cluster
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create -b
```

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create \
  -e etcd_force_create=true \
  -b
```

**Expected Result:**
- Existing data destroyed
- New cluster created
- Data loss warning (expected)

---

### 18.2 Force Deploy on Unhealthy Cluster

⬜ **Test:** Force deploy bypasses health check

**Setup:**
```bash
# Make cluster unhealthy
ansible etcd[1:2] -i inventory/test/inventory.ini -m shell -a "systemctl stop etcd-*" -b
```

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=deploy \
  -e etcd_force_deploy=true \
  -b
```

**Expected Result:**
- Health check bypassed
- Deployment proceeds
- Warnings shown

---

## 19. Error Recovery

### 19.1 Installation Failure Recovery

⬜ **Test:** Retry after partial installation

**Description:** Verify force create recovers from failed install

**Setup:**
```bash
# Simulate failed installation (kill during deploy)
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create -b &
DEPLOY_PID=$!
sleep 30
kill $DEPLOY_PID
```

**Recovery Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create \
  -e etcd_force_create=true \
  -b
```

**Expected Result:**
- Cleanup of partial state
- Fresh installation
- Cluster healthy

---

### 19.2 Split Brain Recovery

⬜ **Test:** Recover from split brain scenario

**Description:** Force new cluster formation

**Setup:**
```bash
# Create split brain (simulate network partition)
# Stop all nodes
ansible etcd -i inventory/test/inventory.ini -m shell -a "systemctl stop etcd-*" -b

# Remove member data from 2 nodes
ansible etcd[1:2] -i inventory/test/inventory.ini -m shell -b -a \
  "rm -rf /var/lib/etcd/etcd-*/member"

# Start all
ansible etcd -i inventory/test/inventory.ini -m shell -a "systemctl start etcd-*" -b
```

**Recovery:**
```bash
# Restore from backup
ansible-playbook -i inventory/test/inventory.ini playbooks/restore-etcd-cluster.yaml \
  --vault-password-file .vault-pass-test
```

**Expected Result:**
- Cluster reformed from backup
- Split brain resolved

---

## 20. Certificate Lifecycle

### 20.1 Certificate Near Expiration

⬜ **Test:** Automatic renewal when near expiration

**Description:** Verify timer triggers renewal at 2/3 lifetime

**Setup:**
```bash
# Fast-forward time or deploy with short-lived cert
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create \
  -e step_cert_default_duration=3h \
  -e step_cert_renew_period=2h \
  -b

# Wait 2 hours or manually trigger
sleep 7200

# Or trigger manually
ansible etcd -i inventory/test/inventory.ini -m shell -b -a \
  "systemctl start step-renew-etcd-test-cluster-peer.timer"
```

**Expected Result:**
- Timer activates at 2/3 lifetime
- Certificate renewed
- etcd service reloaded

---

### 20.2 Certificate Expired

⬜ **Test:** Recover from expired certificates

**Description:** Regenerate all certs when expired

**Setup:**
```bash
# Deploy with very short lifetime
ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create \
  -e step_cert_default_duration=1h \
  -b

# Wait for expiration (or fast-forward system clock)
sleep 3700
```

**Recovery:**
```bash
# Regenerate all certs
ansible-playbook -i inventory/test/inventory.ini playbooks/regenerate-node-certs.yaml \
  --vault-password-file .vault-pass-test -b
```

**Expected Result:**
- New certificates issued
- Normal lifetime (2 years)
- Cluster operational

---

## 21. Backup Retention & Cleanup

### 21.1 S3 Retention Policy

⬜ **Test:** Verify old backups cleaned up

**Description:** Test retention cleanup script

**Setup:**
```bash
# Create old backups (manually set dates)
# Or wait for retention period
```

**Command:**
```bash
# Run retention cleanup (implement if needed)
aws s3 ls s3://my-test-etcd-backups/etcd/test-cluster/ --recursive | \
  awk '{print $4}' | while read file; do
    DAYS=$(( ($(date +%s) - $(date -d "$(echo $file | grep -oP '\d{4}-\d{2}-\d{2}')" +%s)) / 86400 ))
    if [ $DAYS -gt 90 ]; then
      echo "Would delete: $file (age: $DAYS days)"
      # aws s3 rm "s3://bucket/$file"
    fi
  done
```

**Expected Result:**
- Backups older than 90 days identified
- Can be deleted with cleanup script

---

### 21.2 Local Backup Cleanup

⬜ **Test:** Clean local backups older than retention

**Command:**
```bash
ansible-playbook -i inventory/test/inventory.ini playbooks/clean-backups.yaml -b
```

**Expected Result:**
- Confirmation prompt
- Backups >30 days deleted
- Recent backups kept

---

## 22. Documentation & Help

### 22.1 Makefile Help

⬜ **Test:** Display help

**Command:**
```bash
make help
```

**Expected Result:**
- Comprehensive help output
- All commands listed
- Examples shown
- Parameters explained

---

### 22.2 Documentation Site

⬜ **Test:** Build documentation

**Command:**
```bash
make docs-build
```

**Expected Result:**
- Documentation built in `site/`
- No errors

---

⬜ **Test:** Serve documentation

**Command:**
```bash
make docs-serve
# Visit http://127.0.0.1:8000
```

**Expected Result:**
- Documentation server runs
- All pages accessible
- No broken links

---

## 23. Complete Workflow Tests

### 23.1 Full Lifecycle Test

⬜ **Test:** Complete cluster lifecycle (create → upgrade → backup → restore → delete)

**Description:** Test entire workflow end-to-end

**Commands:**
```bash
# 1. Create cluster
make create INVENTORY=inventory/test-lifecycle.ini VAULT_PASS_FILE=.vault-pass-test

# 2. Health check
make health INVENTORY=inventory/test-lifecycle.ini

# 3. Create backup
make backup INVENTORY=inventory/test-lifecycle.ini

# 4. Upgrade
make upgrade INVENTORY=inventory/test-lifecycle.ini VAULT_PASS_FILE=.vault-pass-test

# 5. Restore from backup
make restore INVENTORY=inventory/test-lifecycle.ini VAULT_PASS_FILE=.vault-pass-test

# 6. Health check
make health INVENTORY=inventory/test-lifecycle.ini

# 7. Delete cluster
make delete INVENTORY=inventory/test-lifecycle.ini
```

**Expected Result:**
- All steps succeed
- No errors
- Clean state at end

---

### 23.2 Certificate Lifecycle Test

⬜ **Test:** Complete certificate lifecycle

**Commands:**
```bash
# 1. Deploy with certs
make create INVENTORY=inventory/test-cert-lifecycle.ini

# 2. Check expiration
make check-certs INVENTORY=inventory/test-cert-lifecycle.ini

# 3. Manual renewal
make renew-certs INVENTORY=inventory/test-cert-lifecycle.ini

# 4. Node cert regeneration
make regenerate-node-certs INVENTORY=inventory/test-cert-lifecycle.ini

# 5. Full CA regeneration
make regenerate-ca INVENTORY=inventory/test-cert-lifecycle.ini

# 6. Verify health
make health INVENTORY=inventory/test-cert-lifecycle.ini
```

**Expected Result:**
- All steps succeed
- Certificates rotate correctly
- No service interruption (except during restarts)

---

## 24. Performance Benchmarks

### 24.1 Backup Performance

⬜ **Test:** Measure backup time for various sizes

**Description:** Benchmark backup/restore performance

**Test Cases:**
- Empty DB: < 10 seconds
- 1GB DB: < 2 minutes
- 5GB DB: < 10 minutes
- 10GB DB: < 20 minutes

**Command:**
```bash
# Time backup
time ansible-playbook -i inventory/test/inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=backup -b
```

**Expected Result:**
- Times within expected ranges
- No timeouts (default: 30 minutes)

---

### 24.2 Restore Performance

⬜ **Test:** Measure restore time

**Description:** Benchmark complete cluster restore

**Command:**
```bash
time ansible-playbook -i inventory/test/inventory.ini playbooks/restore-etcd-cluster.yaml \
  -e restore_confirm=false
```

**Expected Result:**
- Download phase: < 5 minutes (parallel)
- Restore phase: < 30 seconds (local, fast)
- Total downtime: < 1 minute (stop → restore → start)

---

## 25. Failure Injection

### 25.1 Network Partition

⬜ **Test:** Simulate network partition during backup

**Description:** Verify backup handles network issues

**Setup:**
```bash
# Block S3 access temporarily
sudo iptables -A OUTPUT -d $(dig +short s3.amazonaws.com | head -1) -j DROP

# Trigger backup
ansible etcd[0] -i inventory/test/inventory.ini -m shell -b -a \
  "timeout 60 python3 /opt/backups/etcd-backup.py --config /opt/backups/etcd-backup-config.yaml || echo 'TIMEOUT'"

# Restore access
sudo iptables -D OUTPUT -d $(dig +short s3.amazonaws.com | head -1) -j DROP
```

**Expected Result:**
- S3 upload fails with timeout
- Local snapshot created
- Error logged
- Healthcheck ping: failure

---

### 25.2 Disk Full During Backup

⬜ **Test:** Handle disk full error

**Description:** Verify graceful failure when disk full

**Setup:**
```bash
# Fill disk
ansible etcd[0] -i inventory/test/inventory.ini -m shell -b -a \
  "dd if=/dev/zero of=/var/lib/etcd/fill bs=1G count=100 || true"
```

**Command:**
```bash
ansible etcd[0] -i inventory/test/inventory.ini -m shell -b -a \
  "python3 /opt/backups/etcd-backup.py --config /opt/backups/etcd-backup-config.yaml || echo 'FAILED'"
```

**Expected Result:**
- Error: "Permission denied" or "No space left"
- Backup fails gracefully
- No corrupted files

**Cleanup:**
```bash
ansible etcd[0] -i inventory/test/inventory.ini -m shell -b -a "rm -f /var/lib/etcd/fill"
```

---

## Test Summary Checklist

### Prerequisites (6 tests)
- ⬜ AWS KMS setup
- ⬜ Basic inventory
- ⬜ Vault configuration
- ⬜ Ansible connectivity
- ⬜ S3 bucket access
- ⬜ Required Python packages

### Happy Path (15 tests)
- ⬜ Initial deployment
- ⬜ Health check (text)
- ⬜ Health check (JSON)
- ⬜ Manual backup (etcd)
- ⬜ Manual backup (CA)
- ⬜ Cluster upgrade
- ⬜ Status operations (3)
- ⬜ Database maintenance (2)
- ⬜ Automated backup verification
- ⬜ Distributed backup coordination
- ⬜ Independent backup mode

### Certificate Management (10 tests)
- ⬜ Manual renewal
- ⬜ Node cert regeneration
- ⬜ CA regeneration
- ⬜ Certificate rotation
- ⬜ Expiration check
- ⬜ Custom certificate duration
- ⬜ Renewal timer behavior
- ⬜ Certificate near expiration
- ⬜ Certificate expired recovery
- ⬜ step-ca runtime limits (2)

### Backup & Restore (15 tests)
- ⬜ Encryption methods (3: KMS, symmetric, none)
- ⬜ Restore operations (3: latest, specific, local)
- ⬜ CA restore (2: S3, node)
- ⬜ Checksum verification (3)
- ⬜ Automated cron verification
- ⬜ Retention cleanup (2)
- ⬜ Performance benchmarks (2)

### Disaster Recovery (6 tests)
- ⬜ Single node failure
- ⬜ Cert-manager failover
- ⬜ Complete data loss
- ⬜ CA key loss
- ⬜ Quorum loss
- ⬜ Split brain recovery

### Advanced Features (8 tests)
- ⬜ HA setup
- ⬜ Manual replication
- ⬜ Add nodes
- ⬜ Client certificates
- ⬜ Custom configuration
- ⬜ Performance tuning
- ⬜ Large cluster (5 nodes)
- ⬜ High frequency backups

### Multi-Cluster (2 tests)
- ⬜ Deploy multiple clusters
- ⬜ Multi-cluster upgrade

### Service Control (7 tests)
- ⬜ Stop all
- ⬜ Start all
- ⬜ Restart all
- ⬜ View logs
- ⬜ Follow logs
- ⬜ Clean logs
- ⬜ Cleanup operations (3)

### Edge Cases (10 tests)
- ⬜ Validation errors (5)
- ⬜ Certificate errors (2)
- ⬜ Backup errors (3)

### Security (5 tests)
- ⬜ File permissions (2)
- ⬜ Encryption validation (2)
- ⬜ Vault integration (1)

### Integration (3 tests)
- ⬜ Kubernetes integration
- ⬜ Monitoring integration
- ⬜ Documentation build

### OS Compatibility (3 tests)
- ⬜ Ubuntu/Debian
- ⬜ RHEL/CentOS
- ⬜ CoreOS

### Makefile (8 tests)
- ⬜ Basic commands (4)
- ⬜ Certificate commands (4)

### Force Operations (2 tests)
- ⬜ Force create
- ⬜ Force deploy

### Failure Injection (2 tests)
- ⬜ Network partition
- ⬜ Disk full

### Complete Workflows (2 tests)
- ⬜ Full lifecycle
- ⬜ Certificate lifecycle

---

## Total Test Count: ~105 Test Scenarios

### Priority Levels

**P0 - Critical (Must Pass)**
- 2.1: Initial deployment
- 2.2: Health check
- 2.3: Manual backup
- 2.4: Upgrade
- 4.3: Restore from backup
- 5.3: Complete data loss recovery
- 6.1: HA setup
- 9.1: Validation errors

**P1 - Important (Should Pass)**
- All certificate management tests
- All backup encryption methods
- Disaster recovery scenarios
- Multi-cluster operations

**P2 - Nice to Have (Can Skip)**
- Performance benchmarks
- Documentation tests
- Failure injection

---

## Quick Test Execution

### Minimal Smoke Test (15 minutes)
```bash
# Run only P0 tests
make create INVENTORY=inventory/test/inventory.ini
make health INVENTORY=inventory/test/inventory.ini
make backup INVENTORY=inventory/test/inventory.ini
make restore INVENTORY=inventory/test/inventory.ini
make health INVENTORY=inventory/test/inventory.ini
make delete INVENTORY=inventory/test/inventory.ini
```

### Full Regression Test (2-3 hours)
```bash
# Run all tests in order
# Use test automation script or manual execution
```

### Nightly Automated Tests
```bash
# Suggested nightly test subset:
# - P0 + P1 tests
# - Different OS families
# - All encryption methods
```

---

## Notes for QA Team

1. **Environment Setup:**
   - AWS account with KMS and S3 access
   - Test VMs/instances (minimum 3 nodes)
   - ansible-vault password file
   - SSH access configured

2. **Test Data:**
   - Use separate S3 bucket for testing
   - Use test KMS key alias
   - Use test vault passwords

3. **Cleanup Between Tests:**
   - Delete test clusters: `make delete`
   - Clean S3 buckets
   - Reset VMs to clean state

4. **Tracking Progress:**
   - Update checkboxes as you complete tests
   - Note any failures with details
   - Create GitHub issues for bugs found

5. **Expected Test Duration:**
   - Quick smoke test: ~15 minutes
   - Full test suite: ~2-3 hours
   - Performance tests: +1 hour

6. **Tools Needed:**
   - ansible 2.9+
   - Python 3.6+
   - AWS CLI
   - jq (for JSON parsing)
   - curl (for healthchecks)

7. **Common Issues:**
   - SSH keys: Ensure passwordless SSH to all nodes
   - AWS credentials: Set in vault.yml or environment
   - Timeouts: Increase if needed with -e timeout values
   - Parallel execution: Some tests must run serially

---

## Appendix: Test Environment Setup

### Minimal Test Environment (Vagrant)

```ruby
# Vagrantfile
Vagrant.configure("2") do |config|
  (1..3).each do |i|
    config.vm.define "etcd-test-#{i}" do |node|
      node.vm.box = "ubuntu/jammy64"
      node.vm.hostname = "etcd-test-#{i}"
      node.vm.network "private_network", ip: "10.0.1.#{9+i}"
      node.vm.provider "virtualbox" do |vb|
        vb.memory = "2048"
        vb.cpus = 2
      end
    end
  end
end
```

**Setup:**
```bash
vagrant up
# Configure SSH config for passwordless access
```

---

### Docker-based Test Environment

```bash
# Use docker-compose to create test nodes
# (Implementation depends on requirements)
```

---

## Test Execution Log Template

```markdown
### Test Run: [Date]
**Tester:** [Name]
**Environment:** [AWS/Vagrant/Docker]
**Duration:** [Time]

#### Results:
- Total Tests: 105
- Passed: X
- Failed: Y
- Skipped: Z

#### Failures:
1. [Test Name] - [Reason] - [GitHub Issue #]
2. ...

#### Notes:
- [Any observations]
- [Performance issues]
- [Documentation gaps]
```

---

## Continuous Integration

### Suggested CI Pipeline

```yaml
# .github/workflows/test.yml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Setup test environment
        run: |
          # Setup VMs, AWS credentials, etc.
      - name: Run smoke tests
        run: |
          make create INVENTORY=inventory/test-ci.ini
          make health INVENTORY=inventory/test-ci.ini
          make delete INVENTORY=inventory/test-ci.ini
```

---

**Last Updated:** 2026-01-25
**Version:** 1.0
**Maintainer:** QA Team
