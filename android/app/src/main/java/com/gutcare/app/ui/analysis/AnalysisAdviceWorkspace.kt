package com.gutcare.app.ui.analysis

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.gutcare.app.core.network.AdviceDto
import com.gutcare.app.core.network.AdviceEvidenceDto
import com.gutcare.app.core.network.AnalysisTaskDto

@Composable
fun AnalysisAdviceWorkspace(
    state: AnalysisAdviceUiState,
    model: AnalysisAdviceViewModel,
    onOpenEvidence: (AdviceEvidenceDto) -> Unit = {},
    onOpenCitation: (String) -> Unit = {},
) {
    LaunchedEffect(Unit) { model.load() }
    when {
        state.selectedTask != null -> AnalysisTaskDetail(state.selectedTask, model)
        state.selectedAdvice != null -> AdviceDetail(state.selectedAdvice, model, onOpenEvidence, onOpenCitation)
        else -> LazyColumn(Modifier.fillMaxSize().padding(horizontal = 20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item { Text("分析与建议", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 24.dp)) }
            item { Text("分析任务由业务服务管理。分析结果仅在服务端实际返回后展示，不代表诊断或处方。") }
            item { TaskCreatePanel(state, model) }
            state.error?.let { item { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("analysis_error")) } }
            state.notice?.let { item { Text(it, color = MaterialTheme.colorScheme.primary) } }
            item { Text("分析任务", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold) }
            if (state.tasks.isEmpty()) item { Text("暂无分析任务。创建后，任务状态由业务服务更新；智能体未返回时不会生成演示结果。") }
            items(state.tasks, key = { it.id }) { task -> TaskCard(task) { model.openTask(task.id) } }
            state.taskCursor?.let { item { TextButton(onClick = { model.loadTasks(it) }) { Text("加载更多任务") } } }
            item { Text("建议", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold) }
            if (state.advice.isEmpty()) item { Text("暂无已生成的建议。建议仅在后端收到并验证智能体结果后出现。") }
            items(state.advice, key = { it.id }) { advice -> AdviceCard(advice) { model.openAdvice(advice.id) } }
            state.adviceCursor?.let { item { TextButton(onClick = { model.loadAdvice(it) }) { Text("加载更多建议") } } }
            item { Spacer(Modifier.height(24.dp)) }
        }
    }
}

@Composable private fun TaskCreatePanel(state: AnalysisAdviceUiState, model: AnalysisAdviceViewModel) {
    Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("发起分析", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        OutlinedTextField(state.from, { model.setRange(it, state.to) }, label = { Text("开始时间（ISO 8601，可空）") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(state.to, { model.setRange(state.from, it) }, label = { Text("结束时间（ISO 8601，可空）") }, modifier = Modifier.fillMaxWidth())
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = model::preview, enabled = !state.busy, modifier = Modifier.testTag("analysis_preview")) { Text("预览") }
            Button(onClick = model::create, enabled = !state.busy && state.preview != null, modifier = Modifier.testTag("analysis_create")) { Text("创建任务") }
        }
        state.preview?.let { Text("心情记录：${it.moodRecordCountEligible} 条；排除 ${it.moodRecordCountExcludedByConsent} 条。此计数仅为预览；服务端将在创建时重新校验并生成不可变快照。") }
        if (state.busy) LinearProgressIndicator(Modifier.fillMaxWidth().testTag("analysis_loading"))
    } }
}

@Composable private fun TaskCard(task: AnalysisTaskDto, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick).testTag("analysis_task_${task.id}")) { Column(Modifier.padding(16.dp)) {
        Text("状态：${task.status}", fontWeight = FontWeight.SemiBold); Text("创建于 ${task.createdAt}"); Text("冻结输入的心情记录：${task.inputSummary.includedMoodRecordCount}")
    } }
}

@Composable private fun AnalysisTaskDetail(task: AnalysisTaskDto, model: AnalysisAdviceViewModel) {
    val uiState = model.state.collectAsState().value
    DisposableEffect(task.id) { onDispose { model.stopTaskPolling(task.id) } }
    LazyColumn(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { TextButton(onClick = model::backToList) { Text("返回") }; Text("任务详情", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold) }
        item { Text("任务 ID：${task.id}\n状态：${task.status}\n冻结输入的心情记录：${task.inputSummary.includedMoodRecordCount}") }
        task.result?.let { result ->
            item {
                Card(Modifier.fillMaxWidth().testTag("analysis_result")) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("分析摘要", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
                        Text(result.summary, modifier = Modifier.testTag("analysis_result_summary"))
                        if (result.observations.isNotEmpty()) {
                            Text("观察", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                            result.observations.forEach { Text("• $it") }
                        }
                        if (result.uncertainties.isNotEmpty()) {
                            Text("不确定性", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
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
            if (task.status in listOf("failed", "cancelled")) Button(onClick = { model.retryTask(task.id) }, modifier = Modifier.testTag("analysis_retry")) { Text("重试") }
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

@Composable private fun AdviceDetail(advice: AdviceDto, model: AnalysisAdviceViewModel, onOpenEvidence: (AdviceEvidenceDto) -> Unit, onOpenCitation: (String) -> Unit) {
    LazyColumn(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { TextButton(onClick = model::backToList) { Text("返回") }; Text(advice.title, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold); Text(advice.body) }
        item { Text("安全说明：此建议不是诊断或处方；风险提示优先。") }
        item { Text("适用范围：${advice.applicability.scope}") }
        if (advice.evidence.isEmpty()) item { Text("暂无可展示的证据。") }
        items(advice.evidence) { evidence ->
            val label = evidence.title ?: evidence.sourceType ?: evidence.knowledgeRef ?: "证据"
            TextButton(onClick = { evidence.citationUrl?.takeIf { it.startsWith("https://") }?.let(onOpenCitation) ?: onOpenEvidence(evidence) }) { Text(label) }
        }
        item { Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { model.feedback(advice.id, "helpful") }) { Text("有帮助") }
            OutlinedButton(onClick = { model.archiveAdvice(advice.id) }, enabled = advice.status != "archived") { Text("归档") }
        } }
    }
}
