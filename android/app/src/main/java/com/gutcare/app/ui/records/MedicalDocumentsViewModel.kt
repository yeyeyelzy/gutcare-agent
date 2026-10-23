package com.gutcare.app.ui.records

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.gutcare.app.core.network.ApiResult
import com.gutcare.app.core.network.FileObjectDto
import com.gutcare.app.core.network.MedicalCandidateDecisionDto
import com.gutcare.app.core.network.MedicalDocumentCreateDto
import com.gutcare.app.core.network.MedicalDocumentDto
import com.gutcare.app.core.network.MedicalDocumentPageDto
import com.gutcare.app.core.network.MedicalDocumentsRepository
import com.gutcare.app.core.network.MedicalFieldCandidateDto
import com.gutcare.app.core.network.ConsentNoticeDto
import com.gutcare.app.core.network.ConsentStatusDto
import com.gutcare.app.core.network.ConfirmedMedicalFactDto
import com.gutcare.app.core.network.UploadCreateDto
import java.util.UUID
import com.squareup.moshi.Moshi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import okhttp3.RequestBody

interface MedicalDocumentsGateway {
    suspend fun list(cursor: String?): ApiResult<MedicalDocumentPageDto>
    suspend fun detail(id: String): ApiResult<MedicalDocumentDto>
    suspend fun candidates(documentId: String): ApiResult<List<MedicalFieldCandidateDto>>
    suspend fun confirmedFacts(): ApiResult<List<ConfirmedMedicalFactDto>>
    suspend fun decide(candidateId: String, key: String, body: MedicalCandidateDecisionDto): ApiResult<Unit>
    suspend fun upload(key: String, metadata: UploadCreateDto, content: RequestBody): ApiResult<FileObjectDto>
    suspend fun create(body: MedicalDocumentCreateDto): ApiResult<MedicalDocumentDto>
    suspend fun consents(): ApiResult<List<ConsentStatusDto>>
    suspend fun notice(type: String): ApiResult<ConsentNoticeDto>
    suspend fun grantConsent(type: String, policyVersion: String): ApiResult<ConsentStatusDto>
    suspend fun revokeConsent(type: String, policyVersion: String): ApiResult<ConsentStatusDto>
}

class RepositoryMedicalDocumentsGateway(private val repository: MedicalDocumentsRepository) : MedicalDocumentsGateway {
    override suspend fun list(cursor: String?) = repository.list(cursor)
    override suspend fun detail(id: String) = repository.detail(id)
    override suspend fun candidates(documentId: String) = repository.candidates(documentId)
    override suspend fun confirmedFacts() = repository.confirmedFacts()
    override suspend fun decide(candidateId: String, key: String, body: MedicalCandidateDecisionDto) = repository.decide(candidateId, key, body)
    override suspend fun upload(key: String, metadata: UploadCreateDto, content: RequestBody) = repository.upload(key, metadata, content)
    override suspend fun create(body: MedicalDocumentCreateDto) = repository.create(body)
    override suspend fun consents() = repository.consents()
    override suspend fun notice(type: String) = repository.notice(type)
    override suspend fun grantConsent(type: String, policyVersion: String) = repository.decideConsent(type, policyVersion)
    override suspend fun revokeConsent(type: String, policyVersion: String) = repository.decideConsent(type, policyVersion, granted = false)
}

class UnavailableMedicalDocumentsGateway : MedicalDocumentsGateway {
    private fun <T> unavailable() = ApiResult.Failure(null, "SERVICE_UNAVAILABLE") as ApiResult<T>
    override suspend fun list(cursor: String?) = unavailable<MedicalDocumentPageDto>()
    override suspend fun detail(id: String) = unavailable<MedicalDocumentDto>()
    override suspend fun candidates(documentId: String) = unavailable<List<MedicalFieldCandidateDto>>()
    override suspend fun confirmedFacts() = unavailable<List<ConfirmedMedicalFactDto>>()
    override suspend fun decide(candidateId: String, key: String, body: MedicalCandidateDecisionDto) = unavailable<Unit>()
    override suspend fun upload(key: String, metadata: UploadCreateDto, content: RequestBody) = unavailable<FileObjectDto>()
    override suspend fun create(body: MedicalDocumentCreateDto) = unavailable<MedicalDocumentDto>()
    override suspend fun consents() = unavailable<List<ConsentStatusDto>>()
    override suspend fun notice(type: String) = unavailable<ConsentNoticeDto>()
    override suspend fun grantConsent(type: String, policyVersion: String) = unavailable<ConsentStatusDto>()
    override suspend fun revokeConsent(type: String, policyVersion: String) = unavailable<ConsentStatusDto>()
}

data class MedicalArchiveUiState(
    val loading: Boolean = false,
    val documents: List<MedicalDocumentDto> = emptyList(),
    val error: String? = null,
    val detail: MedicalDocumentDto? = null,
    val detailLoading: Boolean = false,
    val candidates: List<MedicalFieldCandidateDto> = emptyList(),
    val confirmedFacts: List<ConfirmedMedicalFactDto> = emptyList(),
    val confirmedFactsError: String? = null,
    val detailError: String? = null,
    val operationMessage: String? = null,
    val conflict: Boolean = false,
    val uploading: Boolean = false,
    val consentLoading: Boolean = false,
    val consentStatus: Map<String, ConsentStatusDto> = emptyMap(),
    val pendingConsentNotice: ConsentNoticeDto? = null,
)

class MedicalDocumentsViewModel(private val gateway: MedicalDocumentsGateway) : ViewModel() {
    private val mutableState = MutableStateFlow(MedicalArchiveUiState())
    val uiState: StateFlow<MedicalArchiveUiState> = mutableState.asStateFlow()
    private data class PendingAnalyzeUpload(
        val fileName: String, val contentType: String, val sizeBytes: Long, val content: RequestBody,
        val documentType: String, val analyze: Boolean,
    )
    private var pendingAnalyzeUpload: PendingAnalyzeUpload? = null

    fun load() = viewModelScope.launch {
        mutableState.value = mutableState.value.copy(loading = true, error = null)
        when (val result = gateway.list(null)) {
            is ApiResult.Success -> mutableState.value = mutableState.value.copy(loading = false, documents = result.value.items, error = null)
            is ApiResult.Failure -> mutableState.value = mutableState.value.copy(loading = false, error = friendly(result))
        }
    }
    fun loadConsents() = viewModelScope.launch {
        mutableState.value = mutableState.value.copy(consentLoading = true)
        when (val result = gateway.consents()) {
            is ApiResult.Success -> mutableState.value = mutableState.value.copy(consentLoading = false, consentStatus = result.value.associateBy { it.consentType })
            is ApiResult.Failure -> mutableState.value = mutableState.value.copy(consentLoading = false, operationMessage = friendly(result))
        }
    }
    fun open(id: String) = viewModelScope.launch {
        mutableState.value = mutableState.value.copy(detailLoading = true, detailError = null, detail = null, candidates = emptyList(), confirmedFacts = emptyList(), confirmedFactsError = null)
        when (val result = gateway.detail(id)) {
            is ApiResult.Failure -> mutableState.value = mutableState.value.copy(detailLoading = false, detailError = friendly(result))
            is ApiResult.Success -> {
                mutableState.value = mutableState.value.copy(detailLoading = false, detail = result.value)
                loadCandidates(id)
                loadConfirmedFacts()
            }
        }
    }
    private suspend fun loadCandidates(id: String) {
        when (val result = gateway.candidates(id)) {
            is ApiResult.Success -> mutableState.value = mutableState.value.copy(candidates = result.value)
            is ApiResult.Failure -> mutableState.value = mutableState.value.copy(detailError = friendly(result))
        }
    }
    private suspend fun loadConfirmedFacts() {
        when (val result = gateway.confirmedFacts()) {
            is ApiResult.Success -> mutableState.value = mutableState.value.copy(confirmedFacts = result.value, confirmedFactsError = null)
            is ApiResult.Failure -> mutableState.value = mutableState.value.copy(confirmedFactsError = friendly(result))
        }
    }
    fun decide(candidate: MedicalFieldCandidateDto, action: String, correctedValue: String? = null) = viewModelScope.launch {
        if (action == "correct" && correctedValue.isNullOrBlank()) {
            mutableState.value = mutableState.value.copy(operationMessage = "请填写纠正后的字段值。", conflict = false)
            return@launch
        }
        val corrected = if (action == "correct") {
            if (candidate.valueType == "object") runCatching {
                Moshi.Builder().build().adapter(Any::class.java).fromJson(correctedValue!!)
                    ?: error("empty")
            }.getOrElse {
                mutableState.value = mutableState.value.copy(operationMessage = "该字段需要符合格式的 JSON 对象。", conflict = false)
                return@launch
            } else correctedValue
        } else null
        val body = MedicalCandidateDecisionDto(action, candidate.recordVersion, corrected)
        val result = gateway.decide(candidate.id, UUID.randomUUID().toString(), body)
        when (result) {
            is ApiResult.Success -> {
                mutableState.value = mutableState.value.copy(operationMessage = "已记录你的逐项确认。", conflict = false)
                mutableState.value.detail?.id?.let(::open)
            }
            is ApiResult.Failure -> {
                val conflict = result.status == 409
                mutableState.value = mutableState.value.copy(operationMessage = if (conflict) "内容已变化，已刷新最新状态，请再次确认。" else friendly(result), conflict = conflict)
                if (conflict) mutableState.value.detail?.id?.let(::open)
            }
        }
    }
    fun upload(fileName: String, contentType: String, sizeBytes: Long, content: RequestBody, analyze: Boolean, documentType: String = "other") = viewModelScope.launch {
        if (documentType !in setOf("outpatient_record", "discharge_summary", "diagnosis_certificate", "lab_report", "prescription", "other")) {
            mutableState.value = mutableState.value.copy(operationMessage = "请选择有效的报告类型。", conflict = false)
            return@launch
        }
        pendingAnalyzeUpload = PendingAnalyzeUpload(fileName, contentType, sizeBytes, content, documentType, analyze)
        mutableState.value = mutableState.value.copy(operationMessage = null, pendingConsentNotice = null, consentLoading = true)
        refreshConsentAndContinue()
    }

    fun confirmConsentNotice() = viewModelScope.launch {
        val notice = mutableState.value.pendingConsentNotice ?: return@launch
        val version = notice.policyVersion
        if (!notice.enabled || version.isNullOrBlank()) {
            mutableState.value = mutableState.value.copy(pendingConsentNotice = null, operationMessage = "服务端告知不可用，未提交授权。")
            pendingAnalyzeUpload = null
            return@launch
        }
        mutableState.value = mutableState.value.copy(consentLoading = true, pendingConsentNotice = null)
        when (val result = gateway.grantConsent(notice.consentType, version)) {
            is ApiResult.Failure -> {
                mutableState.value = mutableState.value.copy(consentLoading = false, operationMessage = friendly(result))
                pendingAnalyzeUpload = null
            }
            is ApiResult.Success -> {
                mutableState.value = mutableState.value.copy(consentStatus = mutableState.value.consentStatus + (result.value.consentType to result.value))
                refreshConsentAndContinue()
            }
        }
    }

    fun dismissConsentNotice() {
        mutableState.value = mutableState.value.copy(pendingConsentNotice = null, consentLoading = false, operationMessage = "未授予解析所需授权，文件尚未上传。")
        pendingAnalyzeUpload = null
    }

    fun revokeConsent(type: String) = viewModelScope.launch {
        val active = mutableState.value.consentStatus[type]?.takeIf { it.granted }
        val version = active?.policyVersion
        if (version.isNullOrBlank()) {
            mutableState.value = mutableState.value.copy(operationMessage = "当前没有可撤回的有效授权。")
            return@launch
        }
        mutableState.value = mutableState.value.copy(consentLoading = true, operationMessage = null)
        when (val result = gateway.revokeConsent(type, version)) {
            is ApiResult.Success -> mutableState.value = mutableState.value.copy(
                consentLoading = false,
                consentStatus = mutableState.value.consentStatus + (type to result.value),
                operationMessage = "${consentName(type)}已撤回；待处理解析将按服务端规则失效。",
            )
            is ApiResult.Failure -> mutableState.value = mutableState.value.copy(consentLoading = false, operationMessage = friendly(result))
        }
    }

    private suspend fun refreshConsentAndContinue(): Boolean {
        val upload = pendingAnalyzeUpload ?: return false
        val consents = when (val result = gateway.consents()) {
            is ApiResult.Failure -> {
                mutableState.value = mutableState.value.copy(consentLoading = false, operationMessage = friendly(result))
                pendingAnalyzeUpload = null
                return false
            }
            is ApiResult.Success -> result.value.associateBy { it.consentType }
        }
        mutableState.value = mutableState.value.copy(consentLoading = false, consentStatus = consents)
        val requiredConsents = if (upload.analyze) ANALYZE_CONSENTS else listOf(HEALTH_DATA_CONSENT)
        val missing = requiredConsents.firstOrNull { consents[it]?.granted != true }
        if (missing != null) {
            when (val notice = gateway.notice(missing)) {
                is ApiResult.Failure -> {
                    mutableState.value = mutableState.value.copy(operationMessage = friendly(notice))
                    pendingAnalyzeUpload = null
                }
                is ApiResult.Success -> {
                    if (!notice.value.enabled || notice.value.policyVersion.isNullOrBlank() || notice.value.consentType != missing) {
                        mutableState.value = mutableState.value.copy(operationMessage = "服务端当前未提供有效的解析授权告知，文件尚未上传。")
                        pendingAnalyzeUpload = null
                    } else mutableState.value = mutableState.value.copy(pendingConsentNotice = notice.value)
                }
            }
            return false
        }
        pendingAnalyzeUpload = null
        performUpload(upload.fileName, upload.contentType, upload.sizeBytes, upload.content, analyze = upload.analyze, documentType = upload.documentType)
        return true
    }

    private suspend fun performUpload(fileName: String, contentType: String, sizeBytes: Long, content: RequestBody, analyze: Boolean, documentType: String) {
        mutableState.value = mutableState.value.copy(uploading = true, operationMessage = null)
        val file = gateway.upload(UUID.randomUUID().toString(), UploadCreateDto(fileName = fileName, contentType = contentType, sizeBytes = sizeBytes), content)
        if (file is ApiResult.Failure) {
            mutableState.value = mutableState.value.copy(uploading = false, operationMessage = friendly(file), conflict = file.status == 409)
            return
        }
        val fileId = (file as ApiResult.Success).value.id
        when (val created = gateway.create(MedicalDocumentCreateDto(fileId, documentType, processingMode = if (analyze) "analyze" else "store_only"))) {
            is ApiResult.Success -> {
                mutableState.value = mutableState.value.copy(uploading = false, operationMessage = "报告已安全上传。", conflict = false)
                load()
            }
            is ApiResult.Failure -> mutableState.value = mutableState.value.copy(uploading = false, operationMessage = friendly(created), conflict = created.status == 409)
        }
    }
    fun clearForLogout() { pendingAnalyzeUpload = null; mutableState.value = MedicalArchiveUiState() }

    private companion object {
        const val HEALTH_DATA_CONSENT = "health_data_processing"
        val ANALYZE_CONSENTS = listOf(HEALTH_DATA_CONSENT, "third_party_ai")
    }

    private fun consentName(type: String) = if (type == "health_data_processing") "健康数据处理授权" else "第三方 AI 授权"

    private fun friendly(result: ApiResult.Failure) = when (result.status) {
        401 -> "登录状态已失效，请重新登录。"
        409 -> "内容已变化，请刷新后重试。"
        403 -> "当前授权不允许此操作。"
        else -> "暂时无法完成操作，请检查网络后重试。"
    }
}

class MedicalDocumentsViewModelFactory(private val gateway: MedicalDocumentsGateway) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST") override fun <T : ViewModel> create(modelClass: Class<T>): T {
        require(modelClass.isAssignableFrom(MedicalDocumentsViewModel::class.java))
        return MedicalDocumentsViewModel(gateway) as T
    }
}
