# ============================================
# ComfyUI API 연동 모듈
# AI 이미지 생성 자동화 (SDXL 모델 기반)
# ============================================

import json
import urllib.request
import urllib.parse
import time
import uuid
import os
import random
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
    
    def wait_for_completion(self, prompt_id: str, timeout: int = 300) -> dict:
        """프롬프트 실행 완료 대기"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            history = self.get_history(prompt_id)
            
            if prompt_id in history:
                status = history[prompt_id].get('status', {})
                if status.get('completed', False) or 'outputs' in history[prompt_id]:
                    return history[prompt_id]
                if status.get('status_str') == 'error':
                    raise RuntimeError(f"생성 실패: {status.get('messages', '알 수 없는 오류')}")
            
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
        print(f"🚀 프롬프트 ID: {prompt_id}")
        
        # 완료 대기
        print("⏳ 이미지 생성 중...")
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
                        print(f"✅ 저장 완료: {save_path}")
        
        return output_images


# ============================================
# SDXL 이미지 생성 워크플로우
# ============================================

def create_sdxl_workflow(
    prompt: str,
    negative_prompt: str = "blurry, low quality, distorted, ugly, bad anatomy, deformed, amateur, watermark, signature, text",
    width: int = 1024,
    height: int = 1024,
    steps: int = 35,
    cfg: float = 7.5,
    seed: int = -1,
    sampler: str = "dpmpp_2m_sde",
    scheduler: str = "karras"
) -> dict:
    """
    SDXL 이미지 생성 워크플로우
    
    사용 모델:
    - checkpoints/sd_xl_base_1.0.safetensors
    
    Args:
        prompt: 생성할 이미지 설명
        negative_prompt: 피하고 싶은 요소
        width: 이미지 너비 (권장: 1024)
        height: 이미지 높이 (권장: 1024)
        steps: 생성 스텝 수 (20-30 권장)
        cfg: CFG 스케일 (7.0-8.0 권장)
        seed: 랜덤 시드 (-1이면 자동)
        sampler: 샘플러 종류
        scheduler: 스케줄러 종류
    """
    if seed == -1:
        seed = random.randint(0, 2**32 - 1)
    
    workflow = {
        # 체크포인트 로드 (SDXL Base)
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": "sd_xl_base_1.0.safetensors"
            }
        },
        # 긍정 프롬프트 인코딩
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["4", 1],
                "text": prompt
            }
        },
        # 부정 프롬프트 인코딩
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["4", 1],
                "text": negative_prompt
            }
        },
        # 빈 Latent 이미지
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "batch_size": 1,
                "height": height,
                "width": width
            }
        },
        # KSampler
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": cfg,
                "denoise": 1.0,
                "latent_image": ["5", 0],
                "model": ["4", 0],
                "negative": ["7", 0],
                "positive": ["6", 0],
                "sampler_name": sampler,
                "scheduler": scheduler,
                "seed": seed,
                "steps": steps
            }
        },
        # VAE 디코드
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2]
            }
        },
        # 이미지 저장
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "AIStudio",
                "images": ["8", 0]
            }
        }
    }
    
    return workflow


# ============================================
# FLUX.1 이미지 생성 워크플로우 (최고 품질)
# ============================================

def create_flux_workflow(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    steps: int = 4,
    guidance: float = 3.5,
    seed: int = -1
) -> dict:
    """
    FLUX.1-schnell 이미지 생성 워크플로우
    
    FLUX는 negative prompt가 필요 없고, 적은 스텝으로도 고품질 이미지 생성
    
    사용 모델:
    - unet/flux1-schnell-fp8.safetensors
    - clip/clip_l.safetensors
    - clip/t5xxl_fp8_e4m3fn.safetensors
    - vae/ae.safetensors
    
    Args:
        prompt: 생성할 이미지 설명 (상세할수록 좋음)
        width: 이미지 너비 (권장: 1024)
        height: 이미지 높이 (권장: 1024)
        steps: 생성 스텝 수 (schnell은 4스텝 권장)
        guidance: 가이던스 스케일 (3.5 권장)
        seed: 랜덤 시드 (-1이면 자동)
    """
    if seed == -1:
        seed = random.randint(0, 2**32 - 1)
    
    workflow = {
        # UNET 로더 (FLUX 모델)
        "10": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "flux1-schnell-fp8.safetensors",
                "weight_dtype": "fp8_e4m3fn"
            }
        },
        # 듀얼 CLIP 로더 (CLIP-L + T5-XXL)
        "11": {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": "clip_l.safetensors",
                "clip_name2": "t5xxl_fp8_e4m3fn.safetensors",
                "type": "flux"
            }
        },
        # VAE 로더
        "12": {
            "class_type": "VAELoader",
            "inputs": {
                "vae_name": "ae.safetensors"
            }
        },
        # CLIP 텍스트 인코딩 (FLUX용)
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["11", 0],
                "text": prompt
            }
        },
        # 빈 SD3 Latent 이미지 (FLUX 호환)
        "5": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {
                "batch_size": 1,
                "height": height,
                "width": width
            }
        },
        # FluxGuidance (가이던스 설정)
        "13": {
            "class_type": "FluxGuidance",
            "inputs": {
                "conditioning": ["6", 0],
                "guidance": guidance
            }
        },
        # KSampler
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": 1.0,
                "denoise": 1.0,
                "latent_image": ["5", 0],
                "model": ["10", 0],
                "negative": ["6", 0],
                "positive": ["13", 0],
                "sampler_name": "euler",
                "scheduler": "simple",
                "seed": seed,
                "steps": steps
            }
        },
        # VAE 디코드
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["3", 0],
                "vae": ["12", 0]
            }
        },
        # 이미지 저장
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "FLUX",
                "images": ["8", 0]
            }
        }
    }
    
    return workflow


# 현재 사용할 모델 설정 (FLUX가 있으면 FLUX 사용, 없으면 SDXL)
USE_FLUX = True  # True: FLUX 사용, False: SDXL 사용


def get_available_model():
    """사용 가능한 모델 확인"""
    flux_model = Path("D:/AI_Tools/ComfyUI/models/unet/flux1-schnell-fp8.safetensors")
    flux_clip = Path("D:/AI_Tools/ComfyUI/models/clip/t5xxl_fp8_e4m3fn.safetensors")
    
    if flux_model.exists() and flux_clip.exists():
        return "flux"
    return "sdxl"


# ============================================
# 사업용 간편 함수
# ============================================

def generate_product_image(
    product_description: str,
    style: str = "professional product photography",
    background: str = "clean white background",
    output_path: str = None,
    width: int = 1024,
    height: int = 1024
) -> list:
    """
    제품 이미지 생성 (FLUX 또는 SDXL 자동 선택)
    """
    model = get_available_model()
    client = ComfyUIClient()
    
    if model == "flux":
        # FLUX용 프롬프트 (자연어 스타일, 더 상세하게)
        prompt = f"A professional commercial photograph of {product_description}. {style}, {background}. Shot with a high-end DSLR camera, perfect studio lighting, soft shadows, extremely sharp focus, 8K resolution, photorealistic, product photography for advertising campaign"
        
        workflow = create_flux_workflow(
            prompt=prompt,
            width=width,
            height=height,
            steps=4,
            guidance=3.5
        )
    else:
        # SDXL용 프롬프트
        prompt = f"masterpiece, best quality, {product_description}, {style}, {background}, extremely detailed, photorealistic, 8k uhd, high resolution, commercial photography, professional studio lighting, sharp focus, ray tracing, global illumination, perfect shadows, award winning photography"
        negative = "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry, amateur, poorly lit, overexposed, underexposed, distorted, deformed, ugly, duplicate, morbid, mutilated, disfigured"
        
        workflow = create_sdxl_workflow(
            prompt=prompt,
            negative_prompt=negative,
            width=width,
            height=height,
            steps=40,
            cfg=7.0
        )
    
    return client.generate_image(workflow, output_path)


def generate_thumbnail(
    title: str,
    theme: str = "vibrant and eye-catching",
    output_path: str = None
) -> list:
    """
    유튜브 썸네일용 이미지 생성 (FLUX 또는 SDXL 자동 선택)
    """
    model = get_available_model()
    client = ComfyUIClient()
    
    if model == "flux":
        prompt = f"A stunning YouTube thumbnail image about {title}. {theme} style, bold vivid colors, dramatic cinematic lighting, high contrast, eye-catching composition, professional digital art, vibrant, trending on artstation, 8K resolution, volumetric lighting, depth of field, visually striking"
        
        workflow = create_flux_workflow(
            prompt=prompt,
            width=1280,
            height=720,
            steps=4,
            guidance=3.5
        )
    else:
        prompt = f"masterpiece, best quality, {title}, {theme}, youtube thumbnail style, bold vivid colors, dramatic cinematic lighting, high contrast, ultra detailed, eye-catching composition, professional digital art, trending on artstation, 8k resolution, volumetric lighting, depth of field"
        negative = "lowres, blurry, boring, dull colors, low contrast, text, watermark, signature, worst quality, low quality, normal quality, jpeg artifacts, amateur, poorly composed, flat lighting"
        
        workflow = create_sdxl_workflow(
            prompt=prompt,
            negative_prompt=negative,
            width=1280,
            height=720,
            steps=35,
            cfg=7.5
        )
    
    return client.generate_image(workflow, output_path)


def generate_banner(
    concept: str,
    size: tuple = (1536, 512),
    output_path: str = None
) -> list:
    """
    웹 배너 이미지 생성 (FLUX 또는 SDXL 자동 선택)
    """
    model = get_available_model()
    client = ComfyUIClient()
    
    if model == "flux":
        prompt = f"A professional web banner design for {concept}. Modern minimalist style, clean layout, professional, sleek design, high quality, elegant, suitable for website header, 8K resolution"
        
        workflow = create_flux_workflow(
            prompt=prompt,
            width=size[0],
            height=size[1],
            steps=4,
            guidance=3.5
        )
    else:
        prompt = f"{concept}, web banner design, modern, clean, professional, minimalist, high quality, sleek"
        negative = "cluttered, busy, low quality, pixelated, text, watermark"
        
        workflow = create_sdxl_workflow(
            prompt=prompt,
            negative_prompt=negative,
            width=size[0],
            height=size[1],
            steps=25,
            cfg=7.5
        )
    
    return client.generate_image(workflow, output_path)


def generate_custom(
    prompt: str,
    negative_prompt: str = "lowres, bad anatomy, bad hands, text, error, missing fingers, cropped, worst quality, low quality, jpeg artifacts, signature, watermark, blurry, deformed, ugly",
    width: int = 1024,
    height: int = 1024,
    steps: int = 35,
    cfg: float = 7.0,
    output_path: str = None
) -> list:
    """
    커스텀 프롬프트로 이미지 생성 (FLUX 또는 SDXL 자동 선택)
    """
    model = get_available_model()
    client = ComfyUIClient()
    
    if model == "flux":
        # FLUX용: 자연어 스타일로 프롬프트 강화
        enhanced_prompt = f"{prompt}. Highly detailed, professional quality, 8K resolution, sharp focus, beautiful composition"
        
        workflow = create_flux_workflow(
            prompt=enhanced_prompt,
            width=width,
            height=height,
            steps=4,
            guidance=3.5
        )
    else:
        # SDXL용: 품질 태그 추가
        enhanced_prompt = f"masterpiece, best quality, highly detailed, {prompt}, 8k uhd, sharp focus, professional"
        enhanced_negative = f"{negative_prompt}, amateur, poorly drawn, bad proportions"
        
        workflow = create_sdxl_workflow(
            prompt=enhanced_prompt,
            negative_prompt=enhanced_negative,
            width=width,
            height=height,
            steps=steps,
            cfg=cfg
        )
    
    return client.generate_image(workflow, output_path)
    
    client = ComfyUIClient()
    return client.generate_image(workflow, output_path)


def batch_generate(
    prompts: list,
    output_dir: str = None,
    width: int = 1024,
    height: int = 1024
) -> list:
    """
    여러 이미지 일괄 생성
    
    Args:
        prompts: 프롬프트 리스트
        output_dir: 출력 디렉토리
        width: 이미지 너비
        height: 이미지 높이
    
    Returns:
        생성된 이미지 경로 리스트
    """
    client = ComfyUIClient()
    all_images = []
    
    for i, prompt in enumerate(prompts):
        print(f"\n📷 이미지 {i+1}/{len(prompts)} 생성 중...")
        
        if output_dir:
            output_path = os.path.join(output_dir, f"image_{i+1:03d}.png")
        else:
            output_path = None
        
        workflow = create_sdxl_workflow(
            prompt=prompt,
            width=width,
            height=height,
            steps=25
        )
        
        images = client.generate_image(workflow, output_path)
        all_images.extend(images)
    
    return all_images


# ============================================
# 사용 예시
# ============================================

if __name__ == "__main__":
    # ComfyUI 클라이언트 생성
    client = ComfyUIClient()
    
    # 서버 상태 확인
    if not client.is_server_running():
        print("❌ ComfyUI 서버가 실행 중이 아닙니다!")
        print("   D:\\AI_Tools\\ComfyUI 폴더에서 run_nvidia_gpu.bat 을 실행해주세요.")
        exit(1)
    
    print("✅ ComfyUI 서버 연결됨")
    
    # 예시: 제품 이미지 생성
    print("\n📦 제품 이미지 생성 테스트...")
    try:
        images = generate_product_image(
            product_description="luxury perfume bottle with elegant gold accents and glass design",
            style="studio product photography, soft lighting, reflections",
            background="gradient gray background"
        )
        print(f"✅ 생성된 이미지: {images}")
    except Exception as e:
        print(f"❌ 오류: {e}")
        import traceback
        traceback.print_exc()
