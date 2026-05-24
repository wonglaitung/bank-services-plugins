"""
Token 生成工具

用于原型测试时生成加密 Token。
Token 包含 user_id 和 expires_at，使用 AES-256-GCM 加密。

使用方法:
    # 生成密钥并保存
    python generate_token.py --generate-key

    # 生成 Token（使用保存的密钥）
    python generate_token.py --user-id 000000001 --expires 8

    # 或者指定密钥
    TOKEN_KEY=<base64密钥> python generate_token.py --user-id 000000001 --expires 8
"""

import os
import sys
import json
import base64
import argparse
from datetime import datetime, timezone, timedelta

# 添加父目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    print("错误: 需要安装 cryptography 库")
    print("运行: pip install cryptography")
    sys.exit(1)


# 密钥文件路径
KEY_FILE = os.path.join(os.path.dirname(__file__), '.token_key')


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
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, 'rb') as f:
            return f.read()

    # 都没有则生成新密钥并保存
    key = generate_key()
    save_key(key)
    print(f"已生成新密钥并保存到 {KEY_FILE}")
    return key


def generate_token(user_id: str, expires_hours: int = 8, key: bytes = None) -> str:
    """
    生成加密 Token

    Args:
        user_id: 用户编号（9位数字）
        expires_hours: 有效期（小时）
        key: AES-256 密钥（32 bytes），不提供则自动加载

    Returns:
        Base64 编码的加密 Token
    """
    if key is None:
        key = load_key()

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=expires_hours)

    token_data = {
        "user_id": user_id,
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
    return base64.b64encode(encrypted).decode('utf-8')


def main():
    parser = argparse.ArgumentParser(description='生成加密 Token')
    parser.add_argument('--generate-key', action='store_true',
                        help='生成新的 AES-256 密钥并保存')
    parser.add_argument('--user-id', type=str,
                        help='用户编号（9位数字）')
    parser.add_argument('--expires', type=int, default=8,
                        help='有效期（小时），默认 8 小时')
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

        # 生成 Token
        token = generate_token(args.user_id, args.expires)
        print(f"# 用户编号: {args.user_id}")
        print(f"# 有效期: {args.expires} 小时")
        print(f"MCP_AUTH_TOKEN={token}")
        return

    # 无参数时显示帮助
    parser.print_help()


if __name__ == "__main__":
    main()
