import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

MODELS_FOLDER = Path(__file__).resolve().parent / "models"
INPUT_SIZE = 224
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
CLIP_MEAN = (0.4815, 0.4578, 0.4082)
CLIP_STD = (0.2686, 0.2613, 0.2758)


@dataclass(frozen=True)
class ModelSpec:
    name: str
    url: str
    filename: str
    threshold: float
    size_text: str
    mean: tuple[float, float, float] = IMAGENET_MEAN
    std: tuple[float, float, float] = IMAGENET_STD


MODELS = {
    "dinov2": ModelSpec(
        "dinov2",
        "https://huggingface.co/onnx-community/dinov2-small/resolve/main/onnx/model.onnx",
        "dinov2-small.onnx",
        0.6,
        "88 MB",
    ),
    "dinov2-base": ModelSpec(
        "dinov2-base",
        "https://huggingface.co/onnx-community/dinov2-base/resolve/main/onnx/model.onnx",
        "dinov2-base.onnx",
        0.6,
        "346 MB",
    ),
    "clip": ModelSpec(
        "clip",
        "https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/onnx/vision_model.onnx",
        "clip-vit-base-patch32.onnx",
        0.75,
        "350 MB",
        CLIP_MEAN,
        CLIP_STD,
    ),
    "mobilenet": ModelSpec(
        "mobilenet",
        "https://github.com/onnx/models/raw/main/validated/vision/classification/mobilenet/model/mobilenetv2-12.onnx",
        "mobilenetv2-12.onnx",
        0.7,
        "14 MB",
    ),
}


def download(spec: ModelSpec) -> Path:
    path = MODELS_FOLDER / spec.filename
    if path.exists():
        return path
    MODELS_FOLDER.mkdir(parents=True, exist_ok=True)
    print(f"Preuzimam AI model {spec.name} ({spec.size_text})...")
    partial = path.with_suffix(".part")
    urllib.request.urlretrieve(spec.url, partial)
    partial.rename(path)
    return path


def square(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    side = max(height, width)
    canvas = np.full((side, side, 3), 127, dtype=np.uint8)
    top, left = (side - height) // 2, (side - width) // 2
    canvas[top:top + height, left:left + width] = image
    return cv2.resize(canvas, (INPUT_SIZE, INPUT_SIZE))


def to_blob(image: np.ndarray, mean: tuple = IMAGENET_MEAN, std: tuple = IMAGENET_STD) -> np.ndarray:
    rgb = cv2.cvtColor(square(image), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    normalized = (rgb - np.array(mean, dtype=np.float32)) / np.array(std, dtype=np.float32)
    return normalized.transpose(2, 0, 1)[np.newaxis].astype(np.float32).copy()


class OnnxRuntimeModel:
    def __init__(self, path: Path) -> None:
        import onnxruntime

        self.session = onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        outputs = [output.name for output in self.session.get_outputs()]
        self.output_name = next((name for name in ("image_embeds", "pooler_output") if name in outputs), outputs[0])

    def run(self, blob: np.ndarray) -> np.ndarray:
        result = self.session.run([self.output_name], {self.input_name: blob})[0]
        return result[0, 0] if result.ndim == 3 else result.reshape(-1)


class OpenCvModel:
    def __init__(self, path: Path) -> None:
        try:
            self.network = cv2.dnn.readNetFromONNX(str(path), engine=cv2.dnn.ENGINE_CLASSIC)
        except (TypeError, AttributeError):
            self.network = cv2.dnn.readNetFromONNX(str(path))
        self.layer = [name for name in self.network.getLayerNames() if "Pool" in name][-1]

    def run(self, blob: np.ndarray) -> np.ndarray:
        self.network.setInput(blob)
        return self.network.forward(self.layer).reshape(-1)


def load_model(spec: ModelSpec):
    path = download(spec)
    if spec.name == "mobilenet":
        return OpenCvModel(path)
    return OnnxRuntimeModel(path)


class Embedder:
    def __init__(self, name: str | None = None) -> None:
        wanted = name or os.environ.get("CAM_MODEL", "dinov2")
        try:
            self.spec = MODELS[wanted]
            self.model = load_model(self.spec)
        except Exception as error:
            if wanted == "mobilenet":
                raise
            print(f"Model {wanted} nije dostupan ({error}), koristim mobilenet.")
            self.spec = MODELS["mobilenet"]
            self.model = load_model(self.spec)

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def threshold(self) -> float:
        return self.spec.threshold

    def embed(self, image: np.ndarray) -> np.ndarray:
        vector = self.model.run(to_blob(image, self.spec.mean, self.spec.std)).astype(np.float32)
        return vector / (np.linalg.norm(vector) + 1e-9)

    def embed_rotations(self, image: np.ndarray) -> list[np.ndarray]:
        rotations = [image, cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE), cv2.rotate(image, cv2.ROTATE_180),
                     cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)]
        return [self.embed(rotation) for rotation in rotations]
