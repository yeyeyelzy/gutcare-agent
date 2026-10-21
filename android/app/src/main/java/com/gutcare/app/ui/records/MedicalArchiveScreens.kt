package com.gutcare.app.ui.records

import android.content.ContentResolver
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.gutcare.app.core.network.MedicalDocumentDto
import com.gutcare.app.core.network.MedicalFieldCandidateDto
import com.gutcare.app.ui.design.GutCarePage
import java.io.IOException
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody
import okio.BufferedSink
import okio.source

@Composable
fun MedicalArchiveRoute(model: MedicalDocumentsViewModel, onBack: () -> Unit, onOpenDocument: (String) -> Unit) {
    val state by model.uiState.collectAsState()
    val resolver = LocalContext.current.contentResolver
    var pickerError by remember { mutableStateOf<String?>(null) }
    var pendingUpload by remember { mutableStateOf<PickedMedicalFile?>(null) }
    var selectedDocumentType by remember { mutableStateOf("other") }
    var revokeConsentType by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) { model.loadConsents() }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            when (val result = inspectMedicalFile(resolver, uri)) {
                is PickResult.Invalid -> pickerError = result.message
                is PickResult.Valid -> pendingUpload = result.file
            }
        }
    }
    MedicalArchiveScreen(
        state = state,
        onBack = onBack,
        onRetry = model::load,
        onOpen = { document -> onOpenDocument(document.id) },
        onUpload = { picker.launch(arrayOf("application/pdf", "image/jpeg", "image/png")) },
        onRevokeConsent = { revokeConsentType = it },
    )
    pendingUpload?.let { file ->
        UploadModeDialog(
            file = file,
            selectedDocumentType = selectedDocumentType,
            onDocumentTypeChange = { selectedDocumentType = it },
            onDismiss = { pendingUpload = null },
            onConfirm = { analyze -> model.upload(file.name, file.contentType, file.sizeBytes, UriRequestBody(resolver, file.uri, file.contentType), analyze = analyze, documentType = selectedDocumentType); pendingUpload = null },
        )
    }
    state.pendingConsentNotice?.let { notice ->
        AlertDialog(
            onDismissRequest = model::dismissConsentNotice,
            title = { Text("解析授权告知 · ${consentName(notice.consentType)}") },
            text = {
                Column {
                    Text("告知版本：${notice.policyVersion.orEmpty()}")
                    Text(notice.summary.orEmpty())
                    notice.purpose?.let { Text("用途：$it") }
                    notice.dataScope?.let { Text("数据范围：$it") }
                    notice.recipient?.let { Text("接收方：$it") }
                    notice.withdrawalEffect?.let { Text("撤回影响：$it") }
                    Text("仅存档需要健康数据处理授权；申请解析还需要第三方 AI 授权。当前操作所需授权齐备后才会上传文件。")
                }
            },
            confirmButton = { TextButton(onClick = model::confirmConsentNotice, enabled = !state.consentLoading) { Text("阅读并同意") } },
            dismissButton = { TextButton(onClick = model::dismissConsentNotice) { Text("暂不授权") } },
        )
    }
    revokeConsentType?.let { type ->
        AlertDialog(
            onDismissRequest = { revokeConsentType = null },
            title = { Text("撤回解析授权？") },
            text = { Text("撤回${consentName(type)}后，服务端会阻止新的解析处理并使符合条件的待处理任务失效。是否继续？") },
            confirmButton = { TextButton(onClick = { model.revokeConsent(type); revokeConsentType = null }) { Text("确认撤回") } },
            dismissButton = { TextButton(onClick = { revokeConsentType = null }) { Text("取消") } },
        )
    }
    pickerError?.let { message -> AlertDialog(onDismissRequest = { pickerError = null }, title = { Text("无法选择文件") }, text = { Text(message) }, confirmButton = { TextButton(onClick = { pickerError = null }) { Text("知道了") } }) }
}

@Composable
fun MedicalArchiveScreen(
    state: MedicalArchiveUiState,
    onBack: () -> Unit,
    onRetry: () -> Unit,
    onOpen: (MedicalDocumentDto) -> Unit,
    onUpload: () -> Unit,
    onRevokeConsent: (String) -> Unit = {},
) {
    MedicalPage("medical_archive_screen") {
        TextButton(onClick = onBack, modifier = Modifier.testTag("medical_archive_back")) { Text("‹ 返回") }
        Text("健康档案", style = MaterialTheme.typography.headlineMedium)
        Text("报告仅保存在你的私有档案中；解析候选须由你逐项确认。", style = MaterialTheme.typography.bodyMedium)
        Text("授权状态：健康数据处理 ${consentStateLabel(state.consentStatus["health_data_processing"]?.granted)} · 第三方 AI ${consentStateLabel(state.consentStatus["third_party_ai"]?.granted)}", style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("medical_analyze_consent_status"))
        listOf("health_data_processing", "third_party_ai").forEach { type ->
            val active = state.consentStatus[type]?.granted == true
            if (active) TextButton(onClick = { onRevokeConsent(type) }, enabled = !state.consentLoading, modifier = Modifier.testTag("medical_revoke_$type")) { Text("撤回${consentName(type)}") }
        }
        if (state.consentLoading) Text("正在核验授权…", modifier = Modifier.testTag("medical_consent_loading"))
        Spacer(Modifier.height(16.dp))
        OutlinedButton(onClick = onRetry, enabled = !state.loading, modifier = Modifier.fillMaxWidth().testTag("medical_archive_refresh")) {
            Text(if (state.loading && state.documents.isNotEmpty()) "正在刷新…" else "刷新档案")
        }
        if (state.loading && state.documents.isNotEmpty()) CircularProgressIndicator(modifier = Modifier.testTag("medical_archive_refresh_progress"))
        when {
            state.loading && state.documents.isEmpty() -> Text("正在加载你的档案…", modifier = Modifier.testTag("medical_archive_loading"))
            state.error != null -> Column {
                Text(state.error, color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("medical_archive_error"))
                TextButton(onClick = onRetry, modifier = Modifier.testTag("medical_archive_retry")) { Text("重试") }
            }
            state.documents.isEmpty() -> Text("还没有检查报告。", modifier = Modifier.testTag("medical_archive_empty"))
            else -> state.documents.forEachIndexed { index, item ->
                OutlinedButton(onClick = { onOpen(item) }, modifier = Modifier.fillMaxWidth().testTag("medical_archive_document_$index"), shape = RoundedCornerShape(16.dp)) {
                    Column(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                        Text(item.originalName)
                        Text("${documentTypeLabel(item.documentType)} · ${item.documentDate ?: "未填写日期"}")
                        Text(parseStatusLabel(item), color = MaterialTheme.colorScheme.secondary)
                    }
                }
                Spacer(Modifier.height(8.dp))
            }
        }
        state.operationMessage?.let { Text(it, color = if (state.conflict) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary, modifier = Modifier.testTag("medical_archive_feedback")) }
        Spacer(Modifier.height(18.dp))
        OutlinedButton(onClick = onUpload, enabled = !state.uploading, modifier = Modifier.fillMaxWidth().testTag("medical_archive_upload")) { Text(if (state.uploading) "正在安全上传…" else "上传新报告") }
    }
}

@Composable
fun MedicalDocumentDetailScreen(state: MedicalArchiveUiState, onBack: () -> Unit, onRetry: () -> Unit, onDecision: (MedicalFieldCandidateDto, String, String?) -> Unit) {
    MedicalPage("medical_document_detail_screen") {
        TextButton(onClick = onBack, modifier = Modifier.testTag("medical_document_back")) { Text("‹ 返回") }
        when {
            state.detailLoading -> Text("正在加载报告详情…", modifier = Modifier.testTag("medical_document_loading"))
            state.detailError != null -> Column { Text(state.detailError, color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("medical_document_error")); TextButton(onClick = onRetry) { Text("重试") } }
            state.detail != null -> {
                Text(state.detail.originalName, style = MaterialTheme.typography.headlineSmall)
                Text("${documentTypeLabel(state.detail.documentType)} · ${state.detail.documentDate ?: "未填写日期"}")
                Text(parseStatusLabel(state.detail))
                state.detail.parseReasonCode?.let { Text(parseReasonLabel(it), color = MaterialTheme.colorScheme.error) }
                Text(if (state.detail.processingMode == "analyze") "解析模式：${parseStatusDetail(state.detail)}" else "仅存档，未请求解析")
                if (state.detail.processingMode == "analyze") TextButton(onClick = onRetry, modifier = Modifier.testTag("medical_parse_refresh")) { Text("刷新任务与候选状态") }
                Spacer(Modifier.height(12.dp))
                if (state.candidates.isEmpty()) Text("当前没有待你确认的字段。", modifier = Modifier.testTag("medical_candidates_empty"))
                state.candidates.forEachIndexed { index, candidate -> CandidateCard(candidate, index, onDecision) }
                val documentFacts = state.confirmedFacts.filter { it.sourceDocumentId == state.detail.id }
                Text("你已确认的结构化记录", style = MaterialTheme.typography.titleMedium, modifier = Modifier.testTag("medical_confirmed_facts_title"))
                Text("仅展示你确认或更正的字段；这些记录不构成诊断结论。", style = MaterialTheme.typography.bodySmall)
                state.confirmedFactsError?.let { Text("已确认记录暂时无法刷新：$it", color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("medical_confirmed_facts_error")) }
                if (documentFacts.isEmpty() && state.confirmedFactsError == null) {
                    Text("这份报告还没有已确认字段。", modifier = Modifier.testTag("medical_confirmed_facts_empty"))
                }
                documentFacts.forEachIndexed { index, fact ->
                    val rendered = fact.value?.toString() ?: "—"
                    Text(
                        "${medicalFieldLabel(fact.fieldCode).removeSuffix("候选")}：$rendered${fact.unit?.let { " $it" }.orEmpty()}",
                        modifier = Modifier.testTag("medical_confirmed_fact_$index"),
                    )
                }
                Text("候选仅供你核对，不是诊断、处方或既成医疗事实。", style = MaterialTheme.typography.bodySmall)
            }
        }
        state.operationMessage?.let { Text(it, color = if (state.conflict) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary, modifier = Modifier.testTag("medical_detail_feedback")) }
    }
}

@Composable private fun CandidateCard(candidate: MedicalFieldCandidateDto, index: Int, onDecision: (MedicalFieldCandidateDto, String, String?) -> Unit) {
    var correctedValue by remember(candidate.id) { mutableStateOf("") }
    var excerptExpanded by remember(candidate.id) { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().padding(vertical = 10.dp).testTag("medical_candidate_$index")) {
        Text(medicalFieldLabel(candidate.fieldCode), style = MaterialTheme.typography.titleMedium)
        Text("候选值：${candidate.value?.toString() ?: "—"}")
        if (candidate.reviewStatus in setOf("accepted", "corrected")) {
            Text("你确认的值：${candidate.chosenValue?.toString() ?: candidate.value?.toString() ?: "—"}", modifier = Modifier.testTag("medical_candidate_confirmed_value_$index"))
        }
        candidate.unit?.let { Text("单位：$it") }
        candidate.confidence?.let { Text("识别置信度：${(it * 100).toInt()}%") }
        candidate.uncertainty?.let { Text("不确定性：$it") }
        candidate.excerpt?.takeIf(String::isNotBlank)?.let { excerpt ->
            TextButton(
                onClick = { excerptExpanded = !excerptExpanded },
                modifier = Modifier.testTag("medical_candidate_excerpt_toggle_$index"),
            ) { Text(if (excerptExpanded) "收起报告原文" else "查看报告原文") }
            if (excerptExpanded) {
                val limitedExcerpt = excerpt.take(MAX_VISIBLE_CANDIDATE_EXCERPT)
                val displayExcerpt = if (excerpt.length > MAX_VISIBLE_CANDIDATE_EXCERPT) "$limitedExcerpt…" else limitedExcerpt
                Text("报告原文：$displayExcerpt", modifier = Modifier.testTag("medical_candidate_excerpt_$index"))
            }
        }
        if (candidate.reviewStatus == "pending") {
            TextButton(onClick = { onDecision(candidate, "accept", null) }, modifier = Modifier.testTag("medical_candidate_accept_$index")) { Text("确认") }
            TextButton(onClick = { onDecision(candidate, "reject", null) }, modifier = Modifier.testTag("medical_candidate_reject_$index")) { Text("不确认") }
            OutlinedTextField(value = correctedValue, onValueChange = { correctedValue = it }, label = { Text(if (candidate.valueType == "object") "纠正后的值（JSON 对象）" else "纠正后的值") }, modifier = Modifier.fillMaxWidth().testTag("medical_candidate_correct_value_$index"))
            TextButton(onClick = { onDecision(candidate, "correct", correctedValue) }, modifier = Modifier.testTag("medical_candidate_correct_$index")) { Text("提交纠正") }
        } else Text("已处理：${candidateStatusLabel(candidate.reviewStatus)}")
    }
}

private const val MAX_VISIBLE_CANDIDATE_EXCERPT = 160

@Composable private fun UploadModeDialog(file: PickedMedicalFile, selectedDocumentType: String, onDocumentTypeChange: (String) -> Unit, onDismiss: () -> Unit, onConfirm: (Boolean) -> Unit) = AlertDialog(
    onDismissRequest = onDismiss,
    title = { Text("上传检查报告") },
    text = {
        Column {
            Text(file.name)
            Text("选择报告类型")
            listOf("lab_report", "outpatient_record", "discharge_summary", "diagnosis_certificate", "prescription", "other").forEach { type ->
                TextButton(onClick = { onDocumentTypeChange(type) }, modifier = Modifier.testTag("medical_upload_type_$type")) {
                    Text((if (selectedDocumentType == type) "✓ " else "○ ") + documentTypeLabel(type))
                }
            }
            Text("仅存档：文件保存在私有档案，不发起解析。")
            Text("申请解析：仅在分别阅读并同意健康数据处理和第三方 AI 告知后才上传并创建待处理请求。服务端没有生成候选时，本页会如实显示等待或空结果。")
        }
    },
    confirmButton = {
        Column {
            TextButton(onClick = { onConfirm(false) }, modifier = Modifier.testTag("medical_upload_store_only")) { Text("仅存档") }
            TextButton(onClick = { onConfirm(true) }, modifier = Modifier.testTag("medical_upload_analyze")) { Text("申请解析") }
        }
    },
)

private fun documentTypeLabel(type: String) = mapOf("lab_report" to "检验报告", "outpatient_record" to "门诊记录", "discharge_summary" to "出院小结", "diagnosis_certificate" to "诊断证明", "prescription" to "处方")[type] ?: "其他报告"
private fun consentName(type: String) = if (type == "health_data_processing") "健康数据处理" else "第三方 AI 处理"
private fun consentStateLabel(granted: Boolean?) = when (granted) { true -> "已授权"; false -> "未授权"; null -> "未知" }
private fun medicalFieldLabel(code: String) = mapOf("diagnosis" to "诊断候选", "document_date" to "报告日期候选", "recommendation" to "建议候选", "test_item" to "检验项目候选", "test_result" to "检验结果候选", "medication_name" to "药品名称候选", "medication_dose" to "药物剂量候选", "medication_frequency" to "用药频率候选", "medication_duration" to "用药时长候选", "allergy" to "过敏信息候选")[code] ?: "字段候选"
private fun candidateStatusLabel(status: String) = mapOf("accepted" to "已确认", "corrected" to "已修正", "rejected" to "已拒绝", "invalidated" to "已失效")[status] ?: "已处理"
private fun parseStatusLabel(item: MedicalDocumentDto) = when (item.parseStatus) {
    "not_requested" -> "仅存档"
    "pending" -> "排队等待处理"
    "processing" -> "处理中"
    "needs_confirmation" -> when (item.parseOutcome) { "insufficient_quality" -> "扫描质量不足"; "no_supported_facts" -> "未找到可支持字段"; else -> "待逐项确认" }
    "confirmed" -> "已确认"
    "failed" -> "处理失败"
    else -> "状态未知"
}
private fun parseStatusDetail(item: MedicalDocumentDto) = when (item.parseStatus) {
    "pending" -> "已提交解析请求，等待业务任务处理；尚无候选结果。"
    "processing" -> "处理中"
    "needs_confirmation" -> when (item.parseOutcome) { "insufficient_quality" -> "未产生可确认字段，扫描质量不足"; "no_supported_facts" -> "未发现可支持的字段"; else -> "存在待你逐项核对的候选字段" }
    "confirmed" -> "字段已由你确认"
    "failed" -> "处理未完成，可查看失败原因"
    else -> "未请求解析"
}
private fun parseReasonLabel(reason: String) = mapOf("no_supported_fields" to "未发现支持的字段", "unsupported_content" to "文档内容暂不支持", "low_quality_scan" to "扫描质量较低", "illegible_content" to "文档内容无法辨认", "incomplete_document" to "文档可能不完整")[reason] ?: "处理未完成"

data class PickedMedicalFile(val uri: Uri, val name: String, val contentType: String, val sizeBytes: Long)
private sealed interface PickResult { data class Valid(val file: PickedMedicalFile) : PickResult; data class Invalid(val message: String) : PickResult }
private fun inspectMedicalFile(resolver: ContentResolver, uri: Uri): PickResult {
    val type = resolver.getType(uri)?.lowercase() ?: return PickResult.Invalid("无法识别文件类型。")
    val limit = when (type) { "application/pdf" -> 20L * 1024 * 1024; "image/jpeg", "image/png" -> 10L * 1024 * 1024; else -> return PickResult.Invalid("仅支持 PDF、JPEG 或 PNG 文件。") }
    var name = "medical-document"
    var size = -1L
    resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { c -> if (c.moveToFirst()) { name = c.getString(0) ?: name; size = c.getLong(1) } }
    if (size !in 1..limit) return PickResult.Invalid("文件大小不符合要求（PDF 最大 20 MiB，图片最大 10 MiB）。")
    return PickResult.Valid(PickedMedicalFile(uri, name, type, size))
}
private class UriRequestBody(private val resolver: ContentResolver, private val uri: Uri, private val type: String) : RequestBody() {
    override fun contentType() = type.toMediaTypeOrNull()
    override fun writeTo(sink: BufferedSink) { resolver.openInputStream(uri)?.use { sink.writeAll(it.source()) } ?: throw IOException("Cannot open selected document") }
}

@Composable private fun MedicalPage(tag: String, content: @Composable ColumnScope.() -> Unit) {
    GutCarePage(modifier = Modifier.testTag(tag)) { Spacer(Modifier.height(16.dp)); content(); Spacer(Modifier.height(24.dp)) }
}
