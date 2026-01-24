#!/usr/bin/env python3
"""
CA backup script - only backs up when CA files change
Loads configuration from YAML file

Usage: ca-backup-check.py --config /path/to/config.yaml [OPTIONS]

OPTIONS:
  --config PATH   Configuration file (required)
  --force         Force backup even if files haven't changed
  --dry-run       Show what would be done without making changes

Exit codes:
  0 - Success (backup completed or skipped because no changes)
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
import tarfile
import time
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional


class BackupError(Exception):
    """Custom exception for backup errors"""
    pass


def setup_logging() -> logging.Logger:
    """Setup logging configuration"""
    logger = logging.getLogger('ca-backup')
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


def calculate_directory_checksum(directory: Path) -> str:
    """Calculate checksum of all files in directory"""
    checksums = []
    
    for file_path in sorted(directory.rglob('*')):
        if file_path.is_file():
            try:
                checksum = calculate_sha256(file_path)
                checksums.append(f"{file_path}:{checksum}")
            except Exception as e:
                logger.warning(f"Failed to checksum {file_path}: {e}")
    
    combined = '\n'.join(checksums)
    return hashlib.sha256(combined.encode()).hexdigest()


def calculate_ca_checksum(config: dict) -> str:
    """Calculate checksum of CA files"""
    logger.info("Calculating checksum of CA files...")
    
    secrets_checksum = calculate_directory_checksum(config['ca_secrets_dir'])
    config_checksum = calculate_directory_checksum(config['ca_config_dir'])
    
    combined = f"secrets:{secrets_checksum}\nconfig:{config_checksum}"
    final_checksum = hashlib.sha256(combined.encode()).hexdigest()
    
    logger.info(f"CA checksum: {final_checksum}")
    return final_checksum


def create_archive(config: dict, archive_path: Path) -> str:
    """Create tar.gz archive of CA files and return checksum"""
    logger.info("Creating CA backup archive...")
    
    if not config['ca_secrets_dir'].exists():
        raise BackupError(f"CA secrets directory not found: {config['ca_secrets_dir']}")
    if not config['ca_config_dir'].exists():
        raise BackupError(f"CA config directory not found: {config['ca_config_dir']}")
    
    with tarfile.open(archive_path, 'w:gz') as tar:
        tar.add(config['ca_secrets_dir'], arcname='etc/step-ca/secrets')
        tar.add(config['ca_config_dir'], arcname='etc/step-ca/config')
    
    if not archive_path.exists() or archive_path.stat().st_size == 0:
        raise BackupError("Archive creation produced empty file")
    
    logger.info(f"✓ Archive created: {archive_path.stat().st_size} bytes")
    
    # Verify archive integrity
    try:
        with tarfile.open(archive_path, 'r:gz') as tar:
            members = tar.getnames()
            if not members:
                raise BackupError("Archive is empty")
            logger.info(f"✓ Archive contains {len(members)} files")
    except Exception as e:
        raise BackupError(f"Archive integrity check failed: {e}")
    
    checksum = calculate_sha256(archive_path)
    logger.info(f"Archive checksum: {checksum}")
    
    return checksum


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
    test_decrypt = Path(f"/tmp/ca-decrypt-test-{os.getpid()}.tar.gz")
    
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
    temp_file = Path(f"/tmp/ca-verify-{int(time.time())}.tar.gz")
    
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


def backup_ca(config: dict, dry_run: bool = False) -> Optional[str]:
    """
    Backup CA files to S3 with encryption
    
    Returns:
        S3 path of uploaded backup, or None on failure
    """
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    year = datetime.now().strftime('%Y')
    month = datetime.now().strftime('%m')
    
    archive_file = Path(f"/tmp/ca-backup-{timestamp}.tar.gz")
    
    logger.info("Starting CA backup process...")
    logger.info(f"Timestamp: {timestamp}")
    
    if dry_run:
        logger.info("[DRY-RUN] Would create backup archive from /etc/step-ca/")
        return None
    
    # Create archive
    archive_checksum = create_archive(config, archive_file)
    
    # Encrypt if needed
    encryption_method = config['encryption_method']
    
    if encryption_method == 'aws-kms':
        encrypted_file = archive_file.with_suffix('.tar.gz.kms')
        encrypt_with_kms(config, archive_file, encrypted_file)
        
        if not encrypted_file.exists() or encrypted_file.stat().st_size == 0:
            logger.error("Encrypted file is empty or missing (encryption pipe failed)")
            archive_file.unlink(missing_ok=True)
            raise BackupError("Encryption produced empty file")
        
        logger.info(f"✓ Encrypted file created: {encrypted_file.stat().st_size} bytes")
        
        if not validate_encryption(config, encrypted_file, archive_checksum, encryption_method):
            archive_file.unlink(missing_ok=True)
            encrypted_file.unlink(missing_ok=True)
            raise BackupError("Encryption validation failed")
        
        final_file = encrypted_file
        s3_suffix = '.kms'
        
    elif encryption_method == 'symmetric':
        encrypted_file = archive_file.with_suffix('.tar.gz.enc')
        encrypt_with_openssl(config, archive_file, encrypted_file, config['backup_password'])
        
        if not encrypted_file.exists() or encrypted_file.stat().st_size == 0:
            logger.error("Encrypted file is empty or missing")
            archive_file.unlink(missing_ok=True)
            raise BackupError("Encryption produced empty file")
        
        logger.info(f"✓ Encrypted file created: {encrypted_file.stat().st_size} bytes")
        
        if not validate_encryption(config, encrypted_file, archive_checksum, encryption_method):
            archive_file.unlink(missing_ok=True)
            encrypted_file.unlink(missing_ok=True)
            raise BackupError("Encryption validation failed")
        
        final_file = encrypted_file
        s3_suffix = '.enc'
        
    else:  # none
        logger.warning("No encryption - uploading plain backup (not recommended)")
        final_file = archive_file
        s3_suffix = ''
    
    # Calculate final file checksum
    final_checksum = calculate_sha256(final_file)
    logger.info(f"Final file checksum: {final_checksum}")
    
    # Upload to S3
    s3_path = f"{config['s3_prefix']}/{year}/{month}/ca-backup-{timestamp}.tar.gz{s3_suffix}"
    logger.info(f"Uploading backup to S3: s3://{config['s3_bucket']}/{s3_path}")
    
    try:
        run_command([
            config['bin_dir'] / 'aws', 's3', 'cp',
            str(final_file),
            f"s3://{config['s3_bucket']}/{s3_path}",
            '--metadata',
            f"backup-timestamp={timestamp},original-checksum={archive_checksum},encrypted-checksum={final_checksum}"
        ], check=True)
        logger.info("✓ Upload completed")
    except subprocess.CalledProcessError:
        logger.error("Failed to upload backup to S3")
        archive_file.unlink(missing_ok=True)
        if final_file != archive_file:
            final_file.unlink(missing_ok=True)
        raise BackupError("S3 upload failed")
    
    # Verify upload
    logger.info("Verifying upload...")
    if not verify_s3_file_exists(config, s3_path):
        logger.error("Upload verification failed - file not found on S3")
        archive_file.unlink(missing_ok=True)
        if final_file != archive_file:
            final_file.unlink(missing_ok=True)
        raise BackupError("Upload verification failed - file not found")
    
    logger.info("Verifying uploaded file integrity...")
    if not verify_s3_checksum(config, s3_path, final_checksum):
        logger.error("Upload verification failed - checksum mismatch")
        archive_file.unlink(missing_ok=True)
        if final_file != archive_file:
            final_file.unlink(missing_ok=True)
        raise BackupError("Upload verification failed - checksum mismatch")
    
    logger.info("✓ Upload verification PASSED")
    
    # Update latest pointer
    logger.info("Updating 'latest' pointer...")
    latest_path = f"{config['s3_prefix']}/latest-ca-backup.tar.gz{s3_suffix}"
    try:
        run_command([
            config['bin_dir'] / 'aws', 's3', 'cp',
            str(final_file),
            f"s3://{config['s3_bucket']}/{latest_path}",
            '--metadata',
            f"backup-timestamp={timestamp},original-checksum={archive_checksum},encrypted-checksum={final_checksum},retention=long-term"
        ], check=True)
        logger.info("✓ Latest pointer updated")
    except subprocess.CalledProcessError:
        logger.warning("Failed to update latest pointer (non-fatal)")
    
    # Tag for retention
    logger.info("Tagging backup for retention policy...")
    try:
        tags = [
            {'Key': 'Type', 'Value': 'ca-backup'},
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
    
    # Cleanup
    logger.info("Cleaning up temporary files...")
    archive_file.unlink(missing_ok=True)
    if final_file != archive_file:
        final_file.unlink(missing_ok=True)
    logger.info("✓ Cleanup completed")
    
    logger.info("=" * 72)
    logger.info(f"Backup SUCCESS: s3://{config['s3_bucket']}/{s3_path}")
    logger.info(f"Archive checksum: {archive_checksum}")
    logger.info(f"Encrypted checksum: {final_checksum}")
    logger.info("=" * 72)
    
    return s3_path


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
        description='CA backup script',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--config', required=True,
                       help='Path to configuration YAML file')
    parser.add_argument('--force', action='store_true',
                       help='Force backup even if files haven\'t changed')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    
    args = parser.parse_args()
    
    # Load configuration
    config_dict = load_config(args.config)
    
    # Convert paths to Path objects
    config = {
        'state_file': Path(config_dict['state_file']),
        'ca_secrets_dir': Path(config_dict['ca_secrets_dir']),
        'ca_config_dir': Path(config_dict['ca_config_dir']),
        'bin_dir': Path(config_dict['bin_dir']),
        's3_bucket': config_dict['s3_bucket'],
        's3_prefix': config_dict['s3_prefix'],
        'encryption_method': config_dict['encryption_method'],
        'kms_key_id': config_dict.get('kms_key_id', ''),
        'backup_password': config_dict.get('backup_password', ''),
        'healthcheck_url': config_dict.get('healthcheck_url', ''),
        'node_name': config_dict.get('node_name', 'unknown'),
    }
    
    # Set AWS credentials
    if 'aws_access_key_id' in config_dict:
        os.environ['AWS_ACCESS_KEY_ID'] = config_dict['aws_access_key_id']
    if 'aws_secret_access_key' in config_dict:
        os.environ['AWS_SECRET_ACCESS_KEY'] = config_dict['aws_secret_access_key']
    if 'aws_region' in config_dict:
        os.environ['AWS_DEFAULT_REGION'] = config_dict['aws_region']
    
    logger.info("=" * 72)
    logger.info("CA Backup Script Starting")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Config: {args.config}")
    logger.info(f"Node: {config['node_name']}")
    logger.info(f"Encryption: {config['encryption_method']}")
    logger.info(f"S3 Bucket: s3://{config['s3_bucket']}/{config['s3_prefix']}")
    logger.info(f"Force backup: {args.force}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("=" * 72)
    
    try:
        # Calculate current checksum
        current_checksum = calculate_ca_checksum(config)
        
        # Check if forced backup
        if args.force:
            logger.info("Force backup requested, skipping change detection")
        else:
            # Check state file
            if config['state_file'].exists():
                last_checksum = config['state_file'].read_text().strip()
                logger.info(f"Last backup checksum: {last_checksum}")
                
                if current_checksum == last_checksum:
                    logger.info("=" * 72)
                    logger.info("Local checksum UNCHANGED since last backup")
                    logger.info("No backup needed (CA files have not changed)")
                    logger.info("=" * 72)
                    
                    send_healthcheck_ping(config, 'no-changes')
                    return 0
                else:
                    logger.info("CA files CHANGED (checksum mismatch)")
                    logger.info(f"Old: {last_checksum}")
                    logger.info(f"New: {current_checksum}")
            else:
                logger.info("No previous backup state found (first run)")
                config['state_file'].parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        
        # Perform backup
        logger.info("Starting backup operation...")
        result = backup_ca(config, dry_run=args.dry_run)
        
        if result and not args.dry_run:
            # Update state file
            config['state_file'].write_text(current_checksum)
            logger.info("✓ State file updated with new checksum")
            
            # Send healthcheck ping
            send_healthcheck_ping(config, 'success')
        
        logger.info("=" * 72)
        logger.info("CA Backup Completed Successfully")
        logger.info("=" * 72)
        return 0
        
    except BackupError as e:
        logger.error("=" * 72)
        logger.error(f"CA Backup FAILED: {e}")
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
