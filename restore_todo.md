# ETCD Cluster Restore Role - TODO

## Overview
Create a new Ansible role `etcd3/restore` that can restore an etcd cluster from a backup snapshot stored either locally or in S3/object storage.

## Tasks Breakdown

### 1. Role Structure
- [ ] Create role directory: `roles/etcd3/restore/`
- [ ] Create subdirectories:
  - `tasks/`
  - `templates/`
  - `defaults/`
  - `meta/`
  - `vars/`

### 2. Meta Dependencies (`meta/main.yml`)
- [ ] Add dependency on `etcd3` role
- [ ] Add dependency on `etcd3/facts` role
- [ ] Consider conditional dependency on `etcd3/backups` for backup verification

### 3. Default Variables (`defaults/main.yml`)
- [ ] Define restore source types: `etcd_restore_source` (s3, local, url)
- [ ] Define local restore path: `etcd_restore_local_path`
- [ ] Define S3 restore configuration:
  - `etcd_restore_s3_bucket`
  - `etcd_restore_s3_key`
  - `etcd_restore_s3_access_key`
  - `etcd_restore_s3_secret_key`
  - `etcd_restore_s3_region`
  - `etcd_restore_s3_url`
- [ ] Define restore options:
  - `etcd_restore_force` (boolean - force restore even if cluster is healthy)
  - `etcd_restore_skip_hash_check` (boolean)
  - `etcd_restore_data_dir` (where to restore data)
  - `etcd_restore_name` (new cluster name if needed)
  - `etcd_restore_initial_cluster` (peer URLs)
  - `etcd_restore_initial_advertise_peer_urls`

### 4. Pre-restore Tasks (`tasks/pre_restore.yml`)
- [ ] Validate that restore is requested (fail-safe check)
- [ ] Check if snapshot file exists (local) or is accessible (S3)
- [ ] Verify etcdctl binary is available
- [ ] Check current cluster health status
- [ ] Prompt user for confirmation (with pause task)
- [ ] Create backup of current state before restore (safety measure)

### 5. Download/Fetch Snapshot (`tasks/fetch_snapshot.yml`)
- [ ] Create temporary directory for snapshot download
- [ ] Download from S3 if `etcd_restore_source == 's3'`
  - Install boto3/botocore if needed
  - Use `aws_s3` module to download snapshot
- [ ] Copy from local path if `etcd_restore_source == 'local'`
- [ ] Download from URL if `etcd_restore_source == 'url'`
- [ ] Verify snapshot integrity with `etcdctl snapshot status`

### 6. Stop Cluster (`tasks/stop_cluster.yml`)
- [ ] Stop all etcd services across the cluster
  - Use systemd to stop services: `systemctl stop {{etcd_name}}`
  - Verify services are stopped
- [ ] Wait for graceful shutdown (with retries)

### 7. Backup Current Data (`tasks/backup_current.yml`)
- [ ] Move existing data directories to backup location
  - `{{etcd_data_dir}}` → `{{etcd_data_dir}}.backup-{{timestamp}}`
- [ ] Preserve existing certificates
- [ ] Keep configuration files for reference

### 8. Restore Snapshot (`tasks/restore_snapshot.yml`)
- [ ] Run `etcdctl snapshot restore` on first node with:
  - `--data-dir` pointing to the etcd data directory
  - `--name` for the member name
  - `--initial-cluster` with all cluster members
  - `--initial-cluster-token` for the cluster
  - `--initial-advertise-peer-urls` for this member
- [ ] Set correct ownership on restored data directory (etcd user)
- [ ] Set correct permissions (mode 0700)
- [ ] Copy/sync restored data to other cluster members
  - Use `synchronize` module or `rsync`
  - Or restore snapshot on each node individually

### 9. Update Configuration (`tasks/update_config.yml`)
- [ ] Update etcd configuration files if needed
  - Set `initial-cluster-state: existing` after first restore
  - Ensure cluster token matches
- [ ] Verify certificate paths are correct
- [ ] Update systemd service files if needed

### 10. Start Cluster (`tasks/start_cluster.yml`)
- [ ] Start etcd service on first node
- [ ] Wait for first node to become healthy
- [ ] Start etcd services on remaining nodes (one by one)
- [ ] Wait for each node to join and become healthy
- [ ] Use delays/retries to handle startup timing

### 11. Verify Restore (`tasks/verify_restore.yml`)
- [ ] Check cluster health: `etcdctl endpoint health`
- [ ] Verify cluster member list: `etcdctl member list`
- [ ] Check endpoint status: `etcdctl endpoint status`
- [ ] Verify data integrity with sample queries
- [ ] Compare member count with expected count
- [ ] Log successful restore with timestamp

### 12. Cleanup (`tasks/cleanup.yml`)
- [ ] Remove temporary snapshot files
- [ ] Optional: Remove old backup directories after retention period
- [ ] Log cleanup actions

### 13. Main Task File (`tasks/main.yml`)
- [ ] Import all task files in correct order:
  1. `pre_restore.yml`
  2. `fetch_snapshot.yml`
  3. `stop_cluster.yml`
  4. `backup_current.yml`
  5. `restore_snapshot.yml`
  6. `update_config.yml`
  7. `start_cluster.yml`
  8. `verify_restore.yml`
  9. `cleanup.yml`
- [ ] Add proper tags for each section
- [ ] Add conditional checks for when to run each section

### 14. Error Handling & Rollback (`tasks/rollback.yml`)
- [ ] Create rollback tasks that can:
  - Restore previous data directory if restore fails
  - Restart services with old configuration
  - Alert on failure
- [ ] Use `block`/`rescue`/`always` in main tasks

### 15. Integration & Testing
- [ ] Create example playbook: `playbooks/etcd-restore.yaml`
- [ ] Update main `etcd.yaml` playbook to support restore action
- [ ] Add restore action to cluster management role
- [ ] Document in README.md:
  - How to trigger restore
  - Required variables
  - Example commands
  - Safety considerations

### 16. Safety Features
- [ ] Require explicit confirmation variable: `etcd_restore_confirmed: true`
- [ ] Add dry-run mode that shows what would be done
- [ ] Verify cluster name matches before restore
- [ ] Check free disk space before restore
- [ ] Create comprehensive logs of restore process

### 17. Advanced Features (Optional)
- [ ] Support for partial cluster restore (single node)
- [ ] Point-in-time restore (select from multiple backups)
- [ ] Restore to different cluster name
- [ ] Cross-cluster restore (restore to new cluster)
- [ ] Integration with backup rotation/retention policies

## Example Variables Usage

```yaml
# Restore from S3
etcd_action: restore
etcd_restore_confirmed: true
etcd_restore_source: s3
etcd_restore_s3:
  bucket: my-backups
  key: etcd/k8s/2024/01/snapshot.db
  access_key: "{{ vault_aws_access_key }}"
  secret_key: "{{ vault_aws_secret_key }}"
  region: us-east-1

# Restore from local file
etcd_action: restore
etcd_restore_confirmed: true
etcd_restore_source: local
etcd_restore_local_path: /path/to/snapshot.db
```

## References
- Existing backup role: `roles/etcd3/backups/`
- etcd documentation: https://etcd.io/docs/latest/op-guide/recovery/
- Existing cluster management: `roles/etcd3/cluster/`
