import json
import os
import subprocess
import re
from datetime import datetime, timedelta
import argparse

INVENTORY_FILE = 'inventory.json'
USER_KEYS_FILE = 'server_user_keys.json'
COMPRESS_THRESHOLD_DAYS = 5

def load_json_file(path):
    if not os.path.exists(path):
        print(f"❌ File '{path}' not found.")
        exit(1)
    with open(path) as f:
        return json.load(f)

def run_ssh_command(server, user, ssh_key, cmd):
    ssh_cmd = ["ssh", "-i", ssh_key, f"{user}@{server}", cmd]
    try:
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"❌ SSH command failed on {server} user {user}: {result.stderr.strip()}")
            return None
        return result.stdout.strip().splitlines()
    except Exception as e:
        print(f"❌ SSH command error on {server} user {user}: {e}")
        return None

def parse_date_linux(filename):
    m1 = re.search(r'\.(\d{4}-\d{2}-\d{2})', filename)
    if m1:
        try:
            return datetime.strptime(m1.group(1), '%Y-%m-%d').date()
        except:
            return None
    m2 = re.search(r'\.(\d{12})', filename)
    if m2:
        try:
            return datetime.strptime(m2.group(1)[:8], '%Y%m%d').date()
        except:
            return None
    return None

def parse_date_windows(filename):
    m = re.search(r'_ex(\d{6})', filename)
    if m:
        try:
            dt = datetime.strptime(m.group(1), '%y%m%d').date()
            return dt
        except:
            return None
    return None

def matches_pattern(filename, patterns):
    if not patterns:
        return True
    for pat in patterns:
        pat = pat.strip()
        if not pat:
            continue
        regex = '^' + re.escape(pat).replace(r'\*', '.*').replace(r'\?', '.') + '$'
        if re.match(regex, filename, re.IGNORECASE):
            return True
    return False

def find_files_to_compress(server, os_type, user, ssh_key, base_path, include_patterns, exclude_patterns):
    threshold_date = datetime.now().date() - timedelta(days=COMPRESS_THRESHOLD_DAYS)
    
    if os_type.lower() == 'linux':
        # Find files NOT compressed yet (.log, .txt, etc.) but not .gz or .zip
        # Example: find all files except *.gz and *.zip
        cmd = f"find '{base_path}' -type f ! -name '*.gz' ! -name '*.zip'"
    else:
        # Windows powershell: get all files except *.gz and *.zip
        cmd = (f"powershell -Command \"Get-ChildItem -Path '{base_path}' -Recurse "
               f"-File | Where-Object {{ $_.Extension -notin '.gz', '.zip' }} | Select-Object -ExpandProperty FullName\"")

    files = run_ssh_command(server, user, ssh_key, cmd)
    if files is None:
        return []

    filtered_files = []
    for f in files:
        fname = os.path.basename(f)
        if include_patterns and not matches_pattern(fname, include_patterns):
            continue
        if exclude_patterns and matches_pattern(fname, exclude_patterns):
            continue
        
        # parse date from filename
        if os_type.lower() == 'linux':
            file_date = parse_date_linux(fname)
        else:
            file_date = parse_date_windows(fname)

        if file_date is None:
            print(f"⚠️ Could not parse date from filename '{fname}' on {server} user {user}, skipping")
            continue

        if file_date <= threshold_date:
            filtered_files.append(f)
    return filtered_files

def compress_file(server, user, ssh_key, filepath, os_type, dry_run):
    if dry_run:
        print(f"[DRY-RUN] Would compress {filepath} on {server} user {user}")
        return

    if os_type.lower() == 'linux':
        cmd = f"gzip '{filepath}'"
    else:
        # Windows: Use powershell compress archive command for single file? 
        # But gzip may not be installed, so fallback to zip (single file zip)
        # Powershell zip single file: Compress-Archive -Path filepath -DestinationPath filepath.zip
        cmd = (f"powershell -Command \"Compress-Archive -Path '{filepath}' -DestinationPath '{filepath}.zip' -Force; "
               f"Remove-Item -Force '{filepath}'\"")

    result = run_ssh_command(server, user, ssh_key, cmd)
    if result is None:
        print(f"❌ Failed to compress {filepath} on {server} user {user}")
    else:
        print(f"✅ Compressed {filepath} on {server} user {user}")

def main():
    parser = argparse.ArgumentParser(description="Compress log files older than 5 days (not yet compressed).")
    parser.add_argument('--dry-run', action='store_true', help='List files that would be compressed without compressing')
    args = parser.parse_args()

    inventory = load_json_file(INVENTORY_FILE)
    user_keys = load_json_file(USER_KEYS_FILE)

    if not inventory:
        print("⚠️ Inventory is empty.")
        return
    if not user_keys:
        print("⚠️ User keys file is empty or missing.")
        return

    for server, info in inventory.items():
        os_type = info.get('os', 'linux')
        users = info.get('users', {})

        if server not in user_keys:
            print(f"❌ No SSH keys info for server '{server}', skipping.")
            continue
        key_users = user_keys[server].get('users', {})

        for user, entries in users.items():
            ssh_key = key_users.get(user)
            if not ssh_key or not os.path.exists(ssh_key):
                print(f"❌ Missing or invalid SSH key for {user}@{server}, skipping.")
                continue

            for entry in entries:
                base_path = entry.get('log_base_path')
                include_patterns = entry.get('include_patterns', [])
                exclude_patterns = entry.get('exclude_patterns', [])
                print(f"\n🔍 Processing compress on {server} ({os_type}) user {user} base_path '{base_path}'")

                files_to_compress = find_files_to_compress(server, os_type, user, ssh_key, base_path, include_patterns, exclude_patterns)
                if not files_to_compress:
                    print(f"ℹ️ No files to compress on {server} user {user} base_path '{base_path}'")
                    continue

                for filepath in files_to_compress:
                    compress_file(server, user, ssh_key, filepath, os_type, args.dry_run)

if __name__ == '__main__':
    main()
