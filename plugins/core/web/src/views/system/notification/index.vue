<template>
  <ReListPresentation>
  <div class="sys-module sys-page list-page list-presentation-container">
    <section class="list-section">
      <ReMenuViews v-model="mainTab" class="center-tabs list-tabs" @tab-change="onMainTab">
        <!-- 场景配置 -->
        <el-tab-pane label="场景配置" name="scenes">
          <ReListHeading data-list-key="index-0">
            <template #title>场景配置</template>
          </ReListHeading>
          <section class="list-query-panel">
            <div class="filter-panel list-filters">
              <el-form
                :model="sceneQuery"
                label-position="top"
                class="query-form"
              >
                <div class="filter-row">
                  <el-form-item label="关键词">
                    <el-input
                      v-model="sceneQuery.keyword"
                      clearable
                      placeholder="请输入场景标识/名称"
                    />
                  </el-form-item>
                  <el-form-item label="模块">
                    <el-select
                      v-model="sceneQuery.module_code"
                      clearable
                      placeholder="请选择模块"
                      style="width: 100%"
                    >
                      <el-option
                        v-for="item in moduleOptions"
                        :key="item.value"
                        :label="item.label"
                        :value="item.value"
                      />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="启用状态">
                    <el-select
                      v-model="sceneQuery.is_active"
                      placeholder="请选择启用状态"
                      clearable
                      style="width: 100%"
                    >
                      <el-option label="启用" :value="true" />
                      <el-option label="停用" :value="false" />
                    </el-select>
                  </el-form-item>
                  <div class="query-actions">
                    <el-button
                      data-list-query="search"
                      class="search-btn"
                      @click="searchScenes"
                      >搜索</el-button
                    >
                    <el-button
                      data-list-query="reset"
                      class="reset-btn"
                      @click="resetSceneQuery"
                      >重置</el-button
                    >
                  </div>
                </div>
              </el-form>
            </div>
            <div class="table-panel list-section">
              <ReListTable
                :list-heading="false"
                list-key="index-0"
                :list-refresh="loadScenes"
                v-loading="sceneLoading"
                :data="sceneRows"
                row-key="id"
                class="data-table"
              >
                <el-table-column
                  prop="scene_key"
                  label="场景标识"
                  min-width="210"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="scene_name"
                  label="场景名称"
                  min-width="150"
                  show-overflow-tooltip
                />
                <el-table-column prop="module_code" label="模块" width="100">
                  <template #default="{ row }">{{
                    moduleLabel(row.module_code)
                  }}</template>
                </el-table-column>
                <el-table-column
                  prop="severity_code"
                  label="重要程度"
                  width="96"
                  align="center"
                >
                  <template #default="{ row }">
                    <el-tag :type="severityTag(row.severity_code)" size="small">{{
                      severityLabel(row.severity_code)
                    }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="渠道" min-width="200">
                  <template #default="{ row }">
                    <el-tag
                      v-for="code in row.channel_codes"
                      :key="code"
                      size="small"
                      class="channel-tag"
                      >{{ channelLabel(code) }}</el-tag
                    >
                    <span v-if="!row.channel_codes.length" class="muted-text"
                      >未启用</span
                    >
                  </template>
                </el-table-column>
                <el-table-column
                  prop="is_active"
                  label="状态"
                  width="80"
                  align="center"
                >
                  <template #default="{ row }">
                    <el-tag
                      :type="row.is_active ? 'success' : 'info'"
                      size="small"
                      >{{ row.is_active ? "启用" : "停用" }}</el-tag
                    >
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="150" fixed="right">
                  <template #default="{ row }">
                    <span class="action-text success" @click="openEdit(row.id)"
                      >配置</span
                    >
                    <span
                      class="action-text danger"
                      @click="removeScene(row as NotificationSceneRow)"
                      >删除</span
                    >
                  </template>
                </el-table-column>

                <template #list-actions
                  ><div class="header-actions">
                    <el-button
                      data-list-action="create"
                      data-action="primary"
                      v-if="mainTab === 'scenes'"
                      type="primary"
                      :icon="Plus"
                      @click="openCreate"
                      >新增场景</el-button
                    >
                    <el-button
                      data-action="primary"
                      v-if="mainTab === 'logs' && logTab === 'delivery'"
                      type="primary"
                      :icon="Promotion"
                      :loading="sending"
                      @click="sendPending"
                      >投递待发送消息</el-button
                    >

                  </div></template
                >

                <template #list-pagination
                  ><div class="table-footer">

                    <ReListPagination
                      v-model:current-page="sceneQuery.page"
                      v-model:page-size="sceneQuery.page_size"
                      :total="sceneTotal"
                      @current-change="loadScenes"
                    /></div
                ></template>
              </ReListTable>
            </div>
          </section>
        </el-tab-pane>

        <!-- 通知历史 -->
        <el-tab-pane label="通知历史" name="history">
          <ReListHeading data-list-key="index-1">
            <template #title>通知历史</template>
          </ReListHeading>
          <section class="list-query-panel">
            <div class="filter-panel list-filters">
              <el-form
                :model="historyQuery"
                label-position="top"
                class="query-form"
              >
                <div class="filter-row history-filter-row">
                  <el-form-item label="关键词">
                    <el-input
                      v-model="historyQuery.keyword"
                      clearable
                      placeholder="请输入标题/内容/事件键"
                    />
                  </el-form-item>
                  <el-form-item label="场景">
                    <el-select
                      v-model="historyQuery.scene_id"
                      clearable
                      filterable
                      placeholder="请选择场景"
                      style="width: 100%"
                    >
                      <el-option
                        v-for="item in allScenes"
                        :key="item.id"
                        :label="item.scene_name"
                        :value="item.id"
                      />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="重要程度">
                    <el-select
                      v-model="historyQuery.severity_code"
                      clearable
                      placeholder="请选择重要程度"
                      style="width: 100%"
                    >
                      <el-option
                        v-for="item in severityOptions"
                        :key="item.value"
                        :label="item.label"
                        :value="item.value"
                      />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="业务类型">
                    <el-input
                      v-model="historyQuery.business_type_code"
                      clearable
                      placeholder="如 request_review"
                    />
                  </el-form-item>
                  <div class="query-actions">
                    <el-button
                      data-list-query="search"
                      class="search-btn"
                      @click="searchHistory"
                      >搜索</el-button
                    >
                    <el-button
                      data-list-query="reset"
                      class="reset-btn"
                      @click="resetHistory"
                      >重置</el-button
                    >
                  </div>
                </div>
              </el-form>
            </div>
            <div class="table-panel list-section">
              <ReListTable
                :list-heading="false"
                list-key="index-1"
                :list-refresh="loadHistory"
                v-loading="historyLoading"
                :data="historyRows"
                row-key="id"
                class="data-table"
              >
                <el-table-column
                  prop="title"
                  label="标题"
                  min-width="180"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="scene_name_snapshot"
                  label="场景"
                  min-width="130"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="severity_code"
                  label="重要程度"
                  width="96"
                  align="center"
                >
                  <template #default="{ row }">
                    <el-tag :type="severityTag(row.severity_code)" size="small">{{
                      severityLabel(row.severity_code)
                    }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="read_count"
                  label="阅读"
                  width="130"
                  align="center"
                >
                  <template #default="{ row }">
                    {{ row.read_count }}/{{ row.recipient_count }}
                  </template>
                </el-table-column>
                <el-table-column
                  prop="delivery_stats"
                  label="外部渠道"
                  min-width="200"
                >
                  <template #default="{ row }">{{
                    deliverySummary(row.delivery_stats)
                  }}</template>
                </el-table-column>
                <el-table-column
                  prop="occurred_at"
                  label="发生时间"
                  width="170"
                />
                <el-table-column label="操作" width="150" fixed="right">
                  <template #default="{ row }">
                    <span
                      class="action-text primary"
                      @click="openRecipients(row as NotificationHistoryRow)"
                      >接收人</span
                    >
                    <span
                      class="action-text success"
                      @click="viewDeliveries(row as NotificationHistoryRow)"
                      >投递</span
                    >
                  </template>
                </el-table-column>

                <template #list-actions
                  ><div class="header-actions">
                    <el-button
                      data-list-action="create"
                      data-action="primary"
                      v-if="mainTab === 'scenes'"
                      type="primary"
                      :icon="Plus"
                      @click="openCreate"
                      >新增场景</el-button
                    >
                    <el-button
                      data-action="primary"
                      v-if="mainTab === 'logs' && logTab === 'delivery'"
                      type="primary"
                      :icon="Promotion"
                      :loading="sending"
                      @click="sendPending"
                      >投递待发送消息</el-button
                    >

                  </div></template
                >

                <template #list-pagination
                  ><div class="table-footer">

                    <ReListPagination
                      v-model:current-page="historyQuery.page"
                      v-model:page-size="historyQuery.page_size"
                      :total="historyTotal"
                      @current-change="loadHistory"
                    /></div
                ></template>
              </ReListTable>
            </div>
          </section>
        </el-tab-pane>

        <el-tab-pane label="家校回执" name="receipts">
          <div class="table-wrap list-section">
            <p class="muted-text receipt-hint">
              这里查看已经发出的家校通知。请假、课表和成绩会自动出现；缺勤、学业预警和安全事件要在对应页面点「通知家长」。
              站内送达不表示家长已查看；请假和成绩的收件人也可能包含学生或教职工。补发仅新增收件人，重试仅处理失败的外部投递。
            </p>
            <ReListTable
              list-key="index-2"
              :list-refresh="loadReceipts"
              v-loading="receiptLoading"
              :data="receiptRows"
            >
              <el-table-column prop="occurred_at" label="时间" width="170" />
              <el-table-column prop="scene_name" label="场景" width="150" />
              <el-table-column prop="student_name" label="学生" width="100" />
              <el-table-column prop="class_name" label="班级" width="120" />
              <el-table-column prop="title" label="标题" min-width="160" />
              <el-table-column prop="delivery" label="站内送达" width="150">
                <template #default="{ row }">{{ row.delivery }}</template>
              </el-table-column>
              <el-table-column prop="read_count" label="收件人已读" min-width="180">
                <template #default="{ row }"
                  ><span v-if="row.reading_summary">{{ row.reading_summary }}</span><span v-else>{{ row.read_count }}/{{ row.recipient_count }}</span><el-button v-if="row.has_reading_details" link type="primary" @click="openReadingDetails(row.id)">阅读明细 / 跟进</el-button></template
                >
              </el-table-column>
              <el-table-column
                prop="external_sent_count"
                label="外部渠道投递"
                min-width="180"
              >
                <template #default="{ row }">
                  成功 {{ row.external_sent_count }} / 待发
                  {{ row.external_pending_count }} / 失败
                  {{ row.external_failed_count }}
                </template>
              </el-table-column>
              <el-table-column
                prop="requires_confirmation"
                label="家长确认"
                width="110"
              >
                <template #default="{ row }">
                  {{
                    row.requires_confirmation
                      ? `${row.confirmed_count}/${row.recipient_count}`
                      : "不需要"
                  }}
                </template>
              </el-table-column>
              <el-table-column
                prop="task_result"
                label="电话联系"
                min-width="140"
              >
                <template #default="{ row }">
                  <span v-if="!row.task_status">—</span>
                  <span v-else-if="row.task_status === 'closed'"
                    >已完成：{{ row.task_result || "家长已确认" }}</span
                  >
                  <span v-else>{{
                    row.task_reason === "unbound"
                      ? "未绑定家长或无可用账号"
                      : "逾期未确认"
                  }}</span>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="180" fixed="right">
                <template #default="{ row }">
                  <el-button
                    data-action="primary"
                    v-if="row.can_resend"
                    link
                    type="primary"
                    :disabled="receiptSaving"
                    @click="resendReceipt(row as FamilyReceipt)"
                    >补发 / 重试</el-button
                  >
                  <el-button
                    data-action="primary"
                    v-if="row.can_close_task"
                    link
                    type="primary"
                    :disabled="receiptSaving"
                    @click="closeReceiptTask(row as FamilyReceipt)"
                    >记录联系</el-button
                  >
                </template>
              </el-table-column>

              <template #list-title>家校回执</template>

              <template #list-actions
                ><div class="header-actions">
                  <el-button
                    data-list-action="create"
                    data-action="primary"
                    v-if="mainTab === 'scenes'"
                    type="primary"
                    :icon="Plus"
                    @click="openCreate"
                    >新增场景</el-button
                  >
                  <el-button
                    data-action="primary"
                    v-if="mainTab === 'logs' && logTab === 'delivery'"
                    type="primary"
                    :icon="Promotion"
                    :loading="sending"
                    @click="sendPending"
                    >投递待发送消息</el-button
                  >

                </div></template
              >

              <template #list-pagination
                ><div class="table-footer">

                  <ReListPagination
                    v-model:current-page="receiptPage"
                    :page-size="20"
                    :total="receiptTotal"
                    @current-change="loadReceipts"
                  /></div
              ></template>
            </ReListTable>
          </div>
        </el-tab-pane>

        <!-- 日志排查 -->
        <el-tab-pane label="日志排查" name="logs">
          <ReMenuViews view-key="menuSubView" v-model="logTab" @tab-change="loadLogs">
            <el-tab-pane label="投递日志" name="delivery">
              <ReListHeading data-list-key="index-3">
                <template #title>投递日志</template>
              </ReListHeading>
              <section class="list-query-panel">
                <div class="filter-panel list-filters">
                  <el-form
                    :model="deliveryQuery"
                    label-position="top"
                    class="query-form"
                  >
                    <div class="filter-row log-filter-row">
                      <el-form-item label="关键词">
                        <el-input
                          v-model="deliveryQuery.keyword"
                          clearable
                          placeholder="请输入标题/接收人/openid/错误"
                        />
                      </el-form-item>
                      <el-form-item label="渠道">
                        <el-select
                          v-model="deliveryQuery.channel_code"
                          clearable
                          placeholder="请选择渠道"
                          style="width: 100%"
                        >
                          <el-option
                            v-for="item in channelOptions"
                            :key="item.value"
                            :label="item.label"
                            :value="item.value"
                          />
                        </el-select>
                      </el-form-item>
                      <el-form-item label="投递状态">
                        <el-select
                          v-model="deliveryQuery.status_code"
                          clearable
                          placeholder="请选择投递状态"
                          style="width: 100%"
                        >
                          <el-option
                            v-for="item in deliveryStatusOptions"
                            :key="item.value"
                            :label="item.label"
                            :value="item.value"
                          />
                        </el-select>
                      </el-form-item>
                      <el-form-item label="通知">
                        <el-input
                          v-model="deliveryQuery.notification_id"
                          clearable
                          placeholder="请输入通知 ID"
                        />
                      </el-form-item>
                      <div class="query-actions">
                        <el-button
                          data-list-query="search"
                          class="search-btn"
                          @click="searchDelivery"
                          >搜索</el-button
                        >
                        <el-button
                          data-list-query="reset"
                          class="reset-btn"
                          @click="resetDelivery"
                          >重置</el-button
                        >
                      </div>
                    </div>
                  </el-form>
                </div>
                <div class="table-panel list-section">
                  <ReListTable
                    :list-heading="false"
                    list-key="index-3"
                    :list-refresh="loadDelivery"
                    v-loading="deliveryLoading"
                    :data="deliveryRows"
                    row-key="id"
                    class="data-table"
                  >
                    <el-table-column
                      prop="title"
                      label="通知"
                      min-width="160"
                      show-overflow-tooltip
                    />
                    <el-table-column
                      prop="display_name"
                      label="接收人"
                      width="120"
                      show-overflow-tooltip
                    />
                    <el-table-column prop="channel_code" label="渠道" width="120">
                      <template #default="{ row }">{{
                        channelLabel(row.channel_code)
                      }}</template>
                    </el-table-column>
                    <el-table-column
                      prop="status_code"
                      label="状态"
                      width="90"
                      align="center"
                    >
                      <template #default="{ row }">
                        <el-tag
                          :type="deliveryStatusTag(row.status_code)"
                          size="small"
                          >{{ deliveryStatusLabel(row.status_code) }}</el-tag
                        >
                      </template>
                    </el-table-column>
                    <el-table-column
                      prop="target_address"
                      label="投递地址"
                      min-width="150"
                      show-overflow-tooltip
                    />
                    <el-table-column
                      prop="error_message"
                      label="错误信息"
                      min-width="160"
                      show-overflow-tooltip
                    />
                    <el-table-column prop="created_at" label="时间" width="170" />
                    <el-table-column label="操作" width="80" fixed="right">
                      <template #default="{ row }">
                        <span
                          class="action-text primary"
                          @click="showJson('投递报文', row)"
                          >报文</span
                        >
                      </template>
                    </el-table-column>

                    <template #list-actions
                      ><div class="header-actions">
                        <el-button
                          data-list-action="create"
                          data-action="primary"
                          v-if="mainTab === 'scenes'"
                          type="primary"
                          :icon="Plus"
                          @click="openCreate"
                          >新增场景</el-button
                        >
                        <el-button
                          data-action="primary"
                          v-if="mainTab === 'logs' && logTab === 'delivery'"
                          type="primary"
                          :icon="Promotion"
                          :loading="sending"
                          @click="sendPending"
                          >投递待发送消息</el-button
                        >

                      </div></template
                    >

                    <template #list-pagination
                      ><div class="table-footer">

                        <ReListPagination
                          v-model:current-page="deliveryQuery.page"
                          v-model:page-size="deliveryQuery.page_size"
                          :total="deliveryTotal"
                          @current-change="loadDelivery"
                        /></div
                    ></template>
                  </ReListTable>
                </div>
              </section>
            </el-tab-pane>

            <el-tab-pane label="事件日志" name="event">
              <ReListHeading data-list-key="index-4">
                <template #title>事件日志</template>
              </ReListHeading>
              <section class="list-query-panel">
                <div class="filter-panel list-filters">
                  <el-form
                    :model="eventQuery"
                    label-position="top"
                    class="query-form"
                  >
                    <div class="filter-row log-filter-row">
                      <el-form-item label="关键词">
                        <el-input
                          v-model="eventQuery.keyword"
                          clearable
                          placeholder="请输入场景/说明/内容"
                        />
                      </el-form-item>
                      <el-form-item label="场景">
                        <el-select
                          v-model="eventQuery.scene_id"
                          clearable
                          filterable
                          placeholder="请选择场景"
                          style="width: 100%"
                        >
                          <el-option
                            v-for="item in allScenes"
                            :key="item.id"
                            :label="item.scene_name"
                            :value="item.id"
                          />
                        </el-select>
                      </el-form-item>
                      <el-form-item label="处理结果">
                        <el-select
                          v-model="eventQuery.status_code"
                          clearable
                          placeholder="请选择处理结果"
                          style="width: 100%"
                        >
                          <el-option label="已处理" value="processed" />
                          <el-option label="已跳过" value="skipped" />
                          <el-option label="失败" value="failed" />
                        </el-select>
                      </el-form-item>
                      <el-form-item label="业务类型">
                        <el-input
                          v-model="eventQuery.business_type_code"
                          clearable
                        />
                      </el-form-item>
                      <div class="query-actions">
                        <el-button
                          data-list-query="search"
                          class="search-btn"
                          @click="searchEvent"
                          >搜索</el-button
                        >
                        <el-button
                          data-list-query="reset"
                          class="reset-btn"
                          @click="resetEvent"
                          >重置</el-button
                        >
                      </div>
                    </div>
                  </el-form>
                </div>
                <div class="table-panel list-section">
                  <ReListTable
                    :list-heading="false"
                    list-key="index-4"
                    :list-refresh="loadEvent"
                    v-loading="eventLoading"
                    :data="eventRows"
                    row-key="id"
                    class="data-table"
                  >
                    <el-table-column
                      prop="scene_key"
                      label="场景"
                      min-width="200"
                      show-overflow-tooltip
                    />
                    <el-table-column
                      prop="status_code"
                      label="结果"
                      width="90"
                      align="center"
                    >
                      <template #default="{ row }">
                        <el-tag
                          :type="
                            row.status_code === 'processed'
                              ? 'success'
                              : row.status_code === 'failed'
                                ? 'danger'
                                : 'info'
                          "
                          size="small"
                          >{{ eventStatusLabel(row.status_code) }}</el-tag
                        >
                      </template>
                    </el-table-column>
                    <el-table-column prop="message" label="说明" min-width="150">
                      <template #default="{ row }">{{
                        skippedReasonLabel(row.message)
                      }}</template>
                    </el-table-column>
                    <el-table-column
                      prop="business_type_code"
                      label="业务类型"
                      width="130"
                    />
                    <el-table-column prop="created_at" label="时间" width="170" />
                    <el-table-column label="操作" width="80" fixed="right">
                      <template #default="{ row }">
                        <span
                          class="action-text primary"
                          @click="showJson('事件内容', row.payload)"
                          >内容</span
                        >
                      </template>
                    </el-table-column>

                    <template #list-actions
                      ><div class="header-actions"></div
                    ></template>

                    <template #list-pagination
                      ><div class="table-footer">

                        <ReListPagination
                          v-model:current-page="eventQuery.page"
                          v-model:page-size="eventQuery.page_size"
                          :total="eventTotal"
                          @current-change="loadEvent"
                        /></div
                    ></template>
                  </ReListTable>
                </div>
              </section>
            </el-tab-pane>
          </ReMenuViews>
        </el-tab-pane>
      </ReMenuViews>
    </section>

    <!-- 场景配置弹窗 -->
    <el-dialog
      v-model="sceneDialogVisible"
      :title="editingSceneId ? '配置通知场景' : '新增通知场景'"
      width="980px"
      destroy-on-close
    >
      <el-tabs v-model="dialogTab">
        <el-tab-pane label="场景" name="scene">
          <el-form label-position="top">
            <div class="scene-grid">
              <el-form-item label="场景标识" required>
                <el-input
                  v-model="sceneForm.scene_key"
                  maxlength="128"
                  placeholder="由代码定义，如 request_review.approved"
                />
              </el-form-item>
              <el-form-item label="场景名称" required>
                <el-input v-model="sceneForm.scene_name" maxlength="128" />
              </el-form-item>
              <el-form-item label="所属模块" required>
                <el-select v-model="sceneForm.module_code" style="width: 100%">
                  <el-option
                    v-for="item in moduleOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="重要程度">
                <el-select
                  v-model="sceneForm.severity_code"
                  style="width: 100%"
                >
                  <el-option
                    v-for="item in severityOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="渠道降级">
                <el-select
                  v-model="sceneForm.fallback_policy_code"
                  style="width: 100%"
                >
                  <el-option label="不降级" value="none" />
                  <el-option label="外部渠道不可达时发站内信" value="all" />
                </el-select>
              </el-form-item>
              <el-form-item label="启用">
                <el-switch v-model="sceneForm.is_active" />
              </el-form-item>
            </div>
            <el-form-item label="说明">
              <el-input
                v-model="sceneForm.description"
                type="textarea"
                :rows="2"
              />
            </el-form-item>
            <el-form-item label="启用渠道">
              <el-checkbox-group v-model="sceneForm.channel_codes">
                <el-checkbox
                  v-for="item in channelOptions"
                  :key="item.value"
                  :value="item.value"
                  >{{ item.label }}</el-checkbox
                >
              </el-checkbox-group>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="模板" name="templates">
          <el-alert
            type="info"
            :closable="false"
            class="route-policy-alert"
            title="模板用 {字段} 引用发送时的 payload，如 {title}、{applicant_label}；微信模板需填写模板编号与字段映射（模板字段 → payload 字段）。"
          />
          <div class="template-grid">
            <div
              v-for="tpl in sceneTemplates"
              :key="tpl.channel_code"
              class="template-panel"
            >
              <div class="panel-title">
                {{ channelLabel(tpl.channel_code) }}
                <el-switch v-model="tpl.is_active" size="small" />
              </div>
              <el-form label-position="top">
                <el-form-item label="标题模板">
                  <el-input v-model="tpl.title_template" maxlength="512" />
                </el-form-item>
                <el-form-item label="内容模板">
                  <el-input
                    v-model="tpl.content_template"
                    type="textarea"
                    :rows="3"
                  />
                </el-form-item>
                <template v-if="isExternal(tpl.channel_code)">
                  <el-form-item label="微信模板编号">
                    <el-input v-model="tpl.wechat_template_no" />
                  </el-form-item>
                  <el-form-item label="字段映射（JSON）">
                    <el-input
                      v-model="tpl.mapping_text"
                      type="textarea"
                      :rows="3"
                      placeholder='{"thing1": "title", "time2": "occurred_at"}'
                    />
                  </el-form-item>
                </template>
              </el-form>
            </div>
            <div v-if="!sceneTemplates.length" class="muted-text">
              请先在“场景”中启用渠道
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane label="接收人路由" name="routes">
          <el-alert
            type="info"
            :closable="false"
            class="route-policy-alert"
            title="接收人 = 发送时指定的用户 ∪ 路由解析结果。建议按权限或业务相关人配置；业务相关人标识由业务代码在发送时给出（如 applicant、reviewer）。"
          />
          <div class="route-toolbar">
            <el-button data-list-action="create" :icon="Plus" @click="addRoute"
              >添加路由</el-button
            >
          </div>
          <ReListTable
            list-key="index-5"
            :list-controls="false"
            :data="sceneForm.routes"
            class="route-table"
          >
            <el-table-column label="对象类型" width="140">
              <template #default="{ row }">
                <el-select
                  v-model="row.target_type_code"
                  @change="() => resetRouteTarget(row as RouteForm)"
                >
                  <el-option
                    v-for="item in targetTypeOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                  />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="接收对象" min-width="260">
              <template #default="{ row }">
                <el-select
                  v-if="row.target_type_code === 'permission'"
                  v-model="row.permission_id"
                  filterable
                  placeholder="选择权限"
                  style="width: 100%"
                >
                  <el-option
                    v-for="item in routeOptions.permissions"
                    :key="item.id"
                    :label="`${item.permission_name}（${item.permission_key}）`"
                    :value="item.id"
                  />
                </el-select>
                <el-select
                  v-else-if="row.target_type_code === 'role'"
                  v-model="row.role_id"
                  filterable
                  placeholder="选择角色"
                  style="width: 100%"
                >
                  <el-option
                    v-for="item in routeOptions.roles"
                    :key="item.id"
                    :label="item.role_name"
                    :value="item.id"
                  />
                </el-select>
                <el-select
                  v-else-if="row.target_type_code === 'user'"
                  v-model="row.user_id"
                  filterable
                  remote
                  :remote-method="searchUsers"
                  placeholder="输入姓名搜索"
                  style="width: 100%"
                >
                  <el-option
                    v-for="item in userOptions"
                    :key="item.id"
                    :label="item.display_name"
                    :value="item.id"
                  />
                </el-select>
                <el-input
                  v-else-if="row.target_type_code === 'actor'"
                  v-model="row.actor_key"
                  placeholder="业务相关人标识，如 applicant"
                />
                <span v-else class="muted-text">全部有效用户</span>
              </template>
            </el-table-column>
            <el-table-column label="组织范围" width="170">
              <template #default="{ row }">
                <el-select v-model="row.org_scope_code">
                  <el-option label="不限" value="none" />
                  <el-option label="事件所属组织" value="event_organization" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="启用" width="70" align="center">
              <template #default="{ row }">
                <el-switch v-model="row.is_active" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="70">
              <template #default="{ $index }">
                <span
                  class="action-text danger"
                  @click="sceneForm.routes.splice($index, 1)"
                  >删除</span
                >
              </template>
            </el-table-column>
          </ReListTable>
        </el-tab-pane>
      </el-tabs>
      <template #footer>
        <el-button data-action="primary" type="primary" :loading="saving" @click="saveScene"
          >保存</el-button
        >
        <el-button data-action="neutral" class="btn-cancel" @click="sceneDialogVisible = false"
          >取消</el-button
        >
      </template>
    </el-dialog>

    <!-- 接收人 -->
    <el-dialog
      v-model="recipientVisible"
      title="接收人"
      width="640px"
      destroy-on-close
    >
      <ReListTable
        list-key="index-6"
        :list-controls="false"
        :list-refresh="loadRecipients"
        v-loading="recipientLoading"
        :data="recipientRows"
        height="360"
      >
        <el-table-column prop="display_name" label="人员" min-width="160" />
        <el-table-column
          prop="status_code"
          label="状态"
          width="90"
          align="center"
        >
          <template #default="{ row }">{{
            recipientStatusLabel(row.status_code)
          }}</template>
        </el-table-column>
        <el-table-column prop="read_at" label="阅读时间" width="170" />
      </ReListTable>
      <div class="table-footer">
        <ReListPagination
          v-model:current-page="recipientPage"
          :page-size="20"
          :total="recipientTotal"
          @current-change="loadRecipients"
        />
      </div>
    </el-dialog>

    <el-dialog v-model="jsonVisible" :title="jsonTitle" width="720px">
      <pre class="json-detail">{{ jsonText }}</pre>
    </el-dialog>
  </div>

  <el-dialog v-model="readingVisible" title="阅读明细与跟进" width="min(900px, 96vw)">
    <div v-loading="readingLoading">
      <el-alert v-if="readingError" :title="readingError" type="error" :closable="false" />
      <p>{{ readingData?.reading_summary }}</p>
      <el-checkbox v-model="readingFollowup">仅显示需要跟进的记录</el-checkbox>
      <el-table :data="readingData?.reading_details.filter(p => !readingFollowup || p.needs_followup) || []">
        <el-table-column prop="context_name" label="关联对象" />
        <el-table-column prop="recipient_name" label="接收人" />
        <el-table-column prop="audience_name" label="接收身份" />
        <el-table-column prop="status" label="阅读状态" />
        <el-table-column label="首次阅读时间" min-width="180"><template #default="{ row }">{{ row.read_at ? new Date(row.read_at).toLocaleString('zh-CN', { hour12: false }) : '—' }}</template></el-table-column>
      </el-table>
    </div>
  </el-dialog>
  </ReListPresentation>
</template>

<script setup lang="ts">
import { familyReadingDetails, type ReadingDetails } from "@/api/notificationCenter";
import { useMenuNavigation, useMenuView } from "@/utils/menuView";
import { useRoute } from "vue-router";
import { getDictionaryOptions } from "@/api/systemDictionary";
import { Plus, Promotion } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onMounted, reactive, ref, watch } from "vue";
import {
  createNotificationScene,
  deleteNotificationScene,
  getNotificationRouteOptions,
  getNotificationSceneConfig,
  listNotificationDeliveryLogs,
  listNotificationEventLogs,
  listNotificationHistory,
  listNotificationRecipients,
  listNotificationScenes,
  listFamilyReceipts,
  resendFamilyNotice,
  closeFamilyContact,
  searchNotificationRouteUsers,
  sendPendingDeliveries,
  updateNotificationScene,
  type NotificationChannel,
  type NotificationDeliveryLogRow,
  type NotificationDeliveryStatus,
  type NotificationEventLogRow,
  type NotificationHistoryRow,
  type NotificationRecipientRow,
  type NotificationRouteOptions,
  type NotificationRouteRow,
  type NotificationSceneConfig,
  type NotificationSceneRow,
  type NotificationSeverity,
  type FamilyReceipt
} from "@/api/notificationCenter";

defineOptions({ name: "NotificationCenter" });

type TemplateForm = {
  channel_code: NotificationChannel;
  title_template: string;
  content_template: string;
  wechat_template_no: string;
  mapping_text: string;
  is_active: boolean;
};
type RouteForm = Omit<
  NotificationRouteRow,
  "id" | "scene_id" | "role" | "user" | "permission"
>;

getDictionaryOptions(["sys_module"])
  .then(response => {
    if (response.code === 0)
      moduleOptions.value = (response.data.sys_module || []).map(item => ({
        value: item.item_code,
        label: item.item_name
      }));
  })
  .catch(() => undefined);
const moduleOptions = ref<{ value: string; label: string }[]>([]);
const severityOptions: Array<{ value: NotificationSeverity; label: string }> = [
  { value: "normal", label: "普通" },
  { value: "important", label: "重要" },
  { value: "urgent", label: "紧急" }
];
const channelOptions: Array<{ value: NotificationChannel; label: string }> = [
  { value: "in_app", label: "站内信" },
  { value: "wechat_service", label: "微信服务号" },
  { value: "wechat_miniapp_subscribe", label: "小程序订阅消息" }
];
const deliveryStatusOptions: Array<{
  value: NotificationDeliveryStatus;
  label: string;
}> = [
  { value: "pending", label: "待发送" },
  { value: "sent", label: "已发送" },
  { value: "failed", label: "失败" },
  { value: "skipped", label: "已跳过" }
];
const targetTypeOptions = [
  { value: "permission", label: "权限" },
  { value: "actor", label: "业务相关人" },
  { value: "user", label: "用户" },
  { value: "role", label: "角色" },
  { value: "all", label: "全部用户" }
];

const mainTab = useMenuView("scenes", ["scenes","history","receipts","logs"]);
const logTab = useMenuView("delivery", ["delivery", "event"], "menuSubView");
const menuContext = { ...useRoute().query };
const navigateMenu = useMenuNavigation();

function labelOf(options: Array<{ value: string; label: string }>, v: string) {
  return options.find(item => item.value === v)?.label ?? v;
}
const moduleLabel = (v: string) => labelOf(moduleOptions.value, v);
const severityLabel = (v: string) => labelOf(severityOptions, v);
const channelLabel = (v: string) => labelOf(channelOptions, v);
const deliveryStatusLabel = (v: string) => labelOf(deliveryStatusOptions, v);
const severityTag = (v: string) =>
  v === "urgent" ? "danger" : v === "important" ? "warning" : "info";
const deliveryStatusTag = (
  v: string
): "success" | "danger" | "warning" | "info" =>
  v === "sent"
    ? "success"
    : v === "failed"
      ? "danger"
      : v === "pending"
        ? "warning"
        : "info";
const isExternal = (code: string) =>
  code === "wechat_service" || code === "wechat_miniapp_subscribe";
const eventStatusLabel = (v: string) =>
  ({ processed: "已处理", skipped: "已跳过", failed: "失败" })[v] ?? v;
const recipientStatusLabel = (v: string) =>
  ({ unread: "未读", read: "已读", archived: "仅外部渠道" })[v] ?? v;
function skippedReasonLabel(v: string | null) {
  if (!v) return "—";
  return (
    {
      scene_not_configured: "场景未配置",
      scene_disabled: "场景已停用",
      duplicate_event: "重复事件",
      no_recipients: "没有接收人"
    }[v] ?? v
  );
}
function deliverySummary(stats: Record<string, Record<string, number>>) {
  const parts = Object.entries(stats ?? {})
    .filter(([channel]) => channel !== "in_app")
    .map(([channel, byStatus]) => {
      const detail = Object.entries(byStatus)
        .map(([s, n]) => `${deliveryStatusLabel(s)}${n}`)
        .join(" ");
      return `${channelLabel(channel)}：${detail}`;
    });
  return parts.join("；") || "—";
}

// ───────── 场景列表 ─────────
const sceneQuery = reactive({
  page: 1,
  page_size: 20,
  keyword: "",
  module_code: "" as string,
  is_active: undefined as boolean | undefined
});
const sceneRows = ref<NotificationSceneRow[]>([]);
const sceneTotal = ref(0);
const sceneLoading = ref(false);
const allScenes = ref<NotificationSceneRow[]>([]);

async function loadScenes() {
  sceneLoading.value = true;
  try {
    const res = await listNotificationScenes({
      page: sceneQuery.page,
      page_size: sceneQuery.page_size,
      keyword: sceneQuery.keyword.trim() || undefined,
      module_code: sceneQuery.module_code || undefined,
      is_active: sceneQuery.is_active
    });
    sceneRows.value = res.data.items ?? [];
    sceneTotal.value = res.data.total ?? 0;
  } finally {
    sceneLoading.value = false;
  }
}
async function loadAllScenes() {
  const res = await listNotificationScenes({ page: 1, page_size: 100 });
  allScenes.value = res.data.items ?? [];
}
function searchScenes() {
  sceneQuery.page = 1;
  loadScenes();
}
function resetSceneQuery() {
  Object.assign(sceneQuery, {
    page: 1,
    keyword: "",
    module_code: "",
    is_active: undefined
  });
  loadScenes();
}

// ───────── 场景配置弹窗 ─────────
const sceneDialogVisible = ref(false);
const dialogTab = ref("scene");
const editingSceneId = ref<string | null>(null);
const saving = ref(false);
const routeOptions = ref<NotificationRouteOptions>({
  roles: [],
  permissions: []
});
const userOptions = ref<Array<{ id: string; display_name: string }>>([]);

const sceneForm = reactive({
  scene_key: "",
  scene_name: "",
  module_code: "notify",
  description: "",
  severity_code: "normal" as NotificationSeverity,
  fallback_policy_code: "none" as "none" | "all",
  is_active: true,
  channel_codes: ["in_app"] as NotificationChannel[],
  templateMap: {} as Record<string, TemplateForm>,
  routes: [] as RouteForm[]
});

// 每个启用的渠道一个模板；取消渠道时保留已填内容，保存时只提交启用渠道的模板
watch(
  () => [...sceneForm.channel_codes],
  codes => {
    for (const code of codes) {
      if (!sceneForm.templateMap[code]) {
        sceneForm.templateMap[code] = {
          channel_code: code,
          title_template: "{title}",
          content_template: "{content}",
          wechat_template_no: "",
          mapping_text: "",
          is_active: true
        };
      }
    }
  },
  { immediate: true }
);
const sceneTemplates = computed(() =>
  sceneForm.channel_codes
    .map(code => sceneForm.templateMap[code])
    .filter((tpl): tpl is TemplateForm => Boolean(tpl))
);

async function ensureRouteOptions() {
  if (routeOptions.value.permissions.length) return;
  const res = await getNotificationRouteOptions();
  routeOptions.value = res.data;
}
async function searchUsers(keyword: string) {
  const res = await searchNotificationRouteUsers(keyword);
  const selected = new Set(
    sceneForm.routes.map(item => item.user_id).filter(Boolean)
  );
  userOptions.value = [
    ...userOptions.value.filter(item => selected.has(item.id)),
    ...(res.data ?? [])
  ].filter((item, i, arr) => arr.findIndex(o => o.id === item.id) === i);
}

function fillForm(config: NotificationSceneConfig | null) {
  const scene = config?.scene;
  Object.assign(sceneForm, {
    scene_key: scene?.scene_key ?? "",
    scene_name: scene?.scene_name ?? "",
    module_code: scene?.module_code ?? "notify",
    description: scene?.description ?? "",
    severity_code: scene?.severity_code ?? "normal",
    fallback_policy_code: scene?.fallback_policy_code ?? "none",
    is_active: scene?.is_active ?? true,
    channel_codes: config
      ? config.channels.filter(c => c.is_active).map(c => c.channel_code)
      : ["in_app"],
    templateMap: {},
    routes: []
  });
  for (const tpl of config?.templates ?? []) {
    sceneForm.templateMap[tpl.channel_code] = {
      channel_code: tpl.channel_code,
      title_template: tpl.title_template ?? "",
      content_template: tpl.content_template ?? "",
      wechat_template_no: tpl.wechat_template_no ?? "",
      mapping_text: tpl.data_mapping_config
        ? JSON.stringify(tpl.data_mapping_config)
        : "",
      is_active: tpl.is_active
    };
  }
  sceneForm.routes = (config?.routes ?? []).map(route => ({
    target_type_code: route.target_type_code,
    role_id: route.role_id,
    user_id: route.user_id,
    permission_id: route.permission_id,
    actor_key: route.actor_key,
    org_scope_code: route.org_scope_code,
    is_active: route.is_active
  }));
  userOptions.value = (config?.routes ?? [])
    .filter(route => route.user)
    .map(route => route.user!);
}

async function openCreate() {
  editingSceneId.value = null;
  dialogTab.value = "scene";
  fillForm(null);
  sceneDialogVisible.value = true;
  await ensureRouteOptions();
}
async function openEdit(id: string) {
  editingSceneId.value = id;
  dialogTab.value = "scene";
  const [res] = await Promise.all([
    getNotificationSceneConfig(id),
    ensureRouteOptions()
  ]);
  fillForm(res.data);
  sceneDialogVisible.value = true;
}
function addRoute() {
  sceneForm.routes.push({
    target_type_code: "permission",
    role_id: null,
    user_id: null,
    permission_id: null,
    actor_key: null,
    org_scope_code: "none",
    is_active: true
  });
}
function resetRouteTarget(row: RouteForm) {
  row.role_id = null;
  row.user_id = null;
  row.permission_id = null;
  row.actor_key = null;
}

function routeMissing(route: RouteForm) {
  switch (route.target_type_code) {
    case "permission":
      return !route.permission_id;
    case "role":
      return !route.role_id;
    case "user":
      return !route.user_id;
    case "actor":
      return !route.actor_key?.trim();
    default:
      return false;
  }
}

async function saveScene() {
  if (
    !sceneForm.scene_key.trim() ||
    !sceneForm.scene_name.trim() ||
    !sceneForm.module_code
  ) {
    ElMessage.warning("请填写场景标识、名称和模块");
    dialogTab.value = "scene";
    return;
  }
  if (sceneForm.routes.some(routeMissing)) {
    ElMessage.warning("请完善接收人路由");
    dialogTab.value = "routes";
    return;
  }
  const templates = [];
  for (const tpl of sceneTemplates.value) {
    let mapping: Record<string, unknown> | null = null;
    if (tpl.mapping_text.trim()) {
      try {
        mapping = JSON.parse(tpl.mapping_text);
      } catch {
        ElMessage.warning(
          `${channelLabel(tpl.channel_code)}字段映射不是有效 JSON`
        );
        dialogTab.value = "templates";
        return;
      }
    }
    templates.push({
      channel_code: tpl.channel_code,
      title_template: tpl.title_template || null,
      content_template: tpl.content_template || null,
      wechat_template_no: tpl.wechat_template_no.trim() || null,
      data_mapping_config: mapping,
      is_active: tpl.is_active
    });
  }
  const payload = {
    scene_key: sceneForm.scene_key.trim(),
    scene_name: sceneForm.scene_name.trim(),
    module_code: sceneForm.module_code,
    description: sceneForm.description || null,
    severity_code: sceneForm.severity_code,
    fallback_policy_code: sceneForm.fallback_policy_code,
    is_active: sceneForm.is_active,
    channels: sceneForm.channel_codes.map(code => ({
      channel_code: code,
      is_active: true
    })),
    templates,
    routes: sceneForm.routes.map(route => ({
      ...route,
      actor_key: route.actor_key?.trim() || null
    }))
  };
  saving.value = true;
  try {
    if (editingSceneId.value) {
      await updateNotificationScene(editingSceneId.value, payload);
    } else {
      await createNotificationScene(payload);
    }
    ElMessage.success("已保存");
    sceneDialogVisible.value = false;
    await Promise.all([loadScenes(), loadAllScenes()]);
  } finally {
    saving.value = false;
  }
}

async function removeScene(row: NotificationSceneRow) {
  await ElMessageBox.confirm(
    `删除后业务代码按“${row.scene_key}”发送的通知将被跳过，确定删除？`,
    "删除场景",
    {
      confirmButtonClass: "app-button-danger",
      type: "warning"
    }
  );
  await deleteNotificationScene(row.id);
  ElMessage.success("已删除");
  await Promise.all([loadScenes(), loadAllScenes()]);
}

// ───────── 通知历史 ─────────
const historyQuery = reactive({
  page: 1,
  page_size: 20,
  keyword: "",
  scene_id: "",
  severity_code: "" as "" | NotificationSeverity,
  business_type_code: ""
});
const historyRows = ref<NotificationHistoryRow[]>([]);
const historyTotal = ref(0);
const historyLoading = ref(false);

async function loadHistory() {
  historyLoading.value = true;
  try {
    const res = await listNotificationHistory({
      page: historyQuery.page,
      page_size: historyQuery.page_size,
      keyword: historyQuery.keyword.trim() || undefined,
      scene_id: historyQuery.scene_id || undefined,
      severity_code: historyQuery.severity_code || undefined,
      business_type_code: historyQuery.business_type_code.trim() || undefined
    });
    historyRows.value = res.data.items ?? [];
    historyTotal.value = res.data.total ?? 0;
  } finally {
    historyLoading.value = false;
  }
}
function searchHistory() {
  historyQuery.page = 1;
  loadHistory();
}
function resetHistory() {
  Object.assign(historyQuery, {
    page: 1,
    keyword: "",
    scene_id: "",
    severity_code: "",
    business_type_code: ""
  });
  loadHistory();
}

const recipientVisible = ref(false);
const recipientLoading = ref(false);
const recipientRows = ref<NotificationRecipientRow[]>([]);
const recipientTotal = ref(0);
const recipientPage = ref(1);
const recipientNotificationId = ref("");

async function openRecipients(row: NotificationHistoryRow) {
  recipientNotificationId.value = row.id;
  recipientPage.value = 1;
  recipientVisible.value = true;
  await loadRecipients();
}
async function loadRecipients() {
  recipientLoading.value = true;
  try {
    const res = await listNotificationRecipients(
      recipientNotificationId.value,
      { page: recipientPage.value, page_size: 20 }
    );
    recipientRows.value = res.data.items ?? [];
    recipientTotal.value = res.data.total ?? 0;
  } finally {
    recipientLoading.value = false;
  }
}
function viewDeliveries(row: NotificationHistoryRow) {
  if (navigateMenu("logs", { notification_id: row.id }, "delivery")) return;
  mainTab.value = "logs";
  logTab.value = "delivery";
  Object.assign(deliveryQuery, {
    page: 1,
    keyword: "",
    channel_code: "",
    status_code: "",
    notification_id: row.id
  });
  loadDelivery();
}

// ───────── 日志 ─────────
const deliveryQuery = reactive({
  page: 1,
  page_size: 20,
  keyword: "",
  channel_code: "" as "" | NotificationChannel,
  status_code: "" as "" | NotificationDeliveryStatus,
  notification_id: String(menuContext.notification_id || "")
});
const deliveryRows = ref<NotificationDeliveryLogRow[]>([]);
const deliveryTotal = ref(0);
const deliveryLoading = ref(false);
const sending = ref(false);

async function loadDelivery() {
  deliveryLoading.value = true;
  try {
    const res = await listNotificationDeliveryLogs({
      page: deliveryQuery.page,
      page_size: deliveryQuery.page_size,
      keyword: deliveryQuery.keyword.trim() || undefined,
      channel_code: deliveryQuery.channel_code || undefined,
      status_code: deliveryQuery.status_code || undefined,
      notification_id: deliveryQuery.notification_id.trim() || undefined
    });
    deliveryRows.value = res.data.items ?? [];
    deliveryTotal.value = res.data.total ?? 0;
  } finally {
    deliveryLoading.value = false;
  }
}
function searchDelivery() {
  deliveryQuery.page = 1;
  loadDelivery();
}
function resetDelivery() {
  Object.assign(deliveryQuery, {
    page: 1,
    keyword: "",
    channel_code: "",
    status_code: "",
    notification_id: ""
  });
  loadDelivery();
}
async function sendPending() {
  sending.value = true;
  try {
    const res = await sendPendingDeliveries({ limit: 100 });
    const r = res.data;
    ElMessage.success(
      `处理 ${r.scanned_count} 条：成功 ${r.sent_count}，失败 ${r.failed_count}，跳过 ${r.skipped_count}`
    );
    await loadDelivery();
  } finally {
    sending.value = false;
  }
}

const eventQuery = reactive({
  page: 1,
  page_size: 20,
  keyword: "",
  scene_id: "",
  status_code: "" as "" | "processed" | "skipped" | "failed",
  business_type_code: ""
});
const eventRows = ref<NotificationEventLogRow[]>([]);
const eventTotal = ref(0);
const eventLoading = ref(false);

async function loadEvent() {
  eventLoading.value = true;
  try {
    const res = await listNotificationEventLogs({
      page: eventQuery.page,
      page_size: eventQuery.page_size,
      keyword: eventQuery.keyword.trim() || undefined,
      scene_id: eventQuery.scene_id || undefined,
      status_code: eventQuery.status_code || undefined,
      business_type_code: eventQuery.business_type_code.trim() || undefined
    });
    eventRows.value = res.data.items ?? [];
    eventTotal.value = res.data.total ?? 0;
  } finally {
    eventLoading.value = false;
  }
}
function searchEvent() {
  eventQuery.page = 1;
  loadEvent();
}
function resetEvent() {
  Object.assign(eventQuery, {
    page: 1,
    keyword: "",
    scene_id: "",
    status_code: "",
    business_type_code: ""
  });
  loadEvent();
}
function loadLogs() {
  if (logTab.value === "delivery") loadDelivery();
  else loadEvent();
}

const jsonVisible = ref(false);
const jsonTitle = ref("");
const jsonData = ref<unknown>(null);
const jsonText = computed(() => JSON.stringify(jsonData.value, null, 2));
function showJson(title: string, data: unknown) {
  jsonTitle.value = title;
  jsonData.value = data;
  jsonVisible.value = true;
}

const receiptLoading = ref(false);
const readingVisible = ref(false), readingLoading = ref(false), readingFollowup = ref(false);
const readingError = ref("");
const readingData = ref<ReadingDetails>();
async function openReadingDetails(id: string) {
  readingVisible.value = true; readingLoading.value = true; readingError.value = ""; readingData.value = undefined; readingFollowup.value = false;
  try { readingData.value = (await familyReadingDetails(id)).data; }
  catch (e) { readingError.value = e instanceof Error ? e.message : "阅读明细加载失败"; }
  finally { readingLoading.value = false; }
}
const receiptRows = ref<FamilyReceipt[]>([]);
const receiptSaving = ref(false);
const receiptTotal = ref(0);
const receiptPage = ref(1);

async function loadReceipts() {
  receiptLoading.value = true;
  try {
    const { data } = await listFamilyReceipts({
      page: receiptPage.value,
      page_size: 20
    });
    receiptRows.value = (data?.items || []).map(row => ({
      ...row,
      occurred_at: String(row.occurred_at || "")
        .replace("T", " ")
        .slice(0, 16)
    }));
    receiptTotal.value = data?.total || 0;
  } finally {
    receiptLoading.value = false;
  }
}

async function resendReceipt(row: FamilyReceipt) {
  if (receiptSaving.value) return;
  try {
    await ElMessageBox.confirm(
      "为新增绑定家长补发，并将失败的外部投递重新排队？已成功消息不会重复发送。",
      "补发 / 重试"
    );
  } catch {
    return;
  }
  receiptSaving.value = true;
  try {
    const { data } = await resendFamilyNotice(row.id);
    ElMessage.success(
      data.bound
        ? `新增收件人 ${data.added} 人，重试排队 ${data.retried} 条`
        : "暂无可接收消息的家长账号，请先核对绑定或电话联系"
    );
    await loadReceipts();
  } finally {
    receiptSaving.value = false;
  }
}

async function closeReceiptTask(row: FamilyReceipt) {
  if (receiptSaving.value || !row.task_id) return;
  const result = await ElMessageBox.prompt("请填写电话联系结果", "记录联系", {
    inputType: "textarea",
    inputValidator: value =>
      (Boolean(value?.trim()) && value.length <= 2000) ||
      "请填写 1—2000 字的说明"
  }).catch(() => null);
  if (!result) return;
  receiptSaving.value = true;
  try {
    await closeFamilyContact(row.task_id, result.value);
    ElMessage.success("已记录联系结果");
    await loadReceipts();
  } finally {
    receiptSaving.value = false;
  }
}

function onMainTab(name: string | number) {
  if (name === "scenes") return loadScenes();
  else if (name === "history") return loadHistory();
  else if (name === "receipts") return loadReceipts();
  else return loadLogs();
}

onMounted(() => Promise.all([onMainTab(mainTab.value), loadAllScenes()]));
</script>

<style lang="scss">
@use "../system-styles.scss" as *;

.scene-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.template-panel {
  padding: 14px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
}

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.channel-tag {
  margin-right: 6px;
}

.route-policy-alert {
  margin-bottom: 12px;
}

.route-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.route-table {
  width: 100%;
}

.center-tabs {
  margin-top: 4px;
}

.history-filter-row,
.log-filter-row {
  grid-template-columns: repeat(4, minmax(0, 1fr)) auto;
}

.muted-text {
  color: #94a3b8;
}

.receipt-hint {
  margin: 0 0 12px;
  font-size: 13px;
  line-height: 1.6;
}

.json-detail {
  max-height: 560px;
  padding: 14px;
  margin: 0;
  overflow: auto;
  color: #334155;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  background: #f8fafc;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
}

@media (width <= 1100px) {
  .history-filter-row,
  .log-filter-row,
  .scene-grid,
  .template-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (width <= 700px) {
  .history-filter-row,
  .log-filter-row,
  .scene-grid,
  .template-grid {
    grid-template-columns: 1fr;
  }
}
</style>
