# Architecture

Technical architecture of etcd-ansible.

## Role Structure

```
roles/etcd3/
├── cluster/           # Cluster lifecycle
│   ├── install/       # Deploy etcd
│   └── delete/        # Remove cluster
├── certs/smallstep/   # Certificate management
├── facts/             # Cluster facts
├── backups/           # Snapshot creation
├── backups/cron/      # Automated backups
├── restore/           # Disaster recovery
└── download/          # Binary downloads
```

## Certificate Flow

```
step-ca (cert-manager) → HTTPS → step CLI (nodes) → Certificates
```

## Backup Flow

```
etcd → snapshot → KMS encrypt → S3 upload
```

## Related Documentation

- [Variables Reference](variables.md)
- [Commands Reference](commands.md)
- [FAQ](faq.md)
