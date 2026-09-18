"""工作台聚合规则。输入文本不代表事实已核实；审核不等于外部发布。"""
from dataclasses import dataclass
from urllib.parse import urlsplit
from industry_pilots.shared import number, text_number


class Forbidden(ValueError):
    pass


class Conflict(ValueError):
    pass


def text(value, name, limit=10000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} 必须是非空文本，最多 {limit} 字符")
    return value.strip()


def fields(payload, required, optional=()):
    if not isinstance(payload, dict) or set(payload) - set(required) - set(optional) or set(required) - set(payload):
        raise ValueError("输入字段缺失或包含不支持的字段")


def choice(value, allowed, name):
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{name} 不是支持的选项")
    return value


def source_url(value):
    value = text(value, "来源链接", 2000)
    parsed = urlsplit(value)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("来源须为不含凭据的 HTTP/HTTPS 链接；本系统只记录链接，不自动抓取")
    return value


def money(value):
    value = text(value, "金额", 64)
    parsed = number(value, minimum=0, maximum=1000000000000)
    if parsed.as_tuple().exponent < -4:
        raise ValueError("金额最多保留四位小数")
    return text_number(parsed)


@dataclass(frozen=True)
class ContentReview:
    content: dict

    def decide(self, decision, comment):
        if self.content["status"] != "draft":
            raise Conflict("内容已经评审；此版本不支持覆盖评审记录")
        return {**self.content, "status": choice(decision, ("accepted", "rejected"), "评审决定"),
                "review_comment": text(comment, "评审说明"), "reviewed_revision": self.content["revision"],
                "publication_allowed": False}


@dataclass(frozen=True)
class DeliveryTask:
    task: dict

    def record_result(self, outcome, evidence_ref, notes):
        if self.task["status"] == "done":
            raise Conflict("完成项不能被覆盖，请创建后续工作项")
        return {**self.task, "status": choice(outcome, ("done", "blocked"), "结果"),
                "evidence_ref": text(evidence_ref, "证据引用", 2000), "notes": text(notes, "结果说明"),
                "evidence_status": "self_reported"}
