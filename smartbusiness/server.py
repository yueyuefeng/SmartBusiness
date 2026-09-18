"""本地单操作员 HTTP 适配器。不能作为公网生产服务器使用。"""
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
from pathlib import Path
import secrets
import socket
from urllib.parse import urlsplit
from .domain import Conflict, Forbidden, fields

WEB_ROOT = Path(__file__).parent / "web"
MAX_BODY = 128 * 1024


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON 字段重复")
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError("JSON 不允许非有限数字")


def make_server(service, token, port=0):
    if not isinstance(token, str) or len(token) < 24:
        raise ValueError("本地 API token 长度不足")
    operator_session = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        server_version = "SmartBusinessLocal/0.4"

        def log_message(self, format, *args):
            # 请求、来源文本和凭据不写入访问日志。业务审计由应用事务记录。
            pass

        def security_headers(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

        def send_bytes(self, status, data, content_type, cookie=False):
            self.send_response(status)
            self.security_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            if cookie:
                self.send_header("Set-Cookie", f"sb_operator={operator_session}; Path=/; HttpOnly; SameSite=Strict")
            self.end_headers()
            self.wfile.write(data)

        def respond(self, status, body):
            self.send_bytes(status, json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8"), "application/json; charset=utf-8")

        def local_request(self):
            port = self.server.server_address[1]
            hosts = (f"127.0.0.1:{port}", f"localhost:{port}")
            if self.headers.get("Host") not in hosts:
                raise Forbidden("只接受本地工作台地址")
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers["Host"]:
                raise Forbidden("不接受跨来源请求")

        def actor(self):
            authorization = self.headers.get("Authorization")
            if authorization is not None:
                if hmac.compare_digest(authorization, "Bearer " + token):
                    return "agent"
                return None
            try:
                cookie = SimpleCookie()
                cookie.load(self.headers.get("Cookie", ""))
                value = cookie.get("sb_operator")
                if value and hmac.compare_digest(value.value, operator_session):
                    return "operator"
            except Exception:
                return None
            return None

        def do_GET(self):
            try:
                self.local_request()
                path = urlsplit(self.path).path
                if path == "/health":
                    self.respond(200, {"status": "ok", "application": "SmartBusiness", "schema_version": 1})
                    return
                static = {"/": ("index.html", "text/html; charset=utf-8"),
                          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                          "/styles.css": ("styles.css", "text/css; charset=utf-8")}
                if path in static:
                    filename, content_type = static[path]
                    self.send_bytes(200, (WEB_ROOT / filename).read_bytes(), content_type, cookie=path == "/")
                elif path.startswith("/api/"):
                    if self.actor() is None:
                        self.respond(401, {"error": "请先打开本地工作台，或使用 Harness 服务凭据"})
                    elif path == "/api/dashboard":
                        self.respond(200, service.dashboard())
                    elif path.startswith("/api/cases/"):
                        self.respond(200, service.case(path[len("/api/cases/"):]))
                    else:
                        self.respond(404, {"error": "接口不存在"})
                else:
                    self.respond(404, {"error": "资源不存在"})
            except Forbidden as exc:
                self.respond(403, {"error": str(exc)})
            except ValueError as exc:
                self.respond(400, {"error": str(exc)})
            except Exception:
                self.respond(500, {"error": "读取失败，请检查本地服务与数据文件"})

        def do_POST(self):
            try:
                self.local_request()
                actor = self.actor()
                if actor is None:
                    self.respond(401, {"error": "缺少有效本地凭据"})
                    return
                if actor == "operator" and self.headers.get("Origin") != "http://" + self.headers["Host"]:
                    raise Forbidden("浏览器写入需要同源 Origin")
                if urlsplit(self.path).path != "/api/commands":
                    self.respond(404, {"error": "接口不存在"})
                    return
                if self.headers.get_content_type() != "application/json" or self.headers.get("Transfer-Encoding"):
                    raise ValueError("只接受具有 Content-Length 的 JSON 请求")
                length = int(self.headers.get("Content-Length", "-1"))
                if length < 0:
                    raise ValueError("缺少 Content-Length")
                if length > MAX_BODY:
                    self.respond(413, {"error": "请求不能超过 128 KiB"})
                    # 先关闭发送方向，再有限地排空已发送数据，避免 Windows 用 RST 吞掉 413。
                    self.connection.shutdown(socket.SHUT_WR)
                    self.connection.settimeout(1)
                    try:
                        self.rfile.read(min(length, MAX_BODY + 1))
                    except OSError:
                        pass
                    return
                self.connection.settimeout(5)
                data = self.rfile.read(length)
                if len(data) != length:
                    raise ValueError("请求体不完整")
                request = json.loads(data.decode("utf-8"), object_pairs_hook=strict_object, parse_constant=invalid_constant)
                fields(request, ("operation", "payload", "idempotency_key"))
                self.respond(200, service.execute(request["operation"], request["payload"], request["idempotency_key"], actor))
            except Forbidden as exc:
                self.respond(403, {"error": str(exc)})
            except Conflict as exc:
                self.respond(409, {"error": str(exc)})
            except (ValueError, UnicodeError, TypeError) as exc:
                self.respond(400, {"error": "输入不符合业务契约：" + str(exc)})
            except Exception:
                self.respond(500, {"error": "处理失败，命令未确认提交；重试须保留原幂等键"})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
