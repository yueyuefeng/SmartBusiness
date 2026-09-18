"""在临时数据库上验证真实 Harness 工具到 Python HTTP/领域/持久化全链路。"""
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from smartbusiness.service import BusinessService
from smartbusiness.server import make_server


def main():
    node = shutil.which("node")
    if not node:
        raise SystemExit("请先安装 Node.js 并在插件目录执行 npm ci")
    with tempfile.TemporaryDirectory(prefix="smartbusiness-smoke-") as directory:
        token = secrets.token_urlsafe(32)
        service = BusinessService(Path(directory) / "smoke.sqlite3")
        server = make_server(service, token)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        env = os.environ.copy()
        env.update(SMARTBUSINESS_API_URL=f"http://127.0.0.1:{server.server_address[1]}",
                   SMARTBUSINESS_API_TOKEN=token, SMARTBUSINESS_SMOKE_TEMP="1")
        try:
            result = subprocess.run([node, "scripts/smoke.mjs"], cwd=ROOT / "integrations/deepseek-harness",
                                    env=env, timeout=60, check=False)
            return result.returncode
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    raise SystemExit(main())
