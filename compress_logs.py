# compress_logs.py
import os
import json
import argparse
import subprocess
from datetime import datetime, timedelta

INVENTORY_FILE = 'inventory.json'


def load_inventory():
    if not os.path.exists(INVENTORY_FILE):
        raise FileNotFoundError(f"'{INVENTORY_FILE}' not found.")
    with open(INVENTORY_FILE) as f:
        return json.load(f)


def should_include(filename, include_patterns, exclude_patterns):
    from fnmatch import fnmatch
    included = any(fnmatch(filename, pat) for pat in include_patterns) if include_patterns else True
    excluded = any(fnmatch(filename, pat) for pat in exclude_patterns) if exclude_patterns else False
    return included and not excluded


def compress_linux(server, user, ssh_key, base_path, include_patterns, exclude_patterns, dry_run):
    compress_cmd = (
        f"find {base_path} -type f -mtime +5 "
        f"-exec bash -c '"
        f"for f; do "
        f="$(basename \"$f\")";
        f"case \"$f\" in "
    )
    for pat in include_patterns:
        compress_cmd += f"{pat}) [[ ! $f =~ {'|'.join(exclude_patterns)} ]] && gzip \"$f\" ;; ;"
    compress_cmd += (
        "*) ;; esac; done' bash {{}} +"
    )
    ssh_cmd = [
        "ssh", "-i", ssh_key, f"{user}@{server}", compress_cmd
    ]

    print(f"\n[Linux] {server}:{base_path} → Compressing logs...")
    if dry_run:
        print("Dry-run: would run:", ' '.join(ssh_cmd))
    else:
        try:
            subprocess.run(ssh_cmd, check=True)
            print("✅ Compression complete")
        except subprocess.CalledProcessError as e:
            print(f"❌ Error: {e}")


def compress_windows(server, user, ssh_key, base_path, include_patterns, exclude_patterns, dry_run):
    print(f"\n[Windows] {server}:{base_path} → Compressing logs...")
    pattern_filter = " -or ".join([
        f"($_.Name -like '{pat}')" for pat in include_patterns
    ]) if include_patterns else "$true"
    exclude_filter = " -and ".join([
        f"($_.Name -notlike '{pat}')" for pat in exclude_patterns
    ]) if exclude_patterns else "$true"

    powershell_script = (
        f"Get-ChildItem -Path '{base_path}' -File -Recurse | "
        f"Where-Object {{ ($pattern_filter) -and ($exclude_filter) -and ($_.LastWriteTime -lt (Get-Date).AddDays(-5)) }} | "
        f"ForEach-Object {{ Compress-Archive -Path $_.FullName -DestinationPath ($_.FullName + '.zip'); Remove-Item $_.FullName }}"
    )

    ssh_cmd = [
        "ssh", "-i", ssh_key, f"{user}@{server}", f"powershell -Command \"{powershell_script}\""
    ]

    if dry_run:
        print("Dry-run: would run:", ' '.join(ssh_cmd))
    else:
        try:
            subprocess.run(ssh_cmd, check=True)
            print("✅ Compression complete")
        except subprocess.CalledProcessError as e:
            print(f"❌ Error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Compress log files older than 5 days.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without executing")
    parser.add_argument("--execute", action="store_true", help="Actually execute compression")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("❌ Please specify either --dry-run or --execute")
        return

    inventory = load_inventory()
    for server, info in inventory.items():
        os_type = info.get("os")
        users = info.get("users", {})
        for user, entries in users.items():
            ssh_key = info.get("ssh_key", {}).get(user)
            if not ssh_key:
                print(f"⚠️ No SSH key for {user}@{server}, skipping.")
                continue

            for entry in entries:
                base_path = entry["log_base_path"]
                include = entry.get("include_patterns", [])
                exclude = entry.get("exclude_patterns", [])
                if os_type == "linux":
                    compress_linux(server, user, ssh_key, base_path, include, exclude, dry_run=args.dry_run)
                elif os_type == "windows":
                    compress_windows(server, user, ssh_key, base_path, include, exclude, dry_run=args.dry_run)
                else:
                    print(f"⚠️ Unsupported OS '{os_type}' for server {server}.")


if __name__ == "__main__":
    main()
