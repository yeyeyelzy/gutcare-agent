package com.gutcare.app.ui.records

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.gutcare.app.core.network.PatientProfileDto
import com.gutcare.app.navigation.RootTab
import com.gutcare.app.ui.design.GutCarePage
import com.gutcare.app.ui.design.GutCarePrimaryButton
import com.gutcare.app.ui.theme.GutCareBrandGreen
import com.gutcare.app.ui.theme.GutCareMuted

@Composable
fun RecordsHubScreen(
    onOpenCategory: (WorkspaceRecordType) -> Unit,
    onOpenArchive: () -> Unit,
) {
    WorkspacePage("records_hub_screen") {
        Text("记录", style = MaterialTheme.typography.displayLarge)
        Text("查看和管理本人记录", color = GutCareMuted)
        Spacer(Modifier.height(20.dp))
        WorkspaceRecordType.entries.forEach { type ->
            OutlinedButton(
                onClick = { onOpenCategory(type) },
                modifier = Modifier.fillMaxWidth().height(56.dp).testTag("records_open_${type.name.lowercase()}"),
                shape = RoundedCornerShape(18.dp),
            ) { Text("${type.title}记录", modifier = Modifier.weight(1f)); Text("查看 / 新增  ›", color = GutCareBrandGreen) }
            Spacer(Modifier.height(10.dp))
        }
        GutCarePrimaryButton("健康档案", onOpenArchive, testTag = "records_open_health_archive")
    }
}

@Composable
fun RecordListScreen(
    type: WorkspaceRecordType,
    state: RecordsUiState,
    onBack: () -> Unit,
    onRetry: () -> Unit,
    onNew: () -> Unit,
    onOpen: (RecordRow) -> Unit,
    onLoadMore: () -> Unit,
    onDelete: (RecordRow) -> Unit,
) {
    WorkspacePage("record_list_${type.name.lowercase()}_screen") {
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack, modifier = Modifier.testTag("record_list_back")) { Text("‹ 返回") }
            Text("${type.title}记录", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
        }
        Spacer(Modifier.height(14.dp))
        GutCarePrimaryButton("新增${type.title}记录", onNew, testTag = "record_list_new")
        Spacer(Modifier.height(18.dp))
        when (val load = state.loadState) {
            RecordsLoadState.Idle, RecordsLoadState.Loading -> Text("正在加载本人记录…", modifier = Modifier.testTag("record_list_loading"), color = GutCareMuted)
            RecordsLoadState.Empty -> Text("还没有${type.title}记录。", modifier = Modifier.testTag("record_list_empty"), color = GutCareMuted)
            is RecordsLoadState.Error -> Column {
                Text(load.message, color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("record_list_error"))
                TextButton(onClick = onRetry, modifier = Modifier.testTag("record_list_retry")) { Text("重试") }
            }
            is RecordsLoadState.Loaded -> {
                load.records.forEachIndexed { index, record ->
                    RecordRowCard(type, record, index, state.operation, onOpen, onDelete)
                    Spacer(Modifier.height(10.dp))
                }
                state.nextCursor?.let {
                    state.loadMoreError?.let { error -> Text(error, color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("record_list_load_more_error")) }
                    TextButton(onClick = onLoadMore, enabled = !state.loadingMore, modifier = Modifier.testTag("record_list_load_more")) {
                        Text(if (state.loadingMore) "正在加载…" else "加载更多")
                    }
                }
            }
        }
        state.operation.feedback?.let { Text(it, color = if (state.operation.conflict) MaterialTheme.colorScheme.error else GutCareMuted, modifier = Modifier.testTag("record_operation_feedback")) }
    }
}

@Composable
private fun RecordRowCard(type: WorkspaceRecordType, record: RecordRow, index: Int, operation: RecordOperationState, onOpen: (RecordRow) -> Unit, onDelete: (RecordRow) -> Unit) {
    val confirm = remember(record.id) { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().padding(14.dp).testTag("record_row_$index")) {
        Text(record.label, style = MaterialTheme.typography.titleMedium)
        Text(record.occurredAt, color = GutCareMuted)
        TextButton(onClick = { onOpen(record) }, modifier = Modifier.testTag("record_open_$index")) { Text("查看详情") }
        TextButton(onClick = { confirm.value = true }, enabled = !operation.saving, modifier = Modifier.testTag("record_delete_$index")) { Text("删除") }
    }
    if (confirm.value) AlertDialog(
        onDismissRequest = { confirm.value = false },
        title = { Text("删除这条${type.title}记录？") },
        text = { Text("删除后记录会立即从本人列表中隐藏。") },
        confirmButton = { TextButton(onClick = { confirm.value = false; onDelete(record) }, modifier = Modifier.testTag("record_delete_confirm")) { Text("确认删除") } },
        dismissButton = { TextButton(onClick = { confirm.value = false }) { Text("取消") } },
    )
}

@Composable
fun RecordDetailScreen(
    type: WorkspaceRecordType,
    state: RecordsUiState,
    onBack: () -> Unit,
    onRetry: () -> Unit,
    onEdit: () -> Unit,
    onDelete: () -> Unit,
    onManageImages: (() -> Unit)? = null,
) {
    val confirm = remember(state.detailState) { mutableStateOf(false) }
    WorkspacePage("record_detail_${type.name.lowercase()}_screen") {
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack, modifier = Modifier.testTag("record_detail_back")) { Text("‹ 返回") }
            Text("${type.title}记录详情", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
        }
        Spacer(Modifier.height(14.dp))
        when (val detailState = state.detailState) {
            RecordDetailLoadState.Idle, RecordDetailLoadState.Loading -> Text("正在加载本人记录…", modifier = Modifier.testTag("record_detail_loading"), color = GutCareMuted)
            is RecordDetailLoadState.Error -> Column {
                Text(detailState.message, color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("record_detail_error"))
                TextButton(onClick = onRetry, modifier = Modifier.testTag("record_detail_retry")) { Text("重试") }
            }
            is RecordDetailLoadState.Loaded -> {
                val record = detailState.detail
                Text("发生时间：${record.occurredAt}")
                when (type) {
                    WorkspaceRecordType.DIET -> {
                        Text("餐次：${record.payload.mealType.orEmpty()}")
                        record.payload.textDescription?.let { Text("描述：$it") }
                        record.payload.items.orEmpty().forEach { Text("食物：${it.name.orEmpty()} ${it.amountText.orEmpty()}") }
                        record.payload.portionNote?.let { Text("份量：$it") }
                        record.payload.cookingMethod?.let { Text("烹饪方式：$it") }
                        record.payload.subjectiveNote?.let { Text("备注：$it") }
                    }
                    WorkspaceRecordType.STOOL -> {
                        record.payload.bristolType?.let { Text("Bristol 类型：$it") }
                        record.payload.colorCode?.let { Text("颜色描述：$it") }
                        record.payload.bowelAmount?.let { Text("排便量：$it") }
                        record.payload.processSensation.orEmpty().takeIf { it.isNotEmpty() }?.let { Text("过程感受：${it.joinToString()}") }
                        record.payload.notes?.let { Text("备注：$it") }
                    }
                    WorkspaceRecordType.SYMPTOM -> {
                        record.payload.items.orEmpty().forEach { item ->
                            Text("症状：${item.otherDescription ?: item.symptomCode.orEmpty()}")
                            item.severity?.let { Text("主观严重程度：$it / 10") }
                            item.bodyLocation?.let { Text("位置：$it") }
                        }
                        record.payload.durationMinutes?.let { Text("持续时间：$it 分钟") }
                        record.payload.symptomStatus?.let { Text("状态：$it") }
                        record.statusHistoryError?.let { Text("状态历史暂不可用：$it", color = MaterialTheme.colorScheme.error) }
                        record.statusHistory.forEach { Text("${it.status} · ${it.changedAt}") }
                        record.payload.notes?.let { Text("备注：$it") }
                    }
                    WorkspaceRecordType.MOOD -> {
                        Text("心情等级：${record.moodLevel ?: "—"}")
                        if (record.emotionTags.isNotEmpty()) Text("情绪标签：${record.emotionTags.joinToString()}")
                        record.note?.let { Text("备注：$it", modifier = Modifier.testTag("mood_detail_note")) }
                    }
                }
                Spacer(Modifier.height(10.dp))
                OutlinedButton(onClick = onEdit, enabled = !state.operation.saving, modifier = Modifier.fillMaxWidth().testTag("record_detail_edit")) { Text("编辑") }
                onManageImages?.let { action ->
                    OutlinedButton(onClick = action, enabled = !state.operation.saving, modifier = Modifier.fillMaxWidth().testTag("record_detail_images")) { Text("管理记录图片") }
                }
                TextButton(onClick = { confirm.value = true }, enabled = !state.operation.saving, modifier = Modifier.testTag("record_detail_delete")) { Text("删除") }
            }
        }
        state.operation.feedback?.let { Text(it, color = if (state.operation.conflict) MaterialTheme.colorScheme.error else GutCareMuted, modifier = Modifier.testTag("record_detail_feedback")) }
    }
    if (confirm.value) AlertDialog(
        onDismissRequest = { confirm.value = false }, title = { Text("删除这条${type.title}记录？") },
        text = { Text("删除后记录会立即从本人列表中隐藏。") },
        confirmButton = { TextButton(onClick = { confirm.value = false; onDelete() }, modifier = Modifier.testTag("record_detail_delete_confirm")) { Text("确认删除") } },
        dismissButton = { TextButton(onClick = { confirm.value = false }) { Text("取消") } },
    )
}

@Composable
fun RecordEditBootstrapScreen(
    type: WorkspaceRecordType,
    state: RecordsUiState,
    onBack: () -> Unit,
    onRetry: () -> Unit,
) {
    WorkspacePage("record_edit_bootstrap_screen") {
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack, modifier = Modifier.testTag("record_edit_back")) { Text("‹ 返回") }
            Text("编辑${type.title}记录", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
        }
        Spacer(Modifier.height(14.dp))
        when (val detail = state.detailState) {
            RecordDetailLoadState.Idle, RecordDetailLoadState.Loading -> Text("正在读取记录详情…", color = GutCareMuted, modifier = Modifier.testTag("record_edit_loading"))
            is RecordDetailLoadState.Error -> Column {
                Text(detail.message, color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("record_edit_error"))
                TextButton(onClick = onRetry, modifier = Modifier.testTag("record_edit_retry")) { Text("重试") }
            }
            is RecordDetailLoadState.Loaded -> Text("正在准备编辑表单…", color = GutCareMuted, modifier = Modifier.testTag("record_edit_loading"))
        }
    }
}

@Composable
fun HealthArchiveUnavailableScreen(profile: PatientProfileDto?, onBack: () -> Unit, onUnavailableAction: () -> Unit) {
    HealthArchiveScreen(
        uiState = HealthArchiveUiState(
            profile = profile?.let { HealthProfileUiState(it.nickname, it.birthYear, null) },
            errorMessage = "当前 Android 切片尚未接入医疗档案 API，暂不能加载或上传检查报告。",
            uploadEnabled = false,
            profileActionEnabled = false,
            retryEnabled = false,
        ),
        callbacks = HealthArchiveCallbacks(onBack = onBack, onUploadReport = onUnavailableAction, onEditProfile = onUnavailableAction),
    )
}

@Composable
fun ProtectedPlaceholderScreen(tab: RootTab, onLogout: () -> Unit = {}) {
    WorkspacePage("protected_placeholder_${tab.name.lowercase()}") {
        Text(tab.title, style = MaterialTheme.typography.displayLarge)
        Text(if (tab == RootTab.Analysis) "分析任务页面暂未接入业务服务。此入口不会连接智能体或展示示例结果。" else tab.subtitle, color = GutCareMuted)
        if (tab == RootTab.Me) GutCarePrimaryButton("退出登录", onLogout, testTag = "logout")
    }
}

@Composable
private fun WorkspacePage(tag: String, content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit) {
    GutCarePage(modifier = Modifier.testTag(tag)) {
        Spacer(Modifier.height(16.dp))
        content()
        Spacer(Modifier.height(24.dp))
    }
}
