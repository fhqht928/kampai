# ============================================
# Replicate API 연동 모듈
# 프로덕션용 고성능 이미지 생성
# ============================================

import os
import requests
import time
from typing import Optional, Dict, Any
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

# Replicate API 설정 (.env에서 로드)
REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN", "")

# 모델 정의 (플랜별 차등)
MODELS = {
    # 빠르고 저렴한 모델 (Free/Basic)
    "flux-schnell": {
        "version": "black-forest-labs/flux-schnell",
        "name": "FLUX.1 Schnell",
        "cost_per_image": 0.003,  # $0.003
        "speed": "2-4초",
        "quality": "good",
        "max_resolution": 1024
    },
    # Qwen 이미지 모델 (Pro) - 텍스트 렌더링 특화
    "qwen-image": {
        "version": "qwen/qwen-image",
        "name": "Qwen-Image",
        "cost_per_image": 0.025,  # $0.025
        "speed": "3-5초",
        "quality": "excellent",
        "max_resolution": 1440,
        "features": ["text_rendering", "image_editing", "chinese_support"]
    },
    # 고품질 모델 (대안)
    "flux-1.1-pro": {
        "version": "black-forest-labs/flux-1.1-pro",
        "name": "FLUX 1.1 Pro",
        "cost_per_image": 0.04,  # $0.04
        "speed": "3-5초",
        "quality": "excellent",
        "max_resolution": 1440
    },
    # FLUX 2 Pro (최신 모델)
    "flux-2-pro": {
        "version": "black-forest-labs/flux-2-pro",
        "name": "FLUX 2 Pro",
        "cost_per_image": 0.05,  # $0.05
        "speed": "4-7초",
        "quality": "ultra",
        "max_resolution": 2048,
        "features": ["text_rendering", "image_editing", "reference_images", "json_prompting"]
    },
    # 최고급 모델 (Business)
    "flux-1.1-pro-ultra": {
        "version": "black-forest-labs/flux-1.1-pro-ultra",
        "name": "FLUX 1.1 Pro Ultra",
        "cost_per_image": 0.06,  # $0.06
        "speed": "5-8초",
        "quality": "ultra",
        "max_resolution": 2048
    },
    # Ideogram (텍스트/로고 특화 - 대안)
    "ideogram-v3": {
        "version": "ideogram-ai/ideogram-v3-turbo",
        "name": "Ideogram V3",
        "cost_per_image": 0.03,
        "speed": "7-12초",
        "quality": "excellent",
        "max_resolution": 1024,
        "features": ["text_rendering", "logo", "design"]
    },
    # Virtual Try-On (AI 피팅 전용)
    "idm-vton": {
        "version": "cuuupid/idm-vton",
        "name": "IDM-VTON (AI 피팅)",
        "cost_per_image": 0.034,  # $0.034
        "speed": "15-25초",
        "quality": "excellent",
        "max_resolution": 1024,
        "features": ["virtual_tryon", "clothing_transfer", "fashion"]
    },
    # FLUX Kontext Dev (의상 캐릭터 - 옷 이미지 참조하여 캐릭터 생성)
    "flux-kontext-dev": {
        "version": "black-forest-labs/flux-kontext-dev",
        "name": "FLUX Kontext Dev",
        "cost_per_image": 0.025,  # $0.025
        "speed": "5-10초",
        "quality": "excellent",
        "max_resolution": 1440,
        "features": ["image_reference", "style_transfer", "character_generation", "clothing_reference"]
    }
}

# 플랜별 기본 모델
PLAN_MODELS = {
    "free": "flux-schnell",
    "basic": "flux-schnell",
    "pro": "qwen-image",
    "business": "qwen-image"
}

# 플랜별 선택 가능한 모델
PLAN_AVAILABLE_MODELS = {
    "free": ["flux-schnell"],
    "basic": ["flux-schnell"],
    "pro": ["qwen-image", "flux-2-pro", "flux-1.1-pro-ultra"],      # Pro: 선택 가능
    "business": ["qwen-image", "flux-2-pro", "flux-1.1-pro-ultra"]  # Business: 선택 가능
}


class ReplicateClient:
    """Replicate API 클라이언트"""
    
    def __init__(self, api_token: str = None):
        self.api_token = api_token or REPLICATE_API_TOKEN
        self.base_url = "https://api.replicate.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
    
    def is_configured(self) -> bool:
        """API 토큰이 설정되어 있는지 확인"""
        return bool(self.api_token) and len(self.api_token) > 10
    
    def generate_image(
        self,
        prompt: str,
        model_key: str = "flux-schnell",
        width: int = 1024,
        height: int = 1024,
        num_outputs: int = 1,
        guidance_scale: float = 3.5,
        num_inference_steps: int = None,
        seed: int = None,
        input_image: str = None,  # 이미지 편집용 (base64 또는 URL)
        edit_prompt: str = None   # 편집 지시 (FLUX 2 Pro용)
    ) -> Dict[str, Any]:
        """
        이미지 생성 또는 편집
        
        Args:
            prompt: 이미지 설명 프롬프트
            model_key: 모델 키 (flux-schnell, flux-1.1-pro, etc.)
            width: 이미지 너비
            height: 이미지 높이
            num_outputs: 생성할 이미지 수
            guidance_scale: CFG 스케일
            num_inference_steps: 추론 스텝 수 (None이면 모델 기본값)
            seed: 시드값 (재현성)
            input_image: 편집할 이미지 (base64 data URL 또는 URL)
            edit_prompt: 편집 지시 (예: "배경을 바다로 바꿔줘")
        
        Returns:
            {success, images: [url, ...], model, time_taken, error}
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "Replicate API 토큰이 설정되지 않았습니다. 환경변수 REPLICATE_API_TOKEN을 설정하세요."
            }
        
        model_info = MODELS.get(model_key)
        if not model_info:
            return {"success": False, "error": f"알 수 없는 모델: {model_key}"}
        
        # 해상도 제한
        max_res = model_info["max_resolution"]
        width = min(width, max_res)
        height = min(height, max_res)
        
        # 입력 파라미터 구성 (모델별로 다름)
        input_params = {
            "prompt": prompt,
            "output_format": "png"
        }
        
        # aspect ratio 계산
        aspect_ratio = self._get_aspect_ratio(width, height)
        print(f"[Replicate] width={width}, height={height}, aspect_ratio={aspect_ratio}, model={model_key}")
        
        # Qwen-Image 모델 파라미터
        if "qwen" in model_key:
            input_params["aspect_ratio"] = aspect_ratio
            input_params["image_size"] = "optimize_for_quality"
            input_params["go_fast"] = True
            if guidance_scale:
                input_params["guidance"] = min(guidance_scale, 10)  # max 10
            if seed is not None:
                input_params["seed"] = seed
            if num_inference_steps:
                input_params["num_inference_steps"] = min(num_inference_steps, 50)
        # FLUX 2 Pro 파라미터 (특별 처리 - 이미지 편집/레퍼런스 지원)
        elif model_key == "flux-2-pro":
            input_params["aspect_ratio"] = aspect_ratio
            input_params["output_format"] = "png"
            input_params["safety_tolerance"] = 2  # 0-6, 높을수록 허용적
            if guidance_scale:
                input_params["guidance"] = min(guidance_scale, 10)
            if seed is not None:
                input_params["seed"] = seed
            
            # 레퍼런스 이미지 모드 (옷 사진 참조 등)
            # FLUX 2 Pro는 프롬프트에서 "image 1", "the outfit in image 1" 등으로 참조
            if input_image:
                # base64 데이터 URL이면 그대로, URL이면 그대로
                input_params["image_url"] = input_image
                
                # 편집 모드: 이미지 자체를 수정 (배경 바꾸기 등)
                # 레퍼런스 모드: 이미지 요소를 참조해서 새 이미지 생성
                if edit_prompt:
                    # 프롬프트에 이미지 참조 힌트 추가
                    # "이 옷을 입은 캐릭터" → "a character wearing the outfit from the reference image"
                    input_params["prompt"] = edit_prompt
        # FLUX 1.x 모델 파라미터
        elif "flux" in model_key:
            input_params["num_outputs"] = num_outputs
            input_params["aspect_ratio"] = aspect_ratio
            if guidance_scale:
                input_params["guidance"] = guidance_scale
            if seed is not None:
                input_params["seed"] = seed
        # Ideogram 모델
        elif "ideogram" in model_key:
            input_params["aspect_ratio"] = aspect_ratio
            input_params["style_type"] = "Auto"
            input_params["magic_prompt_option"] = "Auto"
        else:
            # 기타 모델 (SD 등)
            input_params["num_outputs"] = num_outputs
            input_params["width"] = width
            input_params["height"] = height
            if guidance_scale:
                input_params["guidance_scale"] = guidance_scale
            if num_inference_steps:
                input_params["num_inference_steps"] = num_inference_steps
        
        start_time = time.time()
        
        try:
            # Prediction 생성
            response = requests.post(
                f"{self.base_url}/models/{model_info['version']}/predictions",
                headers=self.headers,
                json={"input": input_params}
            )
            
            if response.status_code == 422:
                # 모델이 공식 API 형식이 다를 경우 대체 엔드포인트 시도
                response = requests.post(
                    f"{self.base_url}/predictions",
                    headers=self.headers,
                    json={
                        "version": self._get_model_version(model_key),
                        "input": input_params
                    }
                )
            
            if response.status_code != 201:
                return {
                    "success": False,
                    "error": f"API 오류: {response.status_code} - {response.text}"
                }
            
            prediction = response.json()
            prediction_id = prediction["id"]
            
            # 완료될 때까지 폴링
            result = self._wait_for_completion(prediction_id, timeout=120)
            
            elapsed = time.time() - start_time
            
            if result.get("status") == "succeeded":
                output = result.get("output", [])
                if isinstance(output, str):
                    output = [output]
                
                return {
                    "success": True,
                    "images": output,
                    "model": model_info["name"],
                    "model_key": model_key,
                    "time_taken": round(elapsed, 2),
                    "cost": model_info["cost_per_image"] * len(output)
                }
            else:
                error = result.get("error") or "이미지 생성 실패"
                return {"success": False, "error": error}
        
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"네트워크 오류: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"오류: {str(e)}"}
    
    def _get_model_version(self, model_key: str) -> str:
        """모델 버전 ID 반환 (필요시 하드코딩)"""
        # 실제 버전 ID는 Replicate에서 확인 필요
        versions = {
            "flux-schnell": "5599ed30703defd1d160a25a63321b4dec97101d98b4674bcc56e41f62f35637",
            "flux-1.1-pro": "80a09d66baa990429c004cdd5d1b48767e7a4b5a5e2f31acd50dcc32d2b9e3a5",
        }
        return versions.get(model_key, "")
    
    def _get_aspect_ratio(self, width: int, height: int, model_key: str = "flux-schnell") -> str:
        """
        너비/높이를 aspect ratio 문자열로 변환
        각 모델마다 지원하는 비율이 다름
        
        FLUX Schnell 지원: 1:1, 16:9, 9:16, 21:9, 9:21, 4:3, 3:4, 4:5, 5:4, 3:2, 2:3
        Qwen-Image 지원: 1:1, 16:9, 9:16, 4:3, 3:4, 3:2, 2:3
        """
        ratio = width / height
        
        # 가로 비율 (width > height)
        if ratio > 2.0:
            return "21:9"  # 울트라와이드
        elif ratio > 1.6:
            return "16:9"  # 와이드스크린
        elif ratio > 1.4:
            return "3:2"   # 표준 가로
        elif ratio > 1.2:
            return "4:3"   # 클래식 가로
        elif ratio > 1.1:
            return "5:4"   # 거의 정사각
        # 정사각형
        elif ratio > 0.9:
            return "1:1"
        # 세로 비율 (height > width)
        elif ratio > 0.8:
            return "4:5"   # 거의 정사각
        elif ratio > 0.7:
            return "3:4"   # 클래식 세로
        elif ratio > 0.6:
            return "2:3"   # 표준 세로
        elif ratio > 0.5:
            return "9:16"  # 세로 와이드 (모바일)
        else:
            return "9:21"  # 울트라 세로
    
    def _wait_for_completion(self, prediction_id: str, timeout: int = 120) -> Dict:
        """Prediction 완료까지 대기"""
        start = time.time()
        
        while time.time() - start < timeout:
            response = requests.get(
                f"{self.base_url}/predictions/{prediction_id}",
                headers=self.headers
            )
            
            if response.status_code != 200:
                return {"status": "failed", "error": f"상태 확인 실패: {response.status_code}"}
            
            result = response.json()
            status = result.get("status")
            
            if status in ["succeeded", "failed", "canceled"]:
                return result
            
            # 진행 중이면 대기
            time.sleep(0.5)
        
        return {"status": "failed", "error": "타임아웃"}
    
    def get_model_for_plan(self, plan: str) -> str:
        """플랜에 맞는 모델 반환"""
        return PLAN_MODELS.get(plan, "flux-schnell")
    
    def estimate_cost(self, plan: str, num_images: int = 1) -> float:
        """예상 비용 계산"""
        model_key = self.get_model_for_plan(plan)
        model_info = MODELS.get(model_key, {})
        return model_info.get("cost_per_image", 0) * num_images

    def virtual_tryon(
        self,
        human_image: str,
        garment_image: str,
        garment_description: str = "clothing item",
        category: str = "upper_body",
        steps: int = 30,
        seed: int = None
    ) -> Dict[str, Any]:
        """
        Virtual Try-On: 사람 이미지에 옷 이미지를 입힘
        
        Args:
            human_image: 사람/캐릭터 이미지 (base64 data URL 또는 URL)
            garment_image: 옷 이미지 (base64 data URL 또는 URL)
            garment_description: 옷 설명 (예: "blue hoodie", "cute pink top")
            category: 옷 카테고리 ("upper_body", "lower_body", "dresses")
            steps: 생성 스텝 수 (1-40, 기본 30)
            seed: 랜덤 시드 (재현성)
        
        Returns:
            {"success": True, "images": [...], "model": "IDM-VTON", ...}
        """
        if not self.is_configured():
            return {"success": False, "error": "API 토큰이 설정되지 않았습니다"}
        
        model_info = MODELS["idm-vton"]
        
        # IDM-VTON 최신 버전 ID
        version_id = "0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"
        
        input_params = {
            "human_img": human_image,
            "garm_img": garment_image,
            "garment_des": garment_description,
            "category": category,
            "steps": min(max(steps, 1), 40)
        }
        
        if seed is not None:
            input_params["seed"] = seed
        
        start_time = time.time()
        
        try:
            # IDM-VTON 모델 호출 (버전 ID 사용)
            response = requests.post(
                f"{self.base_url}/predictions",
                headers=self.headers,
                json={
                    "version": version_id,
                    "input": input_params
                }
            )
            
            if response.status_code not in [200, 201]:
                return {"success": False, "error": f"API 오류: {response.status_code} - {response.text}"}
            
            prediction = response.json()
            prediction_id = prediction.get("id")
            
            if not prediction_id:
                return {"success": False, "error": "Prediction ID를 받지 못했습니다"}
            
            # 완료 대기 (Try-On은 오래 걸림)
            result = self._wait_for_completion(prediction_id, timeout=180)
            elapsed = time.time() - start_time
            
            if result.get("status") == "succeeded":
                output = result.get("output")
                
                # 출력이 문자열이면 리스트로 변환
                if isinstance(output, str):
                    output = [output]
                elif output is None:
                    return {"success": False, "error": "출력 이미지가 없습니다"}
                
                return {
                    "success": True,
                    "images": output,
                    "model": model_info["name"],
                    "model_key": "idm-vton",
                    "time_taken": round(elapsed, 2),
                    "cost": model_info["cost_per_image"]
                }
            else:
                error = result.get("error") or "Virtual Try-On 실패"
                return {"success": False, "error": error}
        
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"네트워크 오류: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"오류: {str(e)}"}

    def outfit_character(
        self,
        outfit_image: str,
        prompt: str,
        aspect_ratio: str = "1:1",
        seed: int = None,
        output_format: str = "webp"
    ) -> Dict[str, Any]:
        """
        의상 캐릭터 생성: 옷 이미지를 참조하여 그 옷을 입은 캐릭터 생성
        
        Args:
            outfit_image: 옷 이미지 (base64 data URL 또는 URL)
            prompt: 캐릭터 생성 프롬프트 (예: "anime girl wearing this outfit, full body")
            aspect_ratio: 출력 비율 ("1:1", "16:9", "9:16", "4:3", "3:4")
            seed: 랜덤 시드 (재현성)
            output_format: 출력 포맷 ("webp", "png", "jpg")
        
        Returns:
            {"success": True, "images": [...], "model": "FLUX Kontext Dev", ...}
        """
        if not self.is_configured():
            return {"success": False, "error": "API 토큰이 설정되지 않았습니다"}
        
        model_info = MODELS["flux-kontext-dev"]
        
        # 프롬프트 보강: 옷을 입은 새로운 캐릭터를 생성하도록 지시
        enhanced_prompt = f"Generate a new character wearing the outfit shown in the image. {prompt}. The character should be wearing exactly the same clothes/outfit from the reference image. Full body shot, detailed illustration."
        
        input_params = {
            "prompt": enhanced_prompt,
            "input_image": outfit_image,
            "aspect_ratio": aspect_ratio,
            "output_format": output_format
        }
        
        if seed is not None:
            input_params["seed"] = seed
        
        start_time = time.time()
        
        try:
            # FLUX Kontext Dev 호출
            response = requests.post(
                f"{self.base_url}/models/black-forest-labs/flux-kontext-dev/predictions",
                headers=self.headers,
                json={"input": input_params}
            )
            
            if response.status_code not in [200, 201]:
                return {"success": False, "error": f"API 오류: {response.status_code} - {response.text}"}
            
            prediction = response.json()
            prediction_id = prediction.get("id")
            
            if not prediction_id:
                return {"success": False, "error": "Prediction ID를 받지 못했습니다"}
            
            # 완료 대기
            result = self._wait_for_completion(prediction_id, timeout=120)
            elapsed = time.time() - start_time
            
            if result.get("status") == "succeeded":
                output = result.get("output")
                
                # 출력이 문자열이면 리스트로 변환
                if isinstance(output, str):
                    output = [output]
                elif output is None:
                    return {"success": False, "error": "출력 이미지가 없습니다"}
                
                return {
                    "success": True,
                    "images": output,
                    "model": model_info["name"],
                    "model_key": "flux-kontext-dev",
                    "time_taken": round(elapsed, 2),
                    "cost": model_info["cost_per_image"]
                }
            else:
                error = result.get("error") or "의상 캐릭터 생성 실패"
                return {"success": False, "error": error}
        
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"네트워크 오류: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"오류: {str(e)}"}


# 전역 클라이언트 인스턴스
replicate_client = ReplicateClient()


def generate_with_replicate(
    prompt: str,
    plan: str = "free",
    width: int = 1024,
    height: int = 1024,
    **kwargs
) -> Dict[str, Any]:
    """
    편의 함수: 플랜에 맞는 모델로 이미지 생성
    """
    model_key = replicate_client.get_model_for_plan(plan)
    return replicate_client.generate_image(
        prompt=prompt,
        model_key=model_key,
        width=width,
        height=height,
        **kwargs
    )


def check_replicate_status() -> Dict[str, Any]:
    """Replicate API 상태 확인"""
    if not replicate_client.is_configured():
        return {
            "available": False,
            "reason": "API 토큰 미설정",
            "message": "환경변수 REPLICATE_API_TOKEN을 설정하세요"
        }
    
    # 간단한 API 호출로 확인
    try:
        response = requests.get(
            "https://api.replicate.com/v1/models",
            headers=replicate_client.headers,
            timeout=5
        )
        
        if response.status_code == 200:
            return {
                "available": True,
                "message": "Replicate API 연결됨",
                "models": list(MODELS.keys())
            }
        elif response.status_code == 401:
            return {
                "available": False,
                "reason": "인증 실패",
                "message": "API 토큰이 유효하지 않습니다"
            }
        else:
            return {
                "available": False,
                "reason": f"HTTP {response.status_code}",
                "message": response.text
            }
    except Exception as e:
        return {
            "available": False,
            "reason": "연결 실패",
            "message": str(e)
        }
