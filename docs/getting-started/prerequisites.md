# Prerequisites

Before deploying etcd-ansible, ensure your environment meets these requirements.

## System Requirements

### Control Node (Your Laptop/Workstation)

**Required:**

- **Operating System**: Linux, macOS, or WSL2 on Windows
- **Ansible**: Version 2.9 or later
- **Python**: Version 3.6 or later
- **Git**: For cloning the repository
- **SSH Client**: For connecting to target nodes

**Optional but Recommended:**

- **AWS CLI**: Version 2.x for S3 backups and KMS encryption
- **jq**: For JSON processing in scripts
- **yq**: For YAML processing

**Installation:**

```bash
# On Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y ansible python3-pip git awscli jq

# On macOS
brew install ansible awscli jq

# On RHEL/CentOS
sudo yum install -y ansible python3-pip git awscli jq

# Verify versions
ansible --version
python3 --version
aws --version
```

### Target Nodes (etcd Servers)

**Minimum Requirements per Node:**

- **CPU**: 2 cores (4+ recommended for production)
- **RAM**: 2 GB (8+ GB recommended for production)
- **Disk**: 20 GB (SSD strongly recommended)
- **Network**: 1 Gbps (10 Gbps recommended for production)

**Operating Systems Supported:**

- Ubuntu 20.04 LTS or later
- Debian 11 or later
- RHEL 8 or later
- CentOS 8 or later (CentOS Stream)
- Rocky Linux 8 or later
- CoreOS (stable channel)

**Required Software:**

- **Python**: 3.6+ (usually pre-installed)
- **systemd**: For service management
- **tar/gzip**: For backup operations
- **openssl**: For certificate operations

### Cluster Sizing

**Development/Testing:**

- **Nodes**: 1-3 nodes
- **Purpose**: Testing, development environments
- **HA**: Not required

**Production:**

- **Nodes**: 3, 5, or 7 (odd number for quorum)
- **Purpose**: Production workloads
- **HA**: Required (multiple cert-managers recommended)

**Cluster Size Guidelines:**

| Nodes | Fault Tolerance | Use Case |
|-------|----------------|----------|
| 1 | None | Development only |
| 3 | 1 node failure | Small production |
| 5 | 2 node failures | Medium production |
| 7 | 3 node failures | Large production |

!!! warning "Odd Number Required"
    Always use an odd number of nodes (3, 5, 7) for production to maintain quorum during failures.

## Network Requirements

### Ports

**Required Ports:**

| Port | Protocol | Purpose | Source | Destination |
|------|----------|---------|--------|-------------|
| 22 | TCP | SSH | Control node | All etcd nodes |
| 2379 | TCP | etcd client | Clients | All etcd nodes |
| 2380 | TCP | etcd peer | etcd nodes | etcd nodes |
| 9000 | TCP | step-ca | All nodes | Cert-manager nodes |

**Firewall Rules:**

```bash
# On each etcd node, allow these ports:

# SSH (from control node)
sudo ufw allow from <control-node-ip> to any port 22 proto tcp

# etcd client port (from clients)
sudo ufw allow from <client-network> to any port 2379 proto tcp

# etcd peer port (from other etcd nodes)
sudo ufw allow from <etcd-node-1-ip> to any port 2380 proto tcp
sudo ufw allow from <etcd-node-2-ip> to any port 2380 proto tcp
sudo ufw allow from <etcd-node-3-ip> to any port 2380 proto tcp

# step-ca (from all nodes)
sudo ufw allow from <any-node-ip> to any port 9000 proto tcp
```

### DNS/Hostname Resolution

**Option 1: DNS (Recommended)**

Configure DNS records for all nodes:

```
etcd-k8s-1.example.com  A  10.0.1.10
etcd-k8s-2.example.com  A  10.0.1.11
etcd-k8s-3.example.com  A  10.0.1.12
```

**Option 2: /etc/hosts**

Add entries on all nodes:

```bash
# /etc/hosts on all nodes
10.0.1.10  etcd-k8s-1
10.0.1.11  etcd-k8s-2
10.0.1.12  etcd-k8s-3
```

### Network Latency

**Recommendations:**

- **Same Datacenter**: < 1ms latency (ideal)
- **Same Region**: < 10ms latency (acceptable)
- **Cross-Region**: Not recommended for production

**Test Latency:**

```bash
# From control node to each etcd node
ping -c 10 etcd-k8s-1
ping -c 10 etcd-k8s-2
ping -c 10 etcd-k8s-3

# Between etcd nodes (run from etcd-k8s-1)
ssh etcd-k8s-1 "ping -c 10 etcd-k8s-2"
ssh etcd-k8s-1 "ping -c 10 etcd-k8s-3"
```

## AWS Requirements (Optional)

If using S3 backups and KMS encryption:

### IAM Permissions

**For etcd Nodes:**

Create IAM role with these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3BackupAccess",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::your-etcd-backups",
        "arn:aws:s3:::your-etcd-backups/*"
      ]
    },
    {
      "Sid": "KMSAccess",
      "Effect": "Allow",
      "Action": [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:DescribeKey",
        "kms:GenerateDataKey"
      ],
      "Resource": "arn:aws:kms:*:*:key/*",
      "Condition": {
        "StringEquals": {
          "kms:ResourceAliases": "alias/etcd-ca-backup"
        }
      }
    }
  ]
}
```

**For Control Node/CI:**

If running Ansible from AWS (e.g., CodeBuild, EC2):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "kms:CreateKey",
        "kms:CreateAlias",
        "kms:DescribeKey",
        "kms:PutKeyPolicy"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:CreateBucket",
        "s3:PutBucketVersioning",
        "s3:PutBucketEncryption",
        "s3:PutPublicAccessBlock"
      ],
      "Resource": "arn:aws:s3:::your-etcd-backups"
    }
  ]
}
```

### S3 Bucket

Create S3 bucket for backups:

```bash
# Create bucket
aws s3 mb s3://your-org-etcd-backups --region us-east-1

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket your-org-etcd-backups \
  --versioning-configuration Status=Enabled

# Block public access
aws s3api put-public-access-block \
  --bucket your-org-etcd-backups \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

## SSH Access

### SSH Key Setup

**Generate SSH key (if needed):**

```bash
# Generate new SSH key
ssh-keygen -t rsa -b 4096 -C "ansible@etcd-cluster" -f ~/.ssh/etcd-ansible

# Copy to all target nodes
ssh-copy-id -i ~/.ssh/etcd-ansible.pub user@etcd-k8s-1
ssh-copy-id -i ~/.ssh/etcd-ansible.pub user@etcd-k8s-2
ssh-copy-id -i ~/.ssh/etcd-ansible.pub user@etcd-k8s-3
```

**Configure SSH config:**

```bash
# ~/.ssh/config
Host etcd-k8s-*
  IdentityFile ~/.ssh/etcd-ansible
  User ansible
  StrictHostKeyChecking no
  UserKnownHostsFile=/dev/null
```

### Sudo Access

Target nodes must allow passwordless sudo:

```bash
# On each target node
sudo visudo

# Add this line:
ansible ALL=(ALL) NOPASSWD:ALL
```

**Test SSH access:**

```bash
# Test from control node
ansible all -i inventory.ini -m ping
```

Expected output:
```
etcd-k8s-1 | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
etcd-k8s-2 | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
etcd-k8s-3 | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
```

## Storage Requirements

### Disk Layout

**Recommended Partition Scheme:**

```
/               - 20 GB (OS)
/var/lib/etcd   - 50+ GB (etcd data, SSD strongly recommended)
/opt            - 10 GB (binaries)
/var/log        - 10 GB (logs)
```

**Check Disk Space:**

```bash
# On each etcd node
df -h /var/lib/etcd
df -h /opt
df -h /var/log
```

### SSD vs HDD

| Disk Type | Read Latency | Write Latency | Recommendation |
|-----------|-------------|---------------|----------------|
| SSD | < 1ms | < 1ms | **Strongly recommended** |
| HDD | 5-10ms | 10-20ms | Only for testing |

!!! danger "Production Requirement"
    SSD storage is **strongly recommended** for production. HDD will cause performance issues and may lead to cluster instability.

**Test Disk Performance:**

```bash
# Install fio
sudo apt-get install fio

# Test write performance
sudo fio --name=write-test --ioengine=libaio --rw=randwrite \
  --bs=4k --size=1G --numjobs=1 --iodepth=32 \
  --runtime=60 --time_based --end_fsync=1 \
  --directory=/var/lib/etcd

# Look for:
# SSD: > 10,000 IOPS
# HDD: < 100 IOPS (not suitable)
```

## Time Synchronization

Accurate time synchronization is critical for etcd.

**Install and Configure NTP:**

```bash
# On Ubuntu/Debian
sudo apt-get install -y chrony
sudo systemctl enable --now chronyd

# On RHEL/CentOS
sudo yum install -y chrony
sudo systemctl enable --now chronyd

# Verify synchronization
chronyc tracking
```

Expected output:
```
Reference ID    : A9FEA97B (ntp.example.com)
Stratum         : 3
Ref time (UTC)  : Mon Jan 20 15:30:00 2026
System time     : 0.000000234 seconds slow of NTP time
Last offset     : -0.000000123 seconds
RMS offset      : 0.000000456 seconds
```

**Maximum Time Drift:**

- **Acceptable**: < 50ms
- **Warning**: 50-100ms
- **Critical**: > 100ms

## Security Requirements

### SELinux/AppArmor

**SELinux (RHEL/CentOS):**

```bash
# Check status
getenforce

# Option 1: Disable (not recommended for production)
sudo setenforce 0
sudo sed -i 's/^SELINUX=enforcing$/SELINUX=permissive/' /etc/selinux/config

# Option 2: Configure policies (recommended)
# Create custom policy for etcd/step-ca
```

**AppArmor (Ubuntu/Debian):**

```bash
# Check status
sudo aa-status

# Disable for etcd/step-ca if needed
sudo ln -s /etc/apparmor.d/usr.bin.etcd /etc/apparmor.d/disable/
sudo apparmor_parser -R /etc/apparmor.d/usr.bin.etcd
```

### Firewall

**UFW (Ubuntu/Debian):**

```bash
# Enable UFW
sudo ufw enable

# Configure rules (see Network Requirements section)
```

**firewalld (RHEL/CentOS):**

```bash
# Enable firewalld
sudo systemctl enable --now firewalld

# Add rules
sudo firewall-cmd --permanent --add-port=2379/tcp
sudo firewall-cmd --permanent --add-port=2380/tcp
sudo firewall-cmd --permanent --add-port=9000/tcp
sudo firewall-cmd --reload
```

## Verification Checklist

Before proceeding with installation, verify:

- [ ] Control node has Ansible 2.9+
- [ ] Python 3.6+ on all nodes
- [ ] SSH key-based authentication working
- [ ] Passwordless sudo configured
- [ ] All required ports open in firewall
- [ ] DNS/hostname resolution working
- [ ] Network latency < 10ms between nodes
- [ ] SSD storage for /var/lib/etcd
- [ ] Time synchronization configured
- [ ] AWS credentials configured (if using S3)
- [ ] KMS key created (if using KMS encryption)

**Run Verification Script:**

```bash
# Save as verify-prerequisites.sh
#!/bin/bash

echo "Checking Ansible version..."
ansible --version | head -1

echo "Checking Python version..."
python3 --version

echo "Checking SSH connectivity..."
ansible all -i inventory.ini -m ping

echo "Checking sudo access..."
ansible all -i inventory.ini -m shell -a "sudo whoami" -b

echo "Checking disk space..."
ansible all -i inventory.ini -m shell -a "df -h /var/lib/etcd /opt" -b

echo "Checking time synchronization..."
ansible all -i inventory.ini -m shell -a "chronyc tracking" -b

echo "Done! Check output above for any errors."
```

## Next Steps

Once all prerequisites are met:

1. [Quick Start Guide](quick-start.md) - Deploy your first cluster
2. [Inventory Setup](../installation/inventory.md) - Configure your inventory
3. [KMS Setup](../installation/kms-setup.md) - Configure encrypted backups
4. [Deployment Guide](../installation/deployment.md) - Detailed deployment instructions
