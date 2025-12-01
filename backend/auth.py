# ============================================
# Kampai 인증 & 구독 시스템
# 회원가입, 로그인, JWT 인증, 구독 관리
# ============================================

import os
import sqlite3
import hashlib
import secrets
import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

# 설정 (.env에서 로드)
# 클라우드 환경에서는 상대 경로 사용
_default_db = Path(__file__).parent / "kampai.db"
DB_PATH = Path(os.environ.get("DB_PATH", str(_default_db)))
# JWT_SECRET: .env에 설정된 값 사용, 없으면 랜덤 생성 (서버 재시작 시 세션 무효화)
JWT_SECRET = os.environ.get("JWT_SECRET") or secrets.token_hex(32)
JWT_EXPIRY_HOURS = 24 * 7  # 7일

# 플랜 정의 (4단계 + 모델 차등)
PLANS = {
    "free": {
        "name": "Free",
        "price": 0,
        "daily_limit": 3,
        "model": "flux-schnell",
        "model_name": "FLUX.1 Schnell",
        "resolution": "1024x1024",
        "watermark": True,
        "commercial": False,
        "speed": "2-4초",
        "cost_per_image": 0.003
    },
    "basic": {
        "name": "Basic",
        "price": 4900,
        "daily_limit": 30,
        "model": "flux-schnell",
        "model_name": "FLUX.1 Schnell",
        "resolution": "1024x1024",
        "watermark": False,
        "commercial": True,
        "speed": "2-4초",
        "cost_per_image": 0.003
    },
    "pro": {
        "name": "Pro",
        "price": 19900,
        "daily_limit": 100,
        "model": "qwen-image",
        "model_name": "Qwen-Image",
        "available_models": ["qwen-image", "flux-1.1-pro-ultra"],
        "resolution": "2048x2048",
        "watermark": False,
        "commercial": True,
        "speed": "3-8초",
        "cost_per_image": 0.025,
        "features": ["모델 선택", "텍스트 렌더링", "4K 지원"]
    },
    "business": {
        "name": "Business",
        "price": 99000,
        "daily_limit": 500,
        "model": "qwen-image",
        "model_name": "Qwen-Image / FLUX Ultra",
        "available_models": ["qwen-image", "flux-1.1-pro-ultra"],
        "resolution": "2048x2048",
        "watermark": False,
        "commercial": True,
        "speed": "3-8초",
        "cost_per_image": 0.025,
        "team_members": 5,
        "api_access": True
    }
}


def init_db():
    """데이터베이스 초기화"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 사용자 테이블
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT,
            plan TEXT DEFAULT 'free',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    
    # 구독 테이블
    c.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            payment_key TEXT,
            order_id TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # 사용량 테이블
    c.execute('''
        CREATE TABLE IF NOT EXISTS usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date DATE DEFAULT (DATE('now')),
            generation_count INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, date)
        )
    ''')
    
    # 생성 기록 테이블
    c.execute('''
        CREATE TABLE IF NOT EXISTS generations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            prompt TEXT,
            style TEXT,
            image_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # 결제 기록 테이블
    c.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            order_id TEXT UNIQUE NOT NULL,
            payment_key TEXT,
            amount INTEGER NOT NULL,
            plan TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized")


def hash_password(password: str) -> str:
    """비밀번호 해싱"""
    salt = "kampai_salt_2025"  # 프로덕션에서는 개별 salt 사용
    return hashlib.sha256(f"{password}{salt}".encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """비밀번호 검증"""
    return hash_password(password) == password_hash


def create_token(user_id: int, email: str) -> str:
    """JWT 토큰 생성"""
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def verify_token(token: str) -> dict:
    """JWT 토큰 검증"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def token_required(f):
    """인증 필수 데코레이터"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({"success": False, "error": "토큰이 필요합니다"}), 401
        
        payload = verify_token(token)
        if not payload:
            return jsonify({"success": False, "error": "유효하지 않은 토큰입니다"}), 401
        
        # 사용자 정보 조회
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, email, plan, is_active FROM users WHERE id = ?", (payload['user_id'],))
        user = c.fetchone()
        conn.close()
        
        if not user or not user[3]:
            return jsonify({"success": False, "error": "비활성화된 계정입니다"}), 401
        
        request.user = {
            "id": user[0],
            "email": user[1],
            "plan": user[2]
        }
        
        return f(*args, **kwargs)
    return decorated


def optional_token(f):
    """선택적 인증 데코레이터 (비로그인도 허용)"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        request.user = None
        
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        if token:
            payload = verify_token(token)
            if payload:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("SELECT id, email, plan FROM users WHERE id = ?", (payload['user_id'],))
                user = c.fetchone()
                conn.close()
                
                if user:
                    request.user = {
                        "id": user[0],
                        "email": user[1],
                        "plan": user[2]
                    }
        
        return f(*args, **kwargs)
    return decorated


# ============================================
# 회원가입 / 로그인
# ============================================

def register_user(email: str, password: str, name: str = None) -> dict:
    """회원가입"""
    if len(password) < 8:
        return {"success": False, "error": "비밀번호는 8자 이상이어야 합니다"}
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 이메일 중복 확인
    c.execute("SELECT id FROM users WHERE email = ?", (email,))
    if c.fetchone():
        conn.close()
        return {"success": False, "error": "이미 가입된 이메일입니다"}
    
    # 사용자 생성
    password_hash = hash_password(password)
    c.execute(
        "INSERT INTO users (email, password_hash, name, plan) VALUES (?, ?, ?, 'free')",
        (email, password_hash, name)
    )
    user_id = c.lastrowid
    
    # 오늘 사용량 초기화
    c.execute(
        "INSERT OR IGNORE INTO usage (user_id, date, generation_count) VALUES (?, DATE('now'), 0)",
        (user_id,)
    )
    
    conn.commit()
    conn.close()
    
    # 토큰 발급
    token = create_token(user_id, email)
    
    return {
        "success": True,
        "message": "회원가입이 완료되었습니다",
        "user": {
            "id": user_id,
            "email": email,
            "name": name,
            "plan": "free"
        },
        "token": token
    }


def login_user(email: str, password: str) -> dict:
    """로그인"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT id, email, password_hash, name, plan, is_active FROM users WHERE email = ?", (email,))
    user = c.fetchone()
    
    if not user:
        conn.close()
        return {"success": False, "error": "이메일 또는 비밀번호가 올바르지 않습니다"}
    
    if not user[5]:
        conn.close()
        return {"success": False, "error": "비활성화된 계정입니다"}
    
    if not verify_password(password, user[2]):
        conn.close()
        return {"success": False, "error": "이메일 또는 비밀번호가 올바르지 않습니다"}
    
    # 마지막 로그인 업데이트
    c.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user[0],))
    conn.commit()
    conn.close()
    
    # 토큰 발급
    token = create_token(user[0], user[1])
    
    return {
        "success": True,
        "message": "로그인 성공",
        "user": {
            "id": user[0],
            "email": user[1],
            "name": user[3],
            "plan": user[4]
        },
        "token": token
    }


# ============================================
# 사용량 관리
# ============================================

def get_user_usage(user_id: int) -> dict:
    """사용자 사용량 조회"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 사용자 플랜 조회
    c.execute("SELECT plan FROM users WHERE id = ?", (user_id,))
    result = c.fetchone()
    if not result:
        conn.close()
        return None
    
    plan = result[0]
    plan_info = PLANS.get(plan, PLANS['free'])
    
    # 오늘 사용량 조회
    c.execute(
        "SELECT generation_count FROM usage WHERE user_id = ? AND date = DATE('now')",
        (user_id,)
    )
    result = c.fetchone()
    today_count = result[0] if result else 0
    
    # 총 생성 수 조회
    c.execute("SELECT COUNT(*) FROM generations WHERE user_id = ?", (user_id,))
    total_count = c.fetchone()[0]
    
    conn.close()
    
    daily_limit = plan_info['daily_limit']
    remaining = daily_limit - today_count if daily_limit > 0 else -1
    
    return {
        "plan": plan,
        "plan_info": plan_info,
        "today_count": today_count,
        "daily_limit": daily_limit,
        "remaining": remaining,
        "total_generated": total_count,
        "can_generate": daily_limit < 0 or today_count < daily_limit
    }


def check_can_generate(user_id: int) -> dict:
    """생성 가능 여부 확인"""
    usage = get_user_usage(user_id)
    if not usage:
        return {"can_generate": False, "error": "사용자를 찾을 수 없습니다"}
    
    if not usage['can_generate']:
        return {
            "can_generate": False,
            "error": f"오늘의 무료 생성 횟수({usage['daily_limit']}회)를 모두 사용했습니다. Pro로 업그레이드하세요!",
            "usage": usage
        }
    
    return {"can_generate": True, "usage": usage}


def increment_usage(user_id: int, action: str = 'generate', prompt: str = None, style: str = None, image_path: str = None):
    """사용량 증가"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 오늘 사용량 증가 (없으면 생성)
    c.execute('''
        INSERT INTO usage (user_id, date, generation_count) 
        VALUES (?, DATE('now'), 1)
        ON CONFLICT(user_id, date) 
        DO UPDATE SET generation_count = generation_count + 1
    ''', (user_id,))
    
    # 생성 기록 저장
    if prompt or action:
        c.execute(
            "INSERT INTO generations (user_id, prompt, style, image_path) VALUES (?, ?, ?, ?)",
            (user_id, prompt or f'[{action}]', style, image_path)
        )
    
    conn.commit()
    conn.close()


# ============================================
# 구독 관리
# ============================================

def update_user_plan(user_id: int, plan: str, payment_key: str = None, order_id: str = None):
    """사용자 플랜 업데이트"""
    if plan not in PLANS:
        return {"success": False, "error": "유효하지 않은 플랜입니다"}
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 사용자 플랜 업데이트
    c.execute("UPDATE users SET plan = ? WHERE id = ?", (plan, user_id))
    
    # 구독 기록 추가
    expires_at = datetime.now() + timedelta(days=30)  # 30일 구독
    c.execute('''
        INSERT INTO subscriptions (user_id, plan, status, expires_at, payment_key, order_id)
        VALUES (?, ?, 'active', ?, ?, ?)
    ''', (user_id, plan, expires_at, payment_key, order_id))
    
    conn.commit()
    conn.close()
    
    return {"success": True, "message": f"{PLANS[plan]['name']} 플랜으로 업그레이드되었습니다"}


def get_subscription_status(user_id: int) -> dict:
    """구독 상태 조회"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''
        SELECT plan, status, started_at, expires_at 
        FROM subscriptions 
        WHERE user_id = ? AND status = 'active'
        ORDER BY started_at DESC LIMIT 1
    ''', (user_id,))
    
    sub = c.fetchone()
    conn.close()
    
    if not sub:
        return {"active": False, "plan": "free"}
    
    # 만료 확인
    expires_at = datetime.fromisoformat(sub[3]) if sub[3] else None
    is_expired = expires_at and datetime.now() > expires_at
    
    return {
        "active": not is_expired,
        "plan": sub[0],
        "status": sub[1],
        "started_at": sub[2],
        "expires_at": sub[3],
        "is_expired": is_expired
    }


# 초기화
init_db()
