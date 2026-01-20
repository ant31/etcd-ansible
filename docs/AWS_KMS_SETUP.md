# AWS KMS Setup for etcd CA Backups

This guide explains how to set up AWS KMS (Key Management Service) for encrypting etcd CA backups.

## Why KMS?

**Problems with GPG:**
- ❌ Keys tied to individual employees
- ❌ Employee leaves = backups become inaccessible
- ❌ Complex key rotation and management
- ❌ No audit trail

**Benefits of AWS KMS:**
- ✅ Organization-owned encryption keys
- ✅ IAM-based access control
- ✅ Automatic key rotation (optional)
- ✅ Full audit trail in CloudTrail
- ✅ No key management burden
- ✅ Integrates with S3 server-side encryption

## Automated Setup (Recommended)

Use the provided Ansible playbook:

```bash
ansible-playbook playbooks/setup-kms.yaml \
  -e kms_key_alias=alias/etcd-ca-backup \
  -e step_ca_backup_kms_principal="arn:aws:iam::YOUR_ACCOUNT:role/etcd-nodes"
```

This will:
1. Create KMS key with alias `alias/etcd-ca-backup`
2. Configure key policy to allow etcd nodes to encrypt/decrypt
3. Display configuration to add to `vault.yml`

## Manual Setup

### Step 1: Create KMS Key

```bash
# Create the key
aws kms create-key \
  --description "Encryption key for etcd CA backups" \
  --tags TagKey=Purpose,TagValue=etcd-ca-backup TagKey=ManagedBy,TagValue=ansible \
  --region us-east-1

# Save the KeyId from output
# Example: "KeyId": "1234abcd-12ab-34cd-56ef-1234567890ab"
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
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "kms:CallerAccount": "YOUR_ACCOUNT_ID"
        }
      }
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
    },
    {
      "Sid": "Allow CloudWatch Logs",
      "Effect": "Allow",
      "Principal": {
        "Service": "logs.YOUR_REGION.amazonaws.com"
      },
      "Action": [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:ReEncrypt*",
        "kms:GenerateDataKey*",
        "kms:CreateGrant",
        "kms:DescribeKey"
      ],
      "Resource": "*",
      "Condition": {
        "ArnLike": {
          "kms:EncryptionContext:aws:logs:arn": "arn:aws:logs:YOUR_REGION:YOUR_ACCOUNT_ID:*"
        }
      }
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

### Step 4: Grant Access to etcd Nodes

If using EC2 instance profiles (recommended):

```bash
# Attach policy to instance role
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
        "kms:DescribeKey"
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

If using IAM users:

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
# Save access key and secret key in vault.yml
```

### Step 5: Test Encryption

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

### Step 6: Update Ansible Configuration

Add to `group_vars/all/vault.yml`:

```yaml
step_ca_backup_kms_key_id: "alias/etcd-ca-backup"
step_ca_backup_s3_bucket: "your-org-etcd-backups"
```

Encrypt the file:

```bash
ansible-vault encrypt group_vars/all/vault.yml
```

## S3 Bucket Setup

Create S3 bucket for storing backups:

```bash
# Create bucket
aws s3 mb s3://your-org-etcd-backups --region us-east-1

# Enable versioning (optional but recommended)
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

# Set lifecycle policy to delete old backups
aws s3api put-bucket-lifecycle-configuration \
  --bucket your-org-etcd-backups \
  --lifecycle-configuration file://s3-lifecycle.json
```

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
    }
  ]
}
```

## IAM Permissions

### For etcd Nodes (EC2 Instance Profile)

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
        "kms:DescribeKey",
        "kms:GenerateDataKey"
      ],
      "Resource": "arn:aws:kms:*:YOUR_ACCOUNT:key/*",
      "Condition": {
        "StringEquals": {
          "kms:ResourceAliases": "alias/etcd-ca-backup"
        }
      }
    },
    {
      "Sid": "S3Access",
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

### For Ansible Controller (if running from CI/CD)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumeEtcdRole",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::YOUR_ACCOUNT:role/etcd-nodes-role"
    }
  ]
}
```

## Cost Estimation

### KMS Costs

- **Key storage**: $1/month per key
- **Encryption requests**: $0.03 per 10,000 requests
- **Decryption requests**: $0.03 per 10,000 requests

**Example cost for daily backups:**
- 1 key = $1/month
- 30 encrypt operations/month = $0.0001
- Restore once = $0.000003
- **Total: ~$1.01/month**

### S3 Costs

- **Storage**: ~$0.023/GB/month (S3 Standard)
- **PUT requests**: $0.005 per 1,000 requests

**Example cost for 90-day retention:**
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

## Troubleshooting

### KMS Access Denied

```bash
# Check if you have permissions
aws kms describe-key --key-id alias/etcd-ca-backup

# Check IAM role/user permissions
aws iam get-role-policy --role-name etcd-nodes-role --policy-name etcd-kms-access

# Test encryption
echo "test" | aws kms encrypt --key-id alias/etcd-ca-backup --plaintext fileb:///dev/stdin --output text --query CiphertextBlob
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
```

## References

- [AWS KMS Documentation](https://docs.aws.amazon.com/kms/latest/developerguide/)
- [KMS Best Practices](https://docs.aws.amazon.com/kms/latest/developerguide/best-practices.html)
- [KMS Pricing](https://aws.amazon.com/kms/pricing/)
- [S3 Encryption](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingKMSEncryption.html)
