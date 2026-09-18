from pathlib import Path
import re
import json
from decimal import Decimal

root = Path(__file__).resolve().parents[1]
docs = {str(p.relative_to(root)).replace('\\', '/'): p.read_text(encoding='utf-8') for p in root.rglob('*') if p.is_file() and p.suffix in {'.md', '.feature'}}
errors = []
links = 0
for name, body in docs.items():
    if '\ufffd' in body:
        errors.append(f'编码替换符: {name}')
    if name.endswith('.md') and len(re.findall(r'^```', body, re.M)) % 2:
        errors.append(f'代码围栏未配对: {name}')
    for target in re.findall(r'(?<!!)\[[^\]]+\]\(([^)]+)\)', body):
        if '://' in target or target.startswith('#'):
            continue
        links += 1
        resolved = (root / name).parent / target.split('#')[0]
        if not resolved.exists():
            errors.append(f'链接失效: {name} -> {target}')

def check_ids(file, regex, prefix, count):
    nums = [int(n) for n in re.findall(regex, docs[file], re.M)]
    if sorted(nums) != list(range(1, count + 1)):
        errors.append(f'{prefix} 编号不连续或重复: {nums}')
    return {f'{prefix}{n:02d}' for n in nums}

term_ids = check_ids('docs/zh-CN/01-专业词汇与统一语言.md', r'^\|T(\d+)\|', 'T', 144)
req_ids = check_ids('docs/zh-CN/03-业务需求与验收标准.md', r'^\|R(\d+) /', 'R', 23)
check_ids('docs/zh-CN/03-业务需求与验收标准.md', r'^\|N(\d+)\|', 'N', 8)
check_ids('docs/zh-CN/05-DDD战略设计.md', r'^\|BC(\d+) ', 'BC', 17)
rule_ids = check_ids('docs/zh-CN/06-DDD战术设计.md', r'BR(\d+)：', 'BR', 24)
test_ids = check_ids('docs/zh-CN/10-TDD与质量策略.md', r'^\|AT(\d+)\|', 'AT', 23)
check_ids('docs/zh-CN/12-架构决策记录.md', r'^\|ADR-(\d+)\|', 'ADR-', 14)
check_ids('docs/zh-CN/13-研究来源与核实状态.md', r'^\|S(\d+)\|', 'S', 18)
matrix = docs['docs/zh-CN/11-实施路线与追踪矩阵.md']
for req in req_ids:
    if not re.search(r'\b' + req + r'\b', matrix):
        errors.append(f'需求未进入追踪矩阵: {req}')
feature = docs['specs/acceptance/商业闭环.feature']
scenarios = re.findall(r'^  场景: (.+)$', feature, re.M)
if len(scenarios) != 14 or len(set(scenarios)) != 14:
    errors.append('验收规格场景数或名称重复异常')
for tag in re.findall(r'@(R\d+|BR\d+|AT\d+)', feature):
    if tag not in req_ids | rule_ids | test_ids:
        errors.append(f'无效场景标签: {tag}')
for fragment in re.split(r'^  场景: ', feature, flags=re.M)[1:]:
    if not all(word in fragment for word in ['假如 ', '当 ', '那么 ']):
        errors.append('验收例缺少 Given/When/Then')
assert Decimal('8000') - Decimal('2000') == Decimal('6000')
assert Decimal('6000') - Decimal('1000') == Decimal('5000')
assert Decimal('100000') - Decimal('60000') - Decimal('5000') == Decimal('35000')
assert Decimal('35000') - Decimal('10000') == Decimal('25000')
assert Decimal('150000') - Decimal('5000') - Decimal('105000') == Decimal('40000')
assert Decimal('40000') - Decimal('10000') - Decimal('3000') == Decimal('27000')
assert Decimal('1000') * Decimal('0.5') / Decimal('1000') == Decimal('0.5')
report = {'文件数': len(docs), '中文专题文档': len([p for p in docs if p.startswith('docs/')]), '术语数': 144, '功能需求数': 23, '上下文数': 17, '业务规则数': 24, '验收测试规划数': 23, '行为规格场景数': len(scenarios), '相对链接数': links, '示例算术检查': '通过', '产品测试': '未实现、未执行', 'Mermaid': '已检查围栏，未执行图形渲染', '错误': errors}
print(json.dumps(report, ensure_ascii=False, indent=2))
if errors:
    raise SystemExit(1)

