#!/usr/bin/env python3
"""
生成 bcrypt 密码哈希，用于填写 .env 中的 AUTH_PASSWORD_HASH。

用法:
    python scripts/hash_password.py
    python scripts/hash_password.py --password 'your_password'
"""

import argparse
import getpass

import bcrypt


def main():
    parser = argparse.ArgumentParser(description="Generate bcrypt password hash")
    parser.add_argument("--password", "-p", help="Password to hash (prompted if omitted)")
    args = parser.parse_args()

    password = args.password
    if not password:
        password = getpass.getpass("Enter password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("❌ Passwords do not match")
            return

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    print(f"\n✅ Password hash generated. Add this to your .env:\n")
    print(f"AUTH_PASSWORD_HASH={hashed}")


if __name__ == "__main__":
    main()
