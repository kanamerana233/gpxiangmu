import subprocess
import sys
import time
import threading
import os


def is_cloud_env():
    """判断当前是否在云端环境"""
    # Streamlit Cloud 的典型标志
    if os.getenv("STREAMLIT_SHARING_MODE") is not None:
        return True
    if os.getenv("IS_STREAMLIT_CLOUD") == "1":
        return True
    # 云端通常没有 Windows 路径
    if not os.path.exists("C:\\") and not os.path.exists("/Users/"):
        return True
    return False


def start_cn_rss_server():
    """在后台线程中启动 china-finance-rss 服务。云端环境会自动跳过。"""
    if is_cloud_env():
        print("[CN-RSS] 云端环境，跳过启动本地服务")
        return

    def run():
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")
        if not os.path.exists(script_path):
            print(f"[CN-RSS] 找不到 server.py，跳过。路径：{script_path}")
            return
        try:
            subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print("[CN-RSS] 后台服务已启动")
        except Exception as e:
            print(f"[CN-RSS] 启动失败：{e}")

    time.sleep(2)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()