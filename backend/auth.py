# ============================================
# Kampai 인증 & 구독 시스템
# 회원가입, 로그인, JWT 인증, 구독 관리
# PostgreSQL (프로덕션) / SQLite (개발) 지원
# ============================================

import os
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

# ============================================
# 데이터베이스 설정 (PostgreSQL / SQLite)
# ============================================

DATABASE_URL = os.environ.get("DATABASE_URL")
IS_POSTGRES = DATABASE_URL is not None

if IS_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    print(f"🐘 PostgreSQL 모드 활성화")
else:
    import sqlite3
    _default_db = Path(__file__).parent / "kampai.db"
    DB_PATH = Path(os.environ.get("DB_PATH", str(_default_db)))
    print(f"📁 SQLite 모드: {DB_PATH}")


def get_db_connection():
    """데이터베이스 연결 반환"""
    if IS_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn


def get_placeholder():
    """DB별 플레이스홀더 반환 (PostgreSQL: %s, SQLite: ?)"""
    return "%s" if IS_POSTGRES else "?"


# JWT 설정
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
    conn = get_db_connection()
    c = conn.cursor()
    
    if IS_POSTGRES:
        # PostgreSQL 테이블 생성
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT,
                plan TEXT DEFAULT 'free',
                plan_expires TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                plan TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                payment_key TEXT,
                order_id TEXT
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS usage (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                date DATE DEFAULT CURRENT_DATE,
                generation_count INTEGER DEFAULT 0,
                UNIQUE(user_id, date)
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS generations (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                prompt TEXT,
                style TEXT,
                image_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                order_id TEXT UNIQUE NOT NULL,
                payment_key TEXT,
                amount INTEGER NOT NULL,
                plan TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMP
            )
        ''')
    else:
        # SQLite 테이블 생성
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT,
                plan TEXT DEFAULT 'free',
                plan_expires TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
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
    salt = "kampai_salt_2025"
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
        conn = get_db_connection()
        c = conn.cursor()
        ph = get_placeholder()
        c.execute(f"SELECT id, email, plan, is_active FROM users WHERE id = {ph}", (payload['user_id'],))
        user = c.fetchone()
        conn.close()
        
        if not user:
            return jsonify({"success": False, "error": "사용자를 찾을 수 없습니다"}), 401
        
        # Row 객체에서 값 추출
        if IS_POSTGRES:
            user_id, email, plan, is_active = user
        else:
            user_id, email, plan, is_active = user['id'], user['email'], user['plan'], user['is_active']
        
        if not is_active:
            return jsonify({"success": False, "error": "비활성화된 계정입니다"}), 401
        
        request.user = {
            "id": user_id,
            "email": email,
            "plan": plan
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
                conn = get_db_connection()
                c = conn.cursor()
                ph = get_placeholder()
                c.execute(f"SELECT id, email, plan FROM users WHERE id = {ph}", (payload['user_id'],))
                user = c.fetchone()
                conn.close()
                
                if user:
                    if IS_POSTGRES:
                        request.user = {
                            "id": user[0],
                            "email": user[1],
                            "plan": user[2]
                        }
                    else:
                        request.user = {
                            "id": user['id'],
                            "email": user['email'],
                            "plan": user['plan']
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
    
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    # 이메일 중복 확인
    c.execute(f"SELECT id FROM users WHERE email = {ph}", (email,))
    if c.fetchone():
        conn.close()
        return {"success": False, "error": "이미 가입된 이메일입니다"}
    
    # 사용자 생성
    password_hash = hash_password(password)
    
    if IS_POSTGRES:
        c.execute(
            f"INSERT INTO users (email, password_hash, name, plan) VALUES ({ph}, {ph}, {ph}, 'free') RETURNING id",
            (email, password_hash, name)
        )
        user_id = c.fetchone()[0]
        
        # 오늘 사용량 초기화
        c.execute(f'''
            INSERT INTO usage (user_id, date, generation_count) 
            VALUES ({ph}, CURRENT_DATE, 0)
            ON CONFLICT (user_id, date) DO NOTHING
        ''', (user_id,))
    else:
        c.execute(
            f"INSERT INTO users (email, password_hash, name, plan) VALUES ({ph}, {ph}, {ph}, 'free')",
            (email, password_hash, name)
        )
        user_id = c.lastrowid
        
        # 오늘 사용량 초기화
        c.execute(
            f"INSERT OR IGNORE INTO usage (user_id, date, generation_count) VALUES ({ph}, DATE('now'), 0)",
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
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    c.execute(f"SELECT id, email, password_hash, name, plan, is_active FROM users WHERE email = {ph}", (email,))
    user = c.fetchone()
    
    if not user:
        conn.close()
        return {"success": False, "error": "이메일 또는 비밀번호가 올바르지 않습니다"}
    
    # Row에서 값 추출
    if IS_POSTGRES:
        user_id, user_email, password_hash, name, plan, is_active = user
    else:
        user_id = user['id']
        user_email = user['email']
        password_hash = user['password_hash']
        name = user['name']
        plan = user['plan']
        is_active = user['is_active']
    
    if not is_active:
        conn.close()
        return {"success": False, "error": "비활성화된 계정입니다"}
    
    if not verify_password(password, password_hash):
        conn.close()
        return {"success": False, "error": "이메일 또는 비밀번호가 올바르지 않습니다"}
    
    # 마지막 로그인 업데이트
    c.execute(f"UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = {ph}", (user_id,))
    conn.commit()
    conn.close()
    
    # 토큰 발급
    token = create_token(user_id, user_email)
    
    return {
        "success": True,
        "message": "로그인 성공",
        "user": {
            "id": user_id,
            "email": user_email,
            "name": name,
            "plan": plan
        },
        "token": token
    }


# ============================================
# 사용량 관리
# ============================================

def get_user_usage(user_id: int) -> dict:
    """사용자 사용량 조회"""
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    # 사용자 플랜 조회
    c.execute(f"SELECT plan FROM users WHERE id = {ph}", (user_id,))
    result = c.fetchone()
    if not result:
        conn.close()
        return None
    
    plan = result[0] if IS_POSTGRES else result['plan']
    plan_info = PLANS.get(plan, PLANS['free'])
    
    # 오늘 사용량 조회
    if IS_POSTGRES:
        c.execute(
            f"SELECT generation_count FROM usage WHERE user_id = {ph} AND date = CURRENT_DATE",
            (user_id,)
        )
    else:
        c.execute(
            f"SELECT generation_count FROM usage WHERE user_id = {ph} AND date = DATE('now')",
            (user_id,)
        )
    result = c.fetchone()
    today_count = (result[0] if IS_POSTGRES else result['generation_count']) if result else 0
    
    # 총 생성 수 조회
    c.execute(f"SELECT COUNT(*) FROM generations WHERE user_id = {ph}", (user_id,))
    count_result = c.fetchone()
    total_count = count_result[0] if count_result else 0
    
    conn.close()
    
    daily_limit = plan_info['daily_limit']
    remaining = daily_limit - today_count if daily_limit > 0 else -1
    
    return {
        "plan": plan,
        "plan_info": plan_info,
        "today": today_count,
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
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    if IS_POSTGRES:
        # PostgreSQL: UPSERT
        c.execute(f'''
            INSERT INTO usage (user_id, date, generation_count) 
            VALUES ({ph}, CURRENT_DATE, 1)
            ON CONFLICT (user_id, date) 
            DO UPDATE SET generation_count = usage.generation_count + 1
        ''', (user_id,))
    else:
        # SQLite: UPSERT
        c.execute(f'''
            INSERT INTO usage (user_id, date, generation_count) 
            VALUES ({ph}, DATE('now'), 1)
            ON CONFLICT(user_id, date) 
            DO UPDATE SET generation_count = generation_count + 1
        ''', (user_id,))
    
    # 생성 기록 저장
    if prompt or action:
        c.execute(
            f"INSERT INTO generations (user_id, prompt, style, image_path) VALUES ({ph}, {ph}, {ph}, {ph})",
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
    
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    # 사용자 플랜 업데이트
    c.execute(f"UPDATE users SET plan = {ph} WHERE id = {ph}", (plan, user_id))
    
    # 구독 기록 추가
    expires_at = datetime.now() + timedelta(days=30)
    c.execute(f'''
        INSERT INTO subscriptions (user_id, plan, status, expires_at, payment_key, order_id)
        VALUES ({ph}, {ph}, 'active', {ph}, {ph}, {ph})
    ''', (user_id, plan, expires_at, payment_key, order_id))
    
    conn.commit()
    conn.close()
    
    return {"success": True, "message": f"{PLANS[plan]['name']} 플랜으로 업그레이드되었습니다"}


def get_subscription_status(user_id: int) -> dict:
    """구독 상태 조회"""
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    c.execute(f'''
        SELECT plan, status, started_at, expires_at 
        FROM subscriptions 
        WHERE user_id = {ph} AND status = 'active'
        ORDER BY started_at DESC LIMIT 1
    ''', (user_id,))
    
    sub = c.fetchone()
    conn.close()
    
    if not sub:
        return {"active": False, "plan": "free"}
    
    # Row에서 값 추출
    if IS_POSTGRES:
        plan, status, started_at, expires_at = sub
    else:
        plan = sub['plan']
        status = sub['status']
        started_at = sub['started_at']
        expires_at = sub['expires_at']
    
    # 만료 확인
    is_expired = False
    if expires_at:
        if isinstance(expires_at, str):
            expires_at_dt = datetime.fromisoformat(expires_at)
        else:
            expires_at_dt = expires_at
        is_expired = datetime.now() > expires_at_dt
    
    return {
        "active": not is_expired,
        "plan": plan,
        "status": status,
        "started_at": str(started_at) if started_at else None,
        "expires_at": str(expires_at) if expires_at else None,
        "is_expired": is_expired
    }


def cancel_subscription(user_id: int) -> dict:
    """구독 취소 (Free 플랜으로 다운그레이드)"""
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    try:
        # 현재 플랜 확인
        c.execute(f"SELECT plan FROM users WHERE id = {ph}", (user_id,))
        result = c.fetchone()
        if not result:
            conn.close()
            return {"success": False, "error": "사용자를 찾을 수 없습니다"}
        
        current_plan = result[0] if IS_POSTGRES else result['plan']
        
        if current_plan == 'free':
            conn.close()
            return {"success": False, "error": "이미 무료 플랜입니다"}
        
        # 플랜을 free로 변경
        c.execute(f"UPDATE users SET plan = 'free', plan_expires = NULL WHERE id = {ph}", (user_id,))
        
        # 구독 상태도 비활성화
        c.execute(f"UPDATE subscriptions SET status = 'cancelled' WHERE user_id = {ph} AND status = 'active'", (user_id,))
        
        conn.commit()
        conn.close()
        
        return {"success": True, "message": "구독이 취소되었습니다. 무료 플랜으로 변경되었습니다."}
    except Exception as e:
        conn.close()
        return {"success": False, "error": f"구독 취소 중 오류: {str(e)}"}


# DB_PATH export (server.py에서 사용 - SQLite 모드에서만)
if not IS_POSTGRES:
    DB_PATH = DB_PATH
else:
    DB_PATH = None


# 초기화
init_db()
