"""从 lyh 仓库获取训练好的模型权重。

为什么从这里拿：lyh（Fitz8863/lyh）是唯一把训练权重提交进仓库的项目，
不需要自己训练。其余两个候选仓库（Tang1705/BJTU-Sophomore-Mini-Semester、
Britney126/fall-detection）的权重都被 .gitignore 排除了。

用法：
    python tools/fetch_model.py --print-url     # 只打印地址，手动下载用
    python tools/fetch_model.py                 # 自动下载到 model/best.pt
    python tools/fetch_model.py --what onnx     # 下载 best.onnx
"""

from __future__ import annotations

import argparse
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(BASE, "model")

REPO_RAW = "https://github.com/Fitz8863/lyh/raw/main"
WEIGHTS_DIR = "convert/yolov8s_humanaction_250/weights"

URLS = {
    "pt": f"{REPO_RAW}/{WEIGHTS_DIR}/best.pt",
    "onnx": f"{REPO_RAW}/{WEIGHTS_DIR}/best.onnx",
}

# 仓库 API 里登记的字节数，用于校验下载完整性
EXPECTED_SIZE = {
    "pt": 22557411,
    "onnx": 44551012,
}

# 类别表来自 rk3588lyh/model/coco_80_labels_list.txt
LABELS = ["falldown", "sitting", "standing", "walking"]


def print_urls() -> None:
    print("从 lyh 仓库取模型权重的地址：\n")
    for kind, url in URLS.items():
        size_mb = EXPECTED_SIZE[kind] / 1024 / 1024
        print(f"  {kind:5s} ({size_mb:5.1f} MB)  {url}")
    print("\n目标位置：")
    print(f"  {os.path.join(MODEL_DIR, 'best.pt')}")
    print("\n浏览器直接打开上面的 pt 地址即可下载（GitHub 会跳转到 raw）。")
    print("放好后运行：python -m fallwatch.cli --help")


def write_labels() -> None:
    os.makedirs(MODEL_DIR, exist_ok=True)
    path = os.path.join(MODEL_DIR, "labels.txt")
    if os.path.exists(path):
        print(f"类别文件已存在，跳过: {path}")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(LABELS) + "\n")
    print(f"已写入类别文件: {path}")


def download(kind: str, force: bool = False) -> int:
    import urllib.request

    os.makedirs(MODEL_DIR, exist_ok=True)
    dest = os.path.join(MODEL_DIR, f"best.{kind}")

    if os.path.exists(dest) and not force:
        size = os.path.getsize(dest)
        expected = EXPECTED_SIZE.get(kind)
        if expected and size == expected:
            print(f"已存在且大小正确，跳过下载: {dest} ({size} 字节)")
            return 0
        print(f"已存在但大小不符（{size} 字节），将重新下载: {dest}")

    url = URLS[kind]
    expected = EXPECTED_SIZE.get(kind)

    print(f"下载 {url}")
    print(f"  -> {dest}")

    try:
        with urllib.request.urlopen(url, timeout=60) as resp, open(dest, "wb") as out:
            total = int(resp.headers.get("Content-Length") or expected or 0)
            done = 0
            chunk = 1024 * 256
            last_pct = -1
            while True:
                data = resp.read(chunk)
                if not data:
                    break
                out.write(data)
                done += len(data)
                if total:
                    pct = int(100 * done / total)
                    if pct != last_pct and pct % 5 == 0:
                        print(f"  {pct:3d}%  ({done / 1024 / 1024:.1f} MB)", flush=True)
                        last_pct = pct
    except Exception as exc:
        print(f"[错误] 下载失败: {type(exc).__name__}: {exc}")
        print("       可以改用浏览器打开上面的地址手动下载。")
        return 1

    size = os.path.getsize(dest)
    print(f"下载完成: {dest} ({size} 字节)")
    if expected and size != expected:
        print(f"[警告] 大小与仓库登记值不一致（期望 {expected}）。文件可能不完整。")
        return 1

    print("校验通过。")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="从 lyh 仓库获取模型权重")
    parser.add_argument("--what", choices=sorted(URLS), default="pt",
                        help="下载哪个权重（默认 pt）")
    parser.add_argument("--print-url", action="store_true", help="只打印地址")
    parser.add_argument("--force", action="store_true", help="已存在也重新下载")
    parser.add_argument("--no-labels", action="store_true", help="不生成 labels.txt")
    args = parser.parse_args(argv)

    if args.print_url:
        print_urls()
        return 0

    if not args.no_labels:
        write_labels()

    return download(args.what, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
