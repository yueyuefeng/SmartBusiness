"""python -m smartbusiness serve / harness"""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
from urllib.request import Request, urlopen
from .service import BusinessService
from .server import make_server

ROOT = Path(__file__).resolve().parents[1]
HARNESS_VERSION = "0.1.6-alpha.2"


def load_token(data_dir, create=False):
    path = data_dir / "api-token"
    if not path.exists() and create:
        data_dir.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8") as file:
                file.write(secrets.token_urlsafe(32))
            if os.name != "nt":
                path.chmod(0o600)
        except FileExistsError:
            pass
    token = path.read_text(encoding="utf-8").strip()
    if len(token) < 24:
        raise ValueError("本地 token 文件无效")
    return token


def start_harness(args):
    plugin = ROOT / "integrations" / "deepseek-harness"
    token = load_token(args.data_dir)
    base_url = f"http://127.0.0.1:{args.api_port}"
    with urlopen(Request(base_url + "/api/dashboard", headers={"Authorization": "Bearer " + token}), timeout=5) as response:
        json.load(response)
    if not (plugin / "node_modules").is_dir():
        raise ValueError("请先进入 integrations/deepseek-harness 执行 npm ci，再回到仓库根目录启动")
    npx = shutil.which("npx.cmd" if os.name == "nt" else "npx")
    if not npx:
        raise ValueError("未找到 npx，请安装 Node.js 22.19+（或 24+）")
    # 路径 JSON 引号与 YAML 标量兼容。具体入口由插件提供，启动前检查存在。
    entry = plugin / "plugin.mjs"
    if not entry.is_file():
        raise ValueError("Harness 插件入口缺失: " + str(entry))
    patch = args.data_dir / "smartbusiness.patch.yml"
    patch.write_text("- insert:\n    - id: smartbusiness\n      name: " + json.dumps(str(entry), ensure_ascii=False) + "\n", encoding="utf-8")
    env = os.environ.copy()
    env["SMARTBUSINESS_API_URL"] = base_url
    env["SMARTBUSINESS_API_TOKEN"] = token
    env["DSH_HOME"] = str(args.data_dir / "harness-home")
    env["DSH_TOOLS_MODE"] = "native"
    command = [npx, "--yes", "@deepseek-ai/dsh@" + HARNESS_VERSION, "web", "--patch", str(patch), "--no-open", "--port", str(args.port)]
    print(f"启动 DeepSeek Harness {HARNESS_VERSION}：http://127.0.0.1:{args.port}", flush=True)
    print("模型服务请在 Harness 设置中配置。密钥留在本地，不写入仓库。", flush=True)
    return subprocess.call(command, cwd=ROOT, env=env)


def main():
    parser = argparse.ArgumentParser(description="SmartBusiness 本地双行业商业工作台")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="启动本地工作台")
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument("--data-dir", type=Path, default=ROOT / ".smartbusiness")
    harness = commands.add_parser("harness", help="启动固定版本的 DeepSeek Harness 和业务插件")
    harness.add_argument("--api-port", type=int, default=8787)
    harness.add_argument("--port", type=int, default=3080)
    harness.add_argument("--data-dir", type=Path, default=ROOT / ".smartbusiness")
    args = parser.parse_args()
    args.data_dir = args.data_dir.resolve()
    try:
        if args.command == "harness":
            return start_harness(args)
        token = load_token(args.data_dir, create=True)
        service = BusinessService(args.data_dir / "business.sqlite3")
        server = make_server(service, token, args.port)
        print(f"SmartBusiness 工作台：http://127.0.0.1:{server.server_address[1]}", flush=True)
        print("本地试点；Ctrl+C 停止。行业案例为合成数据，真实记录保存在指定 data-dir。", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(1, "启动失败：" + str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
