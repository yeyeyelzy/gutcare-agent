package com.gutcare.app.ui.records

import android.graphics.BitmapFactory
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
    onLoad: (PatientRecordType, String, Int, Int) -> Unit,
    onUpload: (String, String, ByteArray) -> Unit,
    onDelete: (RecordImageAttachmentDto) -> Unit,
    onPreview: (RecordImageAttachmentDto) -> Unit,
    onClearPreview: () -> Unit,
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

    Column(modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, RoundedCornerShape(20.dp)).testTag("record_images_panel")) {
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
        state.message?.let { Text(it, color = if (state.isError) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.testTag("record_image_feedback")) }
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
