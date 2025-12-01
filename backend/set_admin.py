#!/usr/bin/env python
"""
관리자 권한 설정 CLI 스크립트
사용법: python set_admin.py <email> [--remove]
"""

import sys
import os

# 현재 디렉토리를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auth import set_admin, get_db_connection, get_placeholder, IS_POSTGRES


def list_users():
    """모든 사용자 목록 출력"""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT id, email, name, plan, is_admin FROM users ORDER BY id")
    users = c.fetchall()
    conn.close()
    
    print("\n📋 사용자 목록:")
    print("-" * 80)
    print(f"{'ID':<5} {'이메일':<30} {'이름':<15} {'플랜':<10} {'관리자'}")
    print("-" * 80)
    
    for user in users:
        if IS_POSTGRES:
            uid, email, name, plan, is_admin = user
        else:
            uid = user['id']
            email = user['email']
            name = user['name']
            plan = user['plan']
            is_admin = user['is_admin']
        
        admin_mark = "✅" if is_admin else ""
        print(f"{uid:<5} {email:<30} {(name or '-'):<15} {plan:<10} {admin_mark}")
    
    print("-" * 80)
    print(f"총 {len(users)}명")


def main():
    if len(sys.argv) < 2:
        print("Kampai 관리자 설정 도구")
        print("=" * 40)
        print("\n사용법:")
        print("  python set_admin.py <email>           # 관리자 권한 부여")
        print("  python set_admin.py <email> --remove  # 관리자 권한 해제")
        print("  python set_admin.py --list            # 사용자 목록")
        print()
        return
    
    if sys.argv[1] == "--list":
        list_users()
        return
    
    email = sys.argv[1]
    is_admin = "--remove" not in sys.argv
    
    result = set_admin(email, is_admin)
    
    if result['success']:
        print(f"✅ {result['message']}")
    else:
        print(f"❌ {result['error']}")


if __name__ == "__main__":
    main()
