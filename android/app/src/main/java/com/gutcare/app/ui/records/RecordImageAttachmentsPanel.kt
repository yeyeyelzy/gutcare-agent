package com.gutcare.app.ui.records

import android.graphics.BitmapFactory
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.gutcare.app.core.network.PatientRecordType
import com.gutcare.app.core.network.RecordImageAttachmentDto
import com.gutcare.app.core.network.RecordImageRecognitionCandidateDto
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private data class PickedImage(val name: String, val contentType: String, val bytes: ByteArray, val bitmap: android.graphics.Bitmap)

/** F03/F04 attachment UI. Persisted images are fetched only after requesting a fresh grant by
 * attachment ID; selected and downloaded image bytes remain in memory for this page only.
 */
@Composable
fun RecordImageAttachmentsPanel(
    type: PatientRecordType,
    recordId: String,
    recordVersion: Int,
    imageSetVersion: Int,
    state: RecordImagesUiState,
    confirmedFoodNames: List<String> = emptyList(),
    onLoad: (PatientRecordType, String, Int, Int) -> Unit,
    onUpload: (String, String, ByteArray) -> Unit,
    onDelete: (RecordImageAttachmentDto) -> Unit,
    onPreview: (RecordImageAttachmentDto) -> Unit,
    onClearPreview: () -> Unit,
    onRequestRecognition: (String?) -> Unit = {},
    onRefreshRecognition: () -> Unit = {},
    onDismissRecognitionDisclosure: () -> Unit = {},
    onAcceptRecognitionDisclosure: () -> Unit = {},
    onOpenConsentSettings: () -> Unit = {},
    onDecideCandidate: (RecordImageRecognitionCandidateDto, String, String?) -> Unit = { _, _, _ -> },
    onReturnToDietForm: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var picked by remember(recordId) { mutableStateOf<PickedImage?>(null) }
    var pickError by remember(recordId) { mutableStateOf<String?>(null) }
    var downloadedPreview by remember(recordId) { mutableStateOf<android.graphics.Bitmap?>(null) }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val result = withContext(Dispatchers.IO) { readPickedImage(context, uri) }
            result.fold(
                onSuccess = { picked = it; pickError = null },
                onFailure = { pickError = it.message ?: "无法读取所选图片。" },
            )
        }
    }
    LaunchedEffect(type, recordId, recordVersion, imageSetVersion) { onLoad(type, recordId, recordVersion, imageSetVersion) }
    LaunchedEffect(state.previewImageId, state.previewBytes) {
        downloadedPreview = state.previewBytes?.let { bytes -> withContext(Dispatchers.IO) { decodePreview(bytes) } }
    }

    state.recognitionDisclosure?.let { notice ->
        AlertDialog(
            onDismissRequest = onDismissRecognitionDisclosure,
            title = { Text(if (type == PatientRecordType.DIET) "饮食图片识别告知" else "排便图片识别告知") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOfNotNull(notice.summary, notice.purposeText, notice.dataScope, notice.recipient, notice.retention, notice.withdrawalEffect).forEach { Text(it) }
                    Text(
                        if (type == PatientRecordType.STOOL) {
                            "本次将所选排便图片交由已披露的智能服务生成 AI 辅助 Bristol 分类并直接展示；结果不会写入已确认的患者事实。"
                        } else {
                            "本次将所选饮食图片交由已披露的智能服务生成待确认候选。候选不会自动写入记录。"
                        },
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            },
            confirmButton = {
                Button(onClick = onAcceptRecognitionDisclosure, enabled = notice.enabled) {
                    Text(if (type == PatientRecordType.STOOL) "同意并展示 Bristol 分类" else "同意并生成待确认候选")
                }
            },
            dismissButton = { TextButton(onClick = onDismissRecognitionDisclosure) { Text("暂不") } },
        )
    }

    Column(
        modifier.fillMaxWidth()
            .verticalScroll(rememberScrollState())
            .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(20.dp))
            .padding(16.dp)
            .testTag("record_images_panel"),
    ) {
        Text("记录图片", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(6.dp))
        Text(if (type == PatientRecordType.DIET) "饮食记录最多添加 10 张 JPEG/PNG 图片。" else "排便记录最多添加 1 张 JPEG/PNG 图片。",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(8.dp))
        if (state.loading) Text("正在读取图片附件…", modifier = Modifier.testTag("record_images_loading"))
        state.images.forEach { image ->
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                Column(Modifier.weight(1f)) {
                    Text("图片 ${image.position + 1} · ${if (image.fileStatus == "available") "安全扫描通过" else "不可用"}",
                        style = MaterialTheme.typography.bodyMedium)
                    Text("关联于 ${image.createdAt}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                TextButton(onClick = { onPreview(image) }, enabled = image.fileStatus == "available" &&
                    state.previewLoadingImageId != image.id, modifier = Modifier.testTag("record_image_preview_${image.position}")) {
                    Text(if (state.previewLoadingImageId == image.id) "加载中" else "查看")
                }
                TextButton(onClick = { onDelete(image) }, enabled = state.deletingImageId != image.id, modifier = Modifier.testTag("record_image_remove_${image.position}")) {
                    Text(if (state.deletingImageId == image.id) "移除中" else "移除")
                }
            }
        }
        if (state.previewImageId != null && downloadedPreview != null) {
            Spacer(Modifier.height(8.dp))
            Image(bitmap = downloadedPreview!!.asImageBitmap(), contentDescription = "已关联记录图片预览",
                modifier = Modifier.fillMaxWidth().height(180.dp).testTag("record_image_downloaded_preview"))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                TextButton(onClick = { downloadedPreview = null; onClearPreview() }) { Text("关闭预览") }
            }
            Text("图片通过短时授权读取，仅保留在当前页面内存中。", style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        picked?.let { image ->
            Spacer(Modifier.height(8.dp))
            Image(bitmap = image.bitmap.asImageBitmap(), contentDescription = "本次选中的图片预览",
                modifier = Modifier.fillMaxWidth().height(180.dp).testTag("record_image_temporary_preview"))
            Text(image.name, style = MaterialTheme.typography.bodySmall)
            Text("临时预览仅保留在当前页面内存中。", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            OutlinedButton(onClick = { onUpload(image.name, image.contentType, image.bytes) }, enabled = state.canAdd && !state.uploading,
                modifier = Modifier.fillMaxWidth().testTag("record_image_upload")) {
                Text(if (state.uploading) "安全上传中…" else "安全上传并关联")
            }
        }
        pickError?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("record_image_pick_error")) }
        state.message?.takeUnless {
            !state.isError && (state.recognition?.status == "candidates_ready" || type == PatientRecordType.STOOL)
        }?.let { Text(it, color = if (state.isError) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.testTag("record_image_feedback")) }
        if (state.needsConsentSettings) {
            TextButton(onClick = onOpenConsentSettings, modifier = Modifier.testTag("record_image_open_consent_settings")) {
                Text("前往授权设置")
            }
        }
        state.recognition?.let { request ->
            Spacer(Modifier.height(8.dp))
            if (type == PatientRecordType.DIET && request.status != "candidates_ready") {
                Text("图片识别：${recognitionStatusLabel(request.status, type)}", style = MaterialTheme.typography.titleSmall,
                    modifier = Modifier.testTag("record_image_recognition_status"))
            }
            if (request.status == "candidates_ready") {
                if (type == PatientRecordType.DIET) {
                    confirmedFoodNames.map(String::trim).filter(String::isNotEmpty).distinct().forEach { name ->
                        Text(name, style = MaterialTheme.typography.titleMedium, modifier = Modifier.testTag("record_image_confirmed_food_name"))
                    }
                }
                val visibleCandidates = request.candidates.filter { candidate ->
                    if (type == PatientRecordType.DIET) candidate.candidateType == "food_name" && candidate.status == "pending" && candidate.requiresPatientConfirmation
                    else candidate.candidateType == "bristol_type"
                }
                visibleCandidates.forEach { candidate ->
                    if (type == PatientRecordType.STOOL) {
                        candidate.value?.toString()?.takeIf(String::isNotBlank)?.let { value ->
                            Text("识别结果：$value", style = MaterialTheme.typography.titleMedium,
                                modifier = Modifier.testTag("record_image_stool_result"))
                        }
                    } else {
                        RecognitionCandidateCard(candidate, type, state.recognitionBusy) { action, corrected -> onDecideCandidate(candidate, action, corrected) }
                    }
                }
                if (visibleCandidates.isEmpty() && type == PatientRecordType.DIET) {
                    Text("当前没有可展示的待确认候选。")
                }
                if (type == PatientRecordType.DIET && (state.dietFoodSaved || confirmedFoodNames.isNotEmpty())) {
                    Spacer(Modifier.height(10.dp))
                    Button(
                        onClick = onReturnToDietForm,
                        modifier = Modifier.fillMaxWidth().testTag("record_image_return_to_diet_form"),
                    ) { Text("返回饮食记录并保存") }
                }
            }
            if (type == PatientRecordType.DIET && request.status != "candidates_ready") {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextButton(onClick = onRefreshRecognition, enabled = !state.recognitionBusy) { Text("刷新任务") }
                    if (request.status in setOf("failed", "cancelled", "invalidated")) {
                        TextButton(onClick = { onRequestRecognition(request.id) }, enabled = !state.recognitionBusy) { Text("重新识别") }
                    }
                }
            } else if (type == PatientRecordType.STOOL && request.status in setOf("failed", "cancelled", "invalidated")) {
                TextButton(onClick = { onRequestRecognition(request.id) }, enabled = !state.recognitionBusy) {
                    Text(if (state.recognitionBusy) "准备重新识别…" else "重新识别")
                }
            }
        }
        if (state.recognition == null) {
            OutlinedButton(onClick = { onRequestRecognition(null) }, enabled = state.images.isNotEmpty() && !state.recognitionBusy,
                modifier = Modifier.fillMaxWidth().testTag("record_image_recognition_start")) {
                Text(if (state.recognitionBusy) "读取识别告知…" else "发起图片识别")
            }
            if (state.images.isEmpty()) Text("请先安全上传并关联图片，再发起识别。", style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.testTag("record_image_recognition_disabled_reason"))
        }
        if (state.recognitionBusy && type == PatientRecordType.DIET) Text("正在处理识别请求…")
        OutlinedButton(onClick = { picker.launch("image/*") }, enabled = state.canAdd && !state.uploading,
            modifier = Modifier.fillMaxWidth().testTag("record_image_pick")) {
            Text(if (picked == null) "选择图片" else "重新选择")
        }
    }
}

private fun decodePreview(bytes: ByteArray): android.graphics.Bitmap? {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
    if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
    val sample = generateSequence(1) { it * 2 }
        .takeWhile { bounds.outWidth / it > 1600 || bounds.outHeight / it > 1600 }.lastOrNull() ?: 1
    return BitmapFactory.decodeByteArray(bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = sample })
}

private val FOOD_CATEGORIES = setOf("grain_staple", "vegetable", "fruit", "meat", "seafood", "dairy", "egg", "legume", "snack", "beverage", "mixed_dish", "other")

@Composable
private fun RecognitionCandidateCard(
    candidate: RecordImageRecognitionCandidateDto,
    type: PatientRecordType,
    busy: Boolean,
    onDecision: (String, String?) -> Unit,
) {
    var correction by remember(candidate.id) { mutableStateOf("") }
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, RoundedCornerShape(14.dp)).padding(12.dp)
        .testTag("record_image_candidate_${candidate.id}"), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        if (type == PatientRecordType.DIET) {
            val foodName = candidate.value?.toString()?.trim().orEmpty()
            Text(foodName.ifBlank { "未识别出食物名称" }, style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.testTag("record_image_pending_food_name_${candidate.id}"))
            OutlinedTextField(correction, { correction = it.take(160) }, label = { Text("修正食物名称") }, modifier = Modifier.fillMaxWidth())
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                TextButton(onClick = { onDecision("accept", null) }, enabled = !busy && foodName.isNotBlank()) { Text("确认") }
                TextButton(onClick = { onDecision("edit", correction) }, enabled = !busy && correction.isNotBlank()) { Text("修正并确认") }
                TextButton(onClick = { onDecision("reject", null) }, enabled = !busy) { Text("拒绝") }
            }
            return@Column
        }
        val directStoolResult = type == PatientRecordType.STOOL
        Text(if (directStoolResult) "AI 辅助 Bristol 分类" else when (candidate.candidateType) {
            "food_name" -> "食物名称候选"
            "food_category" -> "食物类别候选"
            "portion_description" -> "份量描述候选"
            "bristol_type" -> "Bristol 类型候选"
            else -> "候选"
        }, fontWeight = FontWeight.SemiBold)
        Text("${if (directStoolResult) "识别结果" else "候选值"}：${candidate.value?.toString() ?: "—"}")
        if (!directStoolResult) {
            Text("置信等级：${candidate.confidenceBand}；不确定性：${candidate.uncertaintyCode}")
        }
        if (directStoolResult || !candidate.requiresPatientConfirmation) {
            Text("AI 辅助识别结果；不构成诊断，也不代表已确认的患者事实。", style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.testTag("record_image_direct_result_notice"))
        } else if (candidate.status == "pending") {
            val isBristol = type == PatientRecordType.STOOL
            if (candidate.candidateType == "food_category") {
                Text("受控类别代码：${FOOD_CATEGORIES.joinToString("、")}", style = MaterialTheme.typography.bodySmall)
                OutlinedTextField(correction, { correction = it.take(32) }, label = { Text("修正类别代码") }, modifier = Modifier.fillMaxWidth())
            } else if (isBristol) {
                OutlinedTextField(correction, { correction = it.filter(Char::isDigit).take(1) }, label = { Text("修正 Bristol 类型（1–7）") }, modifier = Modifier.fillMaxWidth())
            } else {
                OutlinedTextField(correction, { correction = it.take(160) }, label = { Text("修正候选值") }, modifier = Modifier.fillMaxWidth())
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                TextButton(onClick = { onDecision("accept", null) }, enabled = !busy) { Text("确认") }
                TextButton(onClick = { onDecision("edit", correction) }, enabled = !busy && correction.isNotBlank() &&
                    (candidate.candidateType != "food_category" || correction in FOOD_CATEGORIES) &&
                    (!isBristol || correction.toIntOrNull() in 1..7)) { Text("修正并确认") }
                TextButton(onClick = { onDecision("reject", null) }, enabled = !busy) { Text("拒绝") }
            }
        } else Text("处理状态：${candidate.status}")
    }
}

private fun recognitionStatusLabel(status: String, type: PatientRecordType) = when (status) {
    "pending" -> "等待处理"; "processing" -> "处理中"
    "candidates_ready" -> if (type == PatientRecordType.STOOL) "分类结果已生成" else "候选待确认"
    "no_candidates" -> "没有可用候选"; "failed" -> "失败"; "cancelled" -> "已取消"; "invalidated" -> "已失效"; else -> "未知状态"
}

private fun readPickedImage(context: android.content.Context, uri: Uri): Result<PickedImage> = runCatching {
    val resolver = context.contentResolver
    val type = resolver.getType(uri)?.lowercase()?.substringBefore(';')
    require(type == "image/jpeg" || type == "image/png") { "仅支持 JPEG 或 PNG 图片。" }
    val name = resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
        if (cursor.moveToFirst()) cursor.getString(0) else null
    }?.takeIf(String::isNotBlank) ?: "record-image.${if (type == "image/png") "png" else "jpg"}"
    val bytes = resolver.openInputStream(uri)?.use { input ->
        val output = java.io.ByteArrayOutputStream()
        val buffer = ByteArray(8192)
        var total = 0
        while (true) {
            val count = input.read(buffer)
            if (count < 0) break
            total += count
            require(total <= 10 * 1024 * 1024) { "图片不能超过 10 MiB。" }
            output.write(buffer, 0, count)
        }
        output.toByteArray()
    } ?: error("无法读取所选图片。")
    require(bytes.isNotEmpty()) { "图片内容为空。" }
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
    require(bounds.outWidth > 0 && bounds.outHeight > 0) { "无法解析图片，请选择有效的 JPEG 或 PNG 文件。" }
    val sample = generateSequence(1) { it * 2 }.takeWhile { bounds.outWidth / it > 1600 || bounds.outHeight / it > 1600 }.lastOrNull() ?: 1
    val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = sample })
        ?: error("无法解析图片，请选择有效的 JPEG 或 PNG 文件。")
    PickedImage(name, type, bytes, bitmap)
}
