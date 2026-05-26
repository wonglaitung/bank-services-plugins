"""
模拟后台 API

提供用户查询接口，不感知用户身份认证。
用户编号由调用方（远端 MCP 服务）控制。
"""

from fastapi import FastAPI, HTTPException
import json
import os

app = FastAPI(title="模拟后台 API")

# 加载模拟用户数据
DATA_FILE = os.path.join(os.path.dirname(__file__), "users.json")
with open(DATA_FILE, encoding="utf-8") as f:
    USERS = json.load(f)


@app.get("/api/user/{user_id}")
async def get_user(user_id: str):
    """
    查询用户信息

    Args:
        user_id: 9位数字用户编号

    Returns:
        用户信息字典

    Raises:
        400: 用户编号格式错误
        404: 用户不存在
    """
    # 验证用户编号格式
    if not user_id.isdigit() or len(user_id) != 9:
        raise HTTPException(400, "用户编号必须为9位数字")

    # 查询用户
    user = USERS.get(user_id)
    if not user:
        raise HTTPException(404, "用户不存在")

    return user


@app.get("/api/admin/{user_id}/users")
async def get_all_users(user_id: str):
    """
    管理员查询所有用户信息（不含金额）

    只有 admin 角色的用户才能调用此接口。
    返回所有用户的基本信息，不包括 balance 字段。

    Args:
        user_id: 9位数字用户编号（调用者）

    Returns:
        用户列表，每个用户包含 user_id, name, department, role

    Raises:
        400: 用户编号格式错误
        403: 非管理员用户
        404: 用户不存在
    """
    # 验证用户编号格式
    if not user_id.isdigit() or len(user_id) != 9:
        raise HTTPException(400, "用户编号必须为9位数字")

    # 查询调用者
    caller = USERS.get(user_id)
    if not caller:
        raise HTTPException(404, "用户不存在")

    # 检查是否为管理员
    if caller.get("role") != "admin":
        raise HTTPException(403, "需要管理员权限")

    # 返回所有用户信息（不含金额）
    users_list = []
    for uid, user in USERS.items():
        users_list.append({
            "user_id": user.get("user_id"),
            "name": user.get("name"),
            "department": user.get("department"),
            "role": user.get("role")
        })

    return {
        "total": len(users_list),
        "users": users_list
    }


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
