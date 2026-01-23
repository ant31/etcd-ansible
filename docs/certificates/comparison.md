# Certificate Operations Comparison

## Quick Reference

| Operation | What Changes | CA Status | Downtime | Frequency | Use Case |
|-----------|--------------|-----------|----------|-----------|----------|
| **check-certs** | Nothing | Unchanged | Zero | Weekly | Monitor expiration |
| **renew-certs** | Expiry dates only | Unchanged | Zero | Emergency | Force early renewal |
| **regenerate-node-certs** | New certs, new serial numbers | **Unchanged** | Zero | **Quarterly** | Routine rotation |
| **regenerate-ca** | New CA + all certs | **NEW CA** | Zero | Rare | Lost password |

## Detailed Breakdown

### 1. check-certs (Monitoring)

**What it does:**
- Checks certificate expiration dates
- Shows days until expiry
- Verifies renewal timers are active

**Command:**
```bash
make check-certs
```

**When to use:**
- Weekly monitoring
- Before planning maintenance
- After any certificate operation

**Impact:**
- Changes: NONE
- CA: Unchanged
- Downtime: Zero
- Risk: None

---

### 2. renew-certs (Emergency Renewal)

**What it does:**
- Forces immediate renewal of existing certificates
- Same certificate, just extended expiry date
- Triggers systemd renewal services

**Command:**
```bash
make renew-certs
```

**When to use:**
- Certificate expires in < 7 days (emergency)
- Auto-renewal failed and needs manual trigger
- Testing renewal process

**What changes:**
- Expiry dates: **NEW** (extended 2 years from now)
- Certificate serial numbers: Same
- Private keys: Same
- CA: Unchanged

**Impact:**
- Changes: Minimal (just expiry dates)
- CA: Unchanged
- Downtime: Zero (hot reload)
- Risk: Very low

**Example:**
```
Before:  Expires 2026-02-01 (7 days from now)
After:   Expires 2028-01-23 (2 years from now)
Serial:  Same (0xABC123...)
```

---

### 3. regenerate-node-certs (Routine Quarterly Rotation)

**What it does:**
- Deletes old node certificates completely
- Generates brand NEW certificates from existing CA
- New serial numbers, new private keys
- Rolling restart one node at a time

**Command:**
```bash
make regenerate-node-certs
```

**When to use:**
- **Quarterly certificate hygiene** (recommended every 3-6 months)
- Node certificate compromised
- Need to add new SANs (hostnames/IPs)
- Change certificate parameters

**What changes:**
- Certificates: **COMPLETELY NEW**
- Serial numbers: **NEW**
- Private keys: **NEW** (generated locally on each node)
- Expiry dates: **NEW** (fresh 2 years)
- CA: **UNCHANGED** (same root CA, same passwords)

**Impact:**
- Changes: Node certificates only
- CA: Unchanged (no password needed)
- Downtime: Zero (rolling restart maintains quorum)
- Risk: Low (routine operation)

**Example:**
```
Before:
  Peer cert:   Serial 0xABC123, expires 2026-12-01
  Server cert: Serial 0xDEF456, expires 2026-12-01
  CA:          Fingerprint abc123... (unchanged)

After:
  Peer cert:   Serial 0x789XYZ, expires 2028-01-23
  Server cert: Serial 0x456UVW, expires 2028-01-23
  CA:          Fingerprint abc123... (same!)
```

---

### 4. regenerate-ca (Disaster Recovery)

**What it does:**
- **Deletes entire CA** (root + intermediate keys)
- **Builds new CA** with NEW passwords from vault.yml
- Generates all NEW certificates from new CA
- Replicates new CA to backup cert-managers
- Rolling restart

**Command:**
```bash
# 1. Update vault.yml with NEW passwords first!
ansible-vault edit group_vars/all/vault.yml

# 2. Run regeneration
make regenerate-ca
```

**When to use (RARE):**
- ❌ **NOT for routine rotation** → use regenerate-node-certs
- ✅ Lost CA password (can't decrypt intermediate_ca_key)
- ✅ CA compromised (security incident)
- ✅ Root CA expired (CA rebuild needed)

**What changes:**
- CA: **COMPLETELY NEW** (different root CA fingerprint)
- All certificates: **NEW** (generated from new CA)
- CA passwords: **NEW** (from vault.yml)
- External clients: **MUST GET NEW CERTS** (old CA invalid)

**Impact:**
- Changes: Everything (CA + all certs)
- CA: **NEW** (different fingerprint)
- Downtime: Zero (rolling restart maintains quorum)
- Risk: **High** (external systems affected)

**Example:**
```
Before:
  CA fingerprint: abc123...
  CA password:    old-password
  All certs:      Trusted by old CA

After:
  CA fingerprint: xyz789... (DIFFERENT!)
  CA password:    new-password
  All certs:      Trusted by NEW CA
  External apps:  Need NEW certificates!
```

---

## Decision Tree

```
Need certificate operation?
│
├─ Just checking status?
│  └─→ make check-certs
│
├─ Cert expires soon (< 7 days)?
│  └─→ make renew-certs (emergency renewal)
│
├─ Routine maintenance (quarterly)?
│  └─→ make regenerate-node-certs (fresh certs, same CA)
│
├─ Lost CA password?
│  └─→ make regenerate-ca (rebuild CA - disaster recovery)
│
└─ CA compromised?
   └─→ make regenerate-ca (rebuild CA - security incident)
```

## Common Mistakes

### ❌ DON'T: Use regenerate-ca for routine rotation
```bash
# WRONG - This rebuilds the entire CA unnecessarily
make regenerate-ca  # Overkill for quarterly rotation
```

**DO:** Use regenerate-node-certs instead
```bash
# CORRECT - Routine quarterly rotation
make regenerate-node-certs  # Fresh certs, same CA
```

---

### ❌ DON'T: Use renew-certs for quarterly rotation
```bash
# WRONG - This just extends expiry, doesn't rotate keys
make renew-certs  # Same cert, same key, just renewed
```

**DO:** Use regenerate-node-certs for real rotation
```bash
# CORRECT - New certs, new keys
make regenerate-node-certs
```

---

### ❌ DON'T: Regenerate CA if you still have the password
```bash
# WRONG - If you have CA password, keep using it!
make regenerate-ca  # Breaks external clients unnecessarily
```

**DO:** Use regenerate-node-certs instead
```bash
# CORRECT - Rotate certs without changing CA
make regenerate-node-certs
```

---

## Frequency Recommendations

| Operation | Frequency | Why |
|-----------|-----------|-----|
| check-certs | **Weekly** | Monitor for issues |
| renew-certs | **As needed** | Only if auto-renewal fails |
| regenerate-node-certs | **Quarterly** | Certificate hygiene best practice |
| regenerate-ca | **Never*** | Only for disaster recovery |

\* regenerate-ca should only be used when CA password is lost or CA is compromised

---

## Examples

### Routine Quarterly Rotation (Most Common)

```bash
# Check current status
make check-certs

# Rotate node certificates (safe, zero downtime)
make regenerate-node-certs INVENTORY=inventory/prod/inventory.ini

# Verify
make health
```

**Result:**
- ✅ Fresh 2-year certificates
- ✅ New private keys
- ✅ Same CA (no external changes)
- ✅ Zero downtime

---

### Emergency Renewal (Auto-renewal Failed)

```bash
# Cert expires in 3 days!
make check-certs  # Shows: "Expires in 3 days"

# Force immediate renewal
make renew-certs INVENTORY=inventory/prod/inventory.ini

# Verify
make check-certs  # Shows: "Expires in 730 days"
```

**Result:**
- ✅ Extended expiry immediately
- ✅ Same certificate (just renewed)
- ✅ Zero downtime

---

### Disaster Recovery (Lost CA Password)

```bash
# Error: "x509: decryption password incorrect"

# 1. Generate new passwords
openssl rand -base64 32  # Use for step_ca_password
openssl rand -base64 32  # Use for step_provisioner_password

# 2. Update vault
ansible-vault edit inventory/prod/group_vars/all/vault.yml
# Set NEW passwords

# 3. Rebuild CA
make regenerate-ca INVENTORY=inventory/prod/inventory.ini

# 4. Update external clients (Kubernetes, etc.)
# They need NEW certificates from NEW CA
```

**Result:**
- ✅ New CA with new passwords
- ⚠️ External clients need new certificates
- ✅ Zero downtime (rolling restart)

---

## Summary

**For 99% of use cases:**
- **Monitoring**: `make check-certs` (weekly)
- **Routine**: `make regenerate-node-certs` (quarterly)

**For emergencies only:**
- **Auto-renewal broken**: `make renew-certs`
- **Lost CA password**: `make regenerate-ca`
