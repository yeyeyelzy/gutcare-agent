package com.gutcare.app.ui.analysis

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.activity.compose.BackHandler
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.gutcare.app.core.network.AdviceDto
import com.gutcare.app.core.network.AnalysisTaskDto
import com.gutcare.app.ui.design.GutCareBackButton

@Composable
fun AnalysisAdviceWorkspace(
    state: AnalysisAdviceUiState,
    model: AnalysisAdviceViewModel,
    patientTimeZone: String = java.time.ZoneId.systemDefault().id,
) {
    LaunchedEffect(Unit) { model.load() }
    LaunchedEffect(patientTimeZone) { model.setTimeZone(patientTimeZone) }
    when {
        state.selectedTask != null -> AnalysisTaskDetail(state.selectedTask, model)
        state.selectedAdvice != null -> AdviceDetail(state.selectedAdvice, model)
        state.showHistory -> AnalysisHistoryPanel(state, model)
        state.showAdviceHistory -> AdviceHistoryPanel(state, model)
        else -> LazyColumn(Modifier.fillMaxSize().padding(horizontal = 20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item { Text("分析与建议", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 24.dp)) }
            item { Text("分析任务由业务服务管理。分析结果仅在服务端实际返回后展示，不代表诊断或处方。") }
            item { TaskCreatePanel(state, model) }
            state.error?.let { item { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("analysis_error")) } }
            item { Text("分析任务", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold) }
            item { OutlinedButton(onClick = model::showHistory, modifier = Modifier.fillMaxWidth().testTag("analysis_history_entry")) { Text("历史分析") } }
            item { Text("建议", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold) }
            item { OutlinedButton(onClick = model::showAdviceHistory, modifier = Modifier.fillMaxWidth().testTag("advice_history_entry")) { Text("历史建议") } }
            item { Spacer(Modifier.height(24.dp)) }
        }
    }
}

@Composable private fun AdviceHistoryPanel(state: AnalysisAdviceUiState, model: AnalysisAdviceViewModel) {
    BackHandler { model.hideAdviceHistory() }
    LazyColumn(Modifier.fillMaxSize().padding(horizontal = 20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                GutCareBackButton(model::hideAdviceHistory, text = "‹ 返回分析", testTag = "advice_history_back")
                Text("历史建议", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            }
        }
        state.error?.let { item { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("advice_history_error")) } }
        if (state.advice.isEmpty() && state.busy) item { LinearProgressIndicator(Modifier.fillMaxWidth().testTag("advice_history_loading")) }
        if (state.advice.isEmpty() && !state.busy && state.error == null) item { Text("暂无历史建议。") }
        items(state.advice.sortedWith(compareByDescending<AdviceDto> { runCatching { java.time.Instant.parse(it.createdAt) }.getOrNull() }.thenByDescending { it.id }), key = { it.id }) { advice ->
            AdviceCard(advice) { model.openAdvice(advice.id) }
        }
        state.adviceCursor?.let { cursor ->
            item { TextButton(onClick = { model.loadAdvice(cursor) }, enabled = !state.busy, modifier = Modifier.testTag("advice_history_load_more")) { Text("加载更多") } }
        }
    }
}

@Composable private fun AnalysisHistoryPanel(state: AnalysisAdviceUiState, model: AnalysisAdviceViewModel) {
    BackHandler { model.hideHistory() }
    LazyColumn(Modifier.fillMaxSize().padding(horizontal = 20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                GutCareBackButton(model::hideHistory, text = "‹ 返回分析", testTag = "analysis_history_back")
                Text("历史分析", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            }
        }
        state.error?.let { item { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("analysis_history_error")) } }
        if (state.tasks.isEmpty() && state.busy) item { LinearProgressIndicator(Modifier.fillMaxWidth().testTag("analysis_history_loading")) }
        if (state.tasks.isEmpty() && !state.busy && state.error == null) item { Text("暂无历史分析。") }
        items(state.tasks.sortedWith(compareByDescending<AnalysisTaskDto> { runCatching { java.time.Instant.parse(it.createdAt) }.getOrNull() }.thenByDescending { it.id }), key = { it.id }) { task ->
            TaskCard(task) { model.openTask(task.id) }
        }
        state.taskCursor?.let { cursor ->
            item { TextButton(onClick = { model.loadTasks(cursor) }, enabled = !state.busy, modifier = Modifier.testTag("analysis_history_load_more")) { Text("加载更多") } }
        }
    }
}

@Composable private fun TaskCreatePanel(state: AnalysisAdviceUiState, model: AnalysisAdviceViewModel) {
    Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("发起分析", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        AnalysisDateField("开始日期", state.from, "analysis_start_date") { model.setRange(it, state.to) }
        AnalysisDateField("结束日期", state.to, "analysis_end_date") { model.setRange(state.from, it) }
        Text("按 ${state.timeZoneId} 转换为 UTC 半开区间；开始日包含，结束日包含整天。日期范围可整体留空。", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        if (state.from.isNotBlank() || state.to.isNotBlank()) TextButton(onClick = { model.setRange("", "") }, modifier = Modifier.testTag("analysis_clear_range")) { Text("清除日期范围") }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = model::preview, enabled = !state.busy, modifier = Modifier.testTag("analysis_preview")) { Text("预览") }
            Button(onClick = model::create, enabled = !state.busy && state.preview != null, modifier = Modifier.testTag("analysis_create")) { Text("创建任务") }
        }
        if (state.busy) LinearProgressIndicator(Modifier.fillMaxWidth().testTag("analysis_loading"))
    } }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable private fun AnalysisDateField(label: String, value: String, tag: String, onSelect: (String) -> Unit) {
    var showPicker by remember { mutableStateOf(false) }
    val selectedMillis = remember(value) {
        runCatching { java.time.LocalDate.parse(value).atStartOfDay(java.time.ZoneOffset.UTC).toInstant().toEpochMilli() }.getOrNull()
    }
    OutlinedButton(onClick = { showPicker = true }, modifier = Modifier.fillMaxWidth().testTag(tag)) {
        Text("$label：${value.ifBlank { "选择日期（可空）" }}")
    }
    if (showPicker) {
        val pickerState = androidx.compose.material3.rememberDatePickerState(initialSelectedDateMillis = selectedMillis)
        DatePickerDialog(
            onDismissRequest = { showPicker = false },
            confirmButton = {
                TextButton(onClick = {
                    pickerState.selectedDateMillis?.let { millis ->
                        onSelect(java.time.Instant.ofEpochMilli(millis).atZone(java.time.ZoneOffset.UTC).toLocalDate().toString())
                    }
                    showPicker = false
                }, modifier = Modifier.testTag("${tag}_confirm")) { Text("确定") }
            },
            dismissButton = { TextButton(onClick = { showPicker = false }) { Text("取消") } },
        ) { DatePicker(state = pickerState) }
    }
}

@Composable private fun TaskCard(task: AnalysisTaskDto, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick).testTag("analysis_task_${task.id}")) { Column(Modifier.padding(16.dp)) {
        Text("状态：${task.status}", fontWeight = FontWeight.SemiBold)
        Text("分析时间：${task.createdAt}")
    } }
}

@Composable private fun AnalysisTaskDetail(task: AnalysisTaskDto, model: AnalysisAdviceViewModel) {
    val uiState = model.state.collectAsState().value
    BackHandler { model.backToList() }
    DisposableEffect(task.id) { onDispose { model.stopTaskPolling(task.id) } }
    LazyColumn(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { GutCareBackButton(model::backToList, testTag = "analysis_task_back"); Text("任务详情", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold) }
        item { Text("任务 ID：${task.id}\n状态：${task.status}") }
        task.result?.let { result ->
            item {
                Card(Modifier.fillMaxWidth().testTag("analysis_result")) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("分析摘要", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
                        Text(result.summary, modifier = Modifier.testTag("analysis_result_summary"))
                        if (result.observations.isNotEmpty()) {
                            Text("综合观察", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                            result.observations.forEach { Text("• $it") }
                        }
                        if (result.uncertainties.isNotEmpty()) {
                            Text("分析范围说明", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                            result.uncertainties.forEach { Text("• $it") }
                        }
                        if (result.missingData.isNotEmpty()) {
                            Text("缺失数据", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                            result.missingData.forEach { Text("• $it") }
                        }
                        if (result.evidence.isNotEmpty()) {
                            val evidenceSummary = result.evidence.groupingBy { it.sourceType }.eachCount()
                                .entries.sortedBy { it.key }
                                .joinToString("；") { (source, count) -> "${sourceLabel(source)} $count 项" }
                            val deletedCount = result.evidence.count { it.sourceDeleted }
                            Text("证据摘要：$evidenceSummary${if (deletedCount > 0) "；来源已删除 $deletedCount 项" else ""}", modifier = Modifier.testTag("analysis_result_evidence"))
                        }
                        Text("结果由服务端返回，仅供健康记录参考，不构成诊断或处方。", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        } ?: item { Text("服务端尚未提供分析结果。此页面不会生成或补写智能体输出。") }
        item { Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { model.refreshTask(task.id) }, enabled = !uiState.busy) { Text("刷新") }
            if (task.status in listOf("pending", "processing", "needs_input")) OutlinedButton(onClick = { model.cancelTask(task.id) }, modifier = Modifier.testTag("analysis_cancel")) { Text("取消") }
            if (task.status == "failed") Button(onClick = { model.retryTask(task.id) }, modifier = Modifier.testTag("analysis_retry")) { Text("重试") }
        } }
        if (uiState.taskPolling) item { Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) { CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp); Text("分析处理中，正在自动刷新任务状态…") } }
        if (uiState.taskPollingTimedOut) item { Text("任务仍在处理中，已暂停自动刷新；可点击“刷新”再次查询。", color = MaterialTheme.colorScheme.onSurfaceVariant) }
        uiState.error?.let { item { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("analysis_error")) } }
    }
}

private fun sourceLabel(sourceType: String): String = when (sourceType) {
    "confirmed_medical_fact" -> "医疗档案"
    "diet_record" -> "饮食记录"
    "stool_record" -> "排便记录"
    "symptom_record" -> "症状记录"
    "mood_record" -> "心情记录"
    "medication_plan" -> "用药计划"
    "medication_checkin" -> "用药打卡"
    "risk_alert" -> "风险提示"
    else -> "其他来源"
}

@Composable private fun AdviceCard(advice: AdviceDto, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick).testTag("advice_${advice.id}")) { Column(Modifier.padding(16.dp)) { Text(advice.title, fontWeight = FontWeight.SemiBold); Text("${advice.category} · ${advice.priority}") } }
}

@Composable private fun AdviceDetail(advice: AdviceDto, model: AnalysisAdviceViewModel) {
    LazyColumn(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { GutCareBackButton(model::backToList, testTag = "advice_detail_back"); Text(advice.title, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold); Text(advice.body) }
        item { Text("安全说明：此建议不是诊断或处方；风险提示优先。") }
        item { Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { model.feedback(advice.id, "helpful") }) { Text("有帮助") }
            OutlinedButton(onClick = { model.archiveAdvice(advice.id) }, enabled = advice.status != "archived") { Text("归档") }
        } }
    }
}
