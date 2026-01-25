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
import subprocess
import sys
import time
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


class BackupError(Exception):
    """Custom exception for backup errors"""
    pass


def setup_logging() -> logging.Logger:
    """Setup logging configuration"""
    logger = logging.getLogger('etcd-backup')
    logger.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
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


def run_command(cmd: list, check: bool = True, capture_output: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result"""
    try:
        logger.debug(f"Running command: {' '.join(str(c) for c in cmd)}")
        result = subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            text=True
        )
        return result
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {' '.join(str(c) for c in cmd)}")
        logger.error(f"Exit code: {e.returncode}")
        if e.stderr:
            logger.error(f"Error output: {e.stderr}")
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
    temp_file = Path(f"/tmp/etcd-verify-{int(time.time())}.db")
    
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
    """Encrypt file with AWS KMS"""
    logger.info(f"Encrypting with AWS KMS (key: {config['kms_key_id']})...")
    
    result = run_command([
        config['bin_dir'] / 'aws', 'kms', 'encrypt',
        '--key-id', config['kms_key_id'],
        '--plaintext', f"fileb://{input_file}",
        '--output', 'text',
        '--query', 'CiphertextBlob'
    ], check=True)
    
    ciphertext = base64.b64decode(result.stdout.strip())
    with open(output_file, 'wb') as f:
        f.write(ciphertext)
    
    logger.info("✓ KMS encryption completed")


def decrypt_with_kms(config: dict, input_file: Path, output_file: Path) -> None:
    """Decrypt file with AWS KMS"""
    logger.info("Test decrypting with AWS KMS...")
    
    result = run_command([
        config['bin_dir'] / 'aws', 'kms', 'decrypt',
        '--ciphertext-blob', f"fileb://{input_file}",
        '--output', 'text',
        '--query', 'Plaintext'
    ], check=True)
    
    plaintext = base64.b64decode(result.stdout.strip())
    with open(output_file, 'wb') as f:
        f.write(plaintext)


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
    test_decrypt = Path(f"/tmp/etcd-decrypt-test-{os.getpid()}.db")
    
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
    
    try:
        first_endpoint = config['etcd_endpoints'].split(',')[0]
        
        run_command([
            config['bin_dir'] / 'etcdctl',
            '--endpoints', first_endpoint,
            '--cert', str(config['cert']),
            '--cacert', str(config['cacert']),
            '--key', str(config['key']),
            'endpoint', 'health'
        ], check=True, capture_output=True)
        
        logger.info("✓ Etcd cluster is healthy")
        return True
    except subprocess.CalledProcessError:
        logger.error("✗ Etcd cluster is unhealthy")
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
    
    if dry_run:
        logger.info(f"[DRY-RUN] Would create snapshot from {config['etcd_endpoints']}")
        return None
    
    # Create directory
    logger.info("Creating backup directory...")
    snapshot_file.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"✓ Directory created: {snapshot_file.parent}")
    
    # Create snapshot
    first_endpoint = config['etcd_endpoints'].split(',')[0]
    logger.info(f"Creating etcd snapshot from: {first_endpoint}")
    
    try:
        run_command([
            config['bin_dir'] / 'etcdctl',
            '--endpoints', first_endpoint,
            '--cert', str(config['cert']),
            '--cacert', str(config['cacert']),
            '--key', str(config['key']),
            'snapshot', 'save', str(snapshot_file)
        ], check=True)
        logger.info(f"✓ Snapshot created: {snapshot_file}")
    except subprocess.CalledProcessError:
        logger.error("Failed to create etcd snapshot")
        raise BackupError("Snapshot creation failed")
    
    # Verify snapshot integrity
    logger.info("Verifying snapshot integrity...")
    try:
        run_command([
            config['bin_dir'] / 'etcdutl',
            'snapshot', 'status', str(snapshot_file),
            '--write-out', 'table'
        ], check=True)
        logger.info("✓ Snapshot integrity verified")
    except subprocess.CalledProcessError:
        logger.error("Snapshot verification failed")
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
    try:
        run_command([
            config['bin_dir'] / 'aws', 's3', 'cp',
            str(final_file),
            f"s3://{config['s3_bucket']}/{latest_path}",
            '--metadata',
            f"backup-timestamp={timestamp},snapshot-checksum={snapshot_checksum},encrypted-checksum={final_checksum},retention=long-term"
        ], check=True)
        logger.info("✓ Latest pointer updated")
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


def main():
    """Main backup logic"""
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
    
    args = parser.parse_args()
    
    # Load configuration
    config_dict = load_config(args.config)
    
    # Convert paths to Path objects
    config = {
        'backup_dir': Path(config_dict['backup_dir']),
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
        
        if not args.dry_run:
            send_healthcheck_ping(config, 'failure')
        
        return 1
    
    except Exception as e:
        logger.error("=" * 72)
        logger.error(f"Unexpected error: {e}")
        logger.error("=" * 72)
        
        if not args.dry_run:
            send_healthcheck_ping(config, 'failure')
        
        return 1


if __name__ == '__main__':
    sys.exit(main())
