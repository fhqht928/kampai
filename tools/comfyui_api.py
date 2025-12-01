# ============================================
# ComfyUI API 연동 모듈
# AI 이미지 생성 자동화
# ============================================

import json
import urllib.request
import urllib.parse
import time
import uuid
import os
from pathlib import Path

# ComfyUI 서버 설정
COMFYUI_URL = "http://127.0.0.1:8188"
OUTPUT_DIR = Path("D:/AI_Tools/ComfyUI/output")


class ComfyUIClient:
    """ComfyUI API 클라이언트"""
    
    def __init__(self, server_url: str = COMFYUI_URL):
        self.server_url = server_url
        self.client_id = str(uuid.uuid4())
    
    def is_server_running(self) -> bool:
        """서버 실행 여부 확인"""
        try:
            urllib.request.urlopen(f"{self.server_url}/system_stats", timeout=5)
            return True
        except:
            return False
    
    def queue_prompt(self, prompt: dict) -> dict:
        """프롬프트를 큐에 추가"""
        data = json.dumps({"prompt": prompt, "client_id": self.client_id}).encode('utf-8')
        req = urllib.request.Request(f"{self.server_url}/prompt", data=data)
        req.add_header('Content-Type', 'application/json')
        
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())
    
    def get_history(self, prompt_id: str) -> dict:
        """프롬프트 실행 결과 조회"""
        with urllib.request.urlopen(f"{self.server_url}/history/{prompt_id}") as response:
            return json.loads(response.read())
    
    def get_image(self, filename: str, subfolder: str = "", folder_type: str = "output") -> bytes:
        """생성된 이미지 다운로드"""
        params = urllib.parse.urlencode({
            "filename": filename,
            "subfolder": subfolder,
            "type": folder_type
        })
        with urllib.request.urlopen(f"{self.server_url}/view?{params}") as response:
            return response.read()
    
    def upload_image(self, image_path: str, subfolder: str = "") -> dict:
        """이미지 업로드"""
        import mimetypes
        
        filename = os.path.basename(image_path)
        content_type = mimetypes.guess_type(image_path)[0] or 'image/png'
        
        with open(image_path, 'rb') as f:
            image_data = f.read()
        
        boundary = uuid.uuid4().hex
        body = (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
            f'Content-Type: {content_type}\r\n\r\n'
        ).encode('utf-8') + image_data + f'\r\n--{boundary}--\r\n'.encode('utf-8')
        
        req = urllib.request.Request(
            f"{self.server_url}/upload/image",
            data=body,
            headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
        )
        
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())
    
    def wait_for_completion(self, prompt_id: str, timeout: int = 300) -> dict:
        """프롬프트 실행 완료 대기"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            history = self.get_history(prompt_id)
            
            if prompt_id in history:
                return history[prompt_id]
            
            time.sleep(1)
        
        raise TimeoutError(f"프롬프트 실행 시간 초과: {timeout}초")
    
    def generate_image(self, workflow: dict, output_path: str = None) -> list:
        """
        이미지 생성 및 저장
        
        Args:
            workflow: ComfyUI 워크플로우 (API 형식)
            output_path: 저장 경로 (None이면 자동 생성)
        
        Returns:
            생성된 이미지 파일 경로 리스트
        """
        # 프롬프트 큐에 추가
        result = self.queue_prompt(workflow)
        prompt_id = result['prompt_id']
        print(f"프롬프트 ID: {prompt_id}")
        
        # 완료 대기
        print("이미지 생성 중...")
        history = self.wait_for_completion(prompt_id)
        
        # 결과 이미지 수집
        output_images = []
        
        if 'outputs' in history:
            for node_id, node_output in history['outputs'].items():
                if 'images' in node_output:
                    for image_info in node_output['images']:
                        filename = image_info['filename']
                        subfolder = image_info.get('subfolder', '')
                        
                        # 이미지 다운로드
                        image_data = self.get_image(filename, subfolder)
                        
                        # 저장 경로 설정
                        if output_path:
                            save_path = Path(output_path)
                            save_path.parent.mkdir(parents=True, exist_ok=True)
                        else:
                            save_path = OUTPUT_DIR / filename
                        
                        # 이미지 저장
                        with open(save_path, 'wb') as f:
                            f.write(image_data)
                        
                        output_images.append(str(save_path))
                        print(f"저장 완료: {save_path}")
        
        return output_images


# ============================================
# 사전 정의된 워크플로우 템플릿
# ============================================

def create_text2img_workflow(
    prompt: str,
    negative_prompt: str = "",
    width: int = 1024,
    height: int = 1024,
    steps: int = 20,
    cfg: float = 7.0,
    seed: int = -1,
    model: str = "z_image_turbo_bf16.safetensors"
) -> dict:
    """
    텍스트 → 이미지 워크플로우 생성
    
    Hunyuan/SDXL 등 다양한 모델에 맞게 수정 필요
    """
    if seed == -1:
        import random
        seed = random.randint(0, 2**32 - 1)
    
    # 기본 SDXL 워크플로우 (모델에 따라 수정 필요)
    workflow = {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": cfg,
                "denoise": 1,
                "latent_image": ["5", 0],
                "model": ["4", 0],
                "negative": ["7", 0],
                "positive": ["6", 0],
                "sampler_name": "euler",
                "scheduler": "normal",
                "seed": seed,
                "steps": steps
            }
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": model
            }
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "batch_size": 1,
                "height": height,
                "width": width
            }
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["4", 1],
                "text": prompt
            }
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["4", 1],
                "text": negative_prompt
            }
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2]
            }
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "ComfyUI",
                "images": ["8", 0]
            }
        }
    }
    
    return workflow


# ============================================
# 사업용 간편 함수
# ============================================

def generate_product_image(
    product_description: str,
    style: str = "professional product photography",
    background: str = "clean white background",
    output_path: str = None
) -> list:
    """
    제품 이미지 생성
    
    Args:
        product_description: 제품 설명
        style: 이미지 스타일
        background: 배경 설정
        output_path: 저장 경로
    
    Returns:
        생성된 이미지 경로 리스트
    """
    prompt = f"{product_description}, {style}, {background}, high quality, 4k, detailed"
    negative = "blurry, low quality, distorted, watermark, text"
    
    workflow = create_text2img_workflow(
        prompt=prompt,
        negative_prompt=negative,
        width=1024,
        height=1024,
        steps=20
    )
    
    client = ComfyUIClient()
    return client.generate_image(workflow, output_path)


def generate_thumbnail(
    title: str,
    theme: str = "vibrant and eye-catching",
    output_path: str = None
) -> list:
    """
    유튜브 썸네일용 이미지 생성
    
    Args:
        title: 썸네일 주제/제목
        theme: 테마/분위기
        output_path: 저장 경로
    
    Returns:
        생성된 이미지 경로 리스트
    """
    prompt = f"{title}, {theme}, youtube thumbnail style, bold colors, dramatic lighting, high contrast"
    negative = "text, watermark, blurry, low quality"
    
    workflow = create_text2img_workflow(
        prompt=prompt,
        negative_prompt=negative,
        width=1280,
        height=720,
        steps=25
    )
    
    client = ComfyUIClient()
    return client.generate_image(workflow, output_path)


def generate_banner(
    concept: str,
    size: tuple = (1920, 600),
    output_path: str = None
) -> list:
    """
    웹 배너 이미지 생성
    
    Args:
        concept: 배너 컨셉
        size: (width, height)
        output_path: 저장 경로
    
    Returns:
        생성된 이미지 경로 리스트
    """
    prompt = f"{concept}, web banner design, modern, clean, professional"
    negative = "cluttered, text, watermark, blurry"
    
    workflow = create_text2img_workflow(
        prompt=prompt,
        negative_prompt=negative,
        width=size[0],
        height=size[1],
        steps=20
    )
    
    client = ComfyUIClient()
    return client.generate_image(workflow, output_path)


# ============================================
# 사용 예시
# ============================================

if __name__ == "__main__":
    # ComfyUI 클라이언트 생성
    client = ComfyUIClient()
    
    # 서버 상태 확인
    if not client.is_server_running():
        print("❌ ComfyUI 서버가 실행 중이 아닙니다!")
        print("   run_comfyui.bat 을 실행해주세요.")
        exit(1)
    
    print("✅ ComfyUI 서버 연결됨")
    
    # 예시 1: 제품 이미지 생성
    print("\n📦 제품 이미지 생성 중...")
    try:
        images = generate_product_image(
            product_description="luxury leather watch with gold accents",
            style="studio product photography",
            background="gradient gray background"
        )
        print(f"생성된 이미지: {images}")
    except Exception as e:
        print(f"오류: {e}")
    
    # 예시 2: 썸네일 생성
    # print("\n🎬 썸네일 생성 중...")
    # images = generate_thumbnail(
    #     title="futuristic tech review background",
    #     theme="neon cyberpunk style"
    # )
    # print(f"생성된 이미지: {images}")
