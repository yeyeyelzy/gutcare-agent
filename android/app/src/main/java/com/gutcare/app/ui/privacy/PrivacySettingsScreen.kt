package com.gutcare.app.ui.privacy

import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import android.widget.Toast
import com.gutcare.app.core.network.ConsentNoticeDto
import com.gutcare.app.core.network.PrivacyRepository
import com.gutcare.app.ui.design.GutCareCard
import com.gutcare.app.ui.design.GutCarePage
import com.gutcare.app.ui.design.GutCarePrimaryButton
import com.gutcare.app.ui.design.GutCareSecondaryButton

/** Wire this entry from the authenticated "我的" area; repository uses the app's authenticated API client. */
@Composable
fun PrivacySettingsEntry(
    repository: PrivacyRepository,
    onBack: () -> Unit,
    model: PrivacyViewModel = viewModel(factory = PrivacyViewModelFactory(RepositoryPrivacyGateway(repository))),
) {
    val state by model.uiState.collectAsState()
    val context = LocalContext.current
    val clipboard = LocalClipboardManager.current
    var pendingSaveBytes by remember { mutableStateOf<ByteArray?>(null) }
    val saveExport = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/zip")) { uri ->
        val bytes = pendingSaveBytes
        pendingSaveBytes = null
        if (uri != null && bytes != null) {
            val result = runCatching {
                context.contentResolver.openOutputStream(uri)?.use { it.write(bytes) } ?: error("Destination unavailable")
            }
            Toast.makeText(context, if (result.isSuccess) "导出 ZIP 已保存" else "保存失败，请重新下载后重试", Toast.LENGTH_SHORT).show()
        }
        model.clearExportBytes()
    }
    var showDeleteConfirmation by remember { mutableStateOf(false) }
    var showRevokeType by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) { model.load() }
    BackHandler { model.clearSensitiveTransient(); onBack() }
    PrivacySettingsScreen(
        state = state,
        onBack = { model.clearSensitiveTransient(); onBack() },
        onRefresh = { model.load() },
        onGrant = model::requestGrantNotice,
        onConfirmGrant = model::confirmGrant,
        onCloseNotice = model::closeNotice,
        onRevoke = { showRevokeType = it },
        onToggleCategory = model::toggleCategory,
        onPreview = model::createPreview,
        onConfirmPreview = model::confirmPreview,
        onClosePreview = { state.preview?.exportId?.let(model::cancelExport) },
        onRefreshExports = model::loadExports,
        onOpenExport = model::refreshExport,
        onCancelExport = model::cancelExport,
        onDownload = model::downloadReadyExport,
        onSaveExport = { bytes -> pendingSaveBytes = bytes; saveExport.launch("GutCare-privacy-export.zip") },
        onCopyDeletionReceipt = { value -> clipboard.setText(AnnotatedString(value)); Toast.makeText(context, "一次性进度凭据已复制", Toast.LENGTH_SHORT).show() },
        onRequestDelete = { showDeleteConfirmation = true },
        onConfirmDelete = { showDeleteConfirmation = false; model.requestDeletion() },
        onQueryDeletion = model::queryDeletionStatus,
    )

    state.pendingNotice?.let { notice ->
        ConsentNoticeDialog(notice, onDismiss = model::closeNotice, onConfirm = model::confirmGrant)
    }
    showRevokeType?.let { type ->
        AlertDialog(
            onDismissRequest = { showRevokeType = null },
            title = { Text("撤回授权？") },
            text = { Text("撤回后将立即影响后续数据处理。历史合法处理不会被追溯改写；是否继续撤回“${consentTitle(type)}”？") },
            confirmButton = { TextButton(onClick = { model.revoke(type); showRevokeType = null }) { Text("确认撤回") } },
            dismissButton = { TextButton(onClick = { showRevokeType = null }) { Text("取消") } },
        )
    }
    if (showDeleteConfirmation) {
        AlertDialog(
            onDismissRequest = { showDeleteConfirmation = false },
            title = { Text("申请注销账号") },
            text = { Text("提交后账号会立即冻结、撤销授权和会话，并启动最长 30 天的数据清理。该操作不可撤销。首次受理会返回一次性进度凭据，请妥善保存。") },
            confirmButton = { TextButton(onClick = { showDeleteConfirmation = false; model.requestDeletion() }) { Text("确认注销") } },
            dismissButton = { TextButton(onClick = { showDeleteConfirmation = false }) { Text("返回") } },
        )
    }
}

@Composable
private fun ConsentNoticeDialog(notice: ConsentNoticeDto, onDismiss: () -> Unit, onConfirm: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("单独授权告知 · ${consentTitle(notice.consentType)}") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("版本：${notice.policyVersion.orEmpty()}")
                Text(notice.summary.orEmpty())
                notice.purpose?.let { Text("用途：$it") }
                notice.dataScope?.let { Text("数据范围：$it") }
                notice.recipient?.let { Text("接收方：$it") }
                notice.withdrawalEffect?.let { Text("撤回影响：$it") }
                Text("仅在阅读并同意本次告知后继续。", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        },
        confirmButton = { TextButton(onClick = onConfirm) { Text("同意并开启") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("暂不授权") } },
    )
}

@Composable
fun PrivacySettingsScreen(
    state: PrivacyUiState,
    onBack: () -> Unit,
    onRefresh: () -> Unit,
    onGrant: (String) -> Unit,
    onConfirmGrant: () -> Unit,
    onCloseNotice: () -> Unit,
    onRevoke: (String) -> Unit,
    onToggleCategory: (String) -> Unit,
    onPreview: () -> Unit,
    onConfirmPreview: () -> Unit,
    onClosePreview: () -> Unit,
    onRefreshExports: () -> Unit,
    onOpenExport: (String) -> Unit,
    onCancelExport: (String) -> Unit,
    onDownload: () -> Unit,
    onSaveExport: (ByteArray) -> Unit,
    onCopyDeletionReceipt: (String) -> Unit,
    onRequestDelete: () -> Unit,
    onConfirmDelete: () -> Unit,
    onQueryDeletion: () -> Unit,
) {
    GutCarePage(modifier = Modifier.testTag("privacy_settings_screen")) {
        Spacer(Modifier.height(18.dp))
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            TextButton(onClick = onBack) { Text("‹ 返回") }
            Text("隐私与授权", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.weight(1f))
            TextButton(onClick = onRefresh) { Text("刷新") }
        }
        Spacer(Modifier.height(12.dp))
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("privacy_error")) }
        state.message?.let { Text(it, color = MaterialTheme.colorScheme.primary, modifier = Modifier.testTag("privacy_message")) }

        if (state.deletionOperationId == null) PrivacySection("数据处理授权", "授权按用途分别管理；未开启时相应处理受限。") {
            ConsentRow("health_data_processing", "健康数据处理", state, onGrant, onRevoke)
            ConsentRow("mood_data_processing", "心情记录处理", state, onGrant, onRevoke)
            ConsentRow("mood_ai_sharing", "向智能体共享心情", state, onGrant, onRevoke)
            ConsentRow("third_party_ai", "第三方 AI 处理", state, onGrant, onRevoke)
            ConsentRow("sensitive_image", "敏感图片处理", state, onGrant, onRevoke)
            ConsentRow("push_notification", "系统推送", state, onGrant, onRevoke)
            Text("privacy_policy 仅可通过账号注销撤回。", style = MaterialTheme.typography.bodySmall)
        }

        if (state.deletionOperationId == null) PrivacySection("导出本人数据", "先选择导出类别并查看预览；确认后服务端才开始异步生成。") {
            privacyExportCategories.forEach { (key, title) ->
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth().testTag("privacy_export_$key")) {
                    Checkbox(checked = key in state.exportSelection, onCheckedChange = { onToggleCategory(key) })
                    Text(title)
                }
            }
            GutCarePrimaryButton("创建导出预览", onPreview, enabled = !state.saving, testTag = "privacy_export_preview")
            state.preview?.let { preview ->
                Text("预览：${preview.categories.joinToString { exportCategoryName(it) }}；状态：${preview.status}")
                GutCarePrimaryButton("确认并生成", onConfirmPreview, enabled = !state.saving, testTag = "privacy_export_confirm")
                TextButton(onClick = onClosePreview) { Text("预览保留在本页") }
            }
        }

        if (state.deletionOperationId == null) PrivacySection("导出任务", "能力仅在当前内存短暂使用，刷新详情可重新取得一次性下载能力。") {
            GutCareSecondaryButton("刷新导出列表", onRefreshExports, enabled = !state.saving)
            state.exports.forEach { item ->
                Text("${exportCategoryName(item.categories.firstOrNull().orEmpty())} 等 ${item.categories.size} 类 · ${exportStatus(item.status)}")
                Text("创建于 ${item.createdAt}", style = MaterialTheme.typography.bodySmall)
                TextButton(onClick = { onOpenExport(item.exportId) }) { Text("查看状态") }
            }
            state.activeExport?.let { item ->
                Text("${exportStatus(item.status)} · ${item.exportId}", modifier = Modifier.testTag("privacy_export_status"))
                item.expiresAt?.let { Text("可用至 $it", style = MaterialTheme.typography.bodySmall) }
                if (item.status == "ready" && !item.downloadCapability.isNullOrBlank()) {
                    GutCarePrimaryButton("安全下载 ZIP", onDownload, enabled = !state.saving, testTag = "privacy_export_download")
                }
                if (item.status in setOf("preview", "pending", "processing")) TextButton(onClick = { onCancelExport(item.exportId) }) { Text("取消导出") }
            }
            state.exportBytes?.let { bytes ->
                Text("已下载 ${(bytes.size / 1024).coerceAtLeast(1)} KB。选择保存位置；文件内容不会写入应用日志。")
                GutCarePrimaryButton("保存 ZIP 文件", { onSaveExport(bytes) }, testTag = "privacy_export_save")
            }
        }

        PrivacySection("账号注销", "注销会冻结当前账号并开始清理流程。") {
            GutCarePrimaryButton("申请注销账号", onRequestDelete, enabled = !state.saving, testTag = "privacy_delete_account")
            state.deletionOperationId?.let {
                Text("操作编号：$it", style = MaterialTheme.typography.bodySmall)
                state.deletionReceiptTransient?.let { receipt ->
                    Text("一次性进度凭据（离开本页后将无法找回）", fontWeight = FontWeight.SemiBold)
                    Text(receipt, style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("privacy_deletion_receipt"))
                    TextButton(onClick = { onCopyDeletionReceipt(receipt) }) { Text("复制一次性凭据") }
                }
                state.deletionOperation?.let { progress ->
                    Text("清理状态：${deletionStatus(progress.status)}")
                    Text("受理时间：${progress.requestedAt} · 预计期限：${progress.dueAt}", style = MaterialTheme.typography.bodySmall)
                    progress.completedAt?.let { done -> Text("完成时间：$done") }
                }
                TextButton(onClick = onQueryDeletion) { Text("查询清理进度") }
            }
        }
        Spacer(Modifier.height(32.dp))
    }
}

@Composable
private fun PrivacySection(title: String, description: String, content: @Composable () -> Unit) {
    GutCareCard(modifier = Modifier.fillMaxWidth().padding(top = 14.dp)) {
        Column(modifier = Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
            Text(description, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            content()
        }
    }
}

@Composable
private fun ConsentRow(type: String, title: String, state: PrivacyUiState, onGrant: (String) -> Unit, onRevoke: (String) -> Unit) {
    val consent = state.consents[type]
    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(modifier = Modifier.weight(1f)) {
            Text(title, fontWeight = FontWeight.Medium)
            Text(if (consent?.granted == true) "已授权 · ${consent.policyVersion}" else "未授权", style = MaterialTheme.typography.bodySmall)
        }
        if (consent?.granted == true) TextButton(onClick = { onRevoke(type) }, enabled = !state.saving) { Text("撤回") }
        else if (type in grantableConsentTypes) TextButton(onClick = { onGrant(type) }, enabled = !state.saving) { Text("查看告知并授权") }
        else Text("由其他流程授权", style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(start = 8.dp))
    }
}

private val grantableConsentTypes = setOf("health_data_processing", "mood_data_processing", "mood_ai_sharing", "third_party_ai")
private fun consentTitle(type: String) = when (type) {
    "health_data_processing" -> "健康数据处理"
    "mood_data_processing" -> "心情记录处理"
    "mood_ai_sharing" -> "向智能体共享心情"
    "third_party_ai" -> "第三方 AI 处理"
    else -> type
}
private fun exportCategoryName(category: String) = privacyExportCategories.firstOrNull { it.first == category }?.second ?: category
private fun exportStatus(value: String) = when (value) {
    "preview" -> "待确认"; "pending" -> "排队中"; "processing" -> "生成中"; "ready" -> "可下载"
    "failed" -> "生成失败"; "cancelled" -> "已取消"; "expired" -> "已过期"; else -> value
}
private fun deletionStatus(value: String) = when (value) {
    "accepted", "pending" -> "等待处理"; "processing" -> "清理中"; "completed" -> "已完成"
    "overdue" -> "超出预计时间"; "dead_letter" -> "需要支持介入"; else -> value
}
