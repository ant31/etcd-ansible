# AWS KMS Setup

Configure AWS KMS (Key Management Service) for encrypting etcd CA backups.

## Why KMS?

**Advantages over GPG:**

- ✅ Organization-owned encryption keys
- ✅ IAM-based access control (no personal keys)
- ✅ Automatic key rotation
- ✅ Full audit trail in CloudTrail
- ✅ No key management burden
- ✅ Integrates with S3 server-side encryption

**Problems with GPG:**

- ❌ Keys tied to individual employees
- ❌ Employee leaves = backups become inaccessible
- ❌ Complex key distribution
- ❌ Manual key rotation required
- ❌ No centralized audit trail

## Quick Setup (Automated)

Use the provided Ansible playbook:

```bash
ansible-playbook playbooks/setup-kms.yaml \
  -e kms_key_alias=alias/etcd-ca-backup \
  -e step_ca_backup_kms_principal="arn:aws:iam::123456789012:role/etcd-nodes"
```

**What it does:**

1. Creates KMS key with description
2. Creates alias for easy reference
3. Configures key policy for etcd nodes
4. Displays configuration to add to vault.yml

**Output:**

```
✅ KMS key setup complete!

KMS Key Alias: alias/etcd-ca-backup
KMS Key ID: 1234abcd-12ab-34cd-56ef-1234567890ab

Add to your vault.yml:
  step_ca_backup_kms_key_id: "alias/etcd-ca-backup"
  
Test encryption:
  echo "test" | aws kms encrypt --key-id alias/etcd-ca-backup --plaintext fileb:///dev/stdin --output text --query CiphertextBlob
```

## Manual Setup

### Step 1: Create KMS Key

```bash
# Create the key
aws kms create-key \
  --description "Encryption key for etcd CA backups" \
  --tags TagKey=Purpose,TagValue=etcd-ca-backup TagKey=ManagedBy,TagValue=ansible \
  --region us-east-1

# Save the KeyId from output
# Example output:
{
  "KeyMetadata": {
    "KeyId": "1234abcd-12ab-34cd-56ef-1234567890ab",
    ...
  }
}
```

### Step 2: Create Alias

Aliases make keys easier to reference:

```bash
aws kms create-alias \
  --alias-name alias/etcd-ca-backup \
  --target-key-id 1234abcd-12ab-34cd-56ef-1234567890ab \
  --region us-east-1
```

### Step 3: Configure Key Policy

Create `kms-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Enable IAM User Permissions",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::YOUR_ACCOUNT_ID:root"
      },
      "Action": "kms:*",
      "Resource": "*"
    },
    {
      "Sid": "Allow etcd nodes to encrypt and decrypt",
      "Effect": "Allow",
      "Principal": {
        "AWS": [
          "arn:aws:iam::YOUR_ACCOUNT_ID:role/etcd-nodes-role",
          "arn:aws:iam::YOUR_ACCOUNT_ID:user/etcd-admin"
        ]
      },
      "Action": [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:DescribeKey",
        "kms:GenerateDataKey"
      ],
      "Resource": "*"
    }
  ]
}
```

Apply the policy:

```bash
aws kms put-key-policy \
  --key-id alias/etcd-ca-backup \
  --policy-name default \
  --policy file://kms-policy.json \
  --region us-east-1
```

### Step 4: Grant IAM Permissions

**For EC2 Instance Profiles (Recommended):**

```bash
# Create or update IAM role for etcd nodes
aws iam put-role-policy \
  --role-name etcd-nodes-role \
  --policy-name etcd-kms-access \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:DescribeKey",
        "kms:GenerateDataKey"
      ],
      "Resource": "arn:aws:kms:us-east-1:YOUR_ACCOUNT:key/*",
      "Condition": {
        "StringEquals": {
          "kms:ResourceAliases": "alias/etcd-ca-backup"
        }
      }
    }]
  }'
```

**For IAM Users (Less Secure):**

```bash
# Create IAM user
aws iam create-user --user-name etcd-backup-user

# Attach inline policy
aws iam put-user-policy \
  --user-name etcd-backup-user \
  --policy-name kms-etcd-backup \
  --policy-document file://kms-user-policy.json

# Generate access keys
aws iam create-access-key --user-name etcd-backup-user
# Save AccessKeyId and SecretAccessKey in vault.yml
```

### Step 5: Test KMS Encryption

```bash
# Test encrypt
echo "test data" | aws kms encrypt \
  --key-id alias/etcd-ca-backup \
  --plaintext fileb:///dev/stdin \
  --output text \
  --query CiphertextBlob \
  > /tmp/encrypted.txt

# Test decrypt
aws kms decrypt \
  --ciphertext-blob fileb:///tmp/encrypted.txt \
  --output text \
  --query Plaintext \
  | base64 -d

# Should output: "test data"
```

## S3 Bucket Setup

### Create S3 Bucket

```bash
# Create bucket
aws s3 mb s3://your-org-etcd-backups --region us-east-1

# Enable versioning (recommended)
aws s3api put-bucket-versioning \
  --bucket your-org-etcd-backups \
  --versioning-configuration Status=Enabled

# Enable encryption with KMS
aws s3api put-bucket-encryption \
  --bucket your-org-etcd-backups \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms",
        "KMSMasterKeyID": "alias/etcd-ca-backup"
      }
    }]
  }'

# Block public access
aws s3api put-public-access-block \
  --bucket your-org-etcd-backups \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

### Configure Lifecycle Policy

Create `s3-lifecycle.json`:

```json
{
  "Rules": [
    {
      "Id": "Delete old CA backups",
      "Status": "Enabled",
      "Prefix": "step-ca/",
      "Expiration": {
        "Days": 90
      }
    },
    {
      "Id": "Delete old etcd snapshots",
      "Status": "Enabled",
      "Prefix": "etcd-default/",
      "Expiration": {
        "Days": 90
      }
    }
  ]
}
```

Apply lifecycle policy:

```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket your-org-etcd-backups \
  --lifecycle-configuration file://s3-lifecycle.json
```

## IAM Policy Examples

### Minimal Policy for etcd Nodes

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "KMSAccess",
      "Effect": "Allow",
      "Action": [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:DescribeKey"
      ],
      "Resource": "arn:aws:kms:*:YOUR_ACCOUNT:key/*",
      "Condition": {
        "StringEquals": {
          "kms:ResourceAliases": "alias/etcd-ca-backup"
        }
      }
    },
    {
      "Sid": "S3BackupAccess",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::your-org-etcd-backups",
        "arn:aws:s3:::your-org-etcd-backups/*"
      ]
    }
  ]
}
```

### Admin Policy for Ansible Controller

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "KMSAdmin",
      "Effect": "Allow",
      "Action": [
        "kms:CreateKey",
        "kms:CreateAlias",
        "kms:DescribeKey",
        "kms:PutKeyPolicy",
        "kms:EnableKeyRotation"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3Admin",
      "Effect": "Allow",
      "Action": [
        "s3:CreateBucket",
        "s3:PutBucketVersioning",
        "s3:PutBucketEncryption",
        "s3:PutBucketPublicAccessBlock",
        "s3:PutBucketLifecycleConfiguration"
      ],
      "Resource": "arn:aws:s3:::*etcd-backups"
    }
  ]
}
```

## Update Ansible Configuration

Add to `group_vars/all/vault.yml` (encrypted):

```yaml
# AWS KMS configuration
step_ca_backup_encryption_method: "aws-kms"
step_ca_backup_kms_key_id: "alias/etcd-ca-backup"
step_ca_backup_s3_bucket: "your-org-etcd-backups"
step_ca_backup_s3_prefix: "step-ca"

# Optional: IAM role ARN for key policy
step_ca_backup_kms_principal: "arn:aws:iam::123456789012:role/etcd-nodes-role"
```

Encrypt the file:

```bash
ansible-vault encrypt group_vars/all/vault.yml
```

## Cost Estimation

### KMS Costs

- **Key storage**: $1/month per key
- **Encryption requests**: $0.03 per 10,000 requests
- **Decryption requests**: $0.03 per 10,000 requests

**Example (daily backups):**
- 1 key = $1/month
- 30 encrypt operations/month = $0.0001
- Restore once = $0.000003
- **Total: ~$1.01/month**

### S3 Costs

- **Storage**: ~$0.023/GB/month (S3 Standard)
- **PUT requests**: $0.005 per 1,000 requests

**Example (90-day retention):**
- Backup size: 10 MB (typical CA backup)
- Daily backups: 90 backups × 10 MB = 900 MB
- Storage: 0.9 GB × $0.023 = $0.02/month
- PUT requests: 30/month = $0.00015
- **Total: ~$0.02/month**

**Combined total: ~$1.03/month**

## Security Best Practices

1. **Enable CloudTrail logging** for KMS key usage audit
2. **Use separate KMS keys** for different environments (prod/staging/dev)
3. **Enable automatic key rotation** (AWS rotates yearly)
4. **Restrict KMS key policy** to minimum required principals
5. **Use IAM roles** instead of static credentials when possible
6. **Monitor failed decrypt attempts** (possible attack indicator)
7. **Test restore procedure** quarterly to ensure it works
8. **Document key ID** in runbook (not in git)

### Enable Key Rotation

```bash
aws kms enable-key-rotation \
  --key-id alias/etcd-ca-backup
```

### Enable CloudTrail

```bash
# Create trail for KMS audit
aws cloudtrail create-trail \
  --name etcd-kms-audit \
  --s3-bucket-name etcd-audit-logs

# Start logging
aws cloudtrail start-logging \
  --name etcd-kms-audit
```

## Troubleshooting

### KMS Access Denied

```bash
# Check if you have permissions
aws kms describe-key --key-id alias/etcd-ca-backup

# Check IAM role/user permissions
aws iam get-role-policy \
  --role-name etcd-nodes-role \
  --policy-name etcd-kms-access

# Test encryption
echo "test" | aws kms encrypt \
  --key-id alias/etcd-ca-backup \
  --plaintext fileb:///dev/stdin \
  --output text \
  --query CiphertextBlob
```

### Key Not Found

```bash
# List all KMS keys
aws kms list-keys

# List all aliases
aws kms list-aliases | grep etcd

# Check if alias exists in correct region
aws kms list-aliases --region us-east-1 | grep etcd-ca-backup
```

### Decryption Fails

```bash
# Verify ciphertext format
file encrypted-backup.tar.gz.kms
# Should be: data

# Check CloudTrail for KMS errors
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=ResourceType,AttributeValue=AWS::KMS::Key \
  --max-results 10

# Verify IAM permissions include kms:Decrypt
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::ACCOUNT:role/etcd-nodes-role \
  --action-names kms:Decrypt \
  --resource-arns arn:aws:kms:us-east-1:ACCOUNT:key/KEY_ID
```

### S3 Access Denied

```bash
# Test S3 permissions
aws s3 ls s3://your-org-etcd-backups/

# Upload test file
echo "test" > /tmp/test.txt
aws s3 cp /tmp/test.txt s3://your-org-etcd-backups/test.txt

# Verify bucket policy
aws s3api get-bucket-policy --bucket your-org-etcd-backups
```

## Alternative: Symmetric Encryption

If you can't use AWS KMS, use symmetric encryption with ansible-vault:

```yaml
# In group_vars/all/vault.yml (encrypted with ansible-vault)
step_ca_backup_encryption_method: "symmetric"
step_ca_backup_password: "VERY_SECURE_PASSWORD_FROM_PASSWORD_MANAGER"
step_ca_backup_s3_bucket: "your-org-etcd-backups"
```

**Backup command:**

```bash
ansible-playbook -i inventory.ini playbooks/backup-ca.yaml \
  --vault-password-file ~/.vault-pass
```

## Next Steps

- [Initial Deployment](deployment.md) - Deploy your etcd cluster
- [Verification](verification.md) - Verify KMS and backups are working
- [Backup & Restore](../operations/backup-restore.md) - Backup and restore procedures
