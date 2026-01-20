# Variables Reference

Complete reference of all configurable variables.

## Cluster Variables

```yaml
etcd_cluster_name: default        # Cluster name
etcd_version: v3.5.26            # etcd version
etcd_cluster_group: etcd         # Inventory group for cluster members
etcd_clients_group: etcd-clients # Inventory group for clients
```

## Certificate Variables

```yaml
step_version: "0.25.2"
step_ca_version: "0.25.2"
step_ca_port: 9000
step_cert_default_duration: "17520h"  # 2 years
```

## Backup Variables

### Schedule & Retention

```yaml
etcd_backup_cron_enabled: true
etcd_backup_interval: "*/30"
ca_backup_cron_enabled: true
etcd_backup_retention_days: 90
ca_backup_retention_days: 365
```

### S3 Configuration (etcd Data)

Required for automated S3 backups of etcd data.

```yaml
etcd_upload_backup:
  storage: s3
  bucket: "your-bucket-name"
  access_key: "AWS_ACCESS_KEY"  # Optional if using IAM roles
  secret_key: "AWS_SECRET_KEY"  # Optional if using IAM roles
  region: "us-east-1"
  prefix: ""                    # Optional object prefix
```

### Monitoring

```yaml
backup_healthcheck_enabled: false
backup_healthcheck_url: ""      # URL to ping on success
ca_backup_healthcheck_url: ""
```

## Network Variables

```yaml
etcd_ports:
  client: 2379
  peer: 2380
```

### Certificate SANs

Add extra Subject Alternative Names to certificates.

```yaml
etcd_cert_alt_names:
  - "etcd.internal"
  - "etcd.cluster.local"

etcd_cert_alt_ips:
  - "10.0.1.100"  # Load balancer IP
```

## Performance Variables

```yaml
etcd_heartbeat_interval: 250
etcd_election_timeout: 5000
etcd_snapshot_count: 10000
etcd_compaction_retention: "8"
```

## Related Documentation

- [Commands Reference](commands.md)
- [Architecture](architecture.md)
