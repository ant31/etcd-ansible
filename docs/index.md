# etcd-ansible Repository Documentation

Complete documentation for **this Ansible repository** that automates etcd cluster deployment with Smallstep CA certificate management.

## What This Repository Does

This Ansible repository automates:

- **Deploying etcd clusters** - Via roles in `roles/etcd3/cluster/`
- **Managing certificates with Smallstep CA** - Via `roles/etcd3/certs/smallstep/`
- **Automated backups** - Via `roles/etcd3/backups/` and `roles/etcd3/backups/cron/`
- **Disaster recovery** - Via `roles/etcd3/restore/` and playbooks in `playbooks/`
- **Binary downloads** - Via `roles/etcd3/download/`

## Repository Structure

```
etcd-ansible/
├── roles/
│   ├── etcd3/                      # Main etcd automation
│   │   ├── cluster/                # Cluster lifecycle (install/delete)
│   │   │   ├── install/            # Deploy etcd cluster
│   │   │   └── delete/             # Remove cluster
│   │   ├── certs/smallstep/        # Smallstep CA integration
│   │   ├── facts/                  # Generate cluster facts for templates
│   │   ├── backups/                # Snapshot creation
│   │   ├── backups/cron/           # Automated backup scheduling
│   │   ├── restore/                # Restore from backups
│   │   └── download/               # Download etcd/step-ca binaries
│   └── adduser/                    # Create etcd system user
├── playbooks/                      # Ready-to-use playbooks
│   ├── backup-ca.yaml              # Backup CA keys to S3
│   ├── restore-ca.yaml             # Restore CA from backup node
│   ├── restore-ca-from-backup.yaml # Restore CA from S3
│   ├── restore-etcd-cluster.yaml   # Restore etcd data
│   ├── replicate-ca.yaml           # Replicate CA to backup nodes
│   └── setup-kms.yaml              # Setup AWS KMS key
├── etcd.yaml                       # Main playbook (cluster operations)
├── inventory.ini                   # Your cluster inventory
├── group_vars/all/vault.yml        # Encrypted secrets (ansible-vault)
└── Makefile                        # Convenient make targets
```

## Required Ansible Inventory Groups

### 🔴 CRITICAL: Three Required Groups

Your inventory **MUST** define these three groups:

#### 1. `[etcd]` - Cluster Member Nodes
```ini
[etcd]
etcd-k8s-1 ansible_host=10.0.1.10
etcd-k8s-2 ansible_host=10.0.1.11
etcd-k8s-3 ansible_host=10.0.1.12
```
Nodes that run the etcd cluster service.

#### 2. `[etcd-cert-managers]` - Step-CA Nodes
```ini
[etcd-cert-managers]
etcd-k8s-1  # Primary: step-ca runs here
etcd-k8s-2  # Backup: CA keys replicated, step-ca stopped
```
**CRITICAL:** These nodes run step-ca and hold CA private keys.
- Must be subset of `[etcd]` group
- First node runs step-ca service
- Additional nodes get CA keys for failover

#### 3. `[etcd-clients]` - Client Certificate Nodes (Optional)
```ini
[etcd-clients]
kube-apiserver-1 ansible_host=10.0.2.10
```
Nodes that need client certificates but don't run etcd.

## How The Automation Works

### 1. Run Main Playbook

```bash
ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=create
```

This triggers:
- `roles/etcd3/cluster/` → Orchestrates deployment
- `roles/etcd3/cluster/install/` → Deploys etcd via meta dependencies:
  - `roles/adduser/` → Creates etcd user
  - `roles/etcd3/facts/` → Generates cluster facts
  - `roles/etcd3/certs/smallstep/` → **Sets up step-ca and issues certificates**
  - `roles/etcd3/download/` → Downloads binaries
  - `roles/etcd3/backups/cron/` → Configures automated backups
  - Then installs etcd cluster

### 2. Certificate Role (`roles/etcd3/certs/smallstep/`)

**On nodes in `[etcd-cert-managers]`:**
- Installs step-ca binary
- Initializes CA (creates root/intermediate certs)
- Starts step-ca service on port 9000
- Replicates CA keys to backup cert-managers

**On all nodes:**
- Installs step CLI
- Requests certificates from step-ca
- Creates systemd renewal timers
- Private keys generated locally (never transmitted)

### 3. Backup Automation (`roles/etcd3/backups/cron/`)

Automatically configured during deployment:
- **CA backups**: When files change (every 5 min check)
- **etcd snapshots**: Every 30 minutes
- Encrypted with AWS KMS
- Uploaded to S3

### 4. Facts Role (`roles/etcd3/facts/`)

Generates variables for use in templates:
- `etcd_access_addresses` - Comma-separated endpoints
- `etcd_peer_addresses` - Peer URLs for cluster formation
- `etcd_cert_paths` - Paths to certificate files
- `etcd_members` - Dict of all cluster nodes

## Key Ansible Variables

### Cluster Control
- `etcd_action: create|upgrade|backup` - What operation to perform
- `etcd_delete_cluster: true` - Delete the cluster
- `etcd_cluster_name: default` - Cluster identifier
- `etcd_version: v3.5.26` - etcd version to install

### Required Secrets (in `group_vars/all/vault.yml`)
- `step_ca_password` - CA password
- `step_provisioner_password` - Provisioner password
- `step_ca_backup_s3_bucket` - S3 bucket name
- `step_ca_backup_kms_key_id` - KMS key for encryption

### Optional Configuration
- `etcd_backup_cron_enabled: true` - Enable automated backups
- `ca_backup_cron_enabled: true` - Enable CA backups
- `backup_healthcheck_url` - Deadman monitoring URL

## Quick Links

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } __Quick Start__

    ---

    Get your first cluster running in 15 minutes

    [:octicons-arrow-right-24: Quick Start Guide](getting-started/quick-start.md)

-   :material-server:{ .lg .middle } __Installation__

    ---

    Detailed installation and deployment guide

    [:octicons-arrow-right-24: Installation Guide](installation/deployment.md)

-   :material-backup-restore:{ .lg .middle } __Operations__

    ---

    Backup, restore, upgrade, and scale your clusters

    [:octicons-arrow-right-24: Operations Guide](operations/cluster-management.md)

-   :material-certificate:{ .lg .middle } __Certificates__

    ---

    Complete certificate management with Smallstep CA

    [:octicons-arrow-right-24: Certificate Guide](certificates/overview.md)

-   :material-book-open-variant:{ .lg .middle } __Playbooks__

    ---

    Available playbooks and how to create custom ones

    [:octicons-arrow-right-24: Playbooks Guide](playbooks/overview.md)

-   :material-help-circle:{ .lg .middle } __Troubleshooting__

    ---

    Common issues and how to resolve them

    [:octicons-arrow-right-24: Troubleshooting Guide](troubleshooting/common-issues.md)

</div>

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ etcd-k8s-1 (Cert-Manager + etcd node)                   │
│ - Runs etcd cluster member                              │
│ - Runs step-ca on port 9000                             │
│ - CA keys stored in /etc/step-ca/secrets/               │
└─────────────────────────────────────────────────────────┘
                         │
                         │ HTTPS (port 9000)
                         │ Certificate requests
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ etcd-k8s-2   │  │ etcd-k8s-3   │  │ client node  │
│ etcd member  │  │ etcd member  │  │              │
│ step CLI     │  │ step CLI     │  │ step CLI     │
│ + timers     │  │ + timers     │  │ + timer      │
└──────────────┘  └──────────────┘  └──────────────┘
```

## What's Next?

- New to etcd-ansible? Start with the [Quick Start Guide](getting-started/quick-start.md)
- Ready to deploy? Check the [Installation Guide](installation/deployment.md)
- Need to perform operations? See [Operations Guide](operations/cluster-management.md)
- Want to understand certificates? Read [Certificate Management](certificates/overview.md)

## Support

- **Documentation Issues**: Open an issue on GitHub
- **Questions**: Check the [FAQ](reference/faq.md)
- **Bugs**: Report on GitHub with reproduction steps
- **Feature Requests**: Open an issue with detailed requirements

## License

This project is licensed under the terms specified in the [LICENSE](https://github.com/your-org/etcd-ansible/blob/main/LICENSE) file.
