<script setup lang="ts">
import ListPagination from "@/components/ListPagination/index.vue";
import ActionButton from "@/components/ActionButton/index.vue";
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { jsonOptions, request, type RecordData } from "../api";

const emit = defineEmits<{ saved: [] }>();
const props = defineProps<{ orgId?: string }>();
const rulesPath = () =>
  "/quote-rules" + (props.orgId ? "?org_id=" + props.orgId : "");
const open = ref(false);
const loading = ref(false);
const dirty = ref(false);
const rules = ref<RecordData | null>(null);
const wordInputs = ref<Record<string, string>>({});
const tab = ref("processes");
const pendingProcesses = ref<string[]>([]);
watch(tab, () => {
  pendingProcesses.value = [];
});
const addingKind = computed(() =>
  tab.value === "external" ? "external_processes" : "processes"
);
function processOptions(kind: string): RecordData[] {
  return (rules.value?.manufacturing_processes || []).filter(
    (row: RecordData) =>
      row.processing_type_code ===
      (kind === "external_processes" ? "outsourced" : "in_house")
  );
}
function isBound(id: string, except?: string) {
  return ["processes", "external_processes"].some(kind =>
    config.value[kind].some(
      (row: RecordData) =>
        row.id !== except && row.process_id === id && row.is_active
    )
  );
}
function bindProcess(row: RecordData, kind: string) {
  row.process_id ||= null;
  const process = processOptions(kind).find(item => item.id === row.process_id);
  if (process) {
    row.name = process.process_name;
    if (kind === "processes")
      row.process_type_code = process.process_type_code || null;
  }
  dirty.value = true;
}
function addProcesses() {
  const kind = addingKind.value;
  if (config.value[kind].length + pendingProcesses.value.length > 100) {
    ElMessage.warning("每类最多100条规则，请先整理已有规则");
    return;
  }
  for (const id of pendingProcesses.value) {
    if (isBound(id)) continue;
    add(kind);
    const row = config.value[kind].at(-1);
    row.process_id = id;
    bindProcess(row, kind);
  }
  pendingProcesses.value = [];
}
const config = computed(() => rules.value!.config);
const materialSearch = ref("");
const materialPage = ref(1);
const filteredMaterials = computed(() =>
  (config.value?.materials || [])
    .map((row: RecordData, index: number) => ({ row, index }))
    .filter(({ row }: { row: RecordData }) =>
      `${row.name} ${row.aliases.join(" ")} ${row.condition || ""}`
        .toLowerCase()
        .includes(materialSearch.value.toLowerCase())
    )
);
const visibleMaterials = computed(() =>
  filteredMaterials.value.slice(
    (materialPage.value - 1) * 20,
    materialPage.value * 20
  )
);
watch(materialSearch, () => {
  materialPage.value = 1;
});
const numbers = [
  "unit_hours",
  "hourly_rate",
  "density",
  "material_price",
  "stock_allowance",
  "rate_per_kg",
  "rate_per_m2",
  "size_min",
  "size_max",
  "minimum_unit"
];

async function show() {
  loading.value = true;
  try {
    rules.value = await request(rulesPath());
    wordInputs.value = {};
    for (const row of rules.value!.config.materials)
      wordInputs.value[row.id] = row.aliases.join(", ");
    for (const row of rules.value!.config.processes)
      wordInputs.value[row.id] = row.keywords.join(", ");
    for (const row of rules.value!.config.external_processes)
      wordInputs.value[row.id] = row.keywords.join(", ");
    function numeric(value: RecordData) {
      for (const [key, item] of Object.entries(value)) {
        if (numbers.includes(key))
          value[key] = item == null ? undefined : Number(item);
        else if (item && typeof item === "object") numeric(item);
      }
    }
    numeric(rules.value!);
    dirty.value = false;
    pendingProcesses.value = [];
    open.value = true;
  } catch (error) {
    ElMessage.error((error as Error).message);
  } finally {
    loading.value = false;
  }
}
defineExpose({ show });

function add(kind: string) {
  const base = { id: crypto.randomUUID(), name: "", is_active: true };
  wordInputs.value[base.id] = "";
  if (kind === "processes")
    config.value.processes.push({
      ...base,
      keywords: [],
      machine_contains: "",
      machine: "",
      unit_hours: undefined,
      hourly_rate: undefined
    });
  else if (kind === "materials")
    config.value.materials.push({
      ...base,
      aliases: [],
      density: undefined,
      material_price: undefined
    });
  else if (kind === "external_processes")
    config.value.external_processes.push({
      ...base,
      keywords: [],
      rate_per_kg: undefined,
      minimum_unit: 0,
      weight_basis_code: "stock",
      price_unit_code: "kg"
    });
  dirty.value = true;
}
function words(value: string) {
  return value
    .split(/[,，;；\n]/)
    .map(item => item.trim())
    .filter(Boolean);
}
function move(rows: RecordData[], index: number, delta: number) {
  const target = index + delta;
  if (target < 0 || target >= rows.length) return;
  [rows[index], rows[target]] = [rows[target], rows[index]];
  dirty.value = true;
}
async function save() {
  for (const row of config.value.materials)
    row.aliases = words(wordInputs.value[row.id] || "");
  for (const row of config.value.processes)
    row.keywords = words(wordInputs.value[row.id] || "");
  for (const row of config.value.external_processes)
    row.keywords = words(wordInputs.value[row.id] || "");
  for (const kind of ["materials", "processes", "external_processes"]) {
    for (const row of config.value[kind]) {
      if (
        !row.name.trim() ||
        (kind === "materials" && !row.aliases.length) ||
        (["processes", "external_processes"].includes(kind) && !row.process_id)
      ) {
        ElMessage.warning("请填写材料名称和匹配条件，工序规则必须选择正式工艺");
        return;
      }
    }
  }
  loading.value = true;
  try {
    await request(
      rulesPath(),
      jsonOptions(
        { version_no: rules.value!.version_no, config: config.value },
        "PUT"
      )
    );
    dirty.value = false;
    open.value = false;
    emit("saved");
    ElMessage.success("报价规则已保存，将用于后续解析；已有零件可点击补齐参数");
  } catch (error) {
    ElMessage.error((error as Error).message);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <el-dialog
    v-model="open"
    title="报价规则"
    width="min(960px, 95vw)"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="!dirty"
  >
    <div
      v-if="rules"
      class="rules-editor"
      @input="dirty = true"
      @change="dirty = true"
    >
      <p class="field-help">
        工序规则只能从现有工艺档案添加。只补空白参数，历史报价及已有数值保留。
      </p>
      <el-checkbox v-model="config.is_auto_apply"
        >解析完成后自动补齐材料与工序参数</el-checkbox
      >
      <div
        v-if="['processes', 'external'].includes(tab)"
        class="process-add erp-query-form"
      >
        <el-select
          v-model="pendingProcesses"
          multiple
          filterable
          collapse-tags
          collapse-tags-tooltip
          placeholder="从正式工艺档案选择，可多选"
          style="width: min(460px, 100%)"
        >
          <el-option
            v-for="item in processOptions(addingKind)"
            :key="item.id"
            :label="`${item.process_no} · ${item.process_name}`"
            :value="item.id"
            :disabled="isBound(item.id)"
          />
        </el-select>
        <ActionButton
          intent="create"
          :disabled="!pendingProcesses.length"
          @click="addProcesses"
          >添加工艺专属规则</ActionButton
        >
      </div>
      <el-tabs v-model="tab">
        <el-tab-pane label="工序参数" name="processes">
          <p class="field-help">
            工序名称和类别来自正式工艺档案，按工艺绑定取价。新增规则的费率需工程填写。
          </p>
          <div
            v-for="(row, index) in config.processes"
            :key="row.id"
            class="rule-row"
          >
            <div class="rule-toolbar">
              <b>工序规则 {{ Number(index) + 1 }}</b
              ><el-tag type="primary">工艺专属</el-tag
              ><el-checkbox v-model="row.is_active">启用</el-checkbox
              ><el-button
                size="small"
                :disabled="index === 0"
                @click="move(config.processes, Number(index), -1)"
                >上移</el-button
              ><el-button
                size="small"
                :disabled="index === config.processes.length - 1"
                @click="move(config.processes, Number(index), 1)"
                >下移</el-button
              ><el-button
                size="small"
                type="danger"
                link
                @click="
                  config.processes.splice(Number(index), 1);
                  dirty = true;
                "
                >删除</el-button
              >
            </div>
            <div class="rules-grid">
              <label
                >正式生产工艺<el-select
                  v-model="row.process_id"
                  filterable
                  placeholder="必须选择现有正式工艺"
                  @change="bindProcess(row, 'processes')"
                >
                  <el-option
                    v-for="item in processOptions('processes')"
                    :key="item.id"
                    :label="`${item.process_no} · ${item.process_name}`"
                    :value="item.id"
                    :disabled="isBound(item.id, row.id)"
                  /> </el-select
              ></label>
              <label
                >工序类别<el-select
                  v-model="row.process_type_code"
                  disabled
                  clearable
                  placeholder="由工艺档案确定"
                >
                  <el-option
                    v-for="item in rules.process_catalog"
                    :key="item.process_type_code"
                    :label="item.name"
                    :value="item.process_type_code"
                  /> </el-select
              ></label>
              <label
                >规则名称<el-input
                  v-model="row.name"
                  readonly
                  maxlength="120"
                  placeholder="从工艺档案提取"
              /></label>
              <label
                >默认设备（仅填空白）<el-input
                  v-model="row.machine"
                  maxlength="120"
              /></label>
            </div>
            <div class="rules-grid three">
              <label
                >备用工时 h/件<el-input-number
                  v-model="row.unit_hours"
                  :min="0"
                  :max="100000000"
                  :precision="4"
                  :controls="false"
                  placeholder="不自动填写"
              /></label>
              <label
                >小时费率 元/h<el-input-number
                  v-model="row.hourly_rate"
                  :min="0.01"
                  :max="100000000"
                  :precision="2"
                  :controls="false"
                  placeholder="不自动填写"
              /></label>
            </div>
          </div>
        </el-tab-pane>
        <el-tab-pane label="外协计价" name="external">
          <p class="field-help">
            只从正式委外工艺档案添加，按工艺绑定取价。支持重量或面积计价及最低收费。
          </p>
          <div
            v-for="(row, index) in config.external_processes"
            :key="row.id"
            class="rule-row"
          >
            <div class="rule-toolbar">
              <el-tag type="primary">工艺专属</el-tag>
              <el-checkbox v-model="row.is_active">启用</el-checkbox>
              <el-button
                :disabled="index === 0"
                @click="move(config.external_processes, Number(index), -1)"
                >上移</el-button
              >
              <el-button
                type="danger"
                link
                @click="
                  config.external_processes.splice(Number(index), 1);
                  dirty = true;
                "
                >删除</el-button
              >
            </div>
            <div class="rules-grid">
              <label
                >正式委外工艺<el-select
                  v-model="row.process_id"
                  filterable
                  placeholder="必须选择现有正式工艺"
                  @change="bindProcess(row, 'external_processes')"
                >
                  <el-option
                    v-for="item in processOptions('external_processes')"
                    :key="item.id"
                    :label="`${item.process_no} · ${item.process_name}`"
                    :value="item.id"
                    :disabled="isBound(item.id, row.id)"
                  /> </el-select
              ></label>
              <label>规则名称<el-input v-model="row.name" readonly /></label>
              <label
                >计价单位<el-select v-model="row.price_unit_code"
                  ><el-option label="元/kg" value="kg" /><el-option
                    label="元/m²"
                    value="m2"
                /></el-select>
              </label>
              <label v-if="row.price_unit_code === 'm2'">
                单价 元/m²<el-input-number
                  v-model="row.rate_per_m2"
                  :min="0"
                  :precision="4"
                  :controls="false"
                />
              </label>
              <label v-else
                >单价 元/kg<el-input-number
                  v-model="row.rate_per_kg"
                  :min="0"
                  :precision="2"
                  :controls="false"
              /></label>
              <label
                >最低收费 元/件<el-input-number
                  v-model="row.minimum_unit"
                  :min="0"
                  :precision="2"
                  :controls="false"
              /></label>
              <label v-if="row.price_unit_code !== 'm2'"
                >计费重量<el-select v-model="row.weight_basis_code"
                  ><el-option
                    label="毛坯重量（核算表口径）"
                    value="stock" /><el-option
                    label="模型净重量"
                    value="net" /></el-select
              ></label>
            </div>
            <p v-if="row.note" class="field-help">{{ row.note }}</p>
            <p v-if="row.source?.range" class="field-help">
              来源：{{ row.source.file }} / {{ row.source.range }}
            </p>
          </div>
        </el-tab-pane>
        <el-tab-pane label="材料价格" name="materials">
          <p class="field-help">
            已导入核算表参考价。AI
            依据牌号、状态、毛坯尺寸和采购条件选择已启用条目，并说明理由；无法确定时需人工选择。价格和密度取自规则库。
          </p>
          <el-input
            v-model="materialSearch"
            clearable
            placeholder="搜索材料、牌号或规格"
          />
          <ListPagination
            v-model:current-page="materialPage"
            :page-size="20"
            :total="filteredMaterials.length"
            layout="total, prev, pager, next"
          />
          <div
            v-for="{ row, index } in visibleMaterials"
            :key="row.id"
            class="rule-row"
          >
            <div class="rule-toolbar">
              <b>材料规则 {{ Number(index) + 1 }}</b
              ><el-checkbox v-model="row.is_active">启用</el-checkbox
              ><el-button
                size="small"
                :disabled="index === 0"
                @click="move(config.materials, Number(index), -1)"
                >上移</el-button
              ><el-button
                size="small"
                :disabled="index === config.materials.length - 1"
                @click="move(config.materials, Number(index), 1)"
                >下移</el-button
              ><el-button
                size="small"
                type="danger"
                link
                @click="
                  config.materials.splice(Number(index), 1);
                  dirty = true;
                "
                >删除</el-button
              >
            </div>
            <div class="rules-grid">
              <label
                >规则名称<el-input
                  v-model="row.name"
                  maxlength="120"
                  placeholder="例如：POM 板材"
              /></label>
              <label
                >材料牌号 / 别名（逗号分隔）<el-input
                  v-model="wordInputs[row.id]"
                  placeholder="例如：POM，聚甲醛"
              /></label>
              <label
                >密度 g/cm³<el-input-number
                  v-model="row.density"
                  :min="0.001"
                  :max="100000000"
                  :precision="3"
                  :controls="false"
                  placeholder="不自动填写"
              /></label>
              <label
                >计价单位<el-select v-model="row.price_unit_code"
                  ><el-option label="元/kg" value="kg" /><el-option
                    label="元/mm"
                    value="mm" /></el-select
              ></label>
              <label
                >采购单价<el-input-number
                  v-model="row.material_price"
                  :min="0.0001"
                  :max="100000000"
                  :precision="4"
                  :controls="false"
                  placeholder="不自动填写"
              /></label>
              <label>采购规格 / 条件<el-input v-model="row.condition" /></label>
              <label
                >规格类别<el-select v-model="row.stock_form_code"
                  ><el-option label="不限" value="any" /><el-option
                    label="板材厚度"
                    value="plate" /><el-option
                    label="棒材直径"
                    value="round" /><el-option
                    label="型材"
                    value="profile" /></el-select
              ></label>
              <label
                >规格下限 mm<el-input-number
                  v-model="row.size_min"
                  :min="0"
                  :controls="false"
              /></label>
              <label
                >规格上限 mm<el-input-number
                  v-model="row.size_max"
                  :min="0"
                  :controls="false"
              /></label>
            </div>
            <p v-if="row.source?.range" class="field-help">
              来源：{{ row.source.file }} / {{ row.source.range }}
            </p>
          </div>
          <el-button @click="add('materials')">添加材料规则</el-button>
        </el-tab-pane>
        <el-tab-pane label="毛坯规则" name="stock">
          <p class="field-help">
            固定规则：每个模型净尺寸加 5 mm，再向上取到 5 mm 的整数倍。
          </p>
          <p>例如：24 → 30 mm，90 → 95 mm，41.5 → 50 mm。</p>
          <p class="field-help">
            解析完成后自动补齐空白毛坯尺寸，不覆盖已有数值；与其他参数的自动补齐开关无关。
            当前按长方体毛坯核算，仍需核对采购规格。
          </p>
        </el-tab-pane>
      </el-tabs>
    </div>
    <template #footer
      ><span v-if="dirty" class="field-help">有未保存修改</span
      ><el-button :disabled="loading" @click="open = false">{{
        dirty ? "放弃修改" : "关闭"
      }}</el-button
      ><el-button type="primary" :loading="loading" @click="save"
        >保存规则</el-button
      ></template
    >
  </el-dialog>
</template>

<style scoped>
.rules-editor {
  max-height: 62vh;
  padding-right: 8px;
  overflow: auto;
}

.rule-row {
  padding: 16px 0;
  border-top: 1px solid #dce2e7;
}

.rule-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 8px;
}

.rule-toolbar b {
  margin-right: auto;
}

.rules-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 20px;
  margin: 12px 0;
}

.process-add {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-top: 20px;
}

.rules-grid.three {
  grid-template-columns: repeat(3, 1fr);
}

.rules-grid > label,
.allowance-field {
  display: flex;
  flex-direction: column;
  gap: 7px;
  font-size: 12px;
  color: #536978;
}

.el-input-number {
  width: 100%;
}

.allowance-field {
  max-width: 350px;
}

@media (width <= 650px) {
  .rules-grid,
  .rules-grid.three {
    grid-template-columns: 1fr;
  }
}
</style>
