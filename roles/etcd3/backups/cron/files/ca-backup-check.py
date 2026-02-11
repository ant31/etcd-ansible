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
import secrets
import subprocess
import sys
import tarfile
import time
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional

# Optional: cryptography for KMS envelope encryption
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
    
    logger = logging.getLogger('ca-backup')
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
        sys.stdout.flush()
        
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
    """Encrypt file with AWS KMS using envelope encryption (supports large files)"""
    logger.info(f"Encrypting with AWS KMS envelope encryption (key: {config['kms_key_id']})...")
    logger.info("Generating data encryption key from KMS...")
    sys.stdout.flush()
    
    # Generate a data encryption key from KMS
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
    
    # Encrypt file with AES-256-GCM
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import secrets
    
    aesgcm = AESGCM(plaintext_key)
    nonce = secrets.token_bytes(12)
    
    with open(input_file, 'rb') as f:
        plaintext_data = f.read()
    
    ciphertext_data = aesgcm.encrypt(nonce, plaintext_data, None)
    
    # Write envelope format
    with open(output_file, 'wb') as f:
        f.write(len(encrypted_key).to_bytes(4, byteorder='big'))
        f.write(encrypted_key)
        f.write(nonce)
        f.write(ciphertext_data)
    
    del plaintext_key
    del plaintext_data
    
    logger.info("✓ KMS envelope encryption completed")
    sys.stdout.flush()


def decrypt_with_kms(config: dict, input_file: Path, output_file: Path) -> None:
    """Decrypt file with AWS KMS envelope encryption"""
    logger.info("Test decrypting with AWS KMS envelope encryption...")
    sys.stdout.flush()
    
    # Read envelope
    with open(input_file, 'rb') as f:
        encrypted_key_length = int.from_bytes(f.read(4), byteorder='big')
        encrypted_key = f.read(encrypted_key_length)
        nonce = f.read(12)
        ciphertext_data = f.read()
    
    logger.info("Decrypting data encryption key with KMS...")
    sys.stdout.flush()
    
    # Decrypt data key
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
    
    # Decrypt file
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    
    aesgcm = AESGCM(plaintext_key)
    plaintext_data = aesgcm.decrypt(nonce, ciphertext_data, None)
    
    with open(output_file, 'wb') as f:
        f.write(plaintext_data)
    
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
    test_decrypt = config['backup_tmp_dir'] / f"ca-decrypt-test-{os.getpid()}.tar.gz"
    
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
    temp_file = config['backup_tmp_dir'] / f"ca-verify-{int(time.time())}.tar.gz"
    
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
    
    archive_file = config['backup_tmp_dir'] / f"ca-backup-{timestamp}.tar.gz"
    
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
    
    # Create and upload SHA256 checksum file for decrypted data verification
    logger.info("Creating SHA256 checksum file for verification...")
    checksum_file = config['backup_tmp_dir'] / f"ca-backup-{timestamp}.tar.gz.sha256"
    checksum_content = f"{archive_checksum}  ca-backup-{timestamp}.tar.gz\n"
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
            f"backup-timestamp={timestamp},archive-file=ca-backup-{timestamp}.tar.gz"
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
    latest_sha256_path = f"{config['s3_prefix']}/latest-ca-backup.tar.gz.sha256"
    
    try:
        run_command([
            config['bin_dir'] / 'aws', 's3', 'cp',
            str(final_file),
            f"s3://{config['s3_bucket']}/{latest_path}",
            '--metadata',
            f"backup-timestamp={timestamp},original-checksum={archive_checksum},encrypted-checksum={final_checksum},retention=long-term"
        ], check=True)
        logger.info("✓ Latest pointer updated")
        
        # Also update latest checksum file
        latest_checksum_file = config['backup_tmp_dir'] / "latest-ca-backup.tar.gz.sha256"
        latest_checksum_file.write_text(f"{archive_checksum}  latest-ca-backup.tar.gz\n")
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
    logger.info(f"SHA256 file: s3://{config['s3_bucket']}/{sha256_s3_path}")
    logger.info("")
    logger.info("To verify after download and decrypt:")
    logger.info(f"  sha256sum -c ca-backup-{timestamp}.tar.gz.sha256")
    logger.info("=" * 72)
    
    return s3_path


def decrypt_file(config: dict, input_file: str, output_file: str, encryption_method: str,
                sha256_value: str = None, sha256_file: str = None, verify_checksum: bool = True) -> int:
    """
    Decrypt a CA backup file
    
    Args:
        config: Configuration dict
        input_file: Path to encrypted file
        output_file: Path for decrypted output
        encryption_method: Encryption method (auto-detected from extension if 'auto')
        sha256_value: Expected SHA256 checksum (hex string)
        sha256_file: Path to .sha256 file containing expected checksum
        verify_checksum: If True, verify decrypted content against checksum
    
    Returns:
        0 on success, 1 on failure
    """
    input_path = Path(input_file)
    output_path = Path(output_file)
    
    logger.info("=" * 72)
    logger.info("DECRYPT MODE")
    logger.info(f"Input:  {input_path}")
    logger.info(f"Output: {output_path}")
    logger.info(f"Verify checksum: {verify_checksum}")
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
    
    # Determine expected checksum
    expected_checksum = None
    if verify_checksum:
        if sha256_value:
            expected_checksum = sha256_value.lower().strip()
            logger.info(f"Using provided SHA256: {expected_checksum}")
        elif sha256_file:
            try:
                sha256_path = Path(sha256_file)
                if sha256_path.exists():
                    content = sha256_path.read_text().strip()
                    parts = content.split()
                    if parts:
                        expected_checksum = parts[0].lower()
                        logger.info(f"Loaded SHA256 from file: {expected_checksum}")
                else:
                    logger.error(f"SHA256 file not found: {sha256_file}")
                    return 1
            except Exception as e:
                logger.error(f"Failed to read SHA256 file: {e}")
                return 1
        else:
            # Try to auto-detect .sha256 file next to input
            auto_sha256_file = input_path.with_suffix('.tar.gz.sha256')
            if auto_sha256_file.exists():
                try:
                    content = auto_sha256_file.read_text().strip()
                    parts = content.split()
                    if parts:
                        expected_checksum = parts[0].lower()
                        logger.info(f"Auto-detected SHA256 file: {auto_sha256_file}")
                        logger.info(f"Expected checksum: {expected_checksum}")
                except Exception as e:
                    logger.warning(f"Failed to read auto-detected SHA256 file (non-fatal): {e}")
            else:
                logger.warning("No SHA256 checksum provided or auto-detected")
                logger.warning("Checksum verification will be skipped")
                verify_checksum = False
    
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
        
        # Verify checksum if requested
        if verify_checksum and expected_checksum:
            logger.info("")
            logger.info("Verifying decrypted file checksum...")
            sys.stdout.flush()
            
            actual_checksum = calculate_sha256(output_path)
            logger.info(f"Expected: {expected_checksum}")
            logger.info(f"Actual:   {actual_checksum}")
            
            if actual_checksum == expected_checksum:
                logger.info("✓ Checksum verification PASSED")
            else:
                logger.error("✗ Checksum verification FAILED")
                logger.error("The decrypted file does NOT match the expected checksum")
                logger.error("This may indicate:")
                logger.error("  - Corrupted backup file")
                logger.error("  - Wrong encryption key/password")
                logger.error("  - File was tampered with")
                logger.info("=" * 72)
                sys.stdout.flush()
                return 1
        elif verify_checksum and not expected_checksum:
            logger.warning("Checksum verification requested but no checksum available")
        
        logger.info("=" * 72)
        sys.stdout.flush()
        
        return 0
        
    except Exception as e:
        logger.error("=" * 72)
        logger.error(f"Decryption FAILED: {e}")
        logger.error("=" * 72)
        sys.stdout.flush()
        return 1


def cleanup_old_backups(config: dict) -> None:
    """
    Remove local CA backups older than retention period (local disk only, not S3)
    
    This function is designed to NEVER fail the backup operation.
    All errors are caught and logged as warnings.
    """
    if not config.get('cleanup_enabled', True):
        logger.info("Cleanup disabled by configuration, skipping")
        return
    
    local_retention_days = config.get('local_retention_days', 365)
    logger.info(f"Cleaning up local CA backups older than {local_retention_days} days...")
    
    try:
        cutoff_time = time.time() - (local_retention_days * 86400)
        deleted_count = 0
        error_count = 0
        
        for backup_file in config['ca_backup_dir'].rglob('*.tar.gz*'):
            try:
                if backup_file.stat().st_mtime < cutoff_time:
                    logger.info(f"Deleting old CA backup: {backup_file}")
                    backup_file.unlink()
                    deleted_count += 1
            except Exception as e:
                error_count += 1
                logger.warning(f"Failed to delete {backup_file} (non-fatal): {e}")
        
        logger.info(f"Deleted {deleted_count} old CA backup(s)")
        if error_count > 0:
            logger.warning(f"Failed to delete {error_count} file(s) (non-fatal)")
        
        # Remove empty directories
        try:
            for dirpath in config['ca_backup_dir'].rglob('*'):
                if dirpath.is_dir() and not any(dirpath.iterdir()):
                    try:
                        dirpath.rmdir()
                    except Exception as e:
                        logger.warning(f"Failed to remove empty directory {dirpath} (non-fatal): {e}")
        except Exception as e:
            logger.warning(f"Directory cleanup failed (non-fatal): {e}")
        
        logger.info("✓ Local CA cleanup completed")
        
    except Exception as e:
        logger.warning(f"CA backup cleanup failed (non-fatal): {e}")
        logger.warning("CA backup was successful, but old file cleanup failed")
        logger.warning("You may need to manually clean old CA backups")


def send_healthcheck_ping(config: dict, status: str = 'success') -> None:
    """Send healthcheck ping if configured"""
    if not config.get('healthcheck_url'):
        return
    
    url = f"{config['healthcheck_url']}?status={status}"
    logger.info(f"Sending healthcheck ping with status: {status.upper()}")
    
    try:
        run_command(['curl', '-fsS', '--retry', '3', url], check=False, capture_output=True)
        logger.info(f"✓ Healthcheck ping sent: {status.upper()}")
    except Exception as e:
        logger.warning(f"Healthcheck ping FAILED to send (non-fatal): {e}")


def main():
    """Main backup logic with overall timeout"""
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
    parser.add_argument('--timeout', type=int, default=1800,
                       help='Overall script timeout in seconds (default: 1800 = 30 minutes)')
    
    # Decrypt mode arguments
    parser.add_argument('--decrypt', action='store_true',
                       help='Decrypt mode: decrypt an encrypted CA backup file')
    parser.add_argument('--input', type=str,
                       help='Input file to decrypt (required with --decrypt)')
    parser.add_argument('--output', type=str,
                       help='Output file for decrypted data (required with --decrypt)')
    parser.add_argument('--encryption', type=str, default='auto',
                       choices=['auto', 'aws-kms', 'symmetric', 'none'],
                       help='Encryption method (default: auto-detect from file extension)')
    parser.add_argument('--sha256', type=str,
                       help='Expected SHA256 checksum (hex string) for verification')
    parser.add_argument('--sha256-file', type=str,
                       help='Path to .sha256 file containing expected checksum')
    parser.add_argument('--no-verify', action='store_true',
                       help='Skip checksum verification (not recommended)')
    
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
        
        return decrypt_file(config, args.input, args.output, args.encryption,
                          sha256_value=args.sha256,
                          sha256_file=args.sha256_file,
                          verify_checksum=not args.no_verify)
    
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
        'state_file': Path(config_dict['state_file']),
        'ca_backup_dir': Path(config_dict['ca_backup_dir']),
        'backup_tmp_dir': Path(config_dict['backup_tmp_dir']),
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
    sys.stdout.flush()
    
    # Validate cryptography is available for KMS encryption
    if config['encryption_method'] == 'aws-kms' and not HAS_CRYPTOGRAPHY:
        logger.error("=" * 72)
        logger.error("ERROR: cryptography library not installed")
        logger.error("AWS KMS encryption requires the 'cryptography' package")
        logger.error("Install with: pip3 install cryptography")
        logger.error("Or use symmetric encryption instead")
        logger.error("=" * 72)
        sys.stdout.flush()
        return 1
    
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
            # Ensure state file directory exists before writing
            config['state_file'].parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            
            # Update state file
            config['state_file'].write_text(current_checksum)
            logger.info("✓ State file updated with new checksum")
            
            # Cleanup old backups AFTER successful backup (non-fatal)
            cleanup_old_backups(config)
            
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
        sys.stdout.flush()
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
        return 1


if __name__ == '__main__':
    # Ensure unbuffered output from the start
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
    sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)
    sys.exit(main())
