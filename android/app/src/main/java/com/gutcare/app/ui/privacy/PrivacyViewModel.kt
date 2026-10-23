package com.gutcare.app.ui.privacy

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.gutcare.app.core.network.ApiResult
import com.gutcare.app.core.network.ConsentNoticeDto
import com.gutcare.app.core.network.ConsentStatusDto
import com.gutcare.app.core.network.PrivacyDeletionStatusDto
import com.gutcare.app.core.network.PrivacyExportDetailDto
import com.gutcare.app.core.network.PrivacyExportPreviewDto
import com.gutcare.app.core.network.PrivacyExportSummaryDto
import com.gutcare.app.core.network.PrivacyRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

interface PrivacyGateway {
    suspend fun consents(): ApiResult<List<ConsentStatusDto>>
    suspend fun notice(type: String): ApiResult<ConsentNoticeDto>
    suspend fun decide(type: String, version: String, granted: Boolean): ApiResult<ConsentStatusDto>
    suspend fun deleteAccount(): ApiResult<com.gutcare.app.core.network.PrivacyDeletionAcceptedDto>
    suspend fun deletionStatus(id: String, receipt: String): ApiResult<PrivacyDeletionStatusDto>
    suspend fun createExport(categories: List<String>): ApiResult<PrivacyExportPreviewDto>
    suspend fun exports(): ApiResult<List<PrivacyExportSummaryDto>>
    suspend fun export(id: String): ApiResult<PrivacyExportDetailDto>
    suspend fun confirmExport(id: String): ApiResult<Unit>
    suspend fun cancelExport(id: String): ApiResult<Unit>
    suspend fun download(capability: String): ApiResult<ByteArray>
}

class RepositoryPrivacyGateway(private val repository: PrivacyRepository) : PrivacyGateway {
    override suspend fun consents() = repository.consents()
    override suspend fun notice(type: String) = repository.notice(type)
    override suspend fun decide(type: String, version: String, granted: Boolean) = repository.decide(type, version, granted)
    override suspend fun deleteAccount() = repository.deleteAccount()
    override suspend fun deletionStatus(id: String, receipt: String) = repository.deletionStatus(id, receipt)
    override suspend fun createExport(categories: List<String>) = repository.createExport(categories)
    override suspend fun exports() = repository.exports()
    override suspend fun export(id: String) = repository.export(id)
    override suspend fun confirmExport(id: String) = repository.confirmExport(id)
    override suspend fun cancelExport(id: String) = repository.cancelExport(id)
    override suspend fun download(capability: String) = repository.download(capability)
}

class PrivacyViewModelFactory(private val gateway: PrivacyGateway) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        require(modelClass.isAssignableFrom(PrivacyViewModel::class.java))
        return PrivacyViewModel(gateway) as T
    }
}

data class PrivacyUiState(
    val loading: Boolean = false,
    val saving: Boolean = false,
    val consents: Map<String, ConsentStatusDto> = emptyMap(),
    val pendingNotice: ConsentNoticeDto? = null,
    val error: String? = null,
    val message: String? = null,
    val exportSelection: Set<String> = setOf("profile", "consents", "diet", "stool", "symptoms"),
    val preview: PrivacyExportPreviewDto? = null,
    val exports: List<PrivacyExportSummaryDto> = emptyList(),
    val activeExport: PrivacyExportDetailDto? = null,
    val exportBytes: ByteArray? = null,
    val deletionOperation: PrivacyDeletionStatusDto? = null,
    val deletionOperationId: String? = null,
    val deletionReceiptTransient: String? = null,
)

class PrivacyViewModel(private val gateway: PrivacyGateway) : ViewModel() {
    private val mutable = MutableStateFlow(PrivacyUiState())
    val uiState: StateFlow<PrivacyUiState> = mutable.asStateFlow()
    private var deletionReceipt: String? = null // ephemeral only; intentionally never saved across process death.

    fun load() = run { mutable.value = mutable.value.copy(loading = true, error = null); launch {
        when (val response = gateway.consents()) {
            is ApiResult.Success -> mutable.value = mutable.value.copy(loading = false, consents = response.value.associateBy { it.consentType })
            is ApiResult.Failure -> fail(response.code)
        }
        loadExports()
    } }

    fun requestGrantNotice(type: String) = launch {
        mutable.value = mutable.value.copy(saving = true, error = null, message = null)
        when (val result = gateway.notice(type)) {
            is ApiResult.Success -> mutable.value = mutable.value.copy(saving = false, pendingNotice = result.value.takeIf { it.enabled && !it.policyVersion.isNullOrBlank() }, error = if (!result.value.enabled) "当前服务端告知暂不可用，未提交授权。" else null)
            is ApiResult.Failure -> fail(result.code)
        }
    }

    fun closeNotice() { mutable.value = mutable.value.copy(pendingNotice = null) }

    fun confirmGrant() {
        val notice = mutable.value.pendingNotice ?: return
        val version = notice.policyVersion ?: return
        decide(notice.consentType, version, true)
    }

    fun revoke(type: String) {
        val version = mutable.value.consents[type]?.takeIf { it.granted }?.policyVersion ?: run { mutable.value = mutable.value.copy(error = "当前没有可撤回的授权。"); return }
        decide(type, version, false)
    }

    private fun decide(type: String, version: String, granted: Boolean) = launch {
        mutable.value = mutable.value.copy(saving = true, pendingNotice = null, error = null, message = null)
        when (val result = gateway.decide(type, version, granted)) {
            is ApiResult.Success -> mutable.value = mutable.value.copy(saving = false, consents = mutable.value.consents + (type to result.value), message = if (granted) "授权已保存。" else "授权已撤回；后续处理立即按服务端规则生效。")
            is ApiResult.Failure -> fail(result.code)
        }
    }

    fun toggleCategory(category: String) {
        val next = mutable.value.exportSelection.toMutableSet().apply { if (!add(category)) remove(category) }
        mutable.value = mutable.value.copy(exportSelection = next, preview = null, error = null)
    }

    fun createPreview() = launch {
        val selected = mutable.value.exportSelection.toList()
        if (selected.isEmpty()) { mutable.value = mutable.value.copy(error = "至少选择一类数据。"); return@launch }
        mutable.value = mutable.value.copy(saving = true, error = null, message = null, preview = null)
        when (val result = gateway.createExport(selected)) {
            is ApiResult.Success -> mutable.value = mutable.value.copy(saving = false, preview = result.value, message = "预览已创建；确认后才会开始生成。")
            is ApiResult.Failure -> fail(result.code)
        }
    }

    fun confirmPreview() {
        val id = mutable.value.preview?.exportId ?: return
        launch {
            mutable.value = mutable.value.copy(saving = true, error = null)
            when (val result = gateway.confirmExport(id)) {
                is ApiResult.Success -> { mutable.value = mutable.value.copy(saving = false, preview = null, message = "已确认生成。可刷新导出状态查看进度。"); loadExports() }
                is ApiResult.Failure -> fail(result.code)
            }
        }
    }

    fun loadExports() = launch {
        when (val result = gateway.exports()) {
            is ApiResult.Success -> mutable.value = mutable.value.copy(exports = result.value)
            is ApiResult.Failure -> if (result.code != "NETWORK_ERROR") mutable.value = mutable.value.copy(error = result.code ?: "导出列表读取失败。")
        }
    }

    fun refreshExport(id: String) = launch {
        mutable.value = mutable.value.copy(saving = true, error = null)
        when (val result = gateway.export(id)) {
            is ApiResult.Success -> mutable.value = mutable.value.copy(saving = false, activeExport = result.value) // capability kept in this state only while screen is alive.
            is ApiResult.Failure -> fail(result.code)
        }
    }

    fun cancelExport(id: String) = launch {
        when (val result = gateway.cancelExport(id)) {
            is ApiResult.Success -> { mutable.value = mutable.value.copy(activeExport = null, preview = mutable.value.preview?.takeUnless { it.exportId == id }, message = "导出已取消。"); loadExports() }
            is ApiResult.Failure -> fail(result.code)
        }
    }

    fun downloadReadyExport() {
        val capability = mutable.value.activeExport?.takeIf { it.status == "ready" }?.downloadCapability ?: run { mutable.value = mutable.value.copy(error = "下载能力不可用或已过期，请刷新导出状态。"); return }
        launch {
            mutable.value = mutable.value.copy(saving = true, exportBytes = null, error = null)
            when (val result = gateway.download(capability)) {
                is ApiResult.Success -> mutable.value = mutable.value.copy(saving = false, exportBytes = result.value, activeExport = mutable.value.activeExport?.copy(downloadCapability = null), message = "导出文件已接收，可立即保存。下载能力已清除。")
                is ApiResult.Failure -> mutable.value = mutable.value.copy(saving = false, activeExport = mutable.value.activeExport?.copy(downloadCapability = null), error = result.code ?: "下载失败；一次性能力已清除，请刷新状态重试。")
            }
        }
    }

    fun clearExportBytes() { mutable.value = mutable.value.copy(exportBytes = null) }
    fun clearSensitiveTransient() {
        deletionReceipt = null
        mutable.value = mutable.value.copy(
            exportBytes = null,
            activeExport = mutable.value.activeExport?.copy(downloadCapability = null),
            deletionReceiptTransient = null,
        )
    }

    fun requestDeletion() = launch {
        mutable.value = mutable.value.copy(saving = true, error = null, message = null)
        when (val result = gateway.deleteAccount()) {
            is ApiResult.Success -> {
                val accepted = result.value
                deletionReceipt = accepted.receipt
                mutable.value = mutable.value.copy(saving = false, deletionOperationId = accepted.operationId, deletionReceiptTransient = accepted.receipt, message = if (accepted.receipt != null) "账户已冻结。请立即复制并安全保存本次一次性进度凭据；凭据只保存在当前内存，离开页面后不可恢复。" else "已有注销操作；本次服务端未重新发放进度凭据。")
                queryDeletionStatus()
            }
            is ApiResult.Failure -> fail(result.code)
        }
    }

    fun queryDeletionStatus() = launch {
        val id = mutable.value.deletionOperationId ?: return@launch
        val receipt = deletionReceipt ?: run { mutable.value = mutable.value.copy(error = "未持有一次性凭据，无法查询操作进度。"); return@launch }
        when (val result = gateway.deletionStatus(id, receipt)) {
            is ApiResult.Success -> mutable.value = mutable.value.copy(deletionOperation = result.value, error = null)
            is ApiResult.Failure -> mutable.value = mutable.value.copy(error = result.code ?: "注销进度暂不可用。")
        }
    }

    private fun launch(block: suspend () -> Unit) = viewModelScope.launch { block() }
    private fun fail(code: String?) { mutable.value = mutable.value.copy(loading = false, saving = false, error = code ?: "请求失败，请稍后重试。") }
}

val privacyExportCategories = listOf(
    "profile" to "基础资料", "consents" to "授权记录", "medical_documents" to "医疗档案", "files" to "文件",
    "diet" to "饮食记录", "stool" to "排便记录", "symptoms" to "症状记录", "mood" to "心情记录",
    "medication" to "用药记录", "activity" to "活动记录", "analysis" to "分析记录", "advice" to "建议",
    "alerts" to "风险提醒", "notifications" to "站内通知",
)
