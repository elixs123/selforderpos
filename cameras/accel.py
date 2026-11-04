import os
from pathlib import Path

MODELS_FOLDER = Path(__file__).resolve().parent / "models"


def _on(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() not in ("", "off", "0", "ne")


def providers(available: list[str], coreml: bool = False, tensorrt: bool = True) -> list:
    """Gdje se model izvršava, redom: NVIDIA (TensorRT/CUDA), Mac (CoreML), procesor kao rezerva.

    CAM_GPU=0 gasi NVIDIA, CAM_TENSORRT=1 uključuje TensorRT (brži, ali prvo pokretanje traje par minuta),
    CAM_COREML=0 gasi CoreML.
    """
    chosen: list = []
    if _on("CAM_GPU", "1"):
        if tensorrt and _on("CAM_TENSORRT", "0") and "TensorrtExecutionProvider" in available:
            cache = MODELS_FOLDER / "tensorrt"
            cache.mkdir(parents=True, exist_ok=True)
            chosen.append(("TensorrtExecutionProvider", {
                "trt_fp16_enable": True,
                "trt_engine_cache_enable": True,
                "trt_engine_cache_path": str(cache),
            }))
        if "CUDAExecutionProvider" in available:
            chosen.append(("CUDAExecutionProvider", {"device_id": 0}))
    if coreml and _on("CAM_COREML", "1") and "CoreMLExecutionProvider" in available:
        chosen.append(("CoreMLExecutionProvider", {"MLComputeUnits": "ALL"}))
    chosen.append("CPUExecutionProvider")
    return chosen


def create_session(path: Path, label: str, coreml: bool = False, tensorrt: bool = True):
    """ONNX model na najbržem dostupnom uređaju; ako to ne uspije, na procesoru."""
    import onnxruntime

    available = onnxruntime.get_available_providers()
    if "CUDAExecutionProvider" in available and hasattr(onnxruntime, "preload_dlls"):
        try:
            # CUDA/cuDNN iz pip paketa (onnxruntime-gpu[cuda,cudnn]) moraju se učitati prije sesije
            onnxruntime.preload_dlls()
        except Exception as error:
            print(f"{label}: CUDA biblioteke nisu učitane: {error!r}")
    try:
        session = onnxruntime.InferenceSession(str(path), providers=providers(available, coreml, tensorrt))
    except Exception as error:
        print(f"{label}: ubrzanje nije uspjelo ({error!r}), radi na procesoru")
        session = onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    print(f"{label} se izvršava na: {', '.join(session.get_providers())}")
    return session
