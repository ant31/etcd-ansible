# Introduction to etcd-ansible

## What is etcd-ansible?

etcd-ansible is a comprehensive Ansible automation solution for deploying and managing production-grade etcd clusters. It provides end-to-end automation for certificate management, backup/restore operations, and cluster lifecycle management.

## Why Use etcd-ansible?

### Traditional Challenges

Deploying and managing etcd clusters traditionally involves:

- ❌ Manual certificate generation and distribution
- ❌ Complex certificate renewal processes
- ❌ No automated backup strategies
- ❌ Difficult disaster recovery procedures
- ❌ Manual cluster scaling
- ❌ Error-prone configuration management

### etcd-ansible Solution

With etcd-ansible, you get:

- ✅ **Automated Certificate Management**: Smallstep CA handles all certificate operations
- ✅ **Zero-Downtime Renewals**: Certificates automatically renew before expiration
- ✅ **Integrated Backups**: Automated encrypted backups to S3 with AWS KMS
- ✅ **Easy Disaster Recovery**: Simple playbooks for CA and data restoration
- ✅ **Cluster Scaling**: Add or remove nodes with single commands
- ✅ **Production Ready**: Tested and hardened for production use

## Key Components

### 1. Smallstep CA Integration

- Modern certificate authority running on designated cert-manager nodes
- Automatic certificate issuance via REST API
- Built-in certificate renewal via systemd timers
- 2-year certificate lifetime (configurable)

### 2. Ansible Roles

```
roles/etcd3/
├── cluster/           # Cluster lifecycle management
├── certs/smallstep/   # Smallstep CA integration
├── facts/             # Cluster facts and variables
├── backups/           # Backup automation
├── backups/cron/      # Automated backup scheduling
├── restore/           # Disaster recovery
└── download/          # Binary downloads
```

### 3. Playbooks

Pre-built playbooks for common operations:

- `etcd.yaml` - Main cluster deployment
- `backup-ca.yaml` - CA key backup
- `restore-ca.yaml` - CA key restoration
- `restore-etcd-cluster.yaml` - Data restoration
- `replicate-ca.yaml` - CA key replication for HA

### 4. Security Features

- **Private Keys Never Transmitted**: Generated locally on each node
- **AWS KMS Encryption**: CA backups encrypted with AWS KMS
- **Role-Based Access**: IAM-based access control
- **Audit Trail**: Complete CloudTrail logging of all operations
- **Automated Rotation**: Certificates renew automatically

## Architecture Overview

### Single Cluster

```
┌─────────────────────────────────────────────────────────┐
│ Cert-Manager Node (etcd-k8s-1)                          │
│ - etcd cluster member                                   │
│ - step-ca service (port 9000)                           │
│ - CA keys in /etc/step-ca/secrets/                      │
└─────────────────────────────────────────────────────────┘
                         │
                         │ HTTPS
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
    ┌────────┐      ┌────────┐      ┌────────┐
    │etcd-k8s-2│    │etcd-k8s-3│    │ clients │
    │+ step CLI│    │+ step CLI│    │+ step CLI│
    └────────┘      └────────┘      └────────┘
```

### High Availability Setup

```
┌─────────────────────────────────────────────────────────┐
│ Primary Cert-Manager (etcd-k8s-1)                       │
│ - step-ca RUNNING                                       │
│ - CA keys active                                        │
└─────────────────────────────────────────────────────────┘
                         │
                         │ CA key replication
                         ▼
┌─────────────────────────────────────────────────────────┐
│ Backup Cert-Manager (etcd-k8s-2)                        │
│ - step-ca STOPPED (ready for failover)                  │
│ - CA keys replicated                                    │
└─────────────────────────────────────────────────────────┘
```

## How It Works

### 1. Initial Deployment

```bash
ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=create
```

This single command:

1. Sets up step-ca on cert-manager node
2. Initializes CA with root and intermediate certificates
3. Installs step CLI on all nodes
4. Generates certificates for all nodes (2-year lifetime)
5. Configures automatic renewal (at 2/3 of lifetime)
6. Deploys etcd cluster
7. Configures automated backups

### 2. Certificate Management

Certificates are automatically managed throughout their lifecycle:

1. **Issuance**: Nodes request certificates from step-ca
2. **Storage**: Private keys stored locally (never transmitted)
3. **Renewal**: Systemd timers renew at ~487 days (for 2-year certs)
4. **Rotation**: Zero-downtime reload of etcd after renewal

### 3. Backup & Recovery

- **Automated Backups**: 
  - CA backups when changed
  - Etcd data backups every 30 minutes (configurable)
  - Encrypted with AWS KMS
  - Uploaded to S3 with retention policy

- **Disaster Recovery**:
  - Simple playbooks for restoration
  - Multiple recovery scenarios supported
  - Detailed runbooks included

## Supported Platforms

### Operating Systems

- Ubuntu 20.04+
- Debian 11+
- RHEL 8+
- CentOS 8+
- Rocky Linux 8+
- CoreOS (stable)

### Etcd Versions

- v3.5.x (recommended)
- v3.6.x (latest)

### Requirements

- **Ansible**: 2.9 or later
- **Python**: 3.6 or later on all nodes
- **AWS CLI**: For S3 backups and KMS encryption
- **Network**: 
  - Port 2379 (client)
  - Port 2380 (peer)
  - Port 9000 (step-ca)

## Comparison with Alternatives

| Feature | etcd-ansible | Manual Setup | cfssl | cert-manager (K8s) |
|---------|-------------|--------------|-------|-------------------|
| Automated Deployment | ✅ | ❌ | ⚠️ Partial | ✅ |
| Certificate Automation | ✅ | ❌ | ❌ | ✅ |
| Auto Renewal | ✅ | ❌ | ❌ | ✅ |
| Backup Automation | ✅ | ❌ | ❌ | ⚠️ Partial |
| Disaster Recovery | ✅ | ⚠️ Manual | ⚠️ Manual | ⚠️ Partial |
| Non-Kubernetes | ✅ | ✅ | ✅ | ❌ |
| Production Ready | ✅ | ⚠️ Complex | ⚠️ Complex | ✅ |
| Learning Curve | Low | High | Medium | Medium |

## Use Cases

### 1. Kubernetes etcd Backend

Deploy dedicated etcd clusters for Kubernetes control plane:

```ini
[etcd]
k8s-etcd-1 ansible_host=10.0.1.10
k8s-etcd-2 ansible_host=10.0.1.11
k8s-etcd-3 ansible_host=10.0.1.12

[etcd-clients]
k8s-master-1 ansible_host=10.0.2.10
k8s-master-2 ansible_host=10.0.2.11
k8s-master-3 ansible_host=10.0.2.12
```

### 2. Application Configuration Store

Centralized configuration management for distributed applications:

```ini
[etcd]
config-etcd-1 ansible_host=10.0.3.10
config-etcd-2 ansible_host=10.0.3.11
config-etcd-3 ansible_host=10.0.3.12

[etcd-clients]
app-server-1 ansible_host=10.0.4.10
app-server-2 ansible_host=10.0.4.11
```

### 3. Service Discovery

etcd as service registry for microservices:

```ini
[etcd]
discovery-etcd-1 ansible_host=10.0.5.10
discovery-etcd-2 ansible_host=10.0.5.11
discovery-etcd-3 ansible_host=10.0.5.12

[etcd-clients]
service-mesh-nodes ansible_host=10.0.6.[10:50]
```

### 4. Multi-Cluster Setup

Separate clusters for different purposes:

- Primary cluster for main data
- Events cluster for event streaming
- Configuration cluster for settings

## Getting Started

Ready to deploy your first cluster? Continue to:

- [Prerequisites](prerequisites.md) - System requirements and preparation
- [Quick Start](quick-start.md) - Deploy your first cluster in 15 minutes
- [Installation Guide](../installation/deployment.md) - Detailed deployment instructions

## Next Steps

Once you're familiar with the basics:

1. [Inventory Setup](../installation/inventory.md) - Configure your inventory
2. [AWS KMS Setup](../installation/kms-setup.md) - Configure encrypted backups
3. [Operations Guide](../operations/cluster-management.md) - Day-2 operations
4. [Certificate Management](../certificates/overview.md) - Deep dive into certificates
