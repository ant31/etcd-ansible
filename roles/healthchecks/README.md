# Healthchecks.io Integration

Optional role to automatically configure healthchecks.io monitoring for etcd backups and services.

## Features

- ✅ **Automatic Check Creation** - Creates checks via healthchecks.io API
- ✅ **Auto-Configuration** - Automatically sets backup healthcheck URLs
- ✅ **Multi-Cluster Support** - Creates separate checks per cluster
- ✅ **Channel Management** - Configure notification channels per check
- ✅ **Idempotent** - Updates existing checks instead of creating duplicates
- ✅ **Optional** - Completely opt-in, no impact if disabled

## Quick Start

### 1. Get API Key

1. Go to https://healthchecks.io/projects/YOUR_PROJECT/settings/
2. Find your API key under "API Access"
3. Copy the key

### 2. Configure in Ansible

Add to `group_vars/all/vault.yml` (encrypted):
```yaml
healthchecks_api_key: "your-api-key-here"
```

Add to `group_vars/all/etcd.yaml`:
```yaml
healthchecks_enabled: true
healthchecks_environment: prod  # or staging, dev
healthchecks_channels:
  - "Slack #alerts"
  - "PagerDuty"
```

### 3. Setup Checks

```bash
# For single cluster
ansible-playbook -i inventory.ini playbooks/setup-healthchecks.yaml \
  --vault-password-file ~/.vault-pass

# For all clusters
ansible-playbook -i inventory.ini playbooks/setup-healthchecks.yaml \
  -e setup_all_clusters=true \
  --vault-password-file ~/.vault-pass
```

### 4. Deploy Cluster

The healthcheck URLs are now automatically configured:

```bash
ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=deploy -b
```

## Configuration

### Basic Settings

```yaml
# Enable/disable (default: false)
healthchecks_enabled: true

# API configuration (in vault.yml)
healthchecks_api_key: "your-api-key"

# Check naming
healthchecks_environment: prod  # Prefix for check names
healthchecks_name_prefix: prod  # Alternative to environment

# Notification channels (optional)
healthchecks_channels:
  - "Slack #ops"
  - "Email Ops Team"
```

### Per-Service Configuration

Customize check settings in `group_vars/all/etcd.yaml`:

```yaml
healthchecks_checks:
  etcd_backup:
    enabled: true
    timeout: 3600   # 1 hour (backup runs every 30min)
    grace: 1800     # 30 minutes grace period
    tags: ["etcd", "backup", "critical"]
    
  ca_backup:
    enabled: true
    timeout: 7200   # 2 hours (change-based)
    grace: 3600     # 1 hour grace
    tags: ["etcd", "ca", "backup"]
    
  cert_renewal:
    enabled: false  # Optional certificate renewal monitoring
```

### Per-Cluster Configuration

Different settings per cluster:

```yaml
etcd_cluster_configs:
  k8s:
    backup_healthcheck_channels:
      - "PagerDuty Critical"
    backup_healthcheck_timeout: 1800  # 30 minutes
    
  events:
    backup_healthcheck_channels:
      - "Slack #monitoring"
    backup_healthcheck_timeout: 7200  # 2 hours
```

## Check Naming

Checks are automatically named using this pattern:
```
{environment}-{cluster_name}-{service}
```

Examples:
- `prod-k8s-etcd-backup`
- `prod-k8s-ca-backup`
- `staging-events-etcd-backup`

## What Gets Created

For each cluster, the following checks are created:

1. **Etcd Data Backup**
   - Name: `{env}-{cluster}-etcd-backup`
   - Monitors: Regular etcd snapshot backups
   - Default timeout: 1 hour
   - Tags: etcd, backup, data

2. **CA Backup**
   - Name: `{env}-{cluster}-ca-backup`
   - Monitors: Change-based CA backups
   - Default timeout: 2 hours
   - Tags: etcd, backup, ca

3. **Certificate Renewal** (optional)
   - Name: `{env}-{cluster}-cert-renewal`
   - Monitors: Automatic certificate renewals
   - Default timeout: 24 hours
   - Tags: etcd, certificates, renewal

## Usage

### Create All Checks

```bash
ansible-playbook -i inventory.ini playbooks/setup-healthchecks.yaml \
  --vault-password-file ~/.vault-pass
```

### List Existing Checks

```bash
python3 /opt/backups/manage-healthchecks.py \
  --config /opt/backups/healthchecks-config-k8s.yaml \
  --action list
```

### Delete a Check

```bash
python3 /opt/backups/manage-healthchecks.py \
  --config /opt/backups/healthchecks-config-k8s.yaml \
  --action delete \
  --check-name "prod-k8s-etcd-backup"
```

### Update Check Settings

Modify configuration and re-run:

```bash
ansible-playbook -i inventory.ini playbooks/setup-healthchecks.yaml
```

Existing checks will be updated with new settings.

## Integration with Backups

When `healthchecks_auto_configure: true` (default), the role automatically:

1. Creates checks in healthchecks.io
2. Sets `backup_healthcheck_url` fact
3. Sets `ca_backup_healthcheck_url` fact
4. These URLs are then used by backup cron configuration

The backup scripts will ping these URLs:
- On success: `curl {ping_url}?status=success`
- On failure: `curl {ping_url}?status=failure`
- On skip: `curl {ping_url}?status=no-changes`

## Manual Configuration (Without Role)

If you prefer to create checks manually:

1. Create checks in healthchecks.io dashboard
2. Copy ping URLs
3. Set in inventory or group_vars:

```yaml
backup_healthcheck_url: "https://hc-ping.com/your-uuid-1"
ca_backup_healthcheck_url: "https://hc-ping.com/your-uuid-2"
```

## Troubleshooting

### API Key Not Working

```bash
# Test API key
curl -H "X-Api-Key: your-api-key" https://healthchecks.io/api/v3/checks/
```

Should return JSON with your checks.

### Checks Not Being Created

1. Check API key is in vault.yml and encrypted
2. Verify healthchecks_enabled: true in configuration
3. Run with verbose output:
   ```bash
   ansible-playbook -i inventory.ini playbooks/setup-healthchecks.yaml -vvv
   ```

### Channel Names Not Resolving

List available channels:
```bash
curl -H "X-Api-Key: your-api-key" https://healthchecks.io/api/v3/channels/
```

Use exact channel names from the response.

### Ping URLs Not Being Set

Check facts after healthchecks role runs:
```bash
ansible etcd -i inventory.ini -m debug -a "var=backup_healthcheck_url"
```

Should show the healthchecks.io ping URL.

## API Reference

The role uses healthchecks.io API v3:
- Docs: https://healthchecks.io/docs/api/
- Endpoint: https://healthchecks.io/api/v3

## Dependencies

- Python 3.6+
- `requests` library (installed automatically)
- `pyyaml` library (installed automatically)

## Security

- ✅ API key stored in ansible-vault
- ✅ Configuration files are root-only (0600)
- ✅ Ping URLs contain unique UUIDs (no API key needed to ping)
- ✅ Channels configured via API (not in config files)

## Examples

### Simple Setup (One Cluster)

```yaml
# group_vars/all/vault.yml (encrypted)
healthchecks_api_key: "abc123..."

# group_vars/all/etcd.yaml
healthchecks_enabled: true
healthchecks_environment: prod
```

### Multi-Cluster with Different Channels

```yaml
# group_vars/all/etcd.yaml
healthchecks_enabled: true
healthchecks_environment: prod

etcd_cluster_configs:
  k8s:
    backup_healthcheck_channels:
      - "PagerDuty Production"
  
  events:
    backup_healthcheck_channels:
      - "Slack #monitoring"
```

### Custom Check Settings

```yaml
# group_vars/all/etcd.yaml
healthchecks_checks:
  etcd_backup:
    timeout: 1800  # 30 minutes
    grace: 900     # 15 minutes
    tags: ["etcd", "backup", "p1"]
  
  ca_backup:
    enabled: false  # Disable CA backup monitoring
```
