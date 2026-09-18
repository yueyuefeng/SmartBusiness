import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { Context } from '@deepseek-ai/cordis';
import SystemPrompt from '@deepseek-ai/dsh-system-prompt';
import ToolRuntime, { defineTool } from '@deepseek-ai/dsh-tools';
import { applyWithClient, createBusinessClient } from '../plugin.mjs';

const expected = [
  'sb_dashboard', 'sb_case', 'sb_evaluate_case', 'sb_capture_signal',
  'sb_propose_opportunity', 'sb_add_resource', 'sb_draft_content',
  'sb_add_contact', 'sb_record_note', 'sb_create_task', 'sb_record_task_result',
];

async function setup(t, handler) {
  const requests = [];
  const server = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const entry = { method: req.method, url: req.url, headers: req.headers,
      body: chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) : null };
    requests.push(entry);
    if (handler) return handler(entry, res);
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify({ result: { id: 'example-1', synthetic: true }, replayed: false }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const apiURL = `http://127.0.0.1:${server.address().port}`;
  const client = createBusinessClient({ apiURL, token: 'test-only-agent-token' });
  const ctx = new Context();
  await ctx.plugin(SystemPrompt);
  await ctx.plugin(ToolRuntime);
  const fiber = await ctx.plugin({ name: 'test-smartbusiness', inject: ['tools', 'systemPrompt'],
    apply: child => applyWithClient(child, client) });
  t.after(() => ctx.fiber.dispose());
  const call = (name, args = {}, signal = new AbortController().signal) =>
    ctx.tools.execute({ callId: 'test-call', name, arguments: args, signal });
  return { ctx, requests, call, fiber, apiURL };
}

test('真实 Harness 注册 11 个受限工具，并自动编入模型提示', async t => {
  const { ctx } = await setup(t);
  assert.deepEqual(ctx.tools.schemas().map(s => s.name).sort(), [...expected].sort());
  const assembled = await ctx.systemPrompt.assemble();
  assert.equal(assembled.tools.length, 11);
  assert.ok(!JSON.stringify(assembled).includes('test-only-agent-token'));
  assert.ok(JSON.stringify(assembled).includes('不可信数据'));
});

test('看板使用 Bearer 认证且输出保留业务值和证据边界', async t => {
  const { requests, call } = await setup(t);
  const result = await call('sb_dashboard');
  assert.equal(result.isError, false);
  assert.equal(requests[0].url, '/api/dashboard');
  assert.equal(requests[0].headers.authorization, 'Bearer test-only-agent-token');
  assert.equal(result.value.result.synthetic, true);
  assert.match(result.content[0].text, /不可信数据/);
});

test('案例 ID 必须是单一路径片段，不能注入另一个 API 路由', async t => {
  const { requests, call } = await setup(t);
  assert.equal((await call('sb_case', { case_id: 'energy-home-eu' })).isError, false);
  assert.equal(requests[0].url, '/api/cases/energy-home-eu');
  assert.equal((await call('sb_case', { case_id: '../dashboard?override=1' })).isError, true);
  assert.equal(requests.length, 1);
});

test('情景评估传递十进制字符串和幂等键，业务运算留给领域服务', async t => {
  const { requests, call } = await setup(t);
  const result = await call('sb_evaluate_case', { case_id: 'energy-home-eu', revenue: '1000.10',
    cost_changes: [{ id: 'battery', amount: '500.00' }], idempotency_key: 'eval-example-1' });
  assert.equal(result.isError, false);
  assert.deepEqual(requests[0].body, { operation: 'evaluate_case',
    payload: { case_id: 'energy-home-eu', revenue: '1000.10', cost_changes: [{ id: 'battery', amount: '500.00' }] },
    idempotency_key: 'eval-example-1' });
});

test('不允许模型注入 actor、operation 或未知字段', async t => {
  const { requests, call } = await setup(t);
  const result = await call('sb_capture_signal', { case_id: 'case-a', title: '访谈',
    source_url: 'https://example.org/interview', excerpt: '演示', customer_problem: '停电',
    idempotency_key: 'capture-1', actor: 'reviewer', operation: 'review_content' });
  assert.equal(result.isError, true);
  assert.equal(requests.length, 0);
});

test('拒绝缺失幂等键、数字金额和非法枚举，均不调用后端', async t => {
  const { requests, call } = await setup(t);
  assert.equal((await call('sb_evaluate_case', { case_id: 'case-a' })).isError, true);
  assert.equal((await call('sb_evaluate_case', { case_id: 'case-a', revenue: 12.34, idempotency_key: 'a' })).isError, true);
  assert.equal((await call('sb_create_task', { opportunity_id: 'o1', kind: 'send_payment', title: 'x', acceptance: 'x', idempotency_key: 'b' })).isError, true);
  assert.equal(requests.length, 0);
});

test('403 错误不当成成功，不泄露原始响应中的凭据', async t => {
  const { call } = await setup(t, (_req, res) => {
    res.writeHead(403, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ error: 'test-only-agent-token should never be reflected' }));
  });
  const result = await call('sb_dashboard');
  assert.equal(result.isError, true);
  assert.match(result.content[0].text, /403/);
  assert.ok(!JSON.stringify(result).includes('test-only-agent-token'));
});

test('业务模式阻止已注册的 shell 工具执行，即使普通策略主动放行', async t => {
  const { ctx, call } = await setup(t);
  let executed = false;
  ctx.tools.register(defineTool({ name: 'shell', description: '测试用 shell 替身，不执行系统命令', parameters: {},
    output: { schema: { type: 'string' }, render: (_args, value) => [{ type: 'text', text: value }] },
    execute: async () => { executed = true; return 'unexpected'; } }));
  ctx.on('tools/pre-execute', async () => ({ kind: 'allow' }));
  const result = await call('shell');
  assert.equal(result.isError, true);
  assert.equal(executed, false);
});

test('拒绝伪造 sb_ 前缀的审批工具，不依靠名称前缀授权', async t => {
  const { ctx, call } = await setup(t);
  let executed = false;
  ctx.tools.register(defineTool({ name: 'sb_review_content', description: '不应调用', parameters: {},
    output: { schema: { type: 'boolean' }, render: () => [] },
    execute: async () => { executed = true; return true; } }));
  assert.equal((await call('sb_review_content')).isError, true);
  assert.equal(executed, false);
});

test('409 幂等冲突提示保留状态码，不自动重试写入', async t => {
  const { call, requests } = await setup(t, (_req, res) => {
    res.writeHead(409, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ error: 'conflict' }));
  });
  const result = await call('sb_evaluate_case', { case_id: 'c1', idempotency_key: 'same-key' });
  assert.equal(result.isError, true);
  assert.match(result.content[0].text, /409/);
  assert.equal(requests.length, 1);
});

test('不跟随重定向，避免把本地 agent 凭据发送给其它服务', async t => {
  const { call, requests } = await setup(t, (_req, res) => {
    res.writeHead(302, { location: 'https://example.org/untrusted' }); res.end();
  });
  assert.equal((await call('sb_dashboard')).isError, true);
  assert.equal(requests.length, 1);
});

test('仅连接指定的本机 HTTP API，拒绝远端、嵌入凭据和空 token', () => {
  for (const apiURL of ['https://example.org', 'http://alice:password@127.0.0.1:8787', 'http://127.0.0.1:8787/api?x=1']) {
    assert.throws(() => createBusinessClient({ apiURL, token: 'local-test' }));
  }
  assert.throws(() => createBusinessClient({ apiURL: 'http://127.0.0.1:8787', token: '' }));
});

test('提前取消的工具调用不触发后端请求', async t => {
  const { call, requests } = await setup(t);
  const controller = new AbortController(); controller.abort();
  assert.equal((await call('sb_dashboard', {}, controller.signal)).isError, true);
  assert.equal(requests.length, 0);
});

test('插件卸载后不残留业务工具', async t => {
  const { ctx, fiber } = await setup(t);
  await fiber.dispose();
  assert.equal(ctx.tools.schemas().length, 0);
});

test('其它 8 个命令逐项映射到固定 operation，不包含发送、发布、付款或审批', async t => {
  const { requests, call } = await setup(t);
  const entries = [
    ['capture_signal', { case_id: 'c1', title: '需求', source_url: 'https://example.org', excerpt: '素材', customer_problem: '备电' }],
    ['propose_opportunity', { signal_id: 's1', customer_segment: '安装商', value_proposition: '交付', monetization: 'product', market: 'EU' }],
    ['add_resource', { case_id: 'c1', name: '供应商候选', kind: 'supplier', source_url: 'https://example.org', capabilities: '电池', quote_amount: '500.00', currency: 'EUR' }],
    ['draft_content', { opportunity_id: 'o1', channel: 'linkedin', title: '演示草稿', body: '待核实' }],
    ['add_contact', { name: '演示客户', company: '演示公司', channel: 'manual', external_ref: 'ref-1' }],
    ['record_note', { contact_id: 'p1', body: '手工记录', direction: 'internal' }],
    ['create_task', { opportunity_id: 'o1', kind: 'hardware', title: '样机', acceptance: '台架报告' }],
    ['record_task_result', { task_id: 't1', outcome: 'blocked', evidence_ref: 'sample-report', notes: '缺报告' }],
  ];
  for (const [operation, payload] of entries) {
    const result = await call(`sb_${operation}`, { ...payload, idempotency_key: `test-${operation}` });
    assert.equal(result.isError, false, operation);
    assert.deepEqual(requests.at(-1).body, { operation, payload, idempotency_key: `test-${operation}` });
  }
  assert.equal(requests.length, 8);
});
