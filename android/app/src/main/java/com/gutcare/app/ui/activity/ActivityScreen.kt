package com.gutcare.app.ui.activity

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.Button
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.gutcare.app.core.network.ActivityRecordDto
import com.gutcare.app.core.network.ActivityRecordsRepository
import com.gutcare.app.ui.design.GutCarePage
import com.gutcare.app.ui.design.GutCareBackButton
import com.gutcare.app.ui.theme.GutCareBrandGreen
import com.gutcare.app.ui.theme.GutCareLine
import com.gutcare.app.ui.theme.GutCareMuted
import com.gutcare.app.ui.theme.GutCareSage
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter

const val ACTIVITY_ROUTE = "activity"

@Composable
fun ActivityFeatureEntry(gateway: ActivityFeatureGateway, onBack: () -> Unit = {}, onSessionExpired: () -> Unit = {}) {
    val model: ActivityViewModel = viewModel(factory = remember(gateway) { ActivityViewModelFactory(gateway) })
    val state by model.uiState.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { model.load() }
    LaunchedEffect(state.sessionExpired) { if (state.sessionExpired) onSessionExpired() }
    ActivityScreen(
        state = state, onBack = onBack, onRefresh = model::load, onLoadMore = model::loadMore,
        onCreate = model::beginCreate, onEdit = model::beginEdit, onCloseForm = model::closeForm,
        onDraft = model::updateDraft, onSave = model::save, onDelete = model::delete,
        onKeepDraft = model::keepDraftWithLatestVersion, onDiscardDraft = model::discardDraftAndLoadLatest,
        onOpenDetail = model::openDetail, onRetryDetail = model::retryDetail, onCloseDetail = model::closeDetail,
    )
}

@Composable
fun ActivityFeatureEntry(repository: ActivityRecordsRepository, onBack: () -> Unit = {}, onSessionExpired: () -> Unit = {}) =
    ActivityFeatureEntry(remember(repository) { RepositoryActivityFeatureGateway(repository) }, onBack, onSessionExpired)

@Composable
fun ActivityScreen(
    state: ActivityUiState,
    onBack: () -> Unit,
    onRefresh: () -> Unit,
    onLoadMore: () -> Unit,
    onCreate: () -> Unit,
    onEdit: (ActivityRecordDto) -> Unit,
    onCloseForm: () -> Unit,
    onDraft: (ActivityDraft) -> Unit,
    onSave: () -> Unit,
    onDelete: (ActivityRecordDto) -> Unit,
    onKeepDraft: () -> Unit,
    onDiscardDraft: () -> Unit,
    onOpenDetail: (String) -> Unit,
    onRetryDetail: () -> Unit,
    onCloseDetail: () -> Unit,
) {
    var deleteTarget by remember { mutableStateOf<ActivityRecordDto?>(null) }
    GutCarePage(modifier = Modifier.statusBarsPadding()) {
        when {
        state.formOpen -> ActivityFormScreen(
            state = state,
            onBack = onCloseForm,
            onDraft = onDraft,
            onSave = onSave,
        )
        state.detailRequestedId != null -> {
            Spacer(Modifier.height(18.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                GutCareBackButton(onCloseDetail, text = "‹", testTag = "activity_detail_back")
                Text("活动记录详情", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, color = GutCareBrandGreen, modifier = Modifier.weight(1f))
                state.detail?.let { record ->
                    TextButton(onClick = { onEdit(record) }, modifier = Modifier.testTag("activity_detail_edit")) { Text("编辑") }
                    TextButton(onClick = { deleteTarget = record }, modifier = Modifier.testTag("activity_detail_delete")) { Text("删除") }
                }
            }
            Spacer(Modifier.height(20.dp))
            when {
                state.detailLoading -> Feedback("正在读取最新活动记录…", "activity_detail_loading")
                state.detailError != null -> {
                    Feedback(state.detailError, "activity_detail_error")
                    TextButton(onClick = onRetryDetail, modifier = Modifier.testTag("activity_detail_retry")) { Text("重试") }
                    GutCareBackButton(onCloseDetail, text = "返回活动列表", testTag = "activity_detail_back_error")
                }
                state.detail != null -> ActivityDetailCard(state.detail)
            }
        }
        else -> {
        Spacer(Modifier.height(18.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            GutCareBackButton(onBack, text = "‹", testTag = "activity_back")
            Column(Modifier.weight(1f)) {
                Text("运动记录", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold, color = GutCareBrandGreen)
                Text("记录活动与身体感受", color = GutCareMuted)
            }
            TextButton(onClick = onRefresh, enabled = !state.loading, modifier = Modifier.testTag("activity_refresh")) { Text("今天") }
        }
        Spacer(Modifier.height(22.dp))
        Button(onClick = onCreate, modifier = Modifier.fillMaxWidth().height(56.dp).testTag("activity_new")) { Text("新增运动记录") }
        state.message?.let { Text(it, color = GutCareBrandGreen, modifier = Modifier.padding(top = 8.dp).testTag("activity_message")) }
        state.error?.takeIf { state.items.isNotEmpty() }?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 8.dp).testTag("activity_error")) }
        Spacer(Modifier.height(24.dp))
        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Text("活动记录", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Spacer(Modifier.weight(1f))
            TextButton(onClick = onCreate, modifier = Modifier.testTag("activity_new_secondary")) { Text("＋ 新增") }
        }
        when {
            state.loading && state.items.isEmpty() -> Feedback("正在加载活动记录…", "activity_loading")
            state.error != null && state.items.isEmpty() -> {
                Feedback(state.error, "activity_list_error")
                TextButton(onClick = onRefresh) { Text("重试") }
            }
            state.items.isEmpty() -> Feedback("还没有活动记录，运动后可以记一笔。", "activity_empty")
            else -> {
                state.items.forEach { ActivityCard(it, state.deletingId == it.id, onOpen = { onOpenDetail(it.id) }, onEdit = { onEdit(it) }, onDelete = { deleteTarget = it }) }
                if (state.nextCursor != null) TextButton(onClick = onLoadMore, enabled = !state.loadingMore, modifier = Modifier.fillMaxWidth().testTag("activity_load_more")) { Text(if (state.loadingMore) "正在加载…" else "加载更多") }
                if (state.loadingMore && state.error != null) TextButton(onClick = onLoadMore) { Text("加载失败，点此重试（已有记录已保留）") }
            }
        }
        }
        }
    }

    if (state.formOpen && state.conflictLatest != null) {
        val latest = state.conflictLatest
        AlertDialog(
            onDismissRequest = {},
            title = { Text("记录已更新") },
            text = { Text("服务器版本：${latest.activityType.label()} · ${latest.durationMinutes}分钟 · v${latest.recordVersion}\n当前草稿仍保留。选择载入最新记录，或保留草稿并基于最新版本继续；保存仍需手动确认。") },
            confirmButton = { TextButton(onClick = onDiscardDraft) { Text("载入最新记录") } },
            dismissButton = { TextButton(onClick = onKeepDraft) { Text("保留我的草稿") } },
            modifier = Modifier.testTag("activity_conflict_dialog"),
        )
    }
    deleteTarget?.let { record ->
        AlertDialog(
            onDismissRequest = { deleteTarget = null },
            title = { Text("删除这条活动记录？") }, text = { Text("删除后会立即从列表隐藏。") },
            confirmButton = { TextButton(onClick = { onDelete(record); deleteTarget = null }, modifier = Modifier.testTag("activity_delete_confirm")) { Text("删除") } },
            dismissButton = { TextButton(onClick = { deleteTarget = null }) { Text("取消") } },
        )
    }
}

@Composable
private fun ActivityFormScreen(state: ActivityUiState, onBack: () -> Unit, onDraft: (ActivityDraft) -> Unit, onSave: () -> Unit) {
    Spacer(Modifier.height(18.dp))
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
        GutCareBackButton(onBack, text = "‹", testTag = "activity_form_back")
        Column {
            Text(if (state.editingId == null) "新增运动记录" else "编辑运动记录", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, color = GutCareBrandGreen)
            Text("记录活动与身体感受", color = GutCareMuted)
        }
    }
    Spacer(Modifier.height(22.dp))
    Card(colors = CardDefaults.cardColors(containerColor = androidx.compose.ui.graphics.Color(0xFFFAF0D0)), shape = RoundedCornerShape(24.dp)) {
        Column(Modifier.fillMaxWidth().padding(20.dp)) {
            Text("今天做了什么运动？", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(12.dp))
            ChipRow(options = listOf("walking" to "散步", "jogging" to "慢跑", "cycling" to "骑行", "other" to "其他"), selected = state.draft.activityType, tag = "activity_type", onSelect = { onDraft(state.draft.copy(activityType = it, description = if (it == "other") state.draft.description else "")) })
            if (state.draft.activityType == "other") {
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(state.draft.description, { onDraft(state.draft.copy(description = it.take(160))) }, label = { Text("活动描述（1–160字）") }, modifier = Modifier.fillMaxWidth().testTag("activity_description"), singleLine = true)
            }
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(state.draft.duration, { onDraft(state.draft.copy(duration = it.filter(Char::isDigit).take(4))) }, label = { Text("运动时长（分钟）") }, modifier = Modifier.fillMaxWidth().testTag("activity_duration"), singleLine = true)
        }
    }
    Spacer(Modifier.height(14.dp))
    ChoiceCard(title = "运动强度", options = listOf("low" to "轻松", "moderate" to "适中", "high" to "剧烈"), selected = state.draft.intensity, tag = "activity_intensity") { onDraft(state.draft.copy(intensity = it)) }
    Spacer(Modifier.height(14.dp))
    Card(colors = CardDefaults.cardColors(containerColor = androidx.compose.ui.graphics.Color.White), shape = RoundedCornerShape(22.dp)) {
        Column(Modifier.fillMaxWidth().padding(18.dp)) {
            Text("记录日期与时间", fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(state.draft.occurredAt, { onDraft(state.draft.copy(occurredAt = it.take(40))) }, label = { Text("开始时间（含时区）") }, placeholder = { Text("2026-10-20T18:30:00+08:00") }, modifier = Modifier.fillMaxWidth().testTag("activity_occurred_at"), singleLine = true)
        }
    }
    Spacer(Modifier.height(14.dp))
    ChoiceCard(title = "运动后的感受", options = listOf("better" to "更好", "same" to "差不多", "worse" to "不适"), selected = state.draft.subjectiveFeeling, tag = "activity_feeling") { onDraft(state.draft.copy(subjectiveFeeling = it)) }
    Spacer(Modifier.height(12.dp))
    Button(onClick = onSave, enabled = !state.saving, modifier = Modifier.fillMaxWidth().height(54.dp).testTag("activity_save")) {
        Text(if (state.saving) "正在保存…" else if (state.editingId == null) "保存运动记录" else "保存修改")
    }
    state.error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 8.dp).testTag("activity_error")) }
}

@Composable
private fun ChoiceCard(title: String, options: List<Pair<String, String>>, selected: String, tag: String, onSelect: (String) -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = androidx.compose.ui.graphics.Color.White), shape = RoundedCornerShape(22.dp)) {
        Column(Modifier.fillMaxWidth().padding(18.dp)) {
            Text(title, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(8.dp))
            ChipRow(options, selected, tag, onSelect)
        }
    }
}

@Composable
private fun ChipRow(options: List<Pair<String, String>>, selected: String, tag: String, onSelect: (String) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        options.forEach { (value, label) ->
            val active = value == selected
            TextButton(
                onClick = { onSelect(value) },
                modifier = Modifier.weight(1f).background(if (active) GutCareBrandGreen else GutCareSage, RoundedCornerShape(24.dp)).testTag("${tag}_$value"),
            ) { Text(label, color = if (active) androidx.compose.ui.graphics.Color.White else GutCareBrandGreen, maxLines = 1) }
        }
    }
}

@Composable
private fun ActivityCard(record: ActivityRecordDto, deleting: Boolean, onOpen: () -> Unit, onEdit: () -> Unit, onDelete: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp), colors = CardDefaults.cardColors(containerColor = androidx.compose.ui.graphics.Color.White), shape = RoundedCornerShape(20.dp), border = androidx.compose.foundation.BorderStroke(1.dp, GutCareLine)) {
        Column(Modifier.padding(16.dp)) {
            Row {
                Column(Modifier.weight(1f)) {
                    Text(record.activityType.label(), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    Text("${record.durationMinutes} 分钟 · ${record.intensity.label()} · ${record.subjectiveFeeling.feeling()}", color = GutCareMuted)
                    Text(formatActivityTime(record.occurredAt), color = GutCareMuted, style = MaterialTheme.typography.bodySmall)
                    record.description?.let { Text(it, modifier = Modifier.padding(top = 5.dp)) }
                }
                Text(if (deleting) "删除中" else "", color = GutCareMuted)
            }
            Row(horizontalArrangement = Arrangement.End, modifier = Modifier.fillMaxWidth()) {
                TextButton(onClick = onOpen, enabled = !deleting, modifier = Modifier.testTag("activity_detail_${record.id}")) { Text("详情") }
                TextButton(onClick = onEdit, enabled = !deleting, modifier = Modifier.testTag("activity_edit_${record.id}")) { Text("编辑") }
                TextButton(onClick = onDelete, enabled = !deleting, modifier = Modifier.testTag("activity_delete_${record.id}")) { Text("删除") }
            }
        }
    }
}

@Composable
private fun ActivityDetailCard(record: ActivityRecordDto) {
    Card(colors = CardDefaults.cardColors(containerColor = androidx.compose.ui.graphics.Color.White), shape = RoundedCornerShape(22.dp), border = androidx.compose.foundation.BorderStroke(1.dp, GutCareLine)) {
        Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text(record.activityType.label(), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, color = GutCareBrandGreen)
            DetailLine("开始时间", formatActivityTime(record.occurredAt))
            DetailLine("持续时间", "${record.durationMinutes} 分钟")
            DetailLine("运动强度", record.intensity.label())
            DetailLine("运动感受", record.subjectiveFeeling.feeling())
            record.description?.let { DetailLine("活动描述", it) }
            DetailLine("记录版本", "v${record.recordVersion}")
            Text("详情来自服务端最新记录。", color = GutCareMuted, style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("activity_detail_loaded"))
        }
    }
}

@Composable
private fun DetailLine(label: String, value: String) {
    Column {
        Text(label, color = GutCareMuted, style = MaterialTheme.typography.bodySmall)
        Text(value, style = MaterialTheme.typography.bodyLarge)
    }
}

@Composable
private fun Feedback(text: String, tag: String) = Text(text, color = GutCareMuted, modifier = Modifier.fillMaxWidth().padding(vertical = 16.dp).testTag(tag))

private fun String.label() = when (this) { "walking" -> "散步"; "jogging" -> "慢跑"; "cycling" -> "骑行"; "other" -> "其他活动"; "low" -> "轻松"; "moderate" -> "适中"; "high" -> "剧烈"; else -> this }
private fun String.feeling() = when (this) { "better" -> "感觉更好"; "same" -> "感觉相近"; "worse" -> "有些不适"; else -> "" }
private fun formatActivityTime(value: String) = runCatching { OffsetDateTime.parse(value).format(DateTimeFormatter.ofPattern("yyyy/MM/dd HH:mm")) }.getOrDefault("活动时间")
