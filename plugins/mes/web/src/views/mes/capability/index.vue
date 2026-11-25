<template>
  <div class="mes-page">
    <el-card shadow="never" class="capability-hero">
      <div class="eyebrow">MES CAPABILITY ROADMAP</div>
      <h2>{{ domain.title }}</h2>
      <p>{{ domain.summary }}</p>
      <el-tag :type="domain.statusType" effect="dark">{{ domain.status }}</el-tag>
    </el-card>

    <el-card shadow="never">
      <template #header><div class="section-header"><span>设计范围</span><span class="muted">页面先行，业务接口按能力包逐步启用</span></div></template>
      <el-table :data="domain.items" size="small">
        <el-table-column prop="name" label="能力" min-width="190" />
        <el-table-column prop="scope" label="包含内容" min-width="360" />
        <el-table-column label="状态" width="120"><template #default="{ row }"><el-tag size="small" :type="row.type">{{ row.status }}</el-tag></template></el-table-column>
        <el-table-column prop="note" label="说明" min-width="280" show-overflow-tooltip />
      </el-table>
    </el-card>

    <el-card shadow="never" class="boundary-card">
      <template #header><span>当前边界</span></template>
      <p v-if="domain.key === 'inventory'">库存主数据、投料、退料、完工入库、报废和库存流水由 L2 统一库存模块维护。本页面保留 MES 与库存的集成边界，不复制一套库存账。</p>
      <p v-else>当前页面不展示虚构的业务数据。后端能力完成后，将在本菜单下接入真实列表、状态机、权限和审计记录。</p>
      <div class="boundary-list"><span>已完成：P0 工单执行、派工、Track-in / Track-out、现场报工、事件时间线</span><span>待完成：该域的模型、迁移、Service、API、权限和端到端测试</span></div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

defineOptions({ name: "MesCapability" });
const route = useRoute();
type Capability = { name: string; scope: string; status: string; type: "success" | "warning" | "info"; note: string };
const definitions: Record<string, { title: string; summary: string; status: string; statusType: "success" | "warning" | "info"; items: Capability[] }> = {
  product_process: {
    title: "产品与工艺版本",
    summary: "承载制造物料扩展、BOM、BOP、Routing 与 Effectivity 的版本化入口。",
    status: "P0 使用物料快照，版本模型待建设",
    statusType: "warning",
    items: [
      { name: "制造物料扩展", scope: "制造属性、批次 / 序列号策略、单位与追溯策略", status: "规划中", type: "info", note: "当前工单引用 md_item 并保存释放快照" },
      { name: "BOM / BOP", scope: "产品结构、工艺路线、工序物料需求", status: "规划中", type: "info", note: "P0 尚未建立版本化主数据" },
      { name: "Routing / Effectivity", scope: "工艺版本、生效日期、数量区间和替代路线", status: "规划中", type: "info", note: "需要独立模型与生效性校验" }
    ]
  },
  quality: {
    title: "质量管理",
    summary: "已实现工序检验、合格放行与退回原工序返工；完整质量体系按需扩展。",
    status: "工序检验闭环已实现",
    statusType: "success",
    items: [
      { name: "工序检验放行", scope: "整工序判定、放行与检验记录", status: "已实现", type: "success", note: "在执行与报工 → 工序检验办理" },
      { name: "SPC", scope: "采样、控制图、规则判异、趋势预警", status: "规划中", type: "info", note: "需要测量值、规格限和规则模型" },
      { name: "退回原工序返工", scope: "不合格原因、复作与复检", status: "已实现", type: "success", note: "保留报工，重新执行后复检；独立 NCR 和部分处置仍未接入" }
    ]
  },
  traceability: {
    title: "追溯与谱系",
    summary: "建设批次、序列号、物料消耗、成品产出和正反向谱系查询。",
    status: "页面入口已建立，后端待建设",
    statusType: "info",
    items: [
      { name: "批次 / 序列号", scope: "生产对象、物料批次、序列号生命周期", status: "规划中", type: "info", note: "需要与库存批次和序列号契约协作" },
      { name: "物料消耗 / 成品产出", scope: "投料、退料、产出、报废事实", status: "规划中", type: "info", note: "由 MES 事实与 L2 库存流水关联" },
      { name: "正向 / 反向谱系", scope: "从原料到成品、从成品反查原料与工序", status: "规划中", type: "info", note: "将使用追加式谱系事实" }
    ]
  },
  equipment: {
    title: "设备集成",
    summary: "统一接入 OPC UA、MQTT、PLC、IoT 事件，并转换为 MES 标准事件。",
    status: "页面入口已建立，后端待建设",
    statusType: "info",
    items: [
      { name: "连接器与端点", scope: "OPC UA / MQTT / PLC / IoT 连接配置", status: "规划中", type: "info", note: "凭据和连接参数需独立授权" },
      { name: "标准化事件", scope: "设备状态、产量、报警、参数和心跳", status: "规划中", type: "info", note: "接入后写入集成事件与执行事实" },
      { name: "设备上下文", scope: "设备、工作站、工作中心和任务绑定", status: "规划中", type: "info", note: "将与派工和 Track-in 关联" }
    ]
  },
  scheduling: {
    title: "有限产能排程",
    summary: "人工工序计划已在生产排程接入；资源日历、技能和自动有限产能优化继续规划。",
    status: "页面入口已建立，后端待建设",
    statusType: "info",
    items: [
      { name: "资源与工作中心", scope: "设备、人员、班组、工作中心和资源组", status: "规划中", type: "info", note: "当前工序只保存名称快照" },
      { name: "日历与技能", scope: "班次、休息、维护、技能资格和可用时段", status: "规划中", type: "info", note: "将复用 L1/L2 人员与组织能力" },
      { name: "有限产能 / 派工", scope: "约束排程、重排、派工和进度反馈", status: "规划中", type: "info", note: "当前支持人工派工及计划时间安排，自动优化未实现" }
    ]
  },
  inventory: {
    title: "MES 库存协同",
    summary: "与 L2 统一库存协作，覆盖投料、退料、完工入库、报废和库存流水。",
    status: "复用 L2 库存，MES 业务集成待建设",
    statusType: "warning",
    items: [
      { name: "统一物料主数据", scope: "制造产品和生产物料引用 md_item", status: "已接入", type: "success", note: "P0 创建工单已通过 inventory.public 合同读取活动物料" },
      { name: "投料 / 退料", scope: "按工单、工序、批次和序列号登记库存动作", status: "规划中", type: "info", note: "不在 MES 内复制库存余额" },
      { name: "完工入库 / 报废", scope: "报工结果触发库存单据或受控事件", status: "规划中", type: "info", note: "需要明确 MES-L2 事务边界" }
    ]
  }
};
const domain = computed(() => {
  const key = String(route.meta.mes_domain || "product_process");
  return { key, ...(definitions[key] || definitions.product_process) };
});
</script>

<style scoped>
.mes-page { padding: 16px; }
.capability-hero { margin-bottom: 16px; background: linear-gradient(135deg, #17324d, #2c7a7b); color: white; }
.eyebrow { font-size: 11px; letter-spacing: 1.5px; opacity: .72; }
h2 { margin: 8px 0; font-size: 24px; }
.capability-hero p { margin: 0 0 16px; color: rgba(255,255,255,.8); }
.section-header { display: flex; justify-content: space-between; gap: 12px; font-weight: 600; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; font-weight: 400; }
.boundary-card { margin-top: 16px; }
.boundary-card p { line-height: 1.75; color: var(--el-text-color-regular); }
.boundary-list { display: flex; flex-direction: column; gap: 8px; color: var(--el-text-color-secondary); font-size: 13px; }
@media (max-width: 700px) { .section-header { align-items: flex-start; flex-direction: column; } }
</style>
