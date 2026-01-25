#!/usr/bin/env python3
"""
Etcd data backup script with encryption validation
Loads configuration from YAML file

Usage: etcd-backup.py --config /path/to/config.yaml [OPTIONS]

OPTIONS:
  --config PATH      Configuration file (required)
  --online-only      Only backup if cluster is healthy (abort if unhealthy)
  --dry-run          Show what would be done without making changes
  --independent      Skip recent backup check (independent mode)

Default behavior: Always backup (online or offline), filename indicates cluster health

Exit codes:
  0 - Success (backup completed)
  1 - Fatal error (backup failed)
"""

import argparse
import base64
import hashlib
import json
import logging
import os
import secrets
import subprocess
import sys
import time
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

# Optional: cryptography for KMS envelope encryption (install if using KMS)
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


class BackupError(Exception):
    """Custom exception for backup errors"""
    pass


def setup_logging() -> logging.Logger:
    """Setup logging configuration with unbuffered output"""
    # Force unbuffered stdout for immediate log visibility
    sys.stdout.reconfigure(line_buffering=True)
    
    logger = logging.getLogger('etcd-backup')
    logger.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)
    
    return logger


logger = setup_logging()


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file"""
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        logger.info(f"Configuration loaded from: {config_path}")
        return config
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)


def run_command(cmd: list, check: bool = True, capture_output: bool = True, timeout: int = 900) -> subprocess.CompletedProcess:
    """Run a shell command and return the result (default 15 minute timeout)"""
    try:
        logger.debug(f"Running command: {' '.join(str(c) for c in cmd)}")
        sys.stdout.flush()  # Ensure logs appear immediately
        
        result = subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            text=True,
            timeout=timeout
        )
        return result
    except subprocess.TimeoutExpired as e:
        logger.error(f"Command timed out after {timeout}s: {' '.join(str(c) for c in cmd)}")
        sys.stdout.flush()
        raise BackupError(f"Command timed out after {timeout}s")
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {' '.join(str(c) for c in cmd)}")
        logger.error(f"Exit code: {e.returncode}")
        if e.stderr:
            logger.error(f"Error output: {e.stderr}")
        sys.stdout.flush()
        raise


def calculate_sha256(file_path: Path) -> str:
    """Calculate SHA256 checksum of a file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def verify_s3_file_exists(config: dict, s3_path: str) -> bool:
    """Check if file exists on S3"""
    logger.info(f"Checking if file exists on S3: {s3_path}")
    try:
        run_command([
            config['bin_dir'] / 'aws', 's3api', 'head-object',
            '--bucket', config['s3_bucket'],
            '--key', s3_path
        ], check=True)
        logger.info("✓ File exists on S3")
        return True
    except subprocess.CalledProcessError:
        logger.warning("File does not exist on S3")
        return False


def verify_s3_checksum(config: dict, s3_path: str, expected_checksum: str) -> bool:
    """Download and verify S3 file checksum"""
    logger.info("Downloading file from S3 for verification...")
    temp_file = config['backup_tmp_dir'] / f"etcd-verify-{int(time.time())}.db"
    
    try:
        run_command([
            config['bin_dir'] / 'aws', 's3', 'cp',
            f"s3://{config['s3_bucket']}/{s3_path}",
            str(temp_file)
        ], check=True)
        
        logger.info("Calculating checksum of downloaded file...")
        actual_checksum = calculate_sha256(temp_file)
        
        logger.info(f"Expected: {expected_checksum}")
        logger.info(f"Actual:   {actual_checksum}")
        
        if expected_checksum == actual_checksum:
            logger.info("✓ Checksum verification PASSED")
            return True
        else:
            logger.error("✗ Checksum verification FAILED")
            return False
    finally:
        temp_file.unlink(missing_ok=True)


def encrypt_with_kms(config: dict, input_file: Path, output_file: Path) -> None:
    """Encrypt file with AWS KMS using envelope encryption (supports large files)"""
    logger.info(f"Encrypting with AWS KMS envelope encryption (key: {config['kms_key_id']})...")
    logger.info("Generating data encryption key from KMS...")
    sys.stdout.flush()
    
    # Generate a data encryption key from KMS (returns plaintext + encrypted key)
    result = run_command([
        config['bin_dir'] / 'aws', 'kms', 'generate-data-key',
        '--key-id', config['kms_key_id'],
        '--key-spec', 'AES_256',
        '--output', 'json'
    ], check=True)
    
    kms_response = json.loads(result.stdout)
    plaintext_key = base64.b64decode(kms_response['Plaintext'])
    encrypted_key = base64.b64decode(kms_response['CiphertextBlob'])
    
    logger.info("✓ Data encryption key generated")
    logger.info("Encrypting file with AES-256-GCM...")
    sys.stdout.flush()
    
    # Encrypt file with AES-256-GCM using the plaintext data key
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import secrets
    
    aesgcm = AESGCM(plaintext_key)
    nonce = secrets.token_bytes(12)  # 96-bit nonce for GCM
    
    # Read and encrypt file
    with open(input_file, 'rb') as f:
        plaintext_data = f.read()
    
    ciphertext_data = aesgcm.encrypt(nonce, plaintext_data, None)
    
    # Write envelope: encrypted_key_length (4 bytes) + encrypted_key + nonce (12 bytes) + ciphertext
    with open(output_file, 'wb') as f:
        f.write(len(encrypted_key).to_bytes(4, byteorder='big'))
        f.write(encrypted_key)
        f.write(nonce)
        f.write(ciphertext_data)
    
    # Clear sensitive data from memory
    del plaintext_key
    del plaintext_data
    
    logger.info("✓ KMS envelope encryption completed")
    sys.stdout.flush()


def decrypt_with_kms(config: dict, input_file: Path, output_file: Path) -> None:
    """Decrypt file with AWS KMS envelope encryption"""
    logger.info("Test decrypting with AWS KMS envelope encryption...")
    sys.stdout.flush()
    
    # Read envelope: encrypted_key_length + encrypted_key + nonce + ciphertext
    with open(input_file, 'rb') as f:
        encrypted_key_length = int.from_bytes(f.read(4), byteorder='big')
        encrypted_key = f.read(encrypted_key_length)
        nonce = f.read(12)
        ciphertext_data = f.read()
    
    logger.info("Decrypting data encryption key with KMS...")
    sys.stdout.flush()
    
    # Decrypt the data encryption key using KMS
    temp_key_file = config['backup_tmp_dir'] / f"temp-key-{os.getpid()}.bin"
    try:
        with open(temp_key_file, 'wb') as f:
            f.write(encrypted_key)
        
        result = run_command([
            config['bin_dir'] / 'aws', 'kms', 'decrypt',
            '--ciphertext-blob', f"fileb://{temp_key_file}",
            '--output', 'text',
            '--query', 'Plaintext'
        ], check=True)
        
        plaintext_key = base64.b64decode(result.stdout.strip())
    finally:
        temp_key_file.unlink(missing_ok=True)
    
    logger.info("✓ Data key decrypted, decrypting file...")
    sys.stdout.flush()
    
    # Decrypt file with AES-256-GCM
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    
    aesgcm = AESGCM(plaintext_key)
    plaintext_data = aesgcm.decrypt(nonce, ciphertext_data, None)
    
    # Write decrypted data
    with open(output_file, 'wb') as f:
        f.write(plaintext_data)
    
    # Clear sensitive data from memory
    del plaintext_key
    del plaintext_data
    
    logger.info("✓ Decryption completed")
    sys.stdout.flush()


def encrypt_with_openssl(config: dict, input_file: Path, output_file: Path, password: str) -> None:
    """Encrypt file with OpenSSL AES-256-CBC"""
    logger.info("Encrypting with OpenSSL AES-256-CBC...")
    
    run_command([
        'openssl', 'enc', '-aes-256-cbc', '-salt', '-pbkdf2', '-iter', '100000',
        '-in', str(input_file),
        '-out', str(output_file),
        '-pass', f'pass:{password}'
    ], check=True)
    
    logger.info("✓ OpenSSL encryption completed")


def decrypt_with_openssl(config: dict, input_file: Path, output_file: Path, password: str) -> None:
    """Decrypt file with OpenSSL AES-256-CBC"""
    logger.info("Test decrypting with OpenSSL...")
    
    run_command([
        'openssl', 'enc', '-aes-256-cbc', '-d', '-pbkdf2', '-iter', '100000',
        '-in', str(input_file),
        '-out', str(output_file),
        '-pass', f'pass:{password}'
    ], check=True)


def validate_encryption(config: dict, encrypted_file: Path, original_checksum: str, encryption_method: str) -> bool:
    """Validate encryption by test-decrypting and comparing checksums"""
    logger.info("Validating encryption (test decrypt)...")
    test_decrypt = config['backup_tmp_dir'] / f"etcd-decrypt-test-{os.getpid()}.db"
    
    try:
        if encryption_method == 'aws-kms':
            decrypt_with_kms(config, encrypted_file, test_decrypt)
        elif encryption_method == 'symmetric':
            decrypt_with_openssl(config, encrypted_file, test_decrypt, config['backup_password'])
        else:
            return True
        
        decrypted_checksum = calculate_sha256(test_decrypt)
        
        if original_checksum == decrypted_checksum:
            logger.info("✓ Encryption validation PASSED (checksums match)")
            return True
        else:
            logger.error("✗ Encryption validation FAILED: checksum mismatch")
            logger.error(f"Original:  {original_checksum}")
            logger.error(f"Decrypted: {decrypted_checksum}")
            return False
    finally:
        test_decrypt.unlink(missing_ok=True)


def check_etcd_health(config: dict) -> bool:
    """Check if etcd cluster is healthy"""
    logger.info("Checking etcd cluster health...")
    sys.stdout.flush()
    
    try:
        first_endpoint = config['etcd_endpoints'].split(',')[0]
        logger.info(f"Testing endpoint: {first_endpoint}")
        sys.stdout.flush()
        
        # Use 1 minute timeout for health check
        run_command([
            config['bin_dir'] / 'etcdctl',
            '--endpoints', first_endpoint,
            '--cert', str(config['cert']),
            '--cacert', str(config['cacert']),
            '--key', str(config['key']),
            '--command-timeout=60s',
            'endpoint', 'health'
        ], check=True, capture_output=True, timeout=90)
        
        logger.info("✓ Etcd cluster is healthy")
        sys.stdout.flush()
        return True
    except (subprocess.CalledProcessError, BackupError) as e:
        logger.error(f"✗ Etcd cluster is unhealthy: {e}")
        sys.stdout.flush()
        return False


def check_recent_backup(config: dict) -> bool:
    """Check if a recent backup exists in S3 (distributed backup coordination)"""
    interval_seconds = config['backup_interval_minutes'] * 60
    current_time = int(time.time())
    cutoff_time = current_time - interval_seconds
    
    logger.info(f"Checking for recent backups (within last {config['backup_interval_minutes']} minutes)...")
    
    cutoff_datetime = datetime.utcfromtimestamp(cutoff_time).strftime('%Y-%m-%dT%H:%M:%S')
    
    try:
        result = run_command([
            config['bin_dir'] / 'aws', 's3api', 'list-objects-v2',
            '--bucket', config['s3_bucket'],
            '--prefix', f"{config['s3_prefix']}/",
            '--query', f"Contents[?LastModified>=`{cutoff_datetime}`].{{Key:Key,Modified:LastModified}}",
            '--output', 'text'
        ], check=False)
        
        if result.stdout.strip():
            logger.info("Recent backup found (created by another node):")
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        logger.info(f"  - s3://{config['s3_bucket']}/{parts[0]} ({parts[1]})")
            return True
        else:
            logger.info("No recent backup found, proceeding with backup creation")
            return False
    except subprocess.CalledProcessError:
        logger.warning("Failed to check for recent backups, proceeding with backup")
        return False


def create_snapshot(config: dict, cluster_online: bool, dry_run: bool = False) -> Optional[Tuple[Path, str]]:
    """
    Create etcd snapshot and upload to S3
    
    Args:
        config: Configuration dict
        cluster_online: True if cluster was healthy, False if unhealthy
        dry_run: If True, don't actually create backup
    
    Returns:
        Tuple of (snapshot_file, s3_path) on success, None on failure
    """
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    year = datetime.now().strftime('%Y')
    month = datetime.now().strftime('%m')
    
    # Include cluster health status in filename
    health_suffix = "online" if cluster_online else "offline"
    snapshot_file = config['backup_dir'] / year / month / f"{config['cluster_name']}-{timestamp}-{health_suffix}-snapshot.db"
    
    logger.info("Starting etcd snapshot creation...")
    logger.info(f"Timestamp: {timestamp}")
    logger.info(f"Cluster status: {'ONLINE (using etcdctl API)' if cluster_online else 'OFFLINE (copying from disk)'}")
    sys.stdout.flush()
    
    if dry_run:
        logger.info(f"[DRY-RUN] Would create snapshot from {config['etcd_endpoints'] if cluster_online else 'disk'}")
        return None
    
    # Create directory
    logger.info("Creating backup directory...")
    sys.stdout.flush()
    
    try:
        snapshot_file.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"✓ Directory created: {snapshot_file.parent}")
        sys.stdout.flush()
    except PermissionError as e:
        logger.error(f"Permission denied creating directory: {snapshot_file.parent}")
        logger.error(f"Error: {e}")
        logger.error(f"Check ownership of {config['backup_dir']}")
        logger.error(f"Should be owned by root (script runs as root)")
        sys.stdout.flush()
        raise BackupError(f"Permission denied: {snapshot_file.parent}")
    
    if cluster_online:
        # ONLINE BACKUP: Use etcdctl API
        first_endpoint = config['etcd_endpoints'].split(',')[0]
        logger.info(f"Creating etcd snapshot from API: {first_endpoint}")
        sys.stdout.flush()
        
        try:
            # Use 10 minute timeout for snapshot
            run_command([
                config['bin_dir'] / 'etcdctl',
                '--endpoints', first_endpoint,
                '--cert', str(config['cert']),
                '--cacert', str(config['cacert']),
                '--key', str(config['key']),
                '--command-timeout=600s',
                'snapshot', 'save', str(snapshot_file)
            ], check=True, timeout=700)
            logger.info(f"✓ Snapshot created: {snapshot_file}")
            sys.stdout.flush()
        except (subprocess.CalledProcessError, BackupError) as e:
            logger.error(f"Failed to create etcd snapshot: {e}")
            sys.stdout.flush()
            raise BackupError("Snapshot creation failed")
    else:
        # OFFLINE BACKUP: Copy from disk (cluster is unhealthy, can't use API)
        logger.info("OFFLINE backup: Copying snapshot from disk...")
        logger.info("Note: Offline backups may be inconsistent if cluster lost quorum")
        sys.stdout.flush()
        
        # Find etcd data directory with snap/db file
        etcd_data_pattern = config.get('etcd_data_dir_pattern', '/var/lib/etcd/etcd-*')
        logger.info(f"Searching for etcd data directories: {etcd_data_pattern}")
        sys.stdout.flush()
        
        import glob
        data_dirs = glob.glob(etcd_data_pattern)
        
        if not data_dirs:
            logger.error(f"No etcd data directories found matching: {etcd_data_pattern}")
            logger.error("Cannot perform offline backup")
            sys.stdout.flush()
            raise BackupError("No etcd data directory found for offline backup")
        
        # Use first matching directory
        etcd_data_dir = data_dirs[0]
        snap_db_file = Path(etcd_data_dir) / 'member' / 'snap' / 'db'
        
        logger.info(f"Data directory: {etcd_data_dir}")
        logger.info(f"Source file: {snap_db_file}")
        sys.stdout.flush()
        
        if not snap_db_file.exists():
            logger.error(f"Snapshot file not found: {snap_db_file}")
            logger.error("Etcd may not have been initialized or data directory is incorrect")
            sys.stdout.flush()
            raise BackupError(f"Snapshot file not found: {snap_db_file}")
        
        logger.info(f"Copying snapshot from disk: {snap_db_file}")
        sys.stdout.flush()
        
        try:
            import shutil
            shutil.copy2(snap_db_file, snapshot_file)
            logger.info(f"✓ Snapshot copied: {snapshot_file} ({snapshot_file.stat().st_size} bytes)")
            sys.stdout.flush()
        except Exception as e:
            logger.error(f"Failed to copy snapshot: {e}")
            sys.stdout.flush()
            raise BackupError(f"Offline backup copy failed: {e}")
    
    # Verify snapshot integrity
    logger.info("Verifying snapshot integrity...")
    sys.stdout.flush()
    
    try:
        run_command([
            config['bin_dir'] / 'etcdutl',
            'snapshot', 'status', str(snapshot_file),
            '--write-out', 'table'
        ], check=True, timeout=30)
        logger.info("✓ Snapshot integrity verified")
        sys.stdout.flush()
    except (subprocess.CalledProcessError, BackupError) as e:
        logger.error(f"Snapshot verification failed: {e}")
        sys.stdout.flush()
        snapshot_file.unlink(missing_ok=True)
        raise BackupError("Snapshot verification failed")
    
    # Calculate checksum
    snapshot_checksum = calculate_sha256(snapshot_file)
    logger.info(f"Snapshot checksum: {snapshot_checksum}")
    
    # Encrypt if needed
    encryption_method = config['encryption_method']
    
    if encryption_method == 'aws-kms':
        encrypted_file = snapshot_file.with_suffix('.db.kms')
        encrypt_with_kms(config, snapshot_file, encrypted_file)
        
        if not encrypted_file.exists() or encrypted_file.stat().st_size == 0:
            logger.error("Encrypted file is empty or missing (encryption pipe failed)")
            snapshot_file.unlink(missing_ok=True)
            raise BackupError("Encryption produced empty file")
        
        logger.info(f"✓ Encrypted file created: {encrypted_file.stat().st_size} bytes")
        
        if not validate_encryption(config, encrypted_file, snapshot_checksum, encryption_method):
            snapshot_file.unlink(missing_ok=True)
            encrypted_file.unlink(missing_ok=True)
            raise BackupError("Encryption validation failed")
        
        final_file = encrypted_file
        s3_suffix = '.kms'
        
    elif encryption_method == 'symmetric':
        encrypted_file = snapshot_file.with_suffix('.db.enc')
        encrypt_with_openssl(config, snapshot_file, encrypted_file, config['backup_password'])
        
        if not encrypted_file.exists() or encrypted_file.stat().st_size == 0:
            logger.error("Encrypted file is empty or missing")
            snapshot_file.unlink(missing_ok=True)
            raise BackupError("Encryption produced empty file")
        
        logger.info(f"✓ Encrypted file created: {encrypted_file.stat().st_size} bytes")
        
        if not validate_encryption(config, encrypted_file, snapshot_checksum, encryption_method):
            snapshot_file.unlink(missing_ok=True)
            encrypted_file.unlink(missing_ok=True)
            raise BackupError("Encryption validation failed")
        
        final_file = encrypted_file
        s3_suffix = '.enc'
        
    else:  # none
        logger.warning("No encryption - uploading plain snapshot (not recommended)")
        final_file = snapshot_file
        s3_suffix = ''
    
    # Calculate final file checksum
    final_checksum = calculate_sha256(final_file)
    logger.info(f"Final file checksum: {final_checksum}")
    
    # Upload to S3 (s3_prefix already includes cluster name from template)
    s3_path = f"{config['s3_prefix']}/{year}/{month}/{snapshot_file.name}{s3_suffix}"
    logger.info(f"Uploading backup to S3: s3://{config['s3_bucket']}/{s3_path}")
    
    try:
        run_command([
            config['bin_dir'] / 'aws', 's3', 'cp',
            str(final_file),
            f"s3://{config['s3_bucket']}/{s3_path}",
            '--metadata',
            f"backup-timestamp={timestamp},snapshot-checksum={snapshot_checksum},encrypted-checksum={final_checksum}"
        ], check=True)
        logger.info("✓ Upload completed")
    except subprocess.CalledProcessError:
        logger.error("Failed to upload backup to S3")
        snapshot_file.unlink(missing_ok=True)
        if final_file != snapshot_file:
            final_file.unlink(missing_ok=True)
        raise BackupError("S3 upload failed")
    
    # Create and upload SHA256 checksum file for decrypted data verification
    logger.info("Creating SHA256 checksum file for verification...")
    checksum_file = config['backup_tmp_dir'] / f"{snapshot_file.name}.sha256"
    checksum_content = f"{snapshot_checksum}  {snapshot_file.name}\n"
    checksum_file.write_text(checksum_content)
    
    sha256_s3_path = f"{s3_path}.sha256"
    logger.info(f"Uploading checksum file to S3: s3://{config['s3_bucket']}/{sha256_s3_path}")
    
    try:
        run_command([
            config['bin_dir'] / 'aws', 's3', 'cp',
            str(checksum_file),
            f"s3://{config['s3_bucket']}/{sha256_s3_path}",
            '--content-type', 'text/plain',
            '--metadata',
            f"backup-timestamp={timestamp},snapshot-file={snapshot_file.name}"
        ], check=True)
        logger.info("✓ Checksum file uploaded")
        checksum_file.unlink()
    except subprocess.CalledProcessError:
        logger.warning("Failed to upload checksum file (non-fatal)")
        checksum_file.unlink(missing_ok=True)
    
    # Verify upload
    logger.info("Verifying upload...")
    if not verify_s3_file_exists(config, s3_path):
        logger.error("Upload verification failed - file not found on S3")
        snapshot_file.unlink(missing_ok=True)
        if final_file != snapshot_file:
            final_file.unlink(missing_ok=True)
        raise BackupError("Upload verification failed - file not found")
    
    logger.info("Verifying uploaded file integrity...")
    if not verify_s3_checksum(config, s3_path, final_checksum):
        logger.error("Upload verification failed - checksum mismatch")
        snapshot_file.unlink(missing_ok=True)
        if final_file != snapshot_file:
            final_file.unlink(missing_ok=True)
        raise BackupError("Upload verification failed - checksum mismatch")
    
    logger.info("✓ Upload verification PASSED")
    
    # Update latest pointer (s3_prefix already includes cluster name)
    logger.info("Updating 'latest' pointer...")
    latest_path = f"{config['s3_prefix']}/latest-snapshot.db{s3_suffix}"
    latest_sha256_path = f"{config['s3_prefix']}/latest-snapshot.db.sha256"
    
    try:
        run_command([
            config['bin_dir'] / 'aws', 's3', 'cp',
            str(final_file),
            f"s3://{config['s3_bucket']}/{latest_path}",
            '--metadata',
            f"backup-timestamp={timestamp},snapshot-checksum={snapshot_checksum},encrypted-checksum={final_checksum},retention=long-term"
        ], check=True)
        logger.info("✓ Latest pointer updated")
        
        # Also update latest checksum file
        latest_checksum_file = config['backup_tmp_dir'] / "latest-snapshot.db.sha256"
        latest_checksum_file.write_text(f"{snapshot_checksum}  latest-snapshot.db\n")
        run_command([
            config['bin_dir'] / 'aws', 's3', 'cp',
            str(latest_checksum_file),
            f"s3://{config['s3_bucket']}/{latest_sha256_path}",
            '--content-type', 'text/plain'
        ], check=True)
        logger.info("✓ Latest checksum file updated")
        latest_checksum_file.unlink()
    except subprocess.CalledProcessError:
        logger.warning("Failed to update latest pointer (non-fatal)")
    
    # Tag for retention
    logger.info("Tagging backup for retention policy...")
    try:
        tags = [
            {'Key': 'Type', 'Value': 'etcd-snapshot'},
            {'Key': 'Cluster', 'Value': config['cluster_name']},
            {'Key': 'Timestamp', 'Value': timestamp},
            {'Key': 'Retention', 'Value': 'long-term'},
            {'Key': 'Latest', 'Value': 'true'}
        ]
        tag_json = json.dumps({'TagSet': tags})
        
        run_command([
            config['bin_dir'] / 'aws', 's3api', 'put-object-tagging',
            '--bucket', config['s3_bucket'],
            '--key', s3_path,
            '--tagging', tag_json
        ], check=False)
    except subprocess.CalledProcessError:
        logger.warning("Failed to set S3 tags (non-fatal)")
    
    # Keep local unencrypted snapshot
    logger.info("Saving local copy...")
    local_copy = config['backup_dir'] / f"{config['cluster_name']}-snapshot.db"
    try:
        import shutil
        shutil.copy2(snapshot_file, local_copy)
        logger.info("✓ Local copy saved")
    except Exception as e:
        logger.warning(f"Failed to save local copy (non-fatal): {e}")
    
    # Cleanup encrypted file
    logger.info("Cleaning up temporary files...")
    if final_file != snapshot_file:
        final_file.unlink(missing_ok=True)
    logger.info("✓ Cleanup completed")
    
    logger.info("=" * 72)
    logger.info(f"Snapshot SUCCESS: s3://{config['s3_bucket']}/{s3_path}")
    logger.info(f"Snapshot checksum: {snapshot_checksum}")
    logger.info(f"Encrypted checksum: {final_checksum}")
    logger.info(f"SHA256 file: s3://{config['s3_bucket']}/{sha256_s3_path}")
    logger.info("")
    logger.info("To verify after download and decrypt:")
    logger.info(f"  sha256sum -c {snapshot_file.name}.sha256")
    logger.info("=" * 72)
    
    return snapshot_file, s3_path


def cleanup_old_backups(config: dict) -> None:
    """Remove local backups older than retention period"""
    retention_days = config['retention_days']
    logger.info(f"Cleaning up local backups older than {retention_days} days...")
    
    cutoff_time = time.time() - (retention_days * 86400)
    deleted_count = 0
    
    for backup_file in config['backup_dir'].rglob('*.db'):
        if backup_file.stat().st_mtime < cutoff_time:
            logger.info(f"Deleting old backup: {backup_file}")
            backup_file.unlink()
            deleted_count += 1
    
    logger.info(f"Deleted {deleted_count} old backup(s)")
    
    # Remove empty directories
    for dirpath in config['backup_dir'].rglob('*'):
        if dirpath.is_dir() and not any(dirpath.iterdir()):
            dirpath.rmdir()
    
    logger.info("✓ Local cleanup completed")


def send_healthcheck_ping(config: dict, status: str = 'success') -> None:
    """Send healthcheck ping if configured"""
    if not config.get('healthcheck_url'):
        return
    
    url = f"{config['healthcheck_url']}?status={status}"
    logger.info("Sending healthcheck ping...")
    
    try:
        run_command(['curl', '-fsS', '--retry', '3', url], check=False, capture_output=True)
        logger.info("✓ Healthcheck ping successful")
    except Exception as e:
        logger.warning(f"Healthcheck ping failed (non-fatal): {e}")


def decrypt_file(config: dict, input_file: str, output_file: str, encryption_method: str) -> int:
    """
    Decrypt a file using the configured encryption method
    
    Args:
        config: Configuration dict
        input_file: Path to encrypted file
        output_file: Path for decrypted output
        encryption_method: Encryption method (auto-detected from extension if 'auto')
    
    Returns:
        0 on success, 1 on failure
    """
    input_path = Path(input_file)
    output_path = Path(output_file)
    
    logger.info("=" * 72)
    logger.info("DECRYPT MODE")
    logger.info(f"Input:  {input_path}")
    logger.info(f"Output: {output_path}")
    logger.info("=" * 72)
    sys.stdout.flush()
    
    # Auto-detect encryption method from file extension
    if encryption_method == 'auto':
        if input_path.suffix == '.kms':
            encryption_method = 'aws-kms'
            logger.info("Auto-detected encryption: aws-kms")
        elif input_path.suffix == '.enc':
            encryption_method = 'symmetric'
            logger.info("Auto-detected encryption: symmetric")
        else:
            encryption_method = 'none'
            logger.info("Auto-detected encryption: none (unencrypted)")
    
    try:
        if encryption_method == 'aws-kms':
            logger.info("Decrypting with AWS KMS envelope encryption...")
            sys.stdout.flush()
            
            if not HAS_CRYPTOGRAPHY:
                logger.error("cryptography library not available")
                logger.error("Install with: pip3 install cryptography")
                return 1
            
            decrypt_with_kms(config, input_path, output_path)
            
        elif encryption_method == 'symmetric':
            logger.info("Decrypting with OpenSSL AES-256-CBC...")
            sys.stdout.flush()
            decrypt_with_openssl(config, input_path, output_path, config['backup_password'])
            
        elif encryption_method == 'none':
            logger.info("No encryption, copying file...")
            sys.stdout.flush()
            import shutil
            shutil.copy2(input_path, output_path)
            
        else:
            logger.error(f"Unknown encryption method: {encryption_method}")
            return 1
        
        # Verify output file exists and has content
        if not output_path.exists() or output_path.stat().st_size == 0:
            logger.error("Decryption produced empty or missing file")
            return 1
        
        logger.info("=" * 72)
        logger.info(f"✓ Decryption successful")
        logger.info(f"Output: {output_path}")
        logger.info(f"Size: {output_path.stat().st_size} bytes ({(output_path.stat().st_size / 1024 / 1024):.2f} MB)")
        logger.info("=" * 72)
        sys.stdout.flush()
        
        return 0
        
    except Exception as e:
        logger.error("=" * 72)
        logger.error(f"Decryption FAILED: {e}")
        logger.error("=" * 72)
        sys.stdout.flush()
        return 1


def main():
    """Main backup logic with overall timeout"""
    parser = argparse.ArgumentParser(
        description='Etcd data backup script',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--config', required=True,
                       help='Path to configuration YAML file')
    parser.add_argument('--online-only', action='store_true',
                       help='Only backup if cluster is healthy (abort if unhealthy)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    parser.add_argument('--independent', action='store_true',
                       help='Skip recent backup check (independent mode)')
    parser.add_argument('--timeout', type=int, default=1800,
                       help='Overall script timeout in seconds (default: 1800 = 30 minutes)')
    
    # Decrypt mode arguments
    parser.add_argument('--decrypt', action='store_true',
                       help='Decrypt mode: decrypt an encrypted backup file')
    parser.add_argument('--input', type=str,
                       help='Input file to decrypt (required with --decrypt)')
    parser.add_argument('--output', type=str,
                       help='Output file for decrypted data (required with --decrypt)')
    parser.add_argument('--encryption', type=str, default='auto',
                       choices=['auto', 'aws-kms', 'symmetric', 'none'],
                       help='Encryption method (default: auto-detect from file extension)')
    
    args = parser.parse_args()
    
    # Handle decrypt mode
    if args.decrypt:
        if not args.input or not args.output:
            logger.error("--decrypt requires both --input and --output arguments")
            return 1
        
        # Load config for credentials and settings
        config_dict = load_config(args.config)
        
        config = {
            'backup_tmp_dir': Path(config_dict['backup_tmp_dir']),
            'bin_dir': Path(config_dict['bin_dir']),
            'encryption_method': args.encryption,
            'kms_key_id': config_dict.get('kms_key_id', ''),
            'backup_password': config_dict.get('backup_password', ''),
        }
        
        # Set AWS credentials
        if 'aws_access_key_id' in config_dict:
            os.environ['AWS_ACCESS_KEY_ID'] = config_dict['aws_access_key_id']
        if 'aws_secret_access_key' in config_dict:
            os.environ['AWS_SECRET_ACCESS_KEY'] = config_dict['aws_secret_access_key']
        if 'aws_region' in config_dict:
            os.environ['AWS_DEFAULT_REGION'] = config_dict['aws_region']
        
        return decrypt_file(config, args.input, args.output, args.encryption)
    
    args = parser.parse_args()
    
    # Set up signal handler for timeout
    import signal
    
    def timeout_handler(signum, frame):
        logger.error("=" * 72)
        logger.error(f"SCRIPT TIMEOUT: Exceeded {args.timeout}s overall execution time")
        logger.error("The backup operation took too long and was killed")
        logger.error("=" * 72)
        sys.stdout.flush()
        sys.exit(1)
    
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(args.timeout)
    
    # Load configuration
    config_dict = load_config(args.config)
    
    # Convert paths to Path objects
    config = {
        'backup_dir': Path(config_dict['backup_dir']),
        'backup_tmp_dir': Path(config_dict['backup_tmp_dir']),
        'bin_dir': Path(config_dict['bin_dir']),
        'cert': Path(config_dict['cert']),
        'key': Path(config_dict['key']),
        'cacert': Path(config_dict['cacert']),
        'etcd_endpoints': config_dict['etcd_endpoints'],
        's3_bucket': config_dict['s3_bucket'],
        's3_prefix': config_dict['s3_prefix'],
        'encryption_method': config_dict['encryption_method'],
        'kms_key_id': config_dict.get('kms_key_id', ''),
        'backup_password': config_dict.get('backup_password', ''),
        'cluster_name': config_dict['cluster_name'],
        'retention_days': config_dict['retention_days'],
        'healthcheck_url': config_dict.get('healthcheck_url', ''),
        'backup_interval_minutes': config_dict['backup_interval_minutes'],
        'distributed_backup': config_dict.get('distributed_backup', True),
        'node_name': config_dict.get('node_name', 'unknown'),
        'etcd_data_dir_pattern': config_dict.get('etcd_data_dir_pattern', '/var/lib/etcd/etcd-*'),
    }
    
    # Set AWS credentials
    if 'aws_access_key_id' in config_dict:
        os.environ['AWS_ACCESS_KEY_ID'] = config_dict['aws_access_key_id']
    if 'aws_secret_access_key' in config_dict:
        os.environ['AWS_SECRET_ACCESS_KEY'] = config_dict['aws_secret_access_key']
    if 'aws_region' in config_dict:
        os.environ['AWS_DEFAULT_REGION'] = config_dict['aws_region']
    os.environ['ETCDCTL_API'] = '3'
    
    logger.info("=" * 72)
    logger.info("Etcd Backup Script Starting")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Config: {args.config}")
    logger.info(f"Node: {config['node_name']}")
    logger.info(f"Cluster: {config['cluster_name']}")
    logger.info(f"Endpoints: {config['etcd_endpoints']}")
    logger.info(f"Encryption: {config['encryption_method']}")
    logger.info(f"S3 Bucket: s3://{config['s3_bucket']}/{config['s3_prefix']}")
    logger.info(f"Distributed backup: {config['distributed_backup']}")
    logger.info(f"Online-only mode: {args.online_only}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("=" * 72)
    sys.stdout.flush()
    
    # Validate cryptography is available for KMS encryption
    if config['encryption_method'] == 'aws-kms' and not HAS_CRYPTOGRAPHY:
        logger.error("=" * 72)
        logger.error("ERROR: cryptography library not installed")
        logger.error("AWS KMS encryption requires the 'cryptography' package")
        logger.error("Install with: pip3 install cryptography")
        logger.error("Or use symmetric encryption instead:")
        logger.error("  step_ca_backup_encryption_method: symmetric")
        logger.error("=" * 72)
        sys.stdout.flush()
        return 1
    
    try:
        # Check etcd health (always check, result goes in filename)
        cluster_online = check_etcd_health(config)
        
        if not cluster_online:
            if args.online_only:
                logger.error("Etcd cluster is unhealthy, aborting backup (--online-only mode)")
                logger.error("Remove --online-only flag to backup anyway")
                send_healthcheck_ping(config, 'cluster-unhealthy')
                return 1
            else:
                logger.warning("Etcd cluster is UNHEALTHY - backup will be marked as 'offline'")
                logger.warning("Offline backups may contain inconsistent data if cluster was not in quorum")
        else:
            logger.info("Etcd cluster is HEALTHY - backup will be marked as 'online'")
        
        # Check for recent backups (distributed coordination)
        if config['distributed_backup'] and not args.independent:
            if check_recent_backup(config):
                logger.info("=" * 72)
                logger.info("Recent backup already exists (created by another node)")
                logger.info("Skipping backup to avoid duplicates")
                logger.info("This is expected behavior in distributed backup mode")
                logger.info("=" * 72)
                send_healthcheck_ping(config, 'backup-exists')
                return 0
        
        if args.independent:
            logger.info("=" * 72)
            logger.info("INDEPENDENT MODE: Creating backup without checking for existing backups")
            logger.info("Multiple backups will be created (one per node)")
            logger.info("=" * 72)
        
        # Create snapshot
        logger.info("Starting snapshot operation...")
        result = create_snapshot(config, cluster_online, dry_run=args.dry_run)
        
        if result and not args.dry_run:
            # Cleanup old backups
            cleanup_old_backups(config)
            
            # Send healthcheck ping
            send_healthcheck_ping(config, 'success')
        
        logger.info("=" * 72)
        logger.info("Etcd Backup Completed Successfully")
        logger.info("=" * 72)
        return 0
        
    except BackupError as e:
        logger.error("=" * 72)
        logger.error(f"Etcd Backup FAILED: {e}")
        logger.error("=" * 72)
        sys.stdout.flush()
        
        if not args.dry_run:
            send_healthcheck_ping(config, 'failure')
        
        return 1
    
    except Exception as e:
        logger.error("=" * 72)
        logger.error(f"Unexpected error: {e}")
        logger.error(f"Type: {type(e).__name__}")
        
        # Show stack trace for debugging
        import traceback
        logger.error("Stack trace:")
        for line in traceback.format_exc().split('\n'):
            if line:
                logger.error(line)
        
        logger.error("=" * 72)
        sys.stdout.flush()
        
        if not args.dry_run:
            send_healthcheck_ping(config, 'failure')
        
        return 1


if __name__ == '__main__':
    # Ensure unbuffered output from the start
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
    sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)
    sys.exit(main())
