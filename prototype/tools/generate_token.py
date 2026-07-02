#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Token 生成与解密工具

用于生成 Access Token 和 Refresh Token 对，以及解密 Token 查看内容。
- Access Token: 15 分钟有效期，用于 API 调用
- Refresh Token: 可配置有效期（默认 7 天），用于获取新 Access Token

使用方法:
    # 生成 RSA 密钥对并保存
    python generate_token.py --generate-key

    # 生成 Token 对
    python generate_token.py --user-id 000000001 --refresh-expires 7

    # 查看公钥（用于本地代理）
    python generate_token.py --show-public-key

    # 查看私钥（用于远端服务）
    python generate_token.py --show-private-key

    # 解密 Token 查看内容
    python generate_token.py --decrypt <token>
    python generate_token.py --decrypt-file /path/to/token.txt
"""

import os
import sys
import json
import base64
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.backends import default_backend
except ImportError:
    print("错误: 需要安装 cryptography 库")
    print("运行: pip install cryptography")
    sys.exit(1)


# 文件路径
TOOLS_DIR = Path(__file__).parent
PRIVATE_KEY_FILE = TOOLS_DIR / "private_key.pem"
PUBLIC_KEY_FILE = TOOLS_DIR / "public_key.pem"
TOKEN_RECORDS_FILE = TOOLS_DIR / "token_records.json"
REVOKED_TOKENS_FILE = TOOLS_DIR / "revoked_tokens.json"

# Token 类型
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

# Token 有效期
ACCESS_TOKEN_EXPIRES_MINUTES = 15  # Access Token 固定 15 分钟


def generate_rsa_keypair():
    """生成 RSA-2048 密钥对"""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    public_key = private_key.public_key()
    return private_key, public_key


def save_keypair(private_key, public_key):
    """保存密钥对到 PEM 文件"""
    # 保存私钥
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    with open(PRIVATE_KEY_FILE, 'wb') as f:
        f.write(private_pem)
    os.chmod(PRIVATE_KEY_FILE, 0o600)

    # 保存公钥
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    with open(PUBLIC_KEY_FILE, 'wb') as f:
        f.write(public_pem)

    print(f"私钥已保存到: {PRIVATE_KEY_FILE}")
    print(f"公钥已保存到: {PUBLIC_KEY_FILE}")


def load_private_key():
    """加载私钥（优先从环境变量，其次从文件）"""
    env_key = os.environ.get('RSA_PRIVATE_KEY')
    if env_key:
        return serialization.load_pem_private_key(
            env_key.encode('utf-8'),
            password=None,
            backend=default_backend()
        )

    if PRIVATE_KEY_FILE.exists():
        with open(PRIVATE_KEY_FILE, 'rb') as f:
            return serialization.load_pem_private_key(
                f.read(),
                password=None,
                backend=default_backend()
            )

    raise FileNotFoundError("未找到私钥，请先运行 --generate-key 生成密钥对")


def load_public_key():
    """加载公钥（优先从环境变量，其次从文件）"""
    env_key = os.environ.get('RSA_PUBLIC_KEY')
    if env_key:
        return serialization.load_pem_public_key(
            env_key.encode('utf-8'),
            backend=default_backend()
        )

    if PUBLIC_KEY_FILE.exists():
        with open(PUBLIC_KEY_FILE, 'rb') as f:
            return serialization.load_pem_public_key(
                f.read(),
                backend=default_backend()
            )

    raise FileNotFoundError("未找到公钥，请先运行 --generate-key 生成密钥对")


def generate_token(user_id: str, token_type: str, expires_at: datetime, public_key) -> str:
    """
    生成 RSA 加密 Token

    Args:
        user_id: 用户编号（9位数字）
        token_type: Token 类型 (access/refresh)
        expires_at: 过期时间
        public_key: RSA 公钥

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

    # RSA-OAEP 加密
    plaintext = json.dumps(token_data).encode('utf-8')
    ciphertext = public_key.encrypt(
        plaintext,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )

    return base64.b64encode(ciphertext).decode('utf-8'), jti


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


def decrypt_token(token_b64: str, private_key) -> dict:
    """
    解密 Token 获取内容

    Args:
        token_b64: Base64 编码的加密 Token
        private_key: RSA 私钥

    Returns:
        包含 user_id, token_type, jti, expires_at, issued_at 的字典

    Raises:
        ValueError: Token 无效或解密失败
    """
    try:
        # 1. 清理 Token 字符串
        token_b64 = token_b64.strip()

        # 2. 补齐 Base64 padding（如果需要）
        padding_needed = 4 - (len(token_b64) % 4)
        if padding_needed != 4:
            token_b64 += '=' * padding_needed

        # 3. Base64 解码
        ciphertext = base64.b64decode(token_b64)

        # 4. RSA-OAEP 解密
        plaintext = private_key.decrypt(
            ciphertext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        # 5. 解析 JSON
        token_data = json.loads(plaintext.decode('utf-8'))

        return token_data

    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Token 解密失败: {str(e)}")


def print_token_info(token_data: dict):
    """打印 Token 信息"""
    print("=" * 50)
    print("Token 内容:")
    print("=" * 50)
    print(f"  用户编号:   {token_data.get('user_id', 'N/A')}")
    print(f"  Token 类型: {token_data.get('token_type', 'N/A')}")
    print(f"  Token ID:   {token_data.get('jti', 'N/A')}")
    print(f"  签发时间:   {token_data.get('issued_at', 'N/A')}")
    print(f"  过期时间:   {token_data.get('expires_at', 'N/A')}")
    print("=" * 50)

    # 检查有效期
    if 'expires_at' in token_data:
        expires_at_str = token_data['expires_at']
        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)

            if now > expires_at:
                print("  状态: ❌ 已过期")
            else:
                remaining = expires_at - now
                if remaining.days > 0:
                    print(f"  状态: ✅ 有效 (剩余 {remaining.days} 天 {remaining.seconds // 3600} 小时)")
                else:
                    hours = remaining.seconds // 3600
                    minutes = (remaining.seconds % 3600) // 60
                    print(f"  状态: ✅ 有效 (剩余 {hours} 小时 {minutes} 分钟)")
        except Exception:
            print("  状态: ⚠️ 无法解析过期时间")

    print()
    print("完整 JSON:")
    print(json.dumps(token_data, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description='生成 Access Token 和 Refresh Token，以及解密 Token')
    parser.add_argument('--generate-key', action='store_true',
                        help='生成新的 RSA-2048 密钥对并保存')
    parser.add_argument('--user-id', type=str,
                        help='用户编号（9位数字）')
    parser.add_argument('--refresh-expires', type=int, default=7,
                        help='Refresh Token 有效期（天），默认 7 天')
    parser.add_argument('--show-public-key', action='store_true',
                        help='显示当前公钥（PEM 格式）')
    parser.add_argument('--show-private-key', action='store_true',
                        help='显示当前私钥（PEM 格式）')
    parser.add_argument('--decrypt', type=str, metavar='TOKEN',
                        help='解密 Token 并显示内容')
    parser.add_argument('--decrypt-file', type=str, metavar='FILE',
                        help='从文件读取 Token 并解密')

    args = parser.parse_args()

    if args.generate_key:
        # 生成新密钥对
        private_key, public_key = generate_rsa_keypair()
        save_keypair(private_key, public_key)
        return

    if args.show_public_key:
        # 显示公钥
        public_key = load_public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        print("RSA_PUBLIC_KEY=")
        print(public_pem.decode('utf-8'))
        return

    if args.show_private_key:
        # 显示私钥
        private_key = load_private_key()
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        print("RSA_PRIVATE_KEY=")
        print(private_pem.decode('utf-8'))
        return

    if args.user_id:
        # 验证用户编号格式
        if not args.user_id.isdigit() or len(args.user_id) != 9:
            print(f"错误: 用户编号必须为9位数字，当前: {args.user_id}")
            sys.exit(1)

        # 加载公钥
        public_key = load_public_key()

        now = datetime.now(timezone.utc)

        # 生成 Access Token（15 分钟有效）
        access_expires = now + timedelta(minutes=ACCESS_TOKEN_EXPIRES_MINUTES)
        access_token, access_jti = generate_token(
            args.user_id, TOKEN_TYPE_ACCESS, access_expires, public_key
        )

        # 生成 Refresh Token（可配置天数）
        refresh_expires = now + timedelta(days=args.refresh_expires)
        refresh_token, refresh_jti = generate_token(
            args.user_id, TOKEN_TYPE_REFRESH, refresh_expires, public_key
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

    if args.decrypt or args.decrypt_file:
        # 解密 Token
        private_key = load_private_key()

        if args.decrypt_file:
            # 从文件读取 Token
            with open(args.decrypt_file, 'r') as f:
                token_b64 = f.read().strip()
        else:
            token_b64 = args.decrypt.strip()

        # 移除可能的前缀 (如 "MCP_REFRESH_TOKEN=")
        # 注意：Base64 padding 也使用 '='，所以只处理明确的前缀格式
        if token_b64.startswith('MCP_REFRESH_TOKEN='):
            token_b64 = token_b64[len('MCP_REFRESH_TOKEN='):]

        try:
            token_data = decrypt_token(token_b64, private_key)
            print_token_info(token_data)
        except ValueError as e:
            print(f"错误: {e}")
            sys.exit(1)

        return

    # 无参数时显示帮助
    parser.print_help()


if __name__ == "__main__":
    main()
