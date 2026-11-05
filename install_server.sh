#!/usr/bin/env bash
# Instalacija paketa za server kamera na Linuxu sa NVIDIA grafičkom.
# requirements.txt (i rapidocr-onnxruntime) uvijek povuku obični onnxruntime; on i onnxruntime-gpu dijele
# isti folder, pa se poslije svake instalacije obični mora skloniti i GPU verzija instalirati iznova.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip uninstall -y onnxruntime onnxruntime-gpu
.venv/bin/pip install --force-reinstall "onnxruntime-gpu[cuda,cudnn]"
.venv/bin/python -c "import onnxruntime as o; o.preload_dlls(); p = o.get_available_providers(); print(o.__version__, p); assert 'CUDAExecutionProvider' in p, 'CUDA nije dostupna'"
