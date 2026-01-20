# Certificate Architecture - Smallstep CA

**Last Updated**: 2026-01-20  
**Implementation**: Smallstep CA (step-ca)  
**Status**: Production-ready

## Quick Reference

### File Locations

**On step-ca node (cert-manager):**
```
/etc/step-ca/
├── config/ca.json              # CA configuration
├── certs/root_ca.crt           # Root CA (public)
├── secrets/root_ca_key         # Root CA key (PRIVATE)
├── certs/intermediate_ca.crt   # Intermediate CA (public)
├── secrets/intermediate_ca_key # Intermediate CA key (PRIVATE)
├── secrets/password            # CA password (PRIVATE)
└── db/                         # Certificate database

/opt/bin/
├── step-ca                     # CA server binary
└── step                        # CLI tool
```

**On each etcd/client node:**
```
/etc/etcd/ssl/
├── etcd-k8s-X-peer.crt         # Peer certificate (public)
├── etcd-k8s-X-peer.key         # Peer private key (PRIVATE)
├── etcd-k8s-X-server.crt       # Server certificate (public)
├── etcd-k8s-X-server.key       # Server private key (PRIVATE)
├── etcd-k8s-X-client.crt       # Client certificate (public)
├── etcd-k8s-X-client.key       # Client private key (PRIVATE)
├── root_ca.crt                 # Root CA (public)
├── peer-ca.crt → root_ca.crt   # Symlink for compatibility
└── client-ca.crt → root_ca.crt # Symlink for compatibility

/opt/bin/
└── step                        # CLI tool
```

### Certificate Lifecycle

| Certificate Type | Lifetime | Renewal Trigger | Auto-Renewal |
|------------------|----------|-----------------|--------------|
| Root CA | 10 years | Manual | No |
| Intermediate CA | 10 years | Manual | No |
| Peer Certificate | 2 years | 487 days (2/3) | Yes (systemd timer) |
| Server Certificate | 2 years | 487 days (2/3) | Yes (systemd timer) |
| Client Certificate | 2 years | 487 days (2/3) | Yes (systemd timer) |

### Service Endpoints

- **step-ca**: `https://<cert-manager-node>:9000`
- **Health check**: `https://<cert-manager-node>:9000/health`

### Systemd Units

**On step-ca node:**
- `step-ca.service` - CA server

**On each etcd node:**
- `step-renew-<etcd-name>-peer.service` - Peer cert renewal
- `step-renew-<etcd-name>-peer.timer` - Peer cert renewal timer
- `step-renew-<etcd-name>-server.service` - Server cert renewal
- `step-renew-<etcd-name>-server.timer` - Server cert renewal timer
- `step-renew-<etcd-name>-client.service` - Client cert renewal
- `step-renew-<etcd-name>-client.timer` - Client cert renewal timer

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Cert-Manager Node (First etcd node)                     │
│                                                          │
│  ┌────────────────────────────────────────────────┐    │
│  │ step-ca (systemd service)                      │    │
│  │ - Listens on port 9000 (HTTPS)                 │    │
│  │ - Issues certificates via REST API             │    │
│  │ - Stores CA keys in /etc/step-ca/secrets/      │    │
│  │ - Certificate database in /etc/step-ca/db/     │    │
│  └────────────────────────────────────────────────┘    │
│                                                          │
│  etcd process also runs here                            │
└─────────────────────────────────────────────────────────┘
                         │
                         │ HTTPS (port 9000)
                         │ Certificate requests
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ etcd node 2  │  │ etcd node 3  │  │ client node  │
│              │  │              │  │              │
│ step CLI     │  │ step CLI     │  │ step CLI     │
│ + timers     │  │ + timers     │  │ + timer      │
│              │  │              │  │              │
│ Requests     │  │ Requests     │  │ Requests     │
│ certs from   │  │ certs from   │  │ certs from   │
│ step-ca      │  │ step-ca      │  │ step-ca      │
└──────────────┘  └──────────────┘  └──────────────┘
```

## Security Properties

### Private Key Security

✅ **Private keys NEVER leave their origin node**
- step-ca generates key pairs locally using `step ca certificate`
- Private key is written directly to node's filesystem
- Only the certificate (public part) comes from step-ca

✅ **CA keys never leave cert-manager node**
- Root and intermediate CA keys in `/etc/step-ca/secrets/`
- File permissions: 0400 (read-only by root)
- Can be backed up encrypted to other nodes for redundancy

✅ **No credentials in Ansible**
- Ansible never sees private keys
- Passwords stored in ansible-vault (encrypted)
- Communication over SSH (encrypted)

### Certificate Issuance Flow

1. Node runs: `step ca certificate <name> <cert-path> <key-path>`
2. step CLI generates key pair locally
3. step CLI sends certificate request to step-ca via HTTPS
4. step-ca validates request and signs certificate
5. step-ca returns signed certificate to node
6. step CLI saves certificate and key locally

**Security**: Only the certificate request and signed certificate traverse the network (both public data).

## Deployment

### Initial Deployment

```bash
# Deploy entire cluster with Smallstep certs
ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=create
```

This will:
1. Install step-ca on cert-manager node
2. Initialize CA with root and intermediate certificates
3. Install step CLI on all nodes
4. Request and install certificates for all nodes
5. Configure automatic renewal
6. Deploy etcd cluster

### Adding a New Node

```bash
# Add node to inventory first
# Then run limited to new node
ansible-playbook -i inventory.ini etcd.yaml --limit=new-node-name
```

The new node will:
1. Install step CLI
2. Bootstrap trust with step-ca
3. Request its certificates
4. Configure automatic renewal
5. Join the etcd cluster

## Operations

### Check Certificate Status

```bash
# On any node, check certificate expiration
step certificate inspect /etc/etcd/ssl/etcd-k8s-1-peer.crt

# Check renewal timer status
systemctl list-timers 'step-renew-*'
```

### Manual Certificate Renewal

```bash
# Force renewal of a specific certificate
systemctl start step-renew-etcd-k8s-1-peer.service

# Check renewal logs
journalctl -u step-renew-etcd-k8s-1-peer.service
```

### Check step-ca Health

```bash
# On cert-manager node
systemctl status step-ca

# Via API
curl -k https://localhost:9000/health
```

### Backup CA Keys

```bash
# On cert-manager node
tar czf step-ca-backup.tar.gz /etc/step-ca/secrets /etc/step-ca/config

# Encrypt
gpg --encrypt --recipient admin@example.com step-ca-backup.tar.gz

# Store securely (e.g., S3)
aws s3 cp step-ca-backup.tar.gz.gpg s3://backups/step-ca/
```

## Configuration

### Change Certificate Lifetime

Edit `roles/etcd3/certs/smallstep/defaults/main.yml`:

```yaml
# Certificate settings
step_cert_default_duration: "17520h"  # 2 years (current default)
step_cert_max_duration: "26280h"      # 3 years
step_cert_min_duration: "1h"
```

Then re-run deployment for new certificates.

### Disable Automatic Renewal

```bash
# On specific node
systemctl disable --now step-renew-etcd-k8s-1-peer.timer
systemctl disable --now step-renew-etcd-k8s-1-server.timer
systemctl disable --now step-renew-etcd-k8s-1-client.timer
```

### Change Renewal Schedule

Edit timer files in `/etc/systemd/system/step-renew-*.timer`:

```ini
[Timer]
# Change from daily at 3 AM to weekly on Sunday at 2 AM
OnCalendar=Sun *-*-* 02:00:00
```

Then reload systemd: `systemctl daemon-reload`

## Troubleshooting

### Certificate Request Fails

**Symptom**: `step ca certificate` command fails

**Check**:
1. Is step-ca running? `systemctl status step-ca`
2. Can node reach step-ca? `curl -k https://<cert-manager>:9000/health`
3. Are provisioner credentials correct?
4. Check step-ca logs: `journalctl -u step-ca -n 100`

### Certificate Renewal Fails

**Symptom**: Timer runs but certificate not renewed

**Check**:
1. Check renewal service logs: `journalctl -u step-renew-<name>.service`
2. Verify certificate is eligible for renewal (< 1/3 lifetime remaining)
3. Check step-ca is reachable
4. Verify provisioner credentials

### etcd Won't Start After Certificate Update

**Symptom**: etcd fails to start after certificate renewal

**Check**:
1. Verify certificate file permissions (0644 for .crt, 0400 for .key)
2. Verify certificate ownership (should be `etcd` user)
3. Verify certificate validity: `step certificate verify /etc/etcd/ssl/etcd-k8s-1-peer.crt --roots /etc/etcd/ssl/root_ca.crt`
4. Check etcd logs: `journalctl -u etcd-<cluster-name>-<index>`

## Migration

### From Old cfssl Setup

If you have an existing cluster with cfssl-based certificates:

1. **Backup everything**:
   ```bash
   ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=backup
   ```

2. **Deploy step-ca on cert-manager** (doesn't affect running cluster):
   ```bash
   ansible-playbook -i inventory.ini etcd.yaml --tags=step-ca --limit=<cert-manager-node>
   ```

3. **Migrate one node at a time**:
   ```bash
   # For each non-cert-manager node
   ansible-playbook -i inventory.ini etcd.yaml --limit=etcd-k8s-2
   # Wait for node to rejoin cluster with new certs
   # Verify cluster health
   # Continue with next node
   ```

4. **Migrate cert-manager last**:
   ```bash
   ansible-playbook -i inventory.ini etcd.yaml --limit=<cert-manager-node>
   ```

5. **Clean up old certificates**:
   ```bash
   # On each node, after verifying new certs work
   rm -f /etc/etcd/ssl/*.pem
   ```

## References

- [Smallstep Documentation](https://smallstep.com/docs/)
- [step-ca Production Guide](https://smallstep.com/docs/step-ca/certificate-authority-server-production)
- [Role README](roles/etcd3/certs/smallstep/README.md)
- [Workflow Documentation](csr_workflow_clarification.md)
