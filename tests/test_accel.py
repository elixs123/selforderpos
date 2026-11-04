import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

from accel import providers

ALL = ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CoreMLExecutionProvider", "CPUExecutionProvider"]


def names(chosen):
    return [item[0] if isinstance(item, tuple) else item for item in chosen]


def test_nvidia_cuda_first_and_cpu_as_fallback(monkeypatch):
    monkeypatch.delenv("CAM_GPU", raising=False)
    monkeypatch.delenv("CAM_TENSORRT", raising=False)
    assert names(providers(["CUDAExecutionProvider", "CPUExecutionProvider"])) == ["CUDAExecutionProvider", "CPUExecutionProvider"]


def test_tensorrt_only_when_enabled(monkeypatch, tmp_path):
    import accel

    monkeypatch.setattr(accel, "MODELS_FOLDER", tmp_path)
    monkeypatch.delenv("CAM_TENSORRT", raising=False)
    assert "TensorrtExecutionProvider" not in names(providers(ALL))
    monkeypatch.setenv("CAM_TENSORRT", "1")
    assert names(providers(ALL))[:2] == ["TensorrtExecutionProvider", "CUDAExecutionProvider"]
    assert (tmp_path / "tensorrt").is_dir()


def test_gpu_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("CAM_GPU", "0")
    assert names(providers(ALL)) == ["CPUExecutionProvider"]


def test_coreml_only_for_models_that_ask(monkeypatch):
    monkeypatch.delenv("CAM_COREML", raising=False)
    mac = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
    assert names(providers(mac, coreml=True)) == mac
    assert names(providers(mac)) == ["CPUExecutionProvider"]
