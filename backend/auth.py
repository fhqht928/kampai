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
                is_active BOOLEAN DEFAULT TRUE,
                is_admin BOOLEAN DEFAULT FALSE
            )
        ''')
        
        # is_admin 컬럼이 없으면 추가 (기존 DB 마이그레이션)
        try:
            c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE")
        except:
            pass
        
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
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS announcements (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                type TEXT DEFAULT 'info',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                created_by INTEGER REFERENCES users(id)
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS admin_logs (
                id SERIAL PRIMARY KEY,
                admin_id INTEGER NOT NULL REFERENCES users(id),
                action TEXT NOT NULL,
                target_type TEXT,
                target_id INTEGER,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                is_active BOOLEAN DEFAULT 1,
                is_admin BOOLEAN DEFAULT 0
            )
        ''')
        
        # is_admin 컬럼이 없으면 추가 (기존 DB 마이그레이션)
        try:
            c.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0")
        except:
            pass
        
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
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                type TEXT DEFAULT 'info',
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                created_by INTEGER,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_type TEXT,
                target_id INTEGER,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (admin_id) REFERENCES users(id)
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


# ============================================
# 관리자 기능
# ============================================

def admin_required(f):
    """관리자 권한 필수 데코레이터"""
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
        
        # 사용자 정보 조회 (is_admin 포함)
        conn = get_db_connection()
        c = conn.cursor()
        ph = get_placeholder()
        c.execute(f"SELECT id, email, plan, is_active, is_admin FROM users WHERE id = {ph}", (payload['user_id'],))
        user = c.fetchone()
        conn.close()
        
        if not user:
            return jsonify({"success": False, "error": "사용자를 찾을 수 없습니다"}), 401
        
        # Row 객체에서 값 추출
        if IS_POSTGRES:
            user_id, email, plan, is_active, is_admin = user
        else:
            user_id, email, plan, is_active, is_admin = user['id'], user['email'], user['plan'], user['is_active'], user['is_admin']
        
        if not is_active:
            return jsonify({"success": False, "error": "비활성화된 계정입니다"}), 401
        
        if not is_admin:
            return jsonify({"success": False, "error": "관리자 권한이 필요합니다"}), 403
        
        request.user = {
            "id": user_id,
            "email": email,
            "plan": plan,
            "is_admin": True
        }
        
        return f(*args, **kwargs)
    return decorated


def log_admin_action(admin_id: int, action: str, target_type: str = None, target_id: int = None, details: str = None):
    """관리자 활동 로그 기록"""
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    c.execute(f'''
        INSERT INTO admin_logs (admin_id, action, target_type, target_id, details)
        VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
    ''', (admin_id, action, target_type, target_id, details))
    
    conn.commit()
    conn.close()


def get_admin_stats():
    """관리자 대시보드 통계"""
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    stats = {}
    
    # 총 사용자 수
    c.execute("SELECT COUNT(*) FROM users")
    stats['total_users'] = c.fetchone()[0]
    
    # 플랜별 사용자 수
    c.execute("SELECT plan, COUNT(*) FROM users GROUP BY plan")
    stats['users_by_plan'] = dict(c.fetchall())
    
    # 오늘 가입자 수
    if IS_POSTGRES:
        c.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = CURRENT_DATE")
    else:
        c.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = DATE('now')")
    stats['today_signups'] = c.fetchone()[0]
    
    # 이번 달 가입자 수
    if IS_POSTGRES:
        c.execute("SELECT COUNT(*) FROM users WHERE DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CURRENT_DATE)")
    else:
        c.execute("SELECT COUNT(*) FROM users WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')")
    stats['month_signups'] = c.fetchone()[0]
    
    # 오늘 총 생성량
    if IS_POSTGRES:
        c.execute("SELECT COALESCE(SUM(generation_count), 0) FROM usage WHERE date = CURRENT_DATE")
    else:
        c.execute("SELECT COALESCE(SUM(generation_count), 0) FROM usage WHERE date = DATE('now')")
    stats['today_generations'] = c.fetchone()[0]
    
    # 총 생성량
    c.execute("SELECT COALESCE(SUM(generation_count), 0) FROM usage")
    stats['total_generations'] = c.fetchone()[0]
    
    # 이번 달 매출
    if IS_POSTGRES:
        c.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM payments 
            WHERE status = 'approved' 
            AND DATE_TRUNC('month', approved_at) = DATE_TRUNC('month', CURRENT_DATE)
        """)
    else:
        c.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM payments 
            WHERE status = 'approved' 
            AND strftime('%Y-%m', approved_at) = strftime('%Y-%m', 'now')
        """)
    stats['month_revenue'] = c.fetchone()[0]
    
    # 총 매출
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'approved'")
    stats['total_revenue'] = c.fetchone()[0]
    
    # 활성 사용자 수 (최근 7일 로그인)
    if IS_POSTGRES:
        c.execute("SELECT COUNT(*) FROM users WHERE last_login >= CURRENT_DATE - INTERVAL '7 days'")
    else:
        c.execute("SELECT COUNT(*) FROM users WHERE last_login >= DATE('now', '-7 days')")
    stats['active_users_7d'] = c.fetchone()[0]
    
    conn.close()
    return stats


def get_all_users(page: int = 1, per_page: int = 20, search: str = None, plan_filter: str = None):
    """모든 사용자 목록 조회"""
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    offset = (page - 1) * per_page
    
    # 기본 쿼리
    base_query = "FROM users WHERE 1=1"
    params = []
    
    # 검색 조건
    if search:
        base_query += f" AND (email LIKE {ph} OR name LIKE {ph})"
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern])
    
    # 플랜 필터
    if plan_filter:
        base_query += f" AND plan = {ph}"
        params.append(plan_filter)
    
    # 총 개수
    c.execute(f"SELECT COUNT(*) {base_query}", params)
    total = c.fetchone()[0]
    
    # 사용자 목록
    if IS_POSTGRES:
        c.execute(f"""
            SELECT id, email, name, plan, is_active, is_admin, created_at, last_login
            {base_query}
            ORDER BY created_at DESC
            LIMIT {ph} OFFSET {ph}
        """, params + [per_page, offset])
    else:
        c.execute(f"""
            SELECT id, email, name, plan, is_active, is_admin, created_at, last_login
            {base_query}
            ORDER BY created_at DESC
            LIMIT {ph} OFFSET {ph}
        """, params + [per_page, offset])
    
    users = []
    for row in c.fetchall():
        if IS_POSTGRES:
            users.append({
                "id": row[0],
                "email": row[1],
                "name": row[2],
                "plan": row[3],
                "is_active": row[4],
                "is_admin": row[5],
                "created_at": str(row[6]) if row[6] else None,
                "last_login": str(row[7]) if row[7] else None
            })
        else:
            users.append({
                "id": row['id'],
                "email": row['email'],
                "name": row['name'],
                "plan": row['plan'],
                "is_active": bool(row['is_active']),
                "is_admin": bool(row['is_admin']),
                "created_at": row['created_at'],
                "last_login": row['last_login']
            })
    
    conn.close()
    return {
        "users": users,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page
    }


def admin_update_user(admin_id: int, user_id: int, updates: dict) -> dict:
    """관리자가 사용자 정보 업데이트"""
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    # 사용자 존재 확인
    c.execute(f"SELECT id, email FROM users WHERE id = {ph}", (user_id,))
    user = c.fetchone()
    if not user:
        conn.close()
        return {"success": False, "error": "사용자를 찾을 수 없습니다"}
    
    # 업데이트 가능한 필드
    allowed_fields = ['plan', 'is_active', 'is_admin', 'name']
    update_parts = []
    params = []
    
    for field in allowed_fields:
        if field in updates:
            update_parts.append(f"{field} = {ph}")
            params.append(updates[field])
    
    if not update_parts:
        conn.close()
        return {"success": False, "error": "업데이트할 필드가 없습니다"}
    
    params.append(user_id)
    query = f"UPDATE users SET {', '.join(update_parts)} WHERE id = {ph}"
    c.execute(query, params)
    
    conn.commit()
    conn.close()
    
    # 로그 기록
    log_admin_action(admin_id, "update_user", "user", user_id, str(updates))
    
    return {"success": True, "message": "사용자 정보가 업데이트되었습니다"}


def get_all_payments(page: int = 1, per_page: int = 20, status_filter: str = None):
    """모든 결제 내역 조회"""
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    offset = (page - 1) * per_page
    
    base_query = "FROM payments p JOIN users u ON p.user_id = u.id WHERE 1=1"
    params = []
    
    if status_filter:
        base_query += f" AND p.status = {ph}"
        params.append(status_filter)
    
    # 총 개수
    c.execute(f"SELECT COUNT(*) {base_query}", params)
    total = c.fetchone()[0]
    
    # 결제 목록
    if IS_POSTGRES:
        c.execute(f"""
            SELECT p.id, p.order_id, p.payment_key, p.amount, p.plan, p.status, 
                   p.created_at, p.approved_at, u.email, u.name
            {base_query}
            ORDER BY p.created_at DESC
            LIMIT {ph} OFFSET {ph}
        """, params + [per_page, offset])
    else:
        c.execute(f"""
            SELECT p.id, p.order_id, p.payment_key, p.amount, p.plan, p.status, 
                   p.created_at, p.approved_at, u.email, u.name
            {base_query}
            ORDER BY p.created_at DESC
            LIMIT {ph} OFFSET {ph}
        """, params + [per_page, offset])
    
    payments = []
    for row in c.fetchall():
        if IS_POSTGRES:
            payments.append({
                "id": row[0],
                "order_id": row[1],
                "payment_key": row[2],
                "amount": row[3],
                "plan": row[4],
                "status": row[5],
                "created_at": str(row[6]) if row[6] else None,
                "approved_at": str(row[7]) if row[7] else None,
                "user_email": row[8],
                "user_name": row[9]
            })
        else:
            payments.append({
                "id": row['id'],
                "order_id": row['order_id'],
                "payment_key": row['payment_key'],
                "amount": row['amount'],
                "plan": row['plan'],
                "status": row['status'],
                "created_at": row['created_at'],
                "approved_at": row['approved_at'],
                "user_email": row['email'],
                "user_name": row['name']
            })
    
    conn.close()
    return {
        "payments": payments,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page
    }


def get_generation_logs(page: int = 1, per_page: int = 50, user_id: int = None):
    """생성 로그 조회"""
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    offset = (page - 1) * per_page
    
    base_query = "FROM generations g JOIN users u ON g.user_id = u.id WHERE 1=1"
    params = []
    
    if user_id:
        base_query += f" AND g.user_id = {ph}"
        params.append(user_id)
    
    # 총 개수
    c.execute(f"SELECT COUNT(*) {base_query}", params)
    total = c.fetchone()[0]
    
    # 로그 목록
    if IS_POSTGRES:
        c.execute(f"""
            SELECT g.id, g.user_id, g.prompt, g.style, g.created_at, u.email
            {base_query}
            ORDER BY g.created_at DESC
            LIMIT {ph} OFFSET {ph}
        """, params + [per_page, offset])
    else:
        c.execute(f"""
            SELECT g.id, g.user_id, g.prompt, g.style, g.created_at, u.email
            {base_query}
            ORDER BY g.created_at DESC
            LIMIT {ph} OFFSET {ph}
        """, params + [per_page, offset])
    
    logs = []
    for row in c.fetchall():
        if IS_POSTGRES:
            logs.append({
                "id": row[0],
                "user_id": row[1],
                "prompt": row[2],
                "style": row[3],
                "created_at": str(row[4]) if row[4] else None,
                "user_email": row[5]
            })
        else:
            logs.append({
                "id": row['id'],
                "user_id": row['user_id'],
                "prompt": row['prompt'],
                "style": row['style'],
                "created_at": row['created_at'],
                "user_email": row['email']
            })
    
    conn.close()
    return {
        "logs": logs,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page
    }


def create_announcement(admin_id: int, title: str, content: str, type: str = 'info', expires_at: str = None) -> dict:
    """공지사항 생성"""
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    if IS_POSTGRES:
        c.execute(f'''
            INSERT INTO announcements (title, content, type, expires_at, created_by)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
            RETURNING id
        ''', (title, content, type, expires_at, admin_id))
        announcement_id = c.fetchone()[0]
    else:
        c.execute(f'''
            INSERT INTO announcements (title, content, type, expires_at, created_by)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
        ''', (title, content, type, expires_at, admin_id))
        announcement_id = c.lastrowid
    
    conn.commit()
    conn.close()
    
    log_admin_action(admin_id, "create_announcement", "announcement", announcement_id, title)
    
    return {"success": True, "id": announcement_id, "message": "공지사항이 등록되었습니다"}


def get_announcements(active_only: bool = False):
    """공지사항 목록 조회"""
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    query = "SELECT id, title, content, type, is_active, created_at, expires_at FROM announcements"
    
    if active_only:
        if IS_POSTGRES:
            query += " WHERE is_active = TRUE AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)"
        else:
            query += " WHERE is_active = 1 AND (expires_at IS NULL OR expires_at > datetime('now'))"
    
    query += " ORDER BY created_at DESC"
    
    c.execute(query)
    
    announcements = []
    for row in c.fetchall():
        if IS_POSTGRES:
            announcements.append({
                "id": row[0],
                "title": row[1],
                "content": row[2],
                "type": row[3],
                "is_active": row[4],
                "created_at": str(row[5]) if row[5] else None,
                "expires_at": str(row[6]) if row[6] else None
            })
        else:
            announcements.append({
                "id": row['id'],
                "title": row['title'],
                "content": row['content'],
                "type": row['type'],
                "is_active": bool(row['is_active']),
                "created_at": row['created_at'],
                "expires_at": row['expires_at']
            })
    
    conn.close()
    return announcements


def update_announcement(admin_id: int, announcement_id: int, updates: dict) -> dict:
    """공지사항 수정"""
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    allowed_fields = ['title', 'content', 'type', 'is_active', 'expires_at']
    update_parts = []
    params = []
    
    for field in allowed_fields:
        if field in updates:
            update_parts.append(f"{field} = {ph}")
            params.append(updates[field])
    
    if not update_parts:
        conn.close()
        return {"success": False, "error": "업데이트할 필드가 없습니다"}
    
    params.append(announcement_id)
    query = f"UPDATE announcements SET {', '.join(update_parts)} WHERE id = {ph}"
    c.execute(query, params)
    
    conn.commit()
    conn.close()
    
    log_admin_action(admin_id, "update_announcement", "announcement", announcement_id, str(updates))
    
    return {"success": True, "message": "공지사항이 수정되었습니다"}


def delete_announcement(admin_id: int, announcement_id: int) -> dict:
    """공지사항 삭제"""
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    c.execute(f"DELETE FROM announcements WHERE id = {ph}", (announcement_id,))
    
    conn.commit()
    conn.close()
    
    log_admin_action(admin_id, "delete_announcement", "announcement", announcement_id)
    
    return {"success": True, "message": "공지사항이 삭제되었습니다"}


def get_admin_logs_list(page: int = 1, per_page: int = 50):
    """관리자 활동 로그 조회"""
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    offset = (page - 1) * per_page
    
    # 총 개수
    c.execute("SELECT COUNT(*) FROM admin_logs")
    total = c.fetchone()[0]
    
    if IS_POSTGRES:
        c.execute(f"""
            SELECT l.id, l.action, l.target_type, l.target_id, l.details, l.created_at, u.email
            FROM admin_logs l
            JOIN users u ON l.admin_id = u.id
            ORDER BY l.created_at DESC
            LIMIT {ph} OFFSET {ph}
        """, (per_page, offset))
    else:
        c.execute(f"""
            SELECT l.id, l.action, l.target_type, l.target_id, l.details, l.created_at, u.email
            FROM admin_logs l
            JOIN users u ON l.admin_id = u.id
            ORDER BY l.created_at DESC
            LIMIT {ph} OFFSET {ph}
        """, (per_page, offset))
    
    logs = []
    for row in c.fetchall():
        if IS_POSTGRES:
            logs.append({
                "id": row[0],
                "action": row[1],
                "target_type": row[2],
                "target_id": row[3],
                "details": row[4],
                "created_at": str(row[5]) if row[5] else None,
                "admin_email": row[6]
            })
        else:
            logs.append({
                "id": row['id'],
                "action": row['action'],
                "target_type": row['target_type'],
                "target_id": row['target_id'],
                "details": row['details'],
                "created_at": row['created_at'],
                "admin_email": row['email']
            })
    
    conn.close()
    return {
        "logs": logs,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page
    }


def set_admin(email: str, is_admin: bool = True) -> dict:
    """특정 이메일을 관리자로 설정 (CLI용)"""
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    c.execute(f"SELECT id FROM users WHERE email = {ph}", (email,))
    user = c.fetchone()
    
    if not user:
        conn.close()
        return {"success": False, "error": "사용자를 찾을 수 없습니다"}
    
    c.execute(f"UPDATE users SET is_admin = {ph} WHERE email = {ph}", (is_admin, email))
    conn.commit()
    conn.close()
    
    return {"success": True, "message": f"{email}의 관리자 권한이 {'부여' if is_admin else '해제'}되었습니다"}


# DB_PATH export (server.py에서 사용 - SQLite 모드에서만)
if not IS_POSTGRES:
    DB_PATH = DB_PATH
else:
    DB_PATH = None


# 기본 관리자 이메일 (환경변수 또는 하드코딩)
ADMIN_EMAILS = os.environ.get("ADMIN_EMAILS", "kampai9909@gmail.com").split(",")


def ensure_admin_accounts():
    """기본 관리자 계정 설정"""
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    for email in ADMIN_EMAILS:
        email = email.strip()
        if not email:
            continue
        
        # 사용자가 존재하면 관리자로 설정
        c.execute(f"SELECT id FROM users WHERE email = {ph}", (email,))
        user = c.fetchone()
        
        if user:
            c.execute(f"UPDATE users SET is_admin = TRUE WHERE email = {ph}", (email,))
            print(f"👑 관리자 설정: {email}")
    
    conn.commit()
    conn.close()


# 초기화
init_db()
ensure_admin_accounts()
