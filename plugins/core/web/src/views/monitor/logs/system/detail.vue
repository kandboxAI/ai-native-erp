<script setup lang="tsx">
import { computed } from "vue";
import "vue-json-pretty/lib/styles.css";
import VueJsonPretty from "vue-json-pretty";

const props = defineProps({
  data: {
    type: Array,
    default: () => []
  }
});

const row = computed(() => (props.data[0] as Record<string, any>) || {});

const columns = [
  {
    label: "IP 地址",
    prop: "ip"
  },
  {
    label: "操作人员",
    prop: "username"
  },
  {
    label: "所属模块",
    prop: "module"
  },
  {
    label: "请求时间",
    prop: "requestTime"
  },
  {
    label: "请求方法",
    prop: "method"
  },
  {
    label: "请求接口",
    prop: "url",
    copy: true
  }
];

const dataList = computed(() => [
  {
    title: "操作内容",
    name: "content",
    data: {
      content: row.value.content || "",
      action: row.value.action || "",
      target_type: row.value.targetType || "",
      target_id: row.value.targetId || "",
      is_agent_action: Boolean(row.value.isAgentAction)
    }
  }
]);
</script>

<template>
  <div>
    <el-scrollbar>
      <PureDescriptions border :data="[row]" :columns="columns" :column="3" />
    </el-scrollbar>
    <el-tabs :modelValue="'content'" type="border-card" class="mt-4">
      <el-tab-pane
        v-for="(item, index) in dataList"
        :key="index"
        :name="item.name"
        :label="item.title"
      >
        <el-scrollbar max-height="calc(100vh - 240px)">
          <vue-json-pretty v-model:data="item.data" />
        </el-scrollbar>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
