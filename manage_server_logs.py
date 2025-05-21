# manage_server_logs.py
import json
import os
import pandas as pd

LOGS_FILE = 'inventory.json'

def load_data():
    return json.load(open(LOGS_FILE)) if os.path.exists(LOGS_FILE) else {}

def save_data(data):
    with open(LOGS_FILE, 'w') as f:
        json.dump(data, f, indent=4)
    print(f"\n✅ Saved data to '{LOGS_FILE}'.")

def parse_patterns(pattern_str):
    return [p.strip() for p in str(pattern_str).split(',') if p.strip()] if pd.notna(pattern_str) else []

def view_data():
    data = load_data()
    if not data:
        print("⚠️ No data found.")
        return

    servers = input("Filter by server(s): ").strip().split(',') if input("Filter by server(s)? (press Enter to skip): ") else None
    users = input("Filter by user(s): ").strip().split(',') if input("Filter by user(s)? (press Enter to skip): ") else None

    for server, info in data.items():
        if servers and server not in servers:
            continue
        print(f"\nServer: {server}")
        print(f"  OS: {info.get('os', 'unknown')}")
        for user, entries in info.get('users', {}).items():
            if users and user not in users:
                continue
            print(f"  User: {user}")
            for e in entries:
                print(f"    Base Path: {e['log_base_path']}, Folder: {e['log_folder']}")
                print(f"    Include: {e['include_patterns']}, Exclude: {e['exclude_patterns']}")

def manual_add_update():
    data = load_data()
    server = input("Enter server name: ").strip()
    if not server:
        print("❌ Server is required.")
        return

    if server not in data:
        os_type = input("Enter OS type (linux/windows): ").strip().lower()
        if os_type not in ['linux', 'windows']:
            print("❌ Invalid OS type.")
            return
        data[server] = {'os': os_type, 'users': {}}

    while True:
        user = input("Enter user (or Enter to stop): ").strip()
        if not user:
            break

        base = input("Log base path: ").strip()
        if not base:
            print("❌ log_base_path required.")
            continue

        folder = input("Log folder: ").strip()
        include = parse_patterns(input("Include patterns (comma-separated): "))
        exclude = parse_patterns(input("Exclude patterns (comma-separated): "))

        entry = {
            'log_base_path': base,
            'log_folder': folder,
            'include_patterns': include,
            'exclude_patterns': exclude
        }

        data[server]['users'].setdefault(user, []).append(entry)
        print(f"✅ Entry added for {user}@{server}.")

    save_data(data)

def bulk_upload():
    filepath = input("CSV/XLSX path: ").strip()
    if not os.path.isfile(filepath):
        print("❌ File not found.")
        return

    try:
        df = pd.read_excel(filepath) if filepath.endswith('.xlsx') else pd.read_csv(filepath)
    except Exception as e:
        print(f"❌ Read error: {e}")
        return

    required = {'server', 'os', 'user', 'log_base_path', 'log_folder', 'include_patterns', 'exclude_patterns'}
    if not required.issubset(df.columns):
        print("❌ Missing required columns.")
        return

    data = load_data()
    stats = {"servers": 0, "users": 0, "entries": 0}

    for _, row in df.iterrows():
        s, os_type = str(row['server']).strip(), str(row['os']).strip().lower()
        u, b = str(row['user']).strip(), str(row['log_base_path']).strip()
        if not all([s, os_type, u, b]):
            continue
        f = str(row['log_folder']).strip() if pd.notna(row['log_folder']) else ""
        inc = parse_patterns(row['include_patterns'])
        exc = parse_patterns(row['exclude_patterns'])

        if s not in data:
            data[s] = {'os': os_type, 'users': {}}
            stats['servers'] += 1

        if u not in data[s]['users']:
            data[s]['users'][u] = []
            stats['users'] += 1

        data[s]['users'][u].append({
            'log_base_path': b, 'log_folder': f, 'include_patterns': inc, 'exclude_patterns': exc
        })
        stats['entries'] += 1

    save_data(data)
    print(f"✅ Bulk upload: {stats['entries']} entries.")

def bulk_remove():
    filepath = input("CSV/XLSX path: ").strip()
    if not os.path.isfile(filepath):
        print("❌ File not found.")
        return

    try:
        df = pd.read_excel(filepath) if filepath.endswith('.xlsx') else pd.read_csv(filepath)
    except Exception as e:
        print(f"❌ Load error: {e}")
        return

    if not {'server', 'user'}.issubset(df.columns):
        print("❌ 'server' and 'user' required.")
        return

    data = load_data()
    removed_u, removed_s = 0, 0

    for _, row in df.iterrows():
        s, u = str(row['server']).strip(), str(row['user']).strip()
        if s in data and u in data[s]['users']:
            del data[s]['users'][u]
            removed_u += 1
            if not data[s]['users']:
                del data[s]
                removed_s += 1

    save_data(data)
    print(f"✅ Removed users: {removed_u}, servers: {removed_s}")

def main():
    while True:
        print("\n📌 Server Log Inventory")
        print("1. View Data")
        print("2. Add/Update Entry")
        print("3. Delete Entry (via file)")
        print("4. Bulk Upload")
        print("5. Bulk Remove")
        print("6. Quit")

        choice = input("Select option (1-6): ").strip()
        if choice == '1':
            view_data()
        elif choice == '2':
            manual_add_update()
        elif choice == '3':
            bulk_remove()
        elif choice == '4':
            bulk_upload()
        elif choice == '5':
            bulk_remove()
        elif choice == '6':
            print("👋 Bye!")
            break
        else:
            print("❌ Invalid choice.")

if __name__ == '__main__':
    main()
