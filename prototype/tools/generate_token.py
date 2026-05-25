#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Token 生成工具

用于生成 Access Token 和 Refresh Token 对。
- Access Token: 15 分钟有效期，用于 API 调用
- Refresh Token: 可配置有效期（默认 7 天），用于获取新 Access Token

使用方法:
    # 生成密钥并保存
    python generate_token.py --generate-key

    # 生成 Token 对
    python generate_token.py --user-id 000000001 --refresh-expires 7

    # 查看密钥
    python generate_token.py --show-key
"""

import os
import sys
import json
import base64
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    print("错误: 需要安装 cryptography 库")
    print("运行: pip install cryptography")
    sys.exit(1)


# 文件路径
TOOLS_DIR = Path(__file__).parent
KEY_FILE = TOOLS_DIR / ".token_key"
TOKEN_RECORDS_FILE = TOOLS_DIR / "token_records.json"
REVOKED_TOKENS_FILE = TOOLS_DIR / "revoked_tokens.json"

# Token 类型
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

# Token 有效期
ACCESS_TOKEN_EXPIRES_MINUTES = 15  # Access Token 固定 15 分钟


def generate_key() -> bytes:
    """生成新的 AES-256 密钥"""
    return os.urandom(32)


def save_key(key: bytes):
    """保存密钥到文件"""
    with open(KEY_FILE, 'wb') as f:
        f.write(key)
    # 设置文件权限为仅所有者可读写
    os.chmod(KEY_FILE, 0o600)


def load_key() -> bytes:
    """加载密钥（优先从环境变量，其次从文件）"""
    # 优先从环境变量读取
    env_key = os.environ.get('TOKEN_KEY')
    if env_key:
        return base64.b64decode(env_key)

    # 其次从文件读取
    if KEY_FILE.exists():
        with open(KEY_FILE, 'rb') as f:
            return f.read()

    # 都没有则生成新密钥并保存
    key = generate_key()
    save_key(key)
    print(f"已生成新密钥并保存到 {KEY_FILE}")
    return key


def generate_token(user_id: str, token_type: str, expires_at: datetime, key: bytes) -> str:
    """
    生成加密 Token

    Args:
        user_id: 用户编号（9位数字）
        token_type: Token 类型 (access/refresh)
        expires_at: 过期时间
        key: AES-256 密钥（32 bytes）

    Returns:
        Base64 编码的加密 Token
    """
    import secrets

    now = datetime.now(timezone.utc)
    jti = secrets.token_urlsafe(16)  # Token 唯一标识

    token_data = {
        "user_id": user_id,
        "token_type": token_type,
        "jti": jti,
        "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "issued_at": now.strftime("%Y-%m-%dT%H:%M:%SZ")
    }

    # AES-GCM 加密
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    plaintext = json.dumps(token_data).encode('utf-8')
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    # 组装并 Base64 编码
    encrypted = nonce + ciphertext
    return base64.b64encode(encrypted).decode('utf-8'), jti


def load_token_records() -> list:
    """加载 Token 记录"""
    if TOKEN_RECORDS_FILE.exists():
        with open(TOKEN_RECORDS_FILE, 'r') as f:
            return json.load(f)
    return []


def save_token_records(records: list):
    """保存 Token 记录"""
    with open(TOKEN_RECORDS_FILE, 'w') as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    os.chmod(TOKEN_RECORDS_FILE, 0o600)


def main():
    parser = argparse.ArgumentParser(description='生成 Access Token 和 Refresh Token')
    parser.add_argument('--generate-key', action='store_true',
                        help='生成新的 AES-256 密钥并保存')
    parser.add_argument('--user-id', type=str,
                        help='用户编号（9位数字）')
    parser.add_argument('--refresh-expires', type=int, default=7,
                        help='Refresh Token 有效期（天），默认 7 天')
    parser.add_argument('--show-key', action='store_true',
                        help='显示当前密钥（Base64）')

    args = parser.parse_args()

    if args.generate_key:
        # 生成新密钥
        key = generate_key()
        save_key(key)
        key_b64 = base64.b64encode(key).decode('utf-8')
        print(f"已生成新密钥:")
        print(f"TOKEN_KEY={key_b64}")
        print(f"密钥已保存到: {KEY_FILE}")
        return

    if args.show_key:
        # 显示当前密钥
        key = load_key()
        key_b64 = base64.b64encode(key).decode('utf-8')
        print(f"TOKEN_KEY={key_b64}")
        return

    if args.user_id:
        # 验证用户编号格式
        if not args.user_id.isdigit() or len(args.user_id) != 9:
            print(f"错误: 用户编号必须为9位数字，当前: {args.user_id}")
            sys.exit(1)

        # 加载密钥
        key = load_key()

        now = datetime.now(timezone.utc)

        # 生成 Access Token（15 分钟有效）
        access_expires = now + timedelta(minutes=ACCESS_TOKEN_EXPIRES_MINUTES)
        access_token, access_jti = generate_token(
            args.user_id, TOKEN_TYPE_ACCESS, access_expires, key
        )

        # 生成 Refresh Token（可配置天数）
        refresh_expires = now + timedelta(days=args.refresh_expires)
        refresh_token, refresh_jti = generate_token(
            args.user_id, TOKEN_TYPE_REFRESH, refresh_expires, key
        )

        # 保存 Token 记录
        records = load_token_records()
        records.append({
            "user_id": args.user_id,
            "refresh_jti": refresh_jti,
            "refresh_expires_at": refresh_expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "issued_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": "active"
        })
        save_token_records(records)

        # 输出结果
        print(f"# 用户编号: {args.user_id}")
        print(f"# Access Token 有效期: {ACCESS_TOKEN_EXPIRES_MINUTES} 分钟")
        print(f"# Refresh Token 有效期: {args.refresh_expires} 天")
        print(f"# Token 记录已保存到: {TOKEN_RECORDS_FILE}")
        print()
        print(f"MCP_REFRESH_TOKEN={refresh_token}")
        print()
        print("# 将此 Refresh Token 配置到 .mcp.json 的 env 中:")
        print('# "MCP_REFRESH_TOKEN": "<Refresh Token>"')

        return

    # 无参数时显示帮助
    parser.print_help()


if __name__ == "__main__":
    main()
