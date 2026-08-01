#!/usr/bin/env python3
"""Backup/restore SQLite database to/from GitHub"""
import os
import sys
import sqlite3
import subprocess
import base64
import json

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
REPO = 'matinhermes/mazoun-hediye'
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mazoun_hediye.db')
BACKUP_PATH = 'db_backup/mazoun_hediye.db'

def backup_to_github():
    """Commit database to GitHub"""
    if not GITHUB_TOKEN or not os.path.exists(DB_PATH):
        return False
    
    # Create backup directory
    os.makedirs('db_backup', exist_ok=True)
    
    # Copy DB to backup location
    import shutil
    shutil.copy2(DB_PATH, BACKUP_PATH)
    
    # Git add and commit
    try:
        subprocess.run(['git', 'add', BACKUP_PATH], check=True, capture_output=True)
        result = subprocess.run(['git', 'diff', '--cached', '--quiet'], capture_output=True)
        if result.returncode != 0:  # There are changes
            subprocess.run(['git', 'commit', '-m', '🤖 auto-backup: database', '-q'], check=True, capture_output=True)
            subprocess.run(['git', 'push'], check=True, capture_output=True)
            print('[BACKUP] Database backed up to GitHub')
            return True
        else:
            print('[BACKUP] No changes to backup')
            return True
    except Exception as e:
        print(f'[BACKUP] Failed: {e}')
        return False

def restore_from_github():
    """Restore database from GitHub backup"""
    if not GITHUB_TOKEN:
        return False
    
    # Check if DB has data
    try:
        conn = sqlite3.connect(DB_PATH)
        count = conn.execute('SELECT COUNT(*) FROM products').fetchone()[0]
        conn.close()
        if count > 0:
            print('[RESTORE] Database already has data, skipping')
            return True
    except:
        pass
    
    # Download from GitHub
    try:
        import requests
        url = f'https://api.github.com/repos/{REPO}/contents/{BACKUP_PATH}'
        headers = {'Authorization': f'token {GITHUB_TOKEN}'}
        resp = requests.get(url, headers=headers, timeout=30)
        
        if resp.status_code == 200:
            data = resp.json()
            content = base64.b64decode(data['content'])
            with open(DB_PATH, 'wb') as f:
                f.write(content)
            print('[RESTORE] Database restored from GitHub backup')
            return True
        else:
            print('[RESTORE] No backup found on GitHub')
            return False
    except Exception as e:
        print(f'[RESTORE] Failed: {e}')
        return False

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'backup':
        backup_to_github()
    elif len(sys.argv) > 1 and sys.argv[1] == 'restore':
        restore_from_github()
    else:
        print('Usage: python backup_db.py [backup|restore]')
