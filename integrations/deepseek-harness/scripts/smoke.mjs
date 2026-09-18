// 使用真实 Cordis/ToolRuntime 和真实 SmartBusiness HTTP 服务，不调用模型。
import assert from 'node:assert/strict';
import { Context } from '@deepseek-ai/cordis';
import SystemPrompt from '@deepseek-ai/dsh-system-prompt';
import ToolRuntime, { defineTool } from '@deepseek-ai/dsh-tools';
import * as SmartBusiness from '../plugin.mjs';

if (process.env.SMARTBUSINESS_SMOKE_TEMP !== '1') {
  throw new Error('请在仓库根目录执行 python scripts/check_harness_integration.py；仅允许临时测试数据库。');
}
const ctx = new Context();
try {
  await ctx.plugin(SystemPrompt);
  await ctx.plugin(ToolRuntime);
  await ctx.plugin(SmartBusiness);
  const call = async (name, args = {}, expectError = false) => {
    const result = await ctx.tools.execute({ callId: crypto.randomUUID(), name, arguments: args,
      signal: new AbortController().signal });
    assert.equal(Boolean(result.isError), expectError, `${name}: ${JSON.stringify(result.content)}`);
    return result.value;
  };
  const command = async (name, args, key = crypto.randomUUID()) =>
    (await call(`sb_${name}`, { ...args, idempotency_key: key }));
  const dashboard = await call('sb_dashboard');
  assert.equal(dashboard.cases.length, 6);
  assert.equal(dashboard.signals.length, 0);
  const original = await call('sb_case', { case_id: 'EN-H01' });
  assert.equal(original.result.finance.contribution_profit, '1700');
  const changed = await command('evaluate_case', { case_id: 'EN-H01', revenue: '10000' });
  assert.equal(changed.result.finance.contribution_profit, '2700');
  assert.equal((await call('sb_case', { case_id: 'EN-H01' })).result.finance.contribution_profit, '1700');
  const signalPayload = { case_id: 'EN-H01', title: '[测试] 家庭备电需求', source_url: 'https://example.com/test',
    excerpt: '合成资料，非真实访谈', customer_problem: '需要确认关键负载与安装条件' };
  const signal = (await command('capture_signal', signalPayload, 'smoke-signal-1')).result;
  assert.equal(signal.status, 'unverified');
  assert.equal((await command('capture_signal', signalPayload, 'smoke-signal-1')).replayed, true);
  const opportunity = (await command('propose_opportunity', { signal_id: signal.id, customer_segment: '[测试] 家庭',
    value_proposition: '提供需求诊断并核实供应资源', monetization: 'brokerage', market: '国家待定' })).result;
  assert.equal(opportunity.status, 'hypothesis');
  const resource = (await command('add_resource', { case_id: 'EN-H01', name: '[测试] 候选安装商', kind: 'installer',
    source_url: 'https://example.com/test-resource', capabilities: '待验证安装能力', quote_amount: '100.00', currency: 'EUR' })).result;
  assert.equal(resource.status, 'unverified');
  const content = (await command('draft_content', { opportunity_id: opportunity.id, channel: '内部测试',
    title: '[测试] 需求诊断', body: '先核实关键负载；不承诺节省或合格。' })).result;
  assert.equal(content.publication_allowed, false);
  const contact = (await command('add_contact', { name: '[测试] 联系人', company: '虚构', channel: 'manual', external_ref: 'test-only' })).result;
  const note = (await command('record_note', { contact_id: contact.id, body: '仅测试本地笔记', direction: 'internal' })).result;
  assert.equal(note.sent, false);
  const task = (await command('create_task', { opportunity_id: opportunity.id, kind: 'hardware',
    title: '[测试] 核实安装条件', acceptance: '提供真实场址资料与专业评审' })).result;
  const taskResult = (await command('record_task_result', { task_id: task.id, outcome: 'blocked',
    evidence_ref: 'test://missing-site-data', notes: '测试案例未包含真实场址' })).result;
  assert.equal(taskResult.status, 'blocked');
  ctx.tools.register(defineTool({ name: 'shell', description: 'forbidden probe', parameters: {},
    output: { schema: { type: 'object', additionalProperties: false, properties: {} } }, execute: () => { throw new Error('不得执行'); } }));
  await call('shell', {}, true);
  const response = await fetch(`${process.env.SMARTBUSINESS_API_URL}/api/commands`, {
    method: 'POST', headers: { authorization: `Bearer ${process.env.SMARTBUSINESS_API_TOKEN}`, 'content-type': 'application/json' },
    body: JSON.stringify({ operation: 'review_content', payload: { content_id: content.id, decision: 'accepted', comment: '禁止测试' }, idempotency_key: 'smoke-forbidden' }),
  });
  assert.equal(response.status, 403);
  const final = await call('sb_dashboard');
  assert.equal(final.events.length, 9);
  assert.equal(final.signals.length, 1);
  assert.equal(final.contents[0].status, 'draft');
  console.log(JSON.stringify({ status: 'passed', official_tool_runtime: '0.1.6-alpha.2',
    business_tools_exercised: 11, persisted_events: 9, idempotency: 'passed',
    forbidden_shell: 'passed', forbidden_agent_review: 'passed', live_model_called: false }, null, 2));
} finally {
  await ctx.fiber.dispose();
}
