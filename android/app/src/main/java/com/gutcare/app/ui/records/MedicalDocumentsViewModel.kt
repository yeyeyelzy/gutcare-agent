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
    suspend fun decide(candidateId: String, key: String, body: MedicalCandidateDecisionDto): ApiResult<Unit>
    suspend fun upload(key: String, metadata: UploadCreateDto, content: RequestBody): ApiResult<FileObjectDto>
    suspend fun create(body: MedicalDocumentCreateDto): ApiResult<MedicalDocumentDto>
}

class RepositoryMedicalDocumentsGateway(private val repository: MedicalDocumentsRepository) : MedicalDocumentsGateway {
    override suspend fun list(cursor: String?) = repository.list(cursor)
    override suspend fun detail(id: String) = repository.detail(id)
    override suspend fun candidates(documentId: String) = repository.candidates(documentId)
    override suspend fun decide(candidateId: String, key: String, body: MedicalCandidateDecisionDto) = repository.decide(candidateId, key, body)
    override suspend fun upload(key: String, metadata: UploadCreateDto, content: RequestBody) = repository.upload(key, metadata, content)
    override suspend fun create(body: MedicalDocumentCreateDto) = repository.create(body)
}

class UnavailableMedicalDocumentsGateway : MedicalDocumentsGateway {
    private fun <T> unavailable() = ApiResult.Failure(null, "SERVICE_UNAVAILABLE") as ApiResult<T>
    override suspend fun list(cursor: String?) = unavailable<MedicalDocumentPageDto>()
    override suspend fun detail(id: String) = unavailable<MedicalDocumentDto>()
    override suspend fun candidates(documentId: String) = unavailable<List<MedicalFieldCandidateDto>>()
    override suspend fun decide(candidateId: String, key: String, body: MedicalCandidateDecisionDto) = unavailable<Unit>()
    override suspend fun upload(key: String, metadata: UploadCreateDto, content: RequestBody) = unavailable<FileObjectDto>()
    override suspend fun create(body: MedicalDocumentCreateDto) = unavailable<MedicalDocumentDto>()
}

data class MedicalArchiveUiState(
    val loading: Boolean = false,
    val documents: List<MedicalDocumentDto> = emptyList(),
    val error: String? = null,
    val detail: MedicalDocumentDto? = null,
    val detailLoading: Boolean = false,
    val candidates: List<MedicalFieldCandidateDto> = emptyList(),
    val detailError: String? = null,
    val operationMessage: String? = null,
    val conflict: Boolean = false,
    val uploading: Boolean = false,
)

class MedicalDocumentsViewModel(private val gateway: MedicalDocumentsGateway) : ViewModel() {
    private val mutableState = MutableStateFlow(MedicalArchiveUiState())
    val uiState: StateFlow<MedicalArchiveUiState> = mutableState.asStateFlow()

    fun load() = viewModelScope.launch {
        mutableState.value = mutableState.value.copy(loading = true, error = null)
        when (val result = gateway.list(null)) {
            is ApiResult.Success -> mutableState.value = mutableState.value.copy(loading = false, documents = result.value.items, error = null)
            is ApiResult.Failure -> mutableState.value = mutableState.value.copy(loading = false, error = friendly(result))
        }
    }
    fun open(id: String) = viewModelScope.launch {
        mutableState.value = mutableState.value.copy(detailLoading = true, detailError = null, detail = null, candidates = emptyList())
        when (val result = gateway.detail(id)) {
            is ApiResult.Failure -> mutableState.value = mutableState.value.copy(detailLoading = false, detailError = friendly(result))
            is ApiResult.Success -> {
                mutableState.value = mutableState.value.copy(detailLoading = false, detail = result.value)
                loadCandidates(id)
            }
        }
    }
    private suspend fun loadCandidates(id: String) {
        when (val result = gateway.candidates(id)) {
            is ApiResult.Success -> mutableState.value = mutableState.value.copy(candidates = result.value)
            is ApiResult.Failure -> mutableState.value = mutableState.value.copy(detailError = friendly(result))
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
    fun upload(fileName: String, contentType: String, sizeBytes: Long, content: RequestBody, analyze: Boolean) = viewModelScope.launch {
        if (analyze) {
            // F02 requires both current consents before a sensitive file can enter the analyze flow.
            // Until the consent read/guide route is wired, do not upload and let the server see a late failure.
            mutableState.value = mutableState.value.copy(operationMessage = "当前版本尚未接入解析授权核验；请仅存档。", conflict = false)
            return@launch
        }
        mutableState.value = mutableState.value.copy(uploading = true, operationMessage = null)
        val file = gateway.upload(UUID.randomUUID().toString(), UploadCreateDto(fileName = fileName, contentType = contentType, sizeBytes = sizeBytes), content)
        if (file is ApiResult.Failure) {
            mutableState.value = mutableState.value.copy(uploading = false, operationMessage = friendly(file), conflict = file.status == 409)
            return@launch
        }
        val fileId = (file as ApiResult.Success).value.id
        when (val created = gateway.create(MedicalDocumentCreateDto(fileId, "other", processingMode = if (analyze) "analyze" else "store_only"))) {
            is ApiResult.Success -> {
                mutableState.value = mutableState.value.copy(uploading = false, operationMessage = "报告已安全上传。", conflict = false)
                load()
            }
            is ApiResult.Failure -> mutableState.value = mutableState.value.copy(uploading = false, operationMessage = friendly(created), conflict = created.status == 409)
        }
    }
    fun clearForLogout() { mutableState.value = MedicalArchiveUiState() }

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
