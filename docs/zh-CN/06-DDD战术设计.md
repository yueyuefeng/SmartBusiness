# 06 DDD 战术设计

## 1. 聚合、命令和不变量

|聚合根 / 上下文|内部对象或值对象|关键命令 / 事件|不变量（规则编号）|
|---|---|---|---|
|IntelligenceItem / BC01|Claim、EvidenceRef、Confidence|VerifyClaim / ClaimVerified|BR01：可采纳判断必须有来源与审核记录；保留相反证据|
|Requirement / BC02|RequirementRevision、Criterion、Classification|Confirm / RequirementConfirmed|BR02：确认必须有负责人、验收条件和来源；已基线修订不可原地改|
|RequirementBaseline / BC02|有界的修订引用清单|Publish / BaselinePublished|BR03：清单只引用已确认且可访问的固定修订；发布后只增新版本|
|CapabilityProfile / BC03|能力、约束、EvidenceRef、Validity|Verify / CapabilityVerified|BR04：核实状态必须有责任人与未过期证据；过期不等于事实永久失效但必须重核|
|BusinessModel / BC04|Segment、RevenueMechanism、CostAssumptions|Submit / BusinessModelSubmitted|BR05：投入评审前必须定义客户、收益机制、成本和失败条件|
|Experiment / BC04|Hypothesis、Threshold、Budget、ObservationRef|Start/Complete / ExperimentCompleted|BR06：启动后原假设、成功阈值与预算快照不可改写；变更需新实验修订|
|DecisionCase / BC05|Alternative、CriteriaVersion、EvidenceRef、Approval|Approve / InvestmentApproved|BR07：硬约束满足；权重非负且总和为 1；授权额度与对象版本校验|
|CustomerAccount / BC06|CustomerProfile、业务属性|UpdateProfile / CustomerUpdated|BR08：租户内身份稳定；合并不消除审计和历史引用|
|IdentityLink / BC06|ChannelIdentity、ContactRef、依据|ConfirmLink/Revoke / IdentityLinked|BR09：不能按昵称自动合并；同一渠道身份的有效关联不能冲突|
|Conversation / BC07|参与者引用、指派和会话状态|Assign/Close / ConversationAssigned|BR10：参与者与坐席权限有效；不把无限消息集合装入聚合|
|OutboundMessage / BC07|PayloadRef、目标、状态、PolicySnapshot|RequestSend / MessageSendRequested|BR11：内容和授权校验；幂等键唯一；送达必须有相应回执|
|Campaign / BC08|目标、预算、受众、归因配置|Activate / CampaignActivated|BR12：预算非负；定义有效期和评价指标|
|ContentAsset / BC08|ContentRevision、SourceRefs、Rights、Approval|Approve / ContentApproved|BR13：审批绑定内容哈希与版本；修改后原审批失效|
|PublicationJob / BC08|账号、时间、ContentRevisionRef、Attempts|Schedule/Dispatch / PublicationRequested|BR14：发布内容必须仍获批准且权限有效；一次逻辑发布不得重复产生外发|
|SalesQuote / BC09|报价行、Money、TaxTreatment、TradeTerm|Accept / SalesQuoteAccepted|BR15：未过期、数量有效、币种及费用范围明确；接受固定报价版本|
|TradeOrder / BC09|OrderLine、PartySnapshot、FulfillmentPolicy|Confirm/Cancel / TradeOrderConfirmed|BR16：引用已接受报价或经批准的独立交易条件；已履约部分只能退货/更正|
|Contract / BC10|ContractRevision、PartySnapshot、Obligation摘要|RecordExecution / ContractExecuted|BR17：证据核实与生效规则满足；生效版本不可原地覆盖|
|Release / BC11|ArtifactRefs、BaselineRef、TestEvidence、Approval|Authorize / ReleaseAuthorized|BR18：制品摘要、构建来源与必要测试一致；旧构建通过不代表新构建通过|
|BOMRevision / BC12|BOMLine、PartRevisionRef、单位和数量|Release / BOMReleased|BR19：数量正、引用明确、无循环、替代料获授权；发布不可变|
|EngineeringChange / BC12|影响分析、Approvals、生效批次|Approve / ECOApproved|BR20：软硬件/采购/质量影响已评估；撤销不抹除已执行事实|
|ReconciliationBatch / BC13|外部记录引用、差异项|Reconcile / SettlementReconciled|BR21：每条外部记录唯一且有来源；未解决差异不能标为已核对|
|ProfitSnapshot / BC13|口径、期间、汇率、收入成本快照|Freeze / ProfitSnapshotFrozen|BR22：缺成本要标不完整；退款/更正产生新快照，不覆盖旧结果|
|MetricObservation / BC14|ValueWithUnit、期间、边界、EvidenceRef|Verify / MetricVerified|BR23：缺失、估计、实测不同状态；单位和报告边界匹配|
|ESGReport / BC14|BoundaryVersion、MetricRefs、FactorVersions、Approval|Publish / ESGReportPublished|BR24：冻结输入和计算版本；已发布报告通过重述更正|

Contact、Message、Obligation、TestRun 等随增长可作独立聚合，不强制嵌套在 CustomerAccount、Conversation、Contract 或 Project 中。聚合应有有限大小，避免“一个客户加载全部消息”。

## 2. 状态机

|对象|允许的主路径|必须显式处理的分支|
|---|---|---|
|Requirement|草稿 → 已澄清 → 已确认 → 已纳入基线 → 已废弃|退回澄清；变更生成新修订，原基线保留|
|Experiment|草稿 → 已批准预算 → 运行中 → 已完成 → 已复盘|提前终止、无结论、数据不足；失败也可正常完成|
|DecisionCase|草稿 → 待评审 → 已批准/已否决 → 已执行 → 已复盘|证据变化触发待重评；执行域独立判断动作授权|
|OutboundMessage|草稿 → 待发送 → 已受理 → 已送达 → 已读|策略阻止、已失败、结果未知；没有回执的渠道停在已受理|
|PublicationJob|草稿 → 待审核 → 已批准 → 已排期 → 提交中 → 已发布|已拒绝、已取消、失败、结果未知；平台删除记录为后续状态|
|TradeOrder|草稿 → 已确认 → 履约中 → 已履约 → 已关闭|部分交付、部分取消、售后中；收付是独立维度|
|Contract|草稿 → 评审中 → 待签署 → 已签署待生效 → 生效 → 履行完成|终止/争议；无额外生效条件时签署后可直接生效|
|BOMRevision|草稿 → 评审中 → 已发布 → 已替代|评审退回；新版本发布不删除历史|
|ESGReport|草稿 → 数据收集中 → 待复核 → 已批准 → 已发布|缺失待处理、撤回、已重述|

退货、售后、对账等状态不能全塞进订单一个枚举；用有限且独立的维度和过程管理器组合。

## 3. 关键值对象

Money(amount: decimal, currency)，Quantity(value: decimal, unit)，Period(start,end,timeZone)，EvidenceRef(id,revision,hash)，TradeTerm(ruleSet,edition,code,namedPlace)，FXRateSnapshot(pair,rate,asOf,source,purpose)，ChannelIdentity(provider,accountScope,externalId)，PolicySnapshot(id,version,evaluatedAt)。

金额禁止二进制浮点；不同币种不直接相加。显示四舍五入和核算精度分开；单位换算具有版本和适用条件；时间存 UTC 同时保留业务时区。

## 4. 仓储与领域服务

- Repository 按聚合根加载/保存，条件包含 tenantId 和 version；领域层不依赖 HTTP、ORM 或消息 SDK。
- DomainService：资源匹配、决策评分、利润口径计算、单位换算。只有无法归属一个聚合的业务规则才使用领域服务。
- ApplicationService：鉴权、加载聚合、执行命令、保存、同事务写 Outbox；不把核心规则写在 Controller 中。
- Policy：发送窗口、审批额度、信用条件、报告发布完整性；策略有版本并按适用地区/账号/业务类型选择。
- 外部语义翻译在 Adapter/ACL，禁止平台错误码、第三方用户类渗入领域。

## 5. 一致性与事件信封

一个聚合变更与 Outbox 同一数据库事务；消费者使用 Inbox 去重并与本地业务变更同事务提交。按聚合版本处理顺序，缺版本进入重放/补偿队列。采用“至少一次投递 + 幂等业务效果”，不宣称网络上的端到端恰好一次。

事件信封候选：

```json
{
  "eventId": "evt-example",
  "eventType": "RequirementConfirmed",
  "schemaVersion": 1,
  "tenantId": "tenant-example",
  "aggregateId": "req-example",
  "aggregateVersion": 3,
  "occurredAt": "2026-09-18T04:00:00Z",
  "correlationId": "flow-example",
  "causationId": "cmd-example",
  "data": {"revision": 2, "baselineCandidate": true}
}
```

事件不直接携带敏感正文、证件或令牌；引用访问仍需权限校验。新增可选字段向后兼容；删除或改变语义需新版本与消费者迁移。

## 6. 并发、删除与审计

乐观锁防止不同设备同时覆盖同一修订。冲突返回服务端当前版本与可比较字段，金额、审批、签约信息不自动合并。聚合逻辑删除和材料物理删除遵从领域保留策略，保全例外经授权后记录。审计不把已删除敏感正文永久复制到无管控日志中。
