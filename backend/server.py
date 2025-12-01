# ============================================
# Kampai 백엔드 서버
# 개발: ComfyUI (로컬) / 프로덕션: Replicate API
# ============================================

import os
from pathlib import Path

# .env 파일 로드 (가장 먼저 실행)
from dotenv import load_dotenv
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import json
import uuid
from datetime import datetime
from pathlib import Path
import threading
import requests

# 환경 설정 (개발/프로덕션)
# KAMPAI_ENV=production 이면 Replicate API 사용
# KAMPAI_ENV=development 또는 미설정이면 ComfyUI 사용
ENVIRONMENT = os.environ.get("KAMPAI_ENV", "development")
IS_PRODUCTION = ENVIRONMENT == "production"

# ComfyUI API 모듈 (개발용)
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from comfyui_api import (
    ComfyUIClient, 
    generate_product_image, 
    generate_thumbnail, 
    generate_banner,
    generate_custom
)

# Replicate API 모듈 (프로덕션용)
from replicate_api import (
    replicate_client,
    generate_with_replicate,
    check_replicate_status,
    MODELS as REPLICATE_MODELS
)

# 인증 & 결제 모듈
from auth import (
    register_user, login_user, token_required, optional_token,
    get_user_usage, check_can_generate, increment_usage,
    get_subscription_status, PLANS, cancel_subscription,
    admin_required, get_admin_stats, get_all_users, admin_update_user,
    get_all_payments, get_generation_logs, create_announcement,
    get_announcements, update_announcement, delete_announcement,
    get_admin_logs_list, set_admin, log_admin_action
)
from payment import (
    create_payment_order, confirm_payment, cancel_payment,
    get_payment_history, handle_webhook, TOSS_CLIENT_KEY
)

# 웹사이트 폴더 경로 (프로덕션: website-prod, 개발: website-dev)
if IS_PRODUCTION:
    WEBSITE_FOLDER = Path(__file__).parent.parent / "website-prod"
else:
    WEBSITE_FOLDER = Path(__file__).parent.parent / "website-dev"

app = Flask(__name__, static_folder=str(WEBSITE_FOLDER), static_url_path='')
CORS(app, origins=["*"])  # 웹사이트에서 API 호출 허용

# 설정 (프로덕션 환경에서는 환경변수 사용)
UPLOAD_FOLDER = Path(os.environ.get("UPLOAD_FOLDER", "D:/AI_Work/uploads"))
OUTPUT_FOLDER = Path(os.environ.get("OUTPUT_FOLDER", "D:/AI_Work/outputs"))
COMFYUI_OUTPUT = Path(os.environ.get("COMFYUI_OUTPUT", "D:/AI_Tools/ComfyUI/output"))
ORDERS_FILE = Path(os.environ.get("ORDERS_FILE", "D:/AI_Work/orders.json"))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

# 주문 데이터 관리
def load_orders():
    if ORDERS_FILE.exists():
        with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_orders(orders):
    with open(ORDERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)

def generate_order_id():
    today = datetime.now().strftime("%Y%m%d")
    orders = load_orders()
    count = len([o for o in orders if o.startswith(f"AS-{today}")]) + 1
    return f"AS-{today}-{count:04d}"


# ============================================
# API 엔드포인트
# ============================================

@app.route('/')
def serve_index():
    """메인 페이지"""
    return send_from_directory(WEBSITE_FOLDER, 'index.html')


@app.route('/<path:filename>')
def serve_static(filename):
    """정적 파일 서빙"""
    return send_from_directory(WEBSITE_FOLDER, filename)


@app.route('/api/health', methods=['GET'])
def health_check():
    """서버 상태 확인"""
    comfy = ComfyUIClient()
    comfy_status = comfy.is_server_running()
    
    # Ollama 상태 확인
    ollama_status = False
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        ollama_status = resp.status_code == 200
    except:
        pass
    
    return jsonify({
        "status": "ok",
        "comfyui": "running" if comfy_status else "stopped",
        "ollama": "running" if ollama_status else "stopped",
        "timestamp": datetime.now().isoformat()
    })


# ============================================
# 한글 → 영어 번역 API (다중 폴백)
# 1순위: MyMemory (1000회/일)
# 2순위: LibreTranslate (무제한)
# 3순위: 사전 기반 (로컬)
# ============================================

def translate_with_mymemory(text):
    """MyMemory API로 번역 (1000회/일 무료)"""
    response = requests.get(
        "https://api.mymemory.translated.net/get",
        params={"q": text, "langpair": "ko|en"},
        timeout=10
    )
    if response.status_code == 200:
        data = response.json()
        if data.get("responseStatus") == 200:
            translated = data["responseData"]["translatedText"]
            # 한도 초과 메시지 체크
            if "MYMEMORY WARNING" in translated.upper() or "LIMIT" in translated.upper():
                raise Exception("MyMemory limit exceeded")
            return translated
    raise Exception("MyMemory failed")


def translate_with_libretranslate(text):
    """LibreTranslate API로 번역 (무제한 무료)"""
    # 공개 LibreTranslate 서버 목록 (하나 실패 시 다음 시도)
    servers = [
        "https://libretranslate.com/translate",
        "https://translate.argosopentech.com/translate",
        "https://translate.terraprint.co/translate"
    ]
    
    for server in servers:
        try:
            response = requests.post(
                server,
                json={
                    "q": text,
                    "source": "ko",
                    "target": "en",
                    "format": "text"
                },
                headers={"Content-Type": "application/json"},
                timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("translatedText", "")
        except:
            continue
    raise Exception("All LibreTranslate servers failed")


@app.route('/api/translate', methods=['POST'])
def translate_prompt():
    """
    한글 프롬프트를 영어로 번역 (다중 폴백 시스템)
    """
    data = request.json
    korean_text = data.get("text", "").strip()
    style = data.get("style", "")
    
    if not korean_text:
        return jsonify({"success": False, "error": "텍스트를 입력해주세요."}), 400
    
    # 스타일 키워드
    style_keywords = {
        "realistic": "photorealistic, ultra realistic, 8k uhd, dslr, professional photography",
        "3d": "3d render, octane render, unreal engine 5, cinema 4d, ray tracing",
        "digitalart": "digital art, digital painting, artstation trending, detailed illustration",
        "concept": "concept art, illustration, matte painting, cinematic, epic composition",
        "cyberpunk": "cyberpunk, neon lights, futuristic city, dark atmosphere, sci-fi",
        "fantasy": "fantasy art, magical, epic, ethereal lighting, mystical atmosphere",
        "anime": "anime style, anime artwork, japanese animation, cel shading, vibrant",
        "oilpaint": "oil painting, classical art, renaissance style, visible brush strokes",
        "minimal": "minimalist, clean design, simple composition, negative space, modern"
    }
    
    style_prefix = style_keywords.get(style.lower(), "") if style else ""
    translated = None
    model_used = None
    
    # 1순위: MyMemory
    try:
        translated = translate_with_mymemory(korean_text)
        model_used = "mymemory"
    except:
        pass
    
    # 2순위: LibreTranslate
    if not translated:
        try:
            translated = translate_with_libretranslate(korean_text)
            model_used = "libretranslate"
        except:
            pass
    
    # 3순위: 개발 환경에서 Ollama
    if not translated and not IS_PRODUCTION:
        try:
            resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
            if resp.status_code == 200:
                response = requests.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={
                        "model": "llama3.1:8b",
                        "prompt": f"Translate to English (short): {korean_text}",
                        "stream": False,
                        "options": {"temperature": 0.7, "num_predict": 100}
                    },
                    timeout=30
                )
                if response.status_code == 200:
                    translated = response.json().get("response", "").strip().strip('"\'')
                    model_used = "ollama"
        except:
            pass
    
    # 번역 실패
    if not translated:
        return jsonify({
            "success": False,
            "error": "번역 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해주세요."
        }), 503
    
    # 불필요한 문자 정리
    translated = translated.strip('"\'')
    
    # 스타일 키워드 추가
    if style_prefix:
        translated = f"{style_prefix}, {translated}, masterpiece, best quality"
    else:
        translated = f"{translated}, high quality, detailed"
    
    return jsonify({
        "success": True,
        "original": korean_text,
        "translated": translated,
        "model": model_used,
        "style_applied": style if style else "none"
    })


@app.route('/api/quote', methods=['POST'])
def request_quote():
    """견적 요청 접수"""
    data = request.json
    
    order_id = generate_order_id()
    
    order = {
        "order_id": order_id,
        "status": "견적요청",
        "created_at": datetime.now().isoformat(),
        "customer": {
            "name": data.get("name"),
            "contact": data.get("contact"),
        },
        "service": data.get("service"),
        "budget": data.get("budget"),
        "description": data.get("description"),
        "images": []
    }
    
    orders = load_orders()
    orders[order_id] = order
    save_orders(orders)
    
    return jsonify({
        "success": True,
        "order_id": order_id,
        "message": "견적 요청이 접수되었습니다. 24시간 내에 연락드리겠습니다."
    })


@app.route('/api/generate/product', methods=['POST'])
def generate_product():
    """제품 이미지 생성 API"""
    data = request.json
    
    # ComfyUI 서버 확인
    comfy = ComfyUIClient()
    if not comfy.is_server_running():
        return jsonify({
            "success": False,
            "error": "이미지 생성 서버가 준비되지 않았습니다."
        }), 503
    
    # 파라미터 추출
    description = data.get("description", "product")
    style = data.get("style", "professional product photography")
    background = data.get("background", "clean white background")
    count = min(data.get("count", 1), 10)  # 최대 10장
    
    # 작업 ID 생성
    job_id = str(uuid.uuid4())[:8]
    output_dir = OUTPUT_FOLDER / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 비동기 생성 시작
    def generate_async():
        results = []
        for i in range(count):
            try:
                output_path = output_dir / f"product_{i+1:02d}.png"
                images = generate_product_image(
                    product_description=description,
                    style=style,
                    background=background,
                    output_path=str(output_path)
                )
                results.extend(images)
            except Exception as e:
                print(f"생성 오류: {e}")
        
        # 결과 저장
        result_file = output_dir / "result.json"
        with open(result_file, 'w') as f:
            json.dump({"images": results, "status": "completed"}, f)
    
    thread = threading.Thread(target=generate_async)
    thread.start()
    
    return jsonify({
        "success": True,
        "job_id": job_id,
        "message": f"{count}장 이미지 생성이 시작되었습니다.",
        "status_url": f"/api/job/{job_id}/status"
    })


@app.route('/api/generate/thumbnail', methods=['POST'])
def generate_thumb():
    """썸네일 생성 API"""
    data = request.json
    
    comfy = ComfyUIClient()
    if not comfy.is_server_running():
        return jsonify({
            "success": False,
            "error": "이미지 생성 서버가 준비되지 않았습니다."
        }), 503
    
    title = data.get("title", "thumbnail")
    theme = data.get("theme", "vibrant and eye-catching")
    
    job_id = str(uuid.uuid4())[:8]
    output_dir = OUTPUT_FOLDER / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_async():
        try:
            output_path = output_dir / "thumbnail.png"
            images = generate_thumbnail(
                title=title,
                theme=theme,
                output_path=str(output_path)
            )
            
            result_file = output_dir / "result.json"
            with open(result_file, 'w') as f:
                json.dump({"images": images, "status": "completed"}, f)
        except Exception as e:
            result_file = output_dir / "result.json"
            with open(result_file, 'w') as f:
                json.dump({"error": str(e), "status": "failed"}, f)
    
    thread = threading.Thread(target=generate_async)
    thread.start()
    
    return jsonify({
        "success": True,
        "job_id": job_id,
        "message": "썸네일 생성이 시작되었습니다.",
        "status_url": f"/api/job/{job_id}/status"
    })


@app.route('/api/job/<job_id>/status', methods=['GET'])
def job_status(job_id):
    """작업 상태 확인"""
    output_dir = OUTPUT_FOLDER / job_id
    result_file = output_dir / "result.json"
    
    if not output_dir.exists():
        return jsonify({"status": "not_found"}), 404
    
    if result_file.exists():
        with open(result_file, 'r') as f:
            result = json.load(f)
        return jsonify(result)
    
    return jsonify({"status": "processing"})


@app.route('/api/job/<job_id>/images/<filename>', methods=['GET'])
def get_image(job_id, filename):
    """생성된 이미지 다운로드"""
    image_path = OUTPUT_FOLDER / job_id / filename
    
    if image_path.exists():
        return send_file(image_path, mimetype='image/png')
    
    return jsonify({"error": "이미지를 찾을 수 없습니다."}), 404


@app.route('/api/orders', methods=['GET'])
def list_orders():
    """주문 목록 조회 (관리자용)"""
    orders = load_orders()
    return jsonify(list(orders.values()))


@app.route('/api/orders/<order_id>', methods=['GET'])
def get_order(order_id):
    """주문 상세 조회"""
    orders = load_orders()
    
    if order_id in orders:
        return jsonify(orders[order_id])
    
    return jsonify({"error": "주문을 찾을 수 없습니다."}), 404


@app.route('/api/orders/<order_id>/status', methods=['PUT'])
def update_order_status(order_id):
    """주문 상태 업데이트 (관리자용)"""
    data = request.json
    orders = load_orders()
    
    if order_id in orders:
        orders[order_id]["status"] = data.get("status")
        orders[order_id]["updated_at"] = datetime.now().isoformat()
        save_orders(orders)
        return jsonify({"success": True})
    
    return jsonify({"error": "주문을 찾을 수 없습니다."}), 404


# ============================================
# 이미지 생성 API
# 개발: ComfyUI (로컬) / 프로덕션: Replicate API
# ============================================

@app.route('/api/generate', methods=['POST'])
@optional_token
def generate_image():
    """
    이미지 생성 API
    - 개발 모드: ComfyUI 사용 (KAMPAI_ENV != production)
    - 프로덕션 모드: Replicate API 사용 (KAMPAI_ENV == production)
    """
    try:
        data = request.json or {}
        
        # 파라미터 추출
        prompt = data.get("prompt", "").strip()
        img_type = data.get("type", "custom")
        width = data.get("width", 1024)
        height = data.get("height", 1024)
        selected_model = data.get("model")  # 사용자가 선택한 모델 (Pro/Business만)
        input_image = data.get("input_image")  # 이미지 편집/레퍼런스용 (base64 또는 URL)
        edit_mode = data.get("edit_mode", False)  # 이미지 편집 모드
        reference_mode = data.get("reference_mode", False)  # 레퍼런스 모드 (옷 참조 등)
        
        if not prompt:
            return jsonify({
                "success": False,
                "error": "프롬프트를 입력해주세요."
            }), 400
        
        # 사용자 플랜 확인 (로그인한 경우)
        user_plan = "free"
        if hasattr(request, 'user') and request.user and isinstance(request.user, dict):
            user_plan = request.user.get('plan', 'free') or 'free'
        
        # Replicate API 토큰이 설정되어 있으면 Replicate 사용 (개발/프로덕션 모두)
        if replicate_client.is_configured():
            return generate_with_replicate_api(prompt, user_plan, width, height, selected_model, input_image, edit_mode, reference_mode)
        
        # Replicate 토큰 없으면 ComfyUI 폴백 (개발 모드)
        else:
            return generate_with_comfyui(prompt, img_type, width, height)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": f"서버 오류: {str(e)}"
        }), 500


def generate_with_comfyui(prompt: str, img_type: str, width: int, height: int):
    """개발용: ComfyUI로 이미지 생성"""
    comfy = ComfyUIClient()
    if not comfy.is_server_running():
        return jsonify({
            "success": False,
            "error": "이미지 생성 서버가 실행 중이 아닙니다. ComfyUI를 먼저 실행해주세요.",
            "mode": "development"
        }), 503
    
    # 타입별 생성
    if img_type == "product":
        images = generate_product_image(
            product_description=prompt,
            width=width,
            height=height
        )
    elif img_type == "thumbnail":
        images = generate_thumbnail(title=prompt)
    elif img_type == "banner":
        images = generate_banner(concept=prompt, size=(width, height))
    else:
        images = generate_custom(prompt=prompt, width=width, height=height)
    
    return jsonify({
        "success": True,
        "images": images,
        "count": len(images),
        "mode": "development",
        "engine": "ComfyUI"
    })


def generate_with_replicate_api(prompt: str, plan: str, width: int, height: int, selected_model: str = None, input_image: str = None, edit_mode: bool = False, reference_mode: bool = False):
    """프로덕션용: Replicate API로 이미지 생성, 편집, 또는 레퍼런스 기반 생성"""
    try:
        from replicate_api import PLAN_AVAILABLE_MODELS
        
        # Replicate API 상태 확인
        status = check_replicate_status()
        if not status.get("available"):
            # 폴백: ComfyUI 시도
            comfy = ComfyUIClient()
            if comfy.is_server_running():
                return generate_with_comfyui(prompt, "custom", width, height)
            
            return jsonify({
                "success": False,
                "error": f"이미지 생성 서비스 이용 불가: {status.get('message')}",
                "mode": "production"
            }), 503
        
        # 플랜에 맞는 모델 선택
        plan_info = PLANS.get(plan, PLANS["free"])
        available_models = PLAN_AVAILABLE_MODELS.get(plan, ["flux-schnell"])
        
        # 사용자가 모델을 선택한 경우 (Pro/Business)
        if selected_model and selected_model in available_models:
            model_key = selected_model
        else:
            model_key = plan_info.get("model", "flux-schnell")
        
        # 이미지 편집/레퍼런스 모드는 FLUX 2 Pro만 지원
        if (edit_mode or reference_mode) and input_image:
            if model_key != "flux-2-pro":
                if "flux-2-pro" in available_models:
                    model_key = "flux-2-pro"
                else:
                    return jsonify({
                        "success": False,
                        "error": "이미지 편집/레퍼런스 기능은 Pro/Business 플랜의 FLUX 2 Pro 모델에서만 사용 가능합니다.",
                        "mode": "production"
                    }), 403
        
        # 해상도 제한 적용
        max_res_str = plan_info.get("resolution", "1024x1024")
        max_res = int(max_res_str.split("x")[0])
        width = min(width, max_res)
        height = min(height, max_res)
        
        # 레퍼런스 모드: 프롬프트에 참조 힌트 추가
        final_prompt = prompt
        if reference_mode and input_image:
            final_prompt = f"{prompt}, using the elements from the reference image"
        
        # Replicate로 생성/편집
        result = replicate_client.generate_image(
            prompt=final_prompt,
            model_key=model_key,
            width=width,
            height=height,
            input_image=input_image if (edit_mode or reference_mode) else None,
            edit_prompt=final_prompt if (edit_mode or reference_mode) else None
        )
        
        if result.get("success"):
            return jsonify({
                "success": True,
                "images": result["images"],
                "count": len(result["images"]),
                "mode": "production",
                "engine": result.get("model", "Replicate"),
                "time_taken": result.get("time_taken"),
                "model": result.get("model_key")
            })
        else:
            return jsonify({
                "success": False,
                "error": result.get("error", "이미지 생성 실패"),
                "mode": "production"
            }), 500
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": f"이미지 생성 중 오류: {str(e)}",
            "mode": "production"
        }), 500


@app.route('/api/tryon', methods=['POST'])
@optional_token
def virtual_tryon():
    """
    Virtual Try-On API
    사람/캐릭터 이미지에 옷 이미지를 입힘 (IDM-VTON 모델)
    
    Request:
        - human_image: 사람/캐릭터 이미지 (base64 data URL)
        - garment_image: 옷 이미지 (base64 data URL)
        - garment_description: 옷 설명 (예: "blue gradient hoodie")
        - category: 옷 카테고리 (upper_body, lower_body, dresses)
    """
    data = request.json
    
    human_image = data.get("human_image")
    garment_image = data.get("garment_image")
    garment_description = data.get("garment_description", "clothing item")
    category = data.get("category", "upper_body")
    
    if not human_image:
        return jsonify({"success": False, "error": "사람/캐릭터 이미지를 업로드해주세요"}), 400
    
    if not garment_image:
        return jsonify({"success": False, "error": "옷 이미지를 업로드해주세요"}), 400
    
    # 플랜 확인 - Pro/Business만 사용 가능
    user_plan = "free"
    if hasattr(request, 'user') and request.user:
        user_plan = request.user.get('plan', 'free')
    if user_plan not in ['pro', 'business']:
        return jsonify({
            "success": False, 
            "error": "AI 피팅 기능은 Pro/Business 플랜에서만 사용 가능합니다. 플랜을 업그레이드해주세요!",
            "upgrade_required": True
        }), 403
    
    # Replicate API 확인
    if not replicate_client.is_configured():
        return jsonify({
            "success": False,
            "error": "이미지 생성 서비스가 설정되지 않았습니다"
        }), 503
    
    try:
        result = replicate_client.virtual_tryon(
            human_image=human_image,
            garment_image=garment_image,
            garment_description=garment_description,
            category=category
        )
        
        if result.get("success"):
            return jsonify({
                "success": True,
                "images": result["images"],
                "model": result.get("model", "IDM-VTON"),
                "time_taken": result.get("time_taken"),
                "cost": result.get("cost")
            })
        else:
            return jsonify({
                "success": False,
                "error": result.get("error", "Virtual Try-On 실패")
            }), 500
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/outfit-character', methods=['POST'])
@optional_token
def outfit_character():
    """
    의상 캐릭터 생성 API
    옷 이미지를 참조하여 그 옷을 입은 캐릭터 생성 (FLUX Kontext Dev)
    
    Request:
        - outfit_image: 옷 이미지 (base64 data URL)
        - prompt: 캐릭터 생성 프롬프트 (예: "anime girl wearing this outfit")
        - aspect_ratio: 출력 비율 (1:1, 16:9, 9:16, 4:3, 3:4)
    """
    data = request.json
    
    outfit_image = data.get("outfit_image")
    prompt = data.get("prompt", "")
    aspect_ratio = data.get("aspect_ratio", "1:1")
    
    if not outfit_image:
        return jsonify({"success": False, "error": "옷 이미지를 업로드해주세요"}), 400
    
    if not prompt:
        return jsonify({"success": False, "error": "프롬프트를 입력해주세요"}), 400
    
    # 플랜 확인 - Pro/Business만 사용 가능
    user_plan = "free"
    if hasattr(request, 'user') and request.user:
        user_plan = request.user.get('plan', 'free')
    if user_plan not in ['pro', 'business']:
        return jsonify({
            "success": False, 
            "error": "의상 캐릭터 생성은 Pro/Business 플랜에서만 사용 가능합니다. 플랜을 업그레이드해주세요!",
            "upgrade_required": True
        }), 403
    
    # Replicate API 확인
    if not replicate_client.is_configured():
        return jsonify({
            "success": False,
            "error": "이미지 생성 서비스가 설정되지 않았습니다"
        }), 503
    
    try:
        result = replicate_client.outfit_character(
            outfit_image=outfit_image,
            prompt=prompt,
            aspect_ratio=aspect_ratio
        )
        
        if result.get("success"):
            return jsonify({
                "success": True,
                "images": result["images"],
                "model": result.get("model", "FLUX Kontext Dev"),
                "time_taken": result.get("time_taken"),
                "cost": result.get("cost")
            })
        else:
            return jsonify({
                "success": False,
                "error": result.get("error", "의상 캐릭터 생성 실패")
            }), 500
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/generate/status', methods=['GET'])
def generate_status():
    """이미지 생성 서비스 상태 확인"""
    result = {
        "environment": ENVIRONMENT,
        "is_production": IS_PRODUCTION
    }
    
    if IS_PRODUCTION:
        replicate_status = check_replicate_status()
        result["replicate"] = replicate_status
        result["available"] = replicate_status.get("available", False)
    else:
        comfy = ComfyUIClient()
        comfy_running = comfy.is_server_running()
        result["comfyui"] = {
            "available": comfy_running,
            "url": "http://localhost:8188"
        }
        result["available"] = comfy_running
    
    return jsonify(result)


@app.route('/api/generate/models', methods=['GET'])
@optional_token
def get_available_models():
    """사용자 플랜에 따른 사용 가능 모델 목록"""
    from replicate_api import MODELS, PLAN_AVAILABLE_MODELS
    
    user_plan = "free"
    if hasattr(request, 'user') and request.user:
        user_plan = request.user.get('plan', 'free')
    
    available_model_keys = PLAN_AVAILABLE_MODELS.get(user_plan, ["flux-schnell"])
    
    models = []
    for key in available_model_keys:
        model_info = MODELS.get(key, {})
        models.append({
            "key": key,
            "name": model_info.get("name", key),
            "cost_per_image": model_info.get("cost_per_image", 0),
            "speed": model_info.get("speed", "N/A"),
            "max_resolution": model_info.get("max_resolution", 1024),
            "features": model_info.get("features", [])
        })
    
    return jsonify({
        "success": True,
        "plan": user_plan,
        "models": models,
        "can_select": len(models) > 1
    })


@app.route('/api/image/<filename>', methods=['GET'])
def serve_image(filename):
    """ComfyUI 출력 이미지 서빙"""
    # ComfyUI 출력 폴더에서 이미지 찾기
    image_path = COMFYUI_OUTPUT / filename
    
    if image_path.exists():
        return send_file(image_path, mimetype='image/png')
    
    # 대안: 전체 출력 폴더 검색
    for f in COMFYUI_OUTPUT.glob(f"**/{filename}"):
        return send_file(f, mimetype='image/png')
    
    return jsonify({"error": "이미지를 찾을 수 없습니다."}), 404


# ============================================
# 인증 API
# ============================================

@app.route('/api/auth/register', methods=['POST'])
def api_register():
    """회원가입"""
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    name = data.get('name', '')
    
    if not email or not password:
        return jsonify({"success": False, "error": "이메일과 비밀번호는 필수입니다"}), 400
    
    result = register_user(email, password, name)
    status_code = 200 if result['success'] else 400
    return jsonify(result), status_code


@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """로그인"""
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    if not email or not password:
        return jsonify({"success": False, "error": "이메일과 비밀번호를 입력하세요"}), 400
    
    result = login_user(email, password)
    status_code = 200 if result['success'] else 401
    return jsonify(result), status_code


@app.route('/api/auth/me', methods=['GET'])
@token_required
def api_me():
    """현재 사용자 정보"""
    user = request.user
    usage = get_user_usage(user['id'])
    subscription = get_subscription_status(user['id'])
    
    return jsonify({
        "success": True,
        "user": user,
        "usage": usage,
        "subscription": subscription,
        "plans": PLANS
    })


@app.route('/api/auth/usage', methods=['GET'])
@token_required
def api_usage():
    """사용량 조회"""
    usage = get_user_usage(request.user['id'])
    return jsonify({"success": True, "usage": usage})


@app.route('/api/subscription', methods=['GET'])
@token_required
def api_subscription():
    """구독 상태 조회 (generate.html에서 사용)"""
    user = request.user
    subscription = get_subscription_status(user['id'])
    usage = get_user_usage(user['id'])
    
    plan = subscription.get('plan', 'free')
    daily_limit = PLANS.get(plan, {}).get('daily_limit', 3)
    used_today = usage.get('today', 0)
    
    # 무제한 플랜이면 remaining_today는 큰 숫자로
    if daily_limit == -1:
        remaining = 99999
    else:
        remaining = max(0, daily_limit - used_today)
    
    return jsonify({
        "success": True,
        "plan": plan,
        "daily_limit": daily_limit,
        "used_today": used_today,
        "remaining_today": remaining,
        "subscription": subscription
    })


@app.route('/api/usage/record', methods=['POST'])
@token_required
def api_record_usage():
    """사용량 기록 (이미지 생성 시 호출)"""
    user_id = request.user['id']
    data = request.json or {}
    action = data.get('action', 'generate')
    
    increment_usage(user_id, action)
    
    # 업데이트된 사용량 반환
    usage = get_user_usage(user_id)
    return jsonify({
        "success": True,
        "usage": usage
    })


# ============================================
# 결제 API
# ============================================

@app.route('/api/payment/plans', methods=['GET'])
def api_plans():
    """플랜 목록"""
    return jsonify({
        "success": True,
        "plans": PLANS,
        "client_key": TOSS_CLIENT_KEY
    })


@app.route('/api/payment/create-order', methods=['POST'])
@token_required
def api_create_order():
    """결제 주문 생성 (프론트엔드용)"""
    data = request.json
    plan = data.get('plan')
    amount = data.get('amount')
    
    if not plan:
        return jsonify({"success": False, "error": "플랜을 선택하세요"}), 400
    
    result = create_payment_order(request.user['id'], plan)
    
    if result['success']:
        # 테스트 모드 여부 추가
        result['testMode'] = True  # 개발 중에는 테스트 모드
        result['clientKey'] = TOSS_CLIENT_KEY
    
    status_code = 200 if result['success'] else 400
    return jsonify(result), status_code


@app.route('/api/payment/create', methods=['POST'])
@token_required
def api_create_payment():
    """결제 주문 생성"""
    data = request.json
    plan = data.get('plan')
    
    if not plan:
        return jsonify({"success": False, "error": "플랜을 선택하세요"}), 400
    
    result = create_payment_order(request.user['id'], plan)
    status_code = 200 if result['success'] else 400
    return jsonify(result), status_code


@app.route('/api/payment/confirm', methods=['POST'])
@token_required
def api_confirm_payment():
    """결제 승인"""
    data = request.json
    payment_key = data.get('paymentKey')
    order_id = data.get('orderId')
    amount = data.get('amount')
    
    if not all([payment_key, order_id, amount]):
        return jsonify({"success": False, "error": "필수 정보가 누락되었습니다"}), 400
    
    result = confirm_payment(payment_key, order_id, amount)
    status_code = 200 if result['success'] else 400
    return jsonify(result), status_code


@app.route('/api/payment/cancel', methods=['POST'])
@token_required
def api_cancel_payment():
    """결제 취소"""
    data = request.json
    payment_key = data.get('paymentKey')
    reason = data.get('reason', '고객 요청')
    
    if not payment_key:
        return jsonify({"success": False, "error": "결제 키가 필요합니다"}), 400
    
    result = cancel_payment(payment_key, reason)
    status_code = 200 if result['success'] else 400
    return jsonify(result), status_code


@app.route('/api/subscription/cancel', methods=['POST'])
@token_required
def api_cancel_subscription():
    """구독 취소 (Free 플랜으로 다운그레이드)"""
    result = cancel_subscription(request.user['id'])
    status_code = 200 if result['success'] else 400
    return jsonify(result), status_code


@app.route('/api/payment/history', methods=['GET'])
@token_required
def api_payment_history():
    """결제 내역"""
    history = get_payment_history(request.user['id'])
    return jsonify({"success": True, "payments": history})


@app.route('/api/payment/webhook', methods=['POST'])
def api_payment_webhook():
    """토스페이먼츠 웹훅"""
    payload = request.json
    result = handle_webhook(payload)
    return jsonify(result)


# ============================================
# 이미지 생성 (인증 연동)
# ============================================

@app.route('/api/generate/check', methods=['GET'])
@token_required
def api_check_generate():
    """생성 가능 여부 확인"""
    result = check_can_generate(request.user['id'])
    return jsonify(result)


# ============================================
# 관리자 API
# ============================================

@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def api_admin_stats():
    """관리자 대시보드 통계"""
    stats = get_admin_stats()
    return jsonify({"success": True, "stats": stats})


@app.route('/api/admin/users', methods=['GET'])
@admin_required
def api_admin_users():
    """사용자 목록 조회"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', None)
    plan_filter = request.args.get('plan', None)
    
    result = get_all_users(page, per_page, search, plan_filter)
    return jsonify({"success": True, **result})


@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@admin_required
def api_admin_update_user(user_id):
    """사용자 정보 수정"""
    updates = request.json
    result = admin_update_user(request.user['id'], user_id, updates)
    status_code = 200 if result['success'] else 400
    return jsonify(result), status_code


@app.route('/api/admin/users/<int:user_id>/plan', methods=['PUT'])
@admin_required
def api_admin_change_plan(user_id):
    """사용자 플랜 변경"""
    data = request.json
    plan = data.get('plan')
    
    if not plan or plan not in PLANS:
        return jsonify({"success": False, "error": "유효하지 않은 플랜입니다"}), 400
    
    result = admin_update_user(request.user['id'], user_id, {"plan": plan})
    return jsonify(result)


@app.route('/api/admin/payments', methods=['GET'])
@admin_required
def api_admin_payments():
    """결제 내역 조회"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status_filter = request.args.get('status', None)
    
    result = get_all_payments(page, per_page, status_filter)
    return jsonify({"success": True, **result})


@app.route('/api/admin/generations', methods=['GET'])
@admin_required
def api_admin_generations():
    """생성 로그 조회"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    user_id = request.args.get('user_id', None, type=int)
    
    result = get_generation_logs(page, per_page, user_id)
    return jsonify({"success": True, **result})


@app.route('/api/admin/announcements', methods=['GET'])
@admin_required
def api_admin_get_announcements():
    """공지사항 목록 (관리자용)"""
    announcements = get_announcements(active_only=False)
    return jsonify({"success": True, "announcements": announcements})


@app.route('/api/admin/announcements', methods=['POST'])
@admin_required
def api_admin_create_announcement():
    """공지사항 생성"""
    data = request.json
    title = data.get('title')
    content = data.get('content')
    type_ = data.get('type', 'info')
    expires_at = data.get('expires_at')
    
    if not title or not content:
        return jsonify({"success": False, "error": "제목과 내용은 필수입니다"}), 400
    
    result = create_announcement(request.user['id'], title, content, type_, expires_at)
    return jsonify(result)


@app.route('/api/admin/announcements/<int:announcement_id>', methods=['PUT'])
@admin_required
def api_admin_update_announcement(announcement_id):
    """공지사항 수정"""
    updates = request.json
    result = update_announcement(request.user['id'], announcement_id, updates)
    return jsonify(result)


@app.route('/api/admin/announcements/<int:announcement_id>', methods=['DELETE'])
@admin_required
def api_admin_delete_announcement(announcement_id):
    """공지사항 삭제"""
    result = delete_announcement(request.user['id'], announcement_id)
    return jsonify(result)


@app.route('/api/admin/logs', methods=['GET'])
@admin_required
def api_admin_logs():
    """관리자 활동 로그 조회"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    result = get_admin_logs_list(page, per_page)
    return jsonify({"success": True, **result})


@app.route('/api/admin/check', methods=['GET'])
@admin_required
def api_admin_check():
    """관리자 권한 확인"""
    return jsonify({
        "success": True,
        "is_admin": True,
        "user": request.user
    })


# 공개 API - 활성 공지사항 조회
@app.route('/api/announcements', methods=['GET'])
def api_public_announcements():
    """활성 공지사항 목록 (사용자용)"""
    announcements = get_announcements(active_only=True)
    return jsonify({"success": True, "announcements": announcements})


# ============================================
# 서버 실행
# ============================================

def select_server_mode():
    """서버 모드 결정 - 환경변수 우선, 없으면 사용자 입력"""
    # 환경변수로 모드가 설정되어 있으면 자동 사용 (Railway, Heroku 등)
    env_mode = os.environ.get("KAMPAI_ENV", "").lower()
    if env_mode == "production":
        return "production"
    elif env_mode == "development":
        return "development"
    
    # 환경변수 없으면 사용자에게 물어봄 (로컬 개발용)
    print("")
    print("서버 모드를 선택하세요:")
    print("  [1] 개발 서버 (Development) - debug=True, 자동 리로드")
    print("  [2] 프로덕션 서버 (Production) - debug=False, 안정적")
    print("")
    
    while True:
        try:
            choice = input("선택 (1 또는 2, 기본값=1): ").strip()
            if choice == "" or choice == "1":
                return "development"
            elif choice == "2":
                return "production"
            else:
                print("  ⚠️ 1 또는 2를 입력하세요")
        except (EOFError, OSError):
            # 입력이 불가능한 환경 (Railway 등)에서는 production으로
            return "production"


if __name__ == '__main__':
    # 포트 설정 (Railway 등 클라우드 환경에서는 PORT 환경변수 사용)
    port = int(os.environ.get("PORT", 5000))
    
    # 환경 확인 - RAILWAY_ENVIRONMENT가 있으면 클라우드 환경
    is_cloud = os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("PORT")
    
    if is_cloud:
        # 클라우드 환경: 바로 시작
        print("🍺 Kampai 서버 시작 (Production)")
        print(f"   Port: {port}")
        print(f"   REPLICATE_API_TOKEN: {'✅ 설정됨' if replicate_client.is_configured() else '❌ 미설정'}")
        print(f"   JWT_SECRET: {'✅ 설정됨' if os.environ.get('JWT_SECRET') else '⚠️ 자동생성'}")
        app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
    else:
        # 로컬 환경: 기존 로직
        print("=" * 50)
        print("🍺 Kampai 백엔드 서버")
        print("=" * 50)
        
        # 서버 모드 선택
        server_mode = select_server_mode()
        is_debug = (server_mode == "development")
        
        print("")
        print(f"🖥️ 서버 모드: {'개발 (Development)' if is_debug else '프로덕션 (Production)'}")
        
        # 이미지 생성 엔진 상태 표시
        print("")
        print("🖼️ 이미지 생성 엔진:")
        if replicate_client.is_configured():
            print("  ✅ Replicate API 활성화 - 실제 AI 모델 사용 중")
        else:
            print("  ⚠️ ComfyUI 폴백 모드 - Replicate 토큰 미설정")
        
        print("")
        print(f"서버 시작: http://localhost:{port}")
        print("=" * 50)
        
        if is_debug:
            app.run(host='0.0.0.0', port=port, debug=True)
        else:
            app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
