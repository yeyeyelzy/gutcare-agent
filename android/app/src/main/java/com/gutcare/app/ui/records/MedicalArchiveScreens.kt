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
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
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
    )
    pendingUpload?.let { file ->
        UploadModeDialog(
            file = file,
            onDismiss = { pendingUpload = null },
            onConfirm = { model.upload(file.name, file.contentType, file.sizeBytes, UriRequestBody(resolver, file.uri, file.contentType), analyze = false); pendingUpload = null },
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
) {
    MedicalPage("medical_archive_screen") {
        TextButton(onClick = onBack, modifier = Modifier.testTag("medical_archive_back")) { Text("‹ 返回") }
        Text("健康档案", style = MaterialTheme.typography.headlineMedium)
        Text("报告仅保存在你的私有档案中；解析候选须由你逐项确认。", style = MaterialTheme.typography.bodyMedium)
        Spacer(Modifier.height(16.dp))
        when {
            state.loading -> Text("正在加载你的档案…", modifier = Modifier.testTag("medical_archive_loading"))
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
                Text(parseStatusLabel(state.detail))
                Spacer(Modifier.height(12.dp))
                if (state.candidates.isEmpty()) Text("当前没有待你确认的字段。", modifier = Modifier.testTag("medical_candidates_empty"))
                state.candidates.forEachIndexed { index, candidate -> CandidateCard(candidate, index, onDecision) }
                Text("候选仅供你核对，不是诊断、处方或既成医疗事实。", style = MaterialTheme.typography.bodySmall)
            }
        }
        state.operationMessage?.let { Text(it, color = if (state.conflict) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary, modifier = Modifier.testTag("medical_detail_feedback")) }
    }
}

@Composable private fun CandidateCard(candidate: MedicalFieldCandidateDto, index: Int, onDecision: (MedicalFieldCandidateDto, String, String?) -> Unit) {
    var correctedValue by remember(candidate.id) { mutableStateOf("") }
    Column(Modifier.fillMaxWidth().padding(vertical = 10.dp).testTag("medical_candidate_$index")) {
        Text(candidate.fieldCode)
        Text(candidate.value?.toString() ?: "—")
        candidate.uncertainty?.let { Text("不确定性：$it") }
        if (candidate.reviewStatus == "pending") {
            TextButton(onClick = { onDecision(candidate, "accept", null) }, modifier = Modifier.testTag("medical_candidate_accept_$index")) { Text("确认") }
            TextButton(onClick = { onDecision(candidate, "reject", null) }, modifier = Modifier.testTag("medical_candidate_reject_$index")) { Text("不确认") }
            OutlinedTextField(value = correctedValue, onValueChange = { correctedValue = it }, label = { Text(if (candidate.valueType == "object") "纠正后的值（JSON 对象）" else "纠正后的值") }, modifier = Modifier.fillMaxWidth().testTag("medical_candidate_correct_value_$index"))
            TextButton(onClick = { onDecision(candidate, "correct", correctedValue) }, modifier = Modifier.testTag("medical_candidate_correct_$index")) { Text("提交纠正") }
        } else Text("已处理：${candidate.reviewStatus}")
    }
}

@Composable private fun UploadModeDialog(file: PickedMedicalFile, onDismiss: () -> Unit, onConfirm: () -> Unit) = AlertDialog(
    onDismissRequest = onDismiss,
    title = { Text("上传检查报告") },
    text = { Text("${file.name}\n本版本仅支持私有存档，不会发送解析请求。报告解析需要在上传前核验当前健康数据处理与第三方 AI 授权；该授权读取与引导尚未接入。") },
    confirmButton = { TextButton(onClick = onConfirm, modifier = Modifier.testTag("medical_upload_store_only")) { Text("仅存档") } },
)

private fun documentTypeLabel(type: String) = mapOf("lab_report" to "检验报告", "outpatient_record" to "门诊记录", "discharge_summary" to "出院小结", "diagnosis_certificate" to "诊断证明", "prescription" to "处方")[type] ?: "其他报告"
private fun parseStatusLabel(item: MedicalDocumentDto) = when (item.parseStatus) {
    "not_requested" -> "仅存档"
    "pending", "processing" -> "正在处理"
    "needs_confirmation" -> when (item.parseOutcome) { "insufficient_quality" -> "扫描质量不足"; "no_supported_facts" -> "未找到可支持字段"; else -> "待逐项确认" }
    "confirmed" -> "已确认"
    "failed" -> "处理失败"
    else -> "状态未知"
}

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
