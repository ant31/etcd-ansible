# etcd-ansible Documentation

Welcome to the comprehensive documentation for **etcd-ansible** - a production-ready Ansible automation for deploying and managing etcd clusters with automated certificate management using Smallstep CA.

## Overview

etcd-ansible provides a complete automation solution for:

- **Automated Certificate Management** - Smallstep CA with automatic 2-year certificate renewal
- **High Availability** - Multi-node clusters with automated CA key replication
- **Secure by Default** - Industry-standard PKI, private keys never transmitted
- **Zero-Downtime Operations** - Rolling upgrades and certificate renewal
- **Disaster Recovery** - AWS KMS encrypted backups with automated restore
- **Production Ready** - Battle-tested in production environments

## Key Features

### 🔐 Security First
- Private keys generated locally on each node (never transmitted)
- AWS KMS encryption for CA backups
- Automatic certificate rotation
- Industry-standard PKI with Smallstep CA

### 🚀 Easy to Deploy
- Single command cluster deployment
- Automated certificate issuance
- Integrated backup configuration
- Comprehensive verification

### 🔄 Operational Excellence
- Zero-downtime upgrades
- Automated backups with retention
- Health check monitoring
- Easy cluster scaling

### 📚 Well Documented
- Step-by-step guides
- Real-world examples
- Troubleshooting guides
- Complete reference documentation

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
