#!/usr/bin/env python3
"""
Healthchecks.io management script
Creates and updates healthcheck monitors via API

Usage: manage-healthchecks.py --config /path/to/config.yaml --action ACTION

Actions:
  create-all    Create/update all configured checks
  list          List all checks in project
  delete        Delete a specific check (requires --check-name)
"""

import argparse
import json
import logging
import requests
import sys
import yaml
from typing import Dict, List, Optional


def setup_logging() -> logging.Logger:
    """Setup logging configuration"""
    logger = logging.getLogger('healthchecks')
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


class HealthchecksAPI:
    """Healthchecks.io API client"""
    
    def __init__(self, api_key: str, api_url: str = "https://healthchecks.io/api/v3"):
        self.api_key = api_key
        self.api_url = api_url.rstrip('/')
        self.headers = {
            'X-Api-Key': api_key,
            'Content-Type': 'application/json'
        }
    
    def list_checks(self) -> List[Dict]:
        """List all checks in project"""
        url = f"{self.api_url}/checks/"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()['checks']
    
    def get_check_by_name(self, name: str) -> Optional[Dict]:
        """Find check by name"""
        checks = self.list_checks()
        for check in checks:
            if check['name'] == name:
                return check
        return None
    
    def create_check(self, check_data: Dict) -> Dict:
        """Create a new check"""
        url = f"{self.api_url}/checks/"
        response = requests.post(url, headers=self.headers, json=check_data)
        response.raise_for_status()
        return response.json()
    
    def update_check(self, check_uuid: str, check_data: Dict) -> Dict:
        """Update existing check"""
        url = f"{self.api_url}/checks/{check_uuid}"
        response = requests.post(url, headers=self.headers, json=check_data)
        response.raise_for_status()
        return response.json()
    
    def delete_check(self, check_uuid: str) -> None:
        """Delete a check"""
        url = f"{self.api_url}/checks/{check_uuid}"
        response = requests.delete(url, headers=self.headers)
        response.raise_for_status()
    
    def list_channels(self) -> List[Dict]:
        """List all notification channels"""
        url = f"{self.api_url}/channels/"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()['channels']
    
    def get_channel_ids(self, channel_names: List[str]) -> List[str]:
        """Convert channel names to UUIDs"""
        if not channel_names:
            return []
        
        channels = self.list_channels()
        channel_map = {ch['name']: ch['id'] for ch in channels}
        
        channel_ids = []
        for name in channel_names:
            if name in channel_map:
                channel_ids.append(channel_map[name])
            else:
                logger.warning(f"Channel '{name}' not found, skipping")
        
        return channel_ids


def load_config(config_path: str) -> Dict:
    """Load configuration from YAML file"""
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        logger.info(f"Configuration loaded from: {config_path}")
        return config
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)


def create_or_update_check(api: HealthchecksAPI, check_config: Dict, channels: List[str]) -> Dict:
    """Create or update a single check"""
    check_name = check_config['name']
    
    # Build check data
    check_data = {
        'name': check_name,
        'tags': ' '.join(check_config.get('tags', [])),
        'desc': check_config.get('desc', ''),
        'timeout': check_config.get('timeout', 86400),
        'grace': check_config.get('grace', 3600),
        'schedule': check_config.get('schedule', '0 * * * *'),
        'tz': check_config.get('tz', 'UTC'),
        'channels': ','.join(channels) if channels else '*',  # * = all project channels
    }
    
    # Check if already exists
    existing = api.get_check_by_name(check_name)
    
    if existing:
        logger.info(f"Check '{check_name}' exists, updating...")
        result = api.update_check(existing['ping_url'].split('/')[-1], check_data)
        logger.info(f"✓ Updated check: {check_name}")
        return result
    else:
        logger.info(f"Creating new check: {check_name}")
        result = api.create_check(check_data)
        logger.info(f"✓ Created check: {check_name}")
        return result


def create_all_checks(config: Dict) -> None:
    """Create/update all configured checks"""
    api = HealthchecksAPI(config['api_key'], config['api_url'])
    
    logger.info("=" * 72)
    logger.info(f"Managing healthchecks for cluster: {config['cluster_name']}")
    logger.info(f"Environment: {config['environment']}")
    logger.info(f"Name prefix: {config['name_prefix']}")
    logger.info("=" * 72)
    
    # Resolve channel names to UUIDs
    channel_ids = []
    if config.get('channels'):
        logger.info(f"Resolving {len(config['channels'])} channel(s)...")
        channel_ids = api.get_channel_ids(config['channels'])
        logger.info(f"✓ Resolved {len(channel_ids)} channel ID(s)")
    else:
        logger.info("No specific channels configured, using project defaults")
    
    # Create/update each enabled check
    created_checks = []
    for check_key, check_config in config.get('checks', {}).items():
        logger.info("")
        logger.info(f"Processing check: {check_key}")
        
        try:
            result = create_or_update_check(api, check_config, channel_ids)
            created_checks.append({
                'key': check_key,
                'name': check_config['name'],
                'uuid': result['ping_url'].split('/')[-1],
                'ping_url': result['ping_url'],
                'pause_url': result['pause_url'],
                'update_url': result['update_url']
            })
            
            logger.info(f"Check UUID: {result['ping_url'].split('/')[-1]}")
            logger.info(f"Ping URL: {result['ping_url']}")
            
        except Exception as e:
            logger.error(f"Failed to create/update check '{check_key}': {e}")
            continue
    
    logger.info("")
    logger.info("=" * 72)
    logger.info(f"Created/updated {len(created_checks)} check(s)")
    logger.info("=" * 72)
    
    # Display summary
    for check in created_checks:
        print(f"\n{check['key']}:")
        print(f"  Name: {check['name']}")
        print(f"  UUID: {check['uuid']}")
        print(f"  Ping URL: {check['ping_url']}")


def list_checks(config: Dict) -> None:
    """List all checks in project"""
    api = HealthchecksAPI(config['api_key'], config['api_url'])
    
    checks = api.list_checks()
    
    logger.info("=" * 72)
    logger.info(f"Checks in project: {len(checks)}")
    logger.info("=" * 72)
    
    for check in checks:
        status = "✅ UP" if check['status'] == 'up' else "⏸️ PAUSED" if check['status'] == 'paused' else "❌ DOWN"
        print(f"\n{check['name']}:")
        print(f"  Status: {status}")
        print(f"  UUID: {check['ping_url'].split('/')[-1]}")
        print(f"  Tags: {check['tags']}")
        print(f"  Timeout: {check['timeout']}s / Grace: {check['grace']}s")
        print(f"  Ping URL: {check['ping_url']}")


def delete_check(config: Dict, check_name: str) -> None:
    """Delete a specific check"""
    api = HealthchecksAPI(config['api_key'], config['api_url'])
    
    existing = api.get_check_by_name(check_name)
    if not existing:
        logger.error(f"Check '{check_name}' not found")
        sys.exit(1)
    
    check_uuid = existing['ping_url'].split('/')[-1]
    logger.info(f"Deleting check: {check_name} (UUID: {check_uuid})")
    
    api.delete_check(check_uuid)
    logger.info(f"✓ Deleted check: {check_name}")


def main():
    """Main logic"""
    parser = argparse.ArgumentParser(
        description='Healthchecks.io management script',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--config', required=True,
                       help='Path to configuration YAML file')
    parser.add_argument('--action', required=True,
                       choices=['create-all', 'list', 'delete'],
                       help='Action to perform')
    parser.add_argument('--check-name', type=str,
                       help='Check name (required for delete action)')
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    try:
        if args.action == 'create-all':
            create_all_checks(config)
        elif args.action == 'list':
            list_checks(config)
        elif args.action == 'delete':
            if not args.check_name:
                logger.error("--check-name required for delete action")
                sys.exit(1)
            delete_check(config, args.check_name)
        
        return 0
        
    except requests.exceptions.HTTPError as e:
        logger.error("=" * 72)
        logger.error(f"API Error: {e}")
        logger.error(f"Response: {e.response.text if hasattr(e, 'response') else 'N/A'}")
        logger.error("=" * 72)
        return 1
    
    except Exception as e:
        logger.error("=" * 72)
        logger.error(f"Unexpected error: {e}")
        logger.error("=" * 72)
        return 1


if __name__ == '__main__':
    sys.exit(main())
