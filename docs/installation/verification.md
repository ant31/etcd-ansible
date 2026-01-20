# Deployment Verification

Comprehensive guide to verify your etcd cluster deployment.

## Quick Verification Checklist

- [ ] etcd cluster is healthy
- [ ] step-ca is running
- [ ] Certificates are valid
- [ ] Automatic renewal is configured
- [ ] Backups are configured
- [ ] Data can be written and read

## 1. Verify etcd Cluster Health

### Check Cluster Status

```bash
# From any etcd node
sudo etcdctl \
  --endpoints=https://etcd-k8s-1:2379,https://etcd-k8s-2:2379,https://etcd-k8s-3:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  endpoint health
```

Expected output:
```
https://etcd-k8s-1:2379 is healthy: successfully committed proposal: took = 2.345ms
https://etcd-k8s-2:2379 is healthy: successfully committed proposal: took = 2.456ms
https://etcd-k8s-3:2379 is healthy: successfully committed proposal: took = 2.567ms
```

### Check Cluster Members

```bash
sudo etcdctl \
  --endpoints=https://etcd-k8s-1:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  member list
```

Expected output:
```
8e9e05c52164694d, started, etcd-default-1, https://10.0.1.10:2380, https://10.0.1.10:2379, false
91bc3c398fb3c146, started, etcd-default-2, https://10.0.1.11:2380, https://10.0.1.11:2379, false
fd422379fda50e48, started, etcd-default-3, https://10.0.1.12:2380, https://10.0.1.12:2379, false
```

### Check Cluster Status

```bash
sudo etcdctl \
  --endpoints=https://etcd-k8s-1:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  endpoint status --write-out=table
```

Expected output:
```
+---------------------------+------------------+---------+---------+-----------+------------+-----------+------------+--------------------+--------+
|         ENDPOINT          |        ID        | VERSION | DB SIZE | IS LEADER | IS LEARNER | RAFT TERM | RAFT INDEX | RAFT APPLIED INDEX | ERRORS |
+---------------------------+------------------+---------+---------+-----------+------------+-----------+------------+--------------------+--------+
| https://10.0.1.10:2379    | 8e9e05c52164694d |  3.5.26 |   20 kB |      true |      false |         2 |         10 |                 10 |        |
+---------------------------+------------------+---------+---------+-----------+------------+-----------+------------+--------------------+--------+
```

## 2. Verify step-ca Service

### Check Service Status

```bash
# On cert-manager node
sudo systemctl status step-ca
```

Expected output:
```
● step-ca.service - Smallstep Certificate Authority
   Loaded: loaded (/etc/systemd/system/step-ca.service; enabled; vendor preset: enabled)
   Active: active (running) since Mon 2026-01-20 15:30:00 UTC; 10min ago
```

### Check Health Endpoint

```bash
curl -k https://etcd-k8s-1:9000/health
```

Expected output:
```json
{"status":"ok"}
```

### Check CA Files

```bash
# On cert-manager node
sudo ls -la /etc/step-ca/secrets/
```

Expected output:
```
total 20
drwx------ 2 root root 4096 Jan 20 15:30 .
drwxr-xr-x 5 root root 4096 Jan 20 15:30 ..
-r-------- 1 root root  227 Jan 20 15:30 intermediate_ca_key
-r-------- 1 root root   32 Jan 20 15:30 password
-r-------- 1 root root  227 Jan 20 15:30 root_ca_key
```

## 3. Verify Certificates

### Check Certificate Expiration

```bash
# On any etcd node
sudo step certificate inspect /etc/etcd/ssl/etcd-k8s-1-peer.crt
```

Look for:
```
Certificate:
    Data:
        Version: 3 (0x2)
        Serial Number:
            1234567890abcdef
    Signature Algorithm: ECDSA-SHA256
        Issuer: CN=etcd-default-ca Intermediate CA
        Validity
            Not Before: Jan 20 15:30:00 2026 GMT
            Not After : Jan 20 15:30:00 2028 GMT  # 2 years
        Subject: CN=etcd-k8s-1
```

### Check All Certificate Files

```bash
# On etcd node
sudo ls -la /etc/etcd/ssl/
```

Expected files:
```
total 48
drwxr-xr-x 2 etcd etcd 4096 Jan 20 15:30 .
drwxr-xr-x 4 root root 4096 Jan 20 15:30 ..
lrwxrwxrwx 1 etcd etcd   13 Jan 20 15:30 client-ca.crt -> root_ca.crt
-rw-r--r-- 1 etcd etcd  989 Jan 20 15:30 etcd-k8s-1-client.crt
-r-------- 1 etcd etcd  227 Jan 20 15:30 etcd-k8s-1-client.key
-rw-r--r-- 1 etcd etcd  989 Jan 20 15:30 etcd-k8s-1-peer.crt
-r-------- 1 etcd etcd  227 Jan 20 15:30 etcd-k8s-1-peer.key
-rw-r--r-- 1 etcd etcd  989 Jan 20 15:30 etcd-k8s-1-server.crt
-r-------- 1 etcd etcd  227 Jan 20 15:30 etcd-k8s-1-server.key
lrwxrwxrwx 1 etcd etcd   13 Jan 20 15:30 peer-ca.crt -> root_ca.crt
-rw-r--r-- 1 etcd etcd 1001 Jan 20 15:30 root_ca.crt
```

### Verify Certificate Chain

```bash
# Verify peer certificate
sudo openssl verify -CAfile /etc/etcd/ssl/root_ca.crt /etc/etcd/ssl/etcd-k8s-1-peer.crt
```

Expected output:
```
/etc/etcd/ssl/etcd-k8s-1-peer.crt: OK
```

## 4. Verify Automatic Renewal

### Check Renewal Timers

```bash
# On any etcd node
sudo systemctl list-timers 'step-renew-*'
```

Expected output:
```
NEXT                         LEFT          LAST  PASSED  UNIT
Tue 2026-01-21 03:00:00 UTC  11h left      -     -       step-renew-etcd-k8s-1-client.timer
Tue 2026-01-21 03:00:00 UTC  11h left      -     -       step-renew-etcd-k8s-1-peer.timer
Tue 2026-01-21 03:00:00 UTC  11h left      -     -       step-renew-etcd-k8s-1-server.timer

3 timers listed.
```

### Check Renewal Services

```bash
sudo systemctl status step-renew-etcd-k8s-1-peer.service
```

### Test Manual Renewal

```bash
# Trigger renewal manually
sudo systemctl start step-renew-etcd-k8s-1-peer.service

# Check status
sudo systemctl status step-renew-etcd-k8s-1-peer.service

# View logs
sudo journalctl -u step-renew-etcd-k8s-1-peer.service -n 20
```

## 5. Verify Backups

### Check Backup Cron Jobs

```bash
# On first etcd node
sudo crontab -l | grep backup
```

Expected output:
```
*/30 * * * * /opt/etcd-backup-scripts/etcd-backup.sh >> /var/log/etcd-backups/etcd-backup.log 2>&1
```

### Check Backup Scripts

```bash
# On cert-manager node
sudo ls -la /opt/etcd-backup-scripts/
```

Expected files:
```
total 16
drwxr-xr-x 2 root root 4096 Jan 20 15:30 .
drwxr-xr-x 3 root root 4096 Jan 20 15:30 ..
-rwxr-xr-x 1 root root 2048 Jan 20 15:30 ca-backup-check.sh
-rwxr-xr-x 1 root root 3072 Jan 20 15:30 etcd-backup.sh
```

### Test Backup

```bash
# Trigger manual backup
ansible-playbook -i inventory.ini etcd.yaml \
  -e etcd_action=backup \
  --vault-password-file ~/.vault-pass -b
```

### Verify Backup in S3

```bash
# List backups
aws s3 ls s3://your-org-etcd-backups/etcd-default/ --recursive

# Check latest backup
aws s3 ls s3://your-org-etcd-backups/etcd-default/latest-snapshot.db.kms
```

## 6. Test Cluster Operations

### Write Test Data

```bash
sudo etcdctl \
  --endpoints=https://etcd-k8s-1:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  put /test/key "Hello, World!"
```

### Read Test Data

```bash
# Read from different node
sudo etcdctl \
  --endpoints=https://etcd-k8s-2:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  get /test/key
```

Expected output:
```
/test/key
Hello, World!
```

### List Keys

```bash
sudo etcdctl \
  --endpoints=https://etcd-k8s-1:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  get --prefix /test/
```

### Delete Test Data

```bash
sudo etcdctl \
  --endpoints=https://etcd-k8s-1:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  del /test/key
```

## 7. Performance Verification

### Check Latency

```bash
sudo etcdctl \
  --endpoints=https://etcd-k8s-1:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  check perf
```

Expected output:
```
 60 / 60 Boooooooooooooooooooooooooooooooooooooooooooooooooooooooooooom  !  100.00%  1m0s
PASS: Throughput is 150 writes/s
PASS: Slowest request took 0.050000s
PASS: Stddev is 0.020000s
PASS
```

### Run Benchmark

```bash
# Write benchmark
sudo benchmark --endpoints=https://etcd-k8s-1:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  put --total=10000 --key-size=8 --val-size=256
```

## Verification Checklist

### etcd Cluster
- [x] All nodes show as healthy
- [x] All members listed correctly
- [x] Leader elected
- [x] Can write and read data
- [x] Data replicates across nodes

### step-ca
- [x] Service running on cert-manager node
- [x] Health endpoint responds
- [x] CA files present with correct permissions
- [x] CA keys backed up

### Certificates
- [x] All certificate files present
- [x] Certificates valid and not expired
- [x] Certificate chain verifies
- [x] Correct permissions on private keys (0400)

### Automatic Renewal
- [x] Renewal timers enabled
- [x] Timers scheduled correctly
- [x] Manual renewal works

### Backups
- [x] Backup scripts present
- [x] Cron jobs configured
- [x] Manual backup works
- [x] Backups uploaded to S3

## Troubleshooting Verification Issues

See [Troubleshooting Guide](../troubleshooting/common-issues.md) for detailed troubleshooting.

### etcd Health Check Fails

```bash
# Check etcd logs
sudo journalctl -u etcd-default-1 -n 100

# Check if etcd is listening
sudo netstat -tlnp | grep etcd

# Check certificate files
sudo ls -la /etc/etcd/ssl/
```

### step-ca Health Check Fails

```bash
# Check step-ca logs
sudo journalctl -u step-ca -n 100

# Check if port 9000 is listening
sudo netstat -tlnp | grep 9000

# Check CA files
sudo ls -la /etc/step-ca/secrets/
```

### Certificate Verification Fails

```bash
# Check certificate details
sudo step certificate inspect /etc/etcd/ssl/etcd-k8s-1-peer.crt

# Check certificate dates
sudo openssl x509 -in /etc/etcd/ssl/etcd-k8s-1-peer.crt -noout -dates

# Verify full chain
sudo openssl verify -verbose -CAfile /etc/etcd/ssl/root_ca.crt /etc/etcd/ssl/etcd-k8s-1-peer.crt
```

## Next Steps

After successful verification:

1. [Operations Guide](../operations/cluster-management.md) - Learn day-2 operations
2. [Backup & Restore](../operations/backup-restore.md) - Backup and restore procedures
3. [Certificate Management](../certificates/overview.md) - Certificate operations
4. [Monitoring](../operations/health-checks.md) - Setup monitoring and alerting
