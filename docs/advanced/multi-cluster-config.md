# Multi-Cluster Configuration

Configure multiple etcd clusters with different settings using the `etcd_cluster_configs` dictionary.

## Overview

Top-level variables define the defaults for ALL clusters. The `etcd_cluster_configs` dictionary provides **optional** per-cluster overrides:

```yaml
# group_vars/all/etcd.yaml

# Defaults for ALL clusters (always defined)
etcd_ports:
  client: 2379
  peer: 2380
etcd_backup_cron_enabled: true
etcd_backup_interval: "*/30"
etcd_backup_retention_days: 90

# Optional per-cluster overrides (only specify what's different)
etcd_cluster_configs:
  k8s:
    # Uses default ports (no override needed)
    backup: 
      interval: "*/30"  # Same as default (could be omitted)
      s3_prefix: "etcd/k8s/"  # Custom S3 path
  k8s-events:
    ports:
      client: 2381  # Override client port
      peer: 2382    # Override peer port
    backup:
      interval: "*/60"  # Different interval
      s3_prefix: "etcd/events/"
      retention_days: 30  # Shorter retention
```

The facts role automatically merges cluster-specific settings with defaults using dictionary combining.

## Available Settings Per Cluster

All settings are **optional overrides** - only specify what's different from defaults.

### Network & Load Balancer

```yaml
etcd_cluster_configs:
  my-cluster:
    # Network ports
    ports:
      client: 2379  # Client API port
      peer: 2380    # Peer communication port
    
    # Load balancer (for stable client endpoint)
    lb:
      enabled: true                          # Enable LB mode
      host: "etcd-lb.internal.example.com"  # LB hostname
      port: 2379                             # LB port (defaults to client port)
      ip: "10.0.1.100"                       # Optional VIP
```

### Certificates

```yaml
etcd_cluster_configs:
  my-cluster:
    cert:
      alt_names:  # Additional DNS names for server certificate
        - "etcd.kube-system.svc.cluster.local"
        - "etcd-custom.example.com"
      alt_ips:    # Additional IP addresses
        - "10.0.1.100"  # Include LB IP if using load balancer
```

### Backup Configuration

```yaml
etcd_cluster_configs:
  my-cluster:
    backup:
      enabled: true                    # Enable/disable backups
      interval: "*/30"                 # Cron interval (every 30 minutes)
      s3_prefix: "etcd/custom/"        # S3 path (default: etcd/{cluster_name}/)
      local_retention_days: 90         # Local disk retention (S3 needs lifecycle policy)
      distributed: true                # Multi-node coordination
      independent: false               # Skip deduplication check
      online_only: false               # Backup even if unhealthy
    
    ca_backup:
      enabled: true                    # Enable/disable CA backups
      check_interval: "0 * * * *"      # How often to check for changes (every hour)
      local_retention_days: 365        # Local disk retention (S3 needs lifecycle policy)
```

### Performance Tuning

```yaml
etcd_cluster_configs:
  my-cluster:
    performance:
      heartbeat_interval: 250      # Raft heartbeat (milliseconds)
      election_timeout: 5000       # Raft election timeout (milliseconds)
      snapshot_count: 10000        # Transactions before snapshot
      compaction_retention: "8"    # Hours of history to keep
      quota_backend_bytes: "8G"    # Max database size (0 = unlimited)
      metrics: "extensive"         # Metrics level (basic/extensive)
```

### Systemd Service Tuning

```yaml
etcd_cluster_configs:
  my-cluster:
    systemd:
      timeout_start_sec: "60s"      # Service startup timeout
      restart_sec: "15s"            # Delay between restarts
      limit_nofile: 40000           # Max open files
      nice_level: -10               # CPU priority (-20 to 19, lower = higher)
      ionice_class: 1               # I/O scheduling (0=none, 1=realtime, 2=best-effort, 3=idle)
      ionice_priority: 0            # I/O priority (0=highest, 7=lowest)
      memory_limit: "4G"            # Memory limit
      cpu_quota: "200%"             # CPU limit (200% = 2 cores)
```

### Security Settings

```yaml
etcd_cluster_configs:
  my-cluster:
    security:
      secure_client: true          # Require client cert authentication
      peer_client_auth: true       # Require peer cert authentication
```

### step-ca Configuration

```yaml
etcd_cluster_configs:
  my-cluster:
    step_ca:
      runtime_minutes: 60          # Auto-shutdown after N minutes (0=infinite)
      port: 9000                   # step-ca API port
```

### Monitoring

```yaml
etcd_cluster_configs:
  my-cluster:
    monitoring:
      backup_healthcheck_url: "https://hc-ping.com/uuid1"      # Etcd backup monitoring
      ca_backup_healthcheck_url: "https://hc-ping.com/uuid2"   # CA backup monitoring
```

## Complete Example

```yaml
# group_vars/all/etcd.yaml

# ============================================================================
# DEFAULT SETTINGS (apply to ALL clusters)
# ============================================================================

# Network
etcd_ports:
  client: 2379
  peer: 2380

# Load balancer (disabled by default)
etcd_lb_enabled: false
etcd_lb_host: ""
etcd_lb_port: 2379
etcd_lb_ip: ""

# Certificates
etcd_cert_alt_names:
  - "etcd.kube-system.svc.{{ dns_domain }}"
  - "etcd.kube-system.svc"
etcd_cert_alt_ips: []

# Backup configuration
etcd_backup_cron_enabled: true
etcd_backup_interval: "*/30"
etcd_backup_retention_days: 90
etcd_backup_distributed: true
etcd_backup_independent: false
etcd_backup_online_only: false

# CA backup configuration
ca_backup_cron_enabled: true
ca_backup_check_interval: "*/5"
ca_backup_retention_days: 365

# Performance
etcd_heartbeat_interval: 250
etcd_election_timeout: 5000
etcd_snapshot_count: 10000
etcd_compaction_retention: "8"
etcd_quota_backend_bytes: 0
etcd_metrics: "extensive"

# Systemd
etcd_systemd_timeout_start_sec: "60s"
etcd_systemd_restart_sec: "15s"
etcd_systemd_limit_nofile: 40000

# Security
etcd_secure_client: true
etcd_peer_client_auth: true

# step-ca
step_ca_runtime_minutes: 60
step_ca_port: 9000

# Monitoring
backup_healthcheck_url: ""
ca_backup_healthcheck_url: ""

# ============================================================================
# OPTIONAL PER-CLUSTER OVERRIDES (only specify differences)
# ============================================================================
etcd_cluster_configs:
  
  # Production Kubernetes cluster (with load balancer)
  k8s:
    # Load balancer for stable client endpoint
    lb:
      enabled: true
      host: "etcd-k8s.internal.example.com"
      ip: "10.0.1.100"
    
    # Include LB in server certificate SANs
    cert:
      alt_names: ["etcd-k8s.internal.example.com", "etcd.kube-system.svc"]
      alt_ips: ["10.0.1.100"]
    
    # Custom S3 prefix
    backup:
      s3_prefix: "prod/k8s/"
    
    # Monitoring
    monitoring:
      backup_healthcheck_url: "https://hc-ping.com/k8s-backup"
      ca_backup_healthcheck_url: "https://hc-ping.com/k8s-ca"
  
  # Events cluster (different ports, no LB)
  k8s-events:
    ports: { client: 2381, peer: 2382 }
    
    # No load balancer for events
    lb:
      enabled: false
    
    # Less frequent backups
    backup:
      interval: "*/60"
      s3_prefix: "prod/events/"
      retention_days: 30
    
    ca_backup:
      check_interval: "*/10"
      retention_days: 180
    
    # Lower resource limits
    performance:
      quota_backend_bytes: "4G"
      snapshot_count: 5000
      metrics: "basic"
    
    systemd:
      memory_limit: "2G"
      cpu_quota: "100%"
  
  # Development cluster (minimal resources)
  dev:
    ports: { client: 2383, peer: 2384 }
    
    # Daily backups only
    backup:
      interval: "0 2 * * *"
      s3_prefix: "dev/"
      retention_days: 7
      distributed: false
      online_only: true
    
    # No CA backups
    ca_backup:
      enabled: false
    
    # Minimal resources
    performance:
      quota_backend_bytes: "2G"
      metrics: "basic"
    
    systemd:
      memory_limit: "1G"
      cpu_quota: "100%"
    
    # step-ca always running (easier dev workflow)
    step_ca:
      runtime_minutes: 0
  
  # High-performance cluster (large database, tuned)
  high-perf:
    ports: { client: 2387, peer: 2388 }
    
    lb:
      enabled: true
      host: "etcd-perf.internal"
      ip: "10.0.1.200"
    
    cert:
      alt_names: ["etcd-perf.internal"]
      alt_ips: ["10.0.1.200"]
    
    # Frequent backups
    backup:
      interval: "*/15"
      s3_prefix: "prod/perf/"
    
    # High performance tuning
    performance:
      heartbeat_interval: 200
      election_timeout: 3000
      quota_backend_bytes: "16G"
      snapshot_count: 100000
      compaction_retention: "12"
      metrics: "extensive"
    
    # High resource limits
    systemd:
      timeout_start_sec: "120s"
      limit_nofile: 65536
      nice_level: -10
      ionice_class: 1
      ionice_priority: 0
      memory_limit: "8G"
      cpu_quota: "400%"
```

**Key points:**
- Top-level variables are **always the defaults**
- Only specify overrides in `etcd_cluster_configs`
- Unspecified settings inherit from top-level defaults
- Dict merging happens automatically (no YAML anchors needed)

**Key points:**
- Top-level variables are **always the defaults**
- Only specify overrides in `etcd_cluster_configs`
- Unspecified settings inherit from top-level defaults
- Dict merging happens automatically (no YAML anchors needed)

## Inventory Setup

### Option 1: Separate Host Groups

```ini
# inventory.ini

[etcd-k8s]
node1 ansible_host=10.0.1.10
node2 ansible_host=10.0.1.11
node3 ansible_host=10.0.1.12

[etcd-k8s-events]
node1 ansible_host=10.0.1.10
node2 ansible_host=10.0.1.11
node3 ansible_host=10.0.1.12

[etcd:children]
etcd-k8s
etcd-k8s-events

[etcd-cert-managers]
node1
```

### Option 2: Same Nodes, Different Plays

```yaml
# playbook
- hosts: etcd
  vars:
    etcd_cluster_name: k8s
    etcd_cluster_group: etcd  # Use same group
  roles:
    - etcd3/cluster

- hosts: etcd
  vars:
    etcd_cluster_name: k8s-events
    etcd_cluster_group: etcd
  roles:
    - etcd3/cluster
```

## Deployment

### Deploy Cluster(s) - Unified Approach

```bash
# ALWAYS the same command (1 cluster or multiple clusters)
ansible-playbook -i inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create -b

# The playbook automatically:
# 1. Detects how many clusters are in etcd_cluster_configs
# 2. Deploys single cluster directly, or loops through all clusters
# 3. Uses same code path regardless of cluster count (DRY)
```

### Override Cluster Name (Optional)

```bash
# Deploy specific cluster only (when you have multiple configured)
ansible-playbook -i inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_cluster_name=k8s \
  -e etcd_cluster_group=etcd-k8s \
  -e etcd_action=create -b

# Or use --limit
ansible-playbook -i inventory.ini playbooks/etcd-cluster.yaml \
  -e etcd_action=create -b \
  --limit=etcd-k8s
```

## How It Works (DRY - Same Path for All Deployments)

1. **You define** cluster configs in `etcd_cluster_configs` (1 or more clusters)
2. **Facts role discovers** all clusters and determines deployment mode
3. **Facts role merges** cluster-specific settings with defaults for each cluster
4. **Cluster role adapts:**
   - Single cluster → direct deployment
   - Multiple clusters → loops internally (same install logic)
5. **All roles** inherit the merged configuration

**Key insight:** Whether deploying 1 cluster or 100 clusters, the code path is identical. Only difference is a loop when multiple clusters are detected.

### Example Merge

**Step 1: Define defaults (top-level variables):**
```yaml
# roles/etcd3/defaults/main.yaml OR group_vars/all/etcd.yaml
etcd_ports: { client: 2379, peer: 2380 }
etcd_backup_interval: "*/30"
etcd_backup_retention_days: 90
etcd_backup_distributed: true
etcd_upload_backup:
  storage: s3
  bucket: "my-bucket"
  prefix: "etcd/"
```

**Step 2: Define overrides (only what's different):**
```yaml
# group_vars/all/etcd.yaml
etcd_cluster_configs:
  k8s-events:
    ports:
      client: 2381  # Override client port
      # peer: 2380 would inherit from default ports
    backup:
      interval: "*/60"  # Override interval
      s3_prefix: "etcd/events/"  # Override S3 prefix
      retention_days: 30  # Override retention
      # distributed: true (inherited)
      # enabled: true (inherited)
```

**Step 3: Automatic merge (happens in facts role):**
```yaml
# Final values for k8s-events cluster:
etcd_ports: { client: 2381, peer: 2382 }  # Merged: client overridden, peer from default
etcd_backup_interval: "*/60"  # Override value
etcd_backup_retention_days: 30  # Override value
etcd_backup_distributed: true  # Inherited from default
etcd_upload_backup:
  storage: s3
  bucket: "my-bucket"
  prefix: "etcd/events/"  # Merged into etcd_upload_backup dict
```

**Merging strategy:**
- **Dict merging** for `etcd_ports` - partial overrides allowed
- **Individual key lookup** for other settings - each optional
- **Dict combine** for `etcd_upload_backup` - updates prefix only

## Benefits

### Before (Manual Per-Cluster Variables)

```yaml
# playbooks/multi-cluster.yaml
- hosts: etcd-k8s
  vars:
    etcd_cluster_name: k8s
    etcd_ports: { client: 2379, peer: 2380 }
    etcd_backup_interval: "*/30"
    etcd_backup_s3_prefix: "etcd/k8s/"
    etcd_backup_retention_days: 90
    etcd_backup_distributed: true
    ca_backup_cron_enabled: true
    # ... repeat 10+ variables ...

- hosts: etcd-events
  vars:
    etcd_cluster_name: k8s-events
    etcd_ports: { client: 2381, peer: 2382 }
    etcd_backup_interval: "*/60"
    etcd_backup_s3_prefix: "etcd/events/"
    etcd_backup_retention_days: 30
    etcd_backup_distributed: true
    ca_backup_cron_enabled: true
    # ... repeat same 10+ variables ...
```

### After (Cluster Configs with Defaults)

```yaml
# group_vars/all/etcd.yaml

# Define defaults ONCE (apply to all clusters)
etcd_ports: { client: 2379, peer: 2380 }
etcd_backup_interval: "*/30"
etcd_backup_retention_days: 90
etcd_backup_distributed: true
ca_backup_cron_enabled: true

# Optional overrides (only specify what's different)
etcd_cluster_configs:
  k8s:
    # Uses all defaults, only override S3 prefix
    backup:
      s3_prefix: "etcd/k8s/"
  k8s-events:
    # Different ports and backup cadence
    ports: { client: 2381, peer: 2382 }
    backup:
      interval: "*/60"
      s3_prefix: "etcd/events/"
      retention_days: 30

# playbooks/multi-cluster.yaml (SIMPLE)
- hosts: etcd-k8s
  vars:
    etcd_cluster_name: k8s      # That's it!
    etcd_cluster_group: etcd-k8s
  roles:
    - etcd3/cluster

- hosts: etcd-events
  vars:
    etcd_cluster_name: k8s-events
    etcd_cluster_group: etcd-k8s-events
  roles:
    - etcd3/cluster
```

**Advantages:**
- ✅ Single source of truth (all cluster configs in one file)
- ✅ Easy to compare settings between clusters
- ✅ Less repetition in playbooks
- ✅ Automatic merging (only override what's different)
- ✅ Works with existing single-cluster deployments (backward compatible)

## Verification

Check which settings were applied:

```bash
# View merged configuration for k8s cluster
ansible etcd-k8s -i inventory.ini -m debug \
  -a "msg='Ports: {{ etcd_ports }}, Backup: {{ etcd_backup_interval }}'" \
  -e etcd_cluster_name=k8s

# View merged configuration for events cluster
ansible etcd-k8s-events -i inventory.ini -m debug \
  -a "msg='Ports: {{ etcd_ports }}, Backup: {{ etcd_backup_interval }}'" \
  -e etcd_cluster_name=k8s-events
```

## Migration from Manual Variables

If you already have multi-cluster playbooks with manual variables:

1. **Extract** cluster-specific variables to `etcd_cluster_configs`
2. **Remove** duplicate vars from playbooks
3. **Keep** only `etcd_cluster_name` and `etcd_cluster_group`

**Example migration:**

```yaml
# OLD playbook (repetitive)
- hosts: etcd-events
  vars:
    etcd_cluster_name: k8s-events
    etcd_cluster_group: etcd-events
    etcd_ports: { client: 2381, peer: 2382 }
    etcd_backup_interval: "*/60"
    etcd_backup_retention_days: 30
    etcd_backup_distributed: true  # Same as other clusters
    ca_backup_cron_enabled: true  # Same as other clusters

# NEW playbook (clean)
- hosts: etcd-events
  vars:
    etcd_cluster_name: k8s-events
    etcd_cluster_group: etcd-events

# Set defaults ONCE in group_vars/all/etcd.yaml:
etcd_ports: { client: 2379, peer: 2380 }  # Default ports
etcd_backup_distributed: true  # Default for all
ca_backup_cron_enabled: true  # Default for all

# Override only differences per cluster:
etcd_cluster_configs:
  k8s-events:
    ports: { client: 2381, peer: 2382 }  # Override ports only
    backup:
      interval: "*/60"  # Override interval only
      retention_days: 30  # Override retention only
      # distributed: true (inherited from top-level default)
```

## Important: Local vs S3 Retention

**Key distinction:**
- `local_retention_days` - Controls **local disk** cleanup only
- S3 retention requires **separate S3 lifecycle policies**

The backup scripts automatically clean up old files from local disk but do **NOT** delete from S3. You must configure S3 lifecycle policies separately.

**Example S3 lifecycle policy:**
```json
{
  "Rules": [
    {
      "Id": "delete-old-k8s-backups",
      "Status": "Enabled",
      "Filter": { "Prefix": "prod/k8s/" },
      "Expiration": { "Days": 90 }
    },
    {
      "Id": "delete-old-events-backups",
      "Status": "Enabled",
      "Filter": { "Prefix": "prod/events/" },
      "Expiration": { "Days": 30 }
    }
  ]
}
```

Apply with:
```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket your-org-etcd-backups \
  --lifecycle-configuration file://lifecycle-policy.json
```

## Complete Variable Reference

### Network & Load Balancer
- `ports.client` - Client API port (default: 2379)
- `ports.peer` - Peer communication port (default: 2380)
- `lb.enabled` - Enable load balancer mode (default: false)
- `lb.host` - Load balancer hostname
- `lb.port` - Load balancer port (default: same as client port)
- `lb.ip` - Load balancer VIP (optional)

### Certificates
- `cert.alt_names` - Additional DNS SANs (list)
- `cert.alt_ips` - Additional IP SANs (list)

### Backup
- `backup.enabled` - Enable/disable backups (default: true)
- `backup.interval` - Backup interval (default: "*/30")
- `backup.s3_prefix` - S3 path prefix (default: "etcd/")
- `backup.local_retention_days` - Local disk retention in days (default: 90, S3 requires lifecycle policy)
- `backup.distributed` - Multi-node coordination (default: true)
- `backup.independent` - Skip deduplication (default: false)
- `backup.online_only` - Only backup when healthy (default: false)

### CA Backup
- `ca_backup.enabled` - Enable/disable CA backups (default: true)
- `ca_backup.check_interval` - Check frequency (default: "0 * * * *" - every hour)
- `ca_backup.local_retention_days` - Local disk retention in days (default: 365, S3 requires lifecycle policy)

### Performance
- `performance.heartbeat_interval` - Raft heartbeat ms (default: 250)
- `performance.election_timeout` - Raft election ms (default: 5000)
- `performance.snapshot_count` - Txns before snapshot (default: 10000)
- `performance.compaction_retention` - History hours (default: "8")
- `performance.quota_backend_bytes` - Max DB size (default: 0=unlimited)
- `performance.metrics` - Metrics level (default: "extensive")

### Systemd Service
- `systemd.timeout_start_sec` - Startup timeout (default: "60s")
- `systemd.restart_sec` - Restart delay (default: "15s")
- `systemd.limit_nofile` - Max file descriptors (default: 40000)
- `systemd.nice_level` - CPU priority -20 to 19 (default: unset)
- `systemd.ionice_class` - I/O class 0-3 (default: unset)
- `systemd.ionice_priority` - I/O priority 0-7 (default: unset)
- `systemd.memory_limit` - Memory limit (default: unset)
- `systemd.cpu_quota` - CPU quota percentage (default: unset)

### Security
- `security.secure_client` - Require client certs (default: true)
- `security.peer_client_auth` - Require peer certs (default: true)

### step-ca
- `step_ca.runtime_minutes` - Auto-shutdown time (default: 60, 0=infinite)
- `step_ca.port` - step-ca API port (default: 9000)

### Monitoring
- `monitoring.backup_healthcheck_url` - Etcd backup ping URL
- `monitoring.ca_backup_healthcheck_url` - CA backup ping URL

## Defining Defaults vs Overrides

**Pattern: Top-level variables = defaults, cluster configs = optional overrides**

```yaml
# group_vars/all/etcd.yaml

# ============================================================================
# STEP 1: Define defaults (apply to ALL clusters)
# ============================================================================
# These are your baseline settings

etcd_ports:
  client: 2379
  peer: 2380

etcd_backup_cron_enabled: true
etcd_backup_interval: "*/30"
etcd_backup_retention_days: 90
etcd_backup_distributed: true

ca_backup_cron_enabled: true
ca_backup_check_interval: "*/5"
ca_backup_retention_days: 365

# ============================================================================
# STEP 2: Define per-cluster overrides (only what's different)
# ============================================================================
# These override defaults for specific clusters

etcd_cluster_configs:
  
  # k8s cluster: Inherits all defaults, only adds custom S3 prefix
  k8s:
    backup:
      s3_prefix: "etcd/k8s/"
      # enabled: true (inherited)
      # interval: "*/30" (inherited)
      # retention_days: 90 (inherited)
      # distributed: true (inherited)
  
  # k8s-events: Overrides ports and backup cadence
  k8s-events:
    ports:
      client: 2381  # Override (different port)
      peer: 2382    # Override (different port)
    backup:
      interval: "*/60"  # Override (less frequent)
      s3_prefix: "etcd/events/"
      retention_days: 30  # Override (shorter)
      # enabled: true (inherited)
      # distributed: true (inherited)
  
  # dev: Overrides many settings for dev environment
  dev:
    ports:
      client: 2383
      peer: 2384
    backup:
      interval: "0 2 * * *"  # Override (daily)
      retention_days: 7  # Override (1 week)
      distributed: false  # Override (single-node)
      online_only: true  # Override (only when healthy)
      s3_prefix: "dev/"
      # enabled: true (inherited)
    ca_backup:
      enabled: false  # Override (disable CA backups in dev)
  
  # legacy: Minimal overrides to disable backups
  legacy:
    ports:
      client: 2385
      peer: 2386
    backup:
      enabled: false  # Override (disable all backups)
      # All other backup settings don't matter when disabled
    ca_backup:
      enabled: false  # Override (disable CA backups)
```

**How merging works:**

1. **Top-level variables** are loaded first (the defaults)
2. **Cluster config** is retrieved: `etcd_cluster_configs[etcd_cluster_name]`
3. **Dict merging** combines top-level with cluster-specific:
   - `etcd_ports` merged with `cluster_config.ports` (if exists)
   - Each backup setting checked individually with `.get()`
4. **Result:** Only overridden values change, rest stay at defaults

**Example for k8s-events cluster:**
```yaml
# Top-level (defaults)
etcd_ports: { client: 2379, peer: 2380 }
etcd_backup_interval: "*/30"
etcd_backup_retention_days: 90

# Cluster config override
ports: { client: 2381, peer: 2382 }
backup: { interval: "*/60", retention_days: 30 }

# Final merged result
etcd_ports: { client: 2381, peer: 2382 }  # Merged dict
etcd_backup_interval: "*/60"  # Override value
etcd_backup_retention_days: 30  # Override value
etcd_backup_distributed: true  # Inherited from default
```

## Real-World Examples

### Example 1: Production with High Availability

```yaml
etcd_cluster_configs:
  prod-k8s:
    # Stable load-balanced endpoint
    lb:
      enabled: true
      host: "etcd.prod.internal"
      ip: "10.0.1.100"
    
    # Include LB in certificates
    cert:
      alt_names: ["etcd.prod.internal", "etcd.kube-system.svc"]
      alt_ips: ["10.0.1.100"]
    
    # Frequent backups with monitoring
    backup:
      interval: "*/20"  # Every 20 minutes
      s3_prefix: "prod/k8s/"
      retention_days: 180  # 6 months
    
    monitoring:
      backup_healthcheck_url: "https://hc-ping.com/prod-backup"
      ca_backup_healthcheck_url: "https://hc-ping.com/prod-ca"
```

### Example 2: Cost-Optimized Non-Production

```yaml
etcd_cluster_configs:
  staging:
    ports: { client: 2381, peer: 2382 }
    
    # No load balancer (save costs)
    lb:
      enabled: false
    
    # Minimal backups
    backup:
      interval: "0 */6 * * *"  # Every 6 hours
      s3_prefix: "staging/"
      retention_days: 14
      distributed: false
    
    ca_backup:
      enabled: false  # No CA backups
    
    # Reduced resources
    performance:
      quota_backend_bytes: "2G"
      metrics: "basic"
    
    systemd:
      memory_limit: "1G"
      cpu_quota: "50%"
```

### Example 3: Large Database Cluster

```yaml
etcd_cluster_configs:
  large-db:
    # Performance optimized
    performance:
      heartbeat_interval: 200       # Faster
      election_timeout: 3000        # Faster
      quota_backend_bytes: "16G"    # Large DB
      snapshot_count: 100000        # Less frequent snapshots
      compaction_retention: "12"    # More history
    
    # High resource limits
    systemd:
      timeout_start_sec: "180s"     # Longer startup for large DB
      limit_nofile: 65536
      nice_level: -10               # High priority
      ionice_class: 1               # Realtime I/O
      memory_limit: "8G"
      cpu_quota: "400%"             # 4 cores
    
    # More frequent backups
    backup:
      interval: "*/15"
      s3_prefix: "prod/large-db/"
```

### Example 4: Multi-Region Setup

```yaml
etcd_cluster_configs:
  # US East cluster
  us-east:
    ports: { client: 2379, peer: 2380 }
    lb:
      enabled: true
      host: "etcd-us-east.internal"
      ip: "10.1.0.100"
    backup:
      s3_prefix: "us-east/k8s/"
    monitoring:
      backup_healthcheck_url: "https://hc-ping.com/us-east-backup"
  
  # EU West cluster
  eu-west:
    ports: { client: 2379, peer: 2380 }
    lb:
      enabled: true
      host: "etcd-eu-west.internal"
      ip: "10.2.0.100"
    backup:
      s3_prefix: "eu-west/k8s/"
    monitoring:
      backup_healthcheck_url: "https://hc-ping.com/eu-west-backup"
```

## See Also

- [Multi-Cluster Deployment](multi-cluster.md)
- [Custom Configuration](custom-config.md)
- [Backup & Restore](../operations/backup-restore.md)
- [Load Balancer Integration](load-balancer.md)
