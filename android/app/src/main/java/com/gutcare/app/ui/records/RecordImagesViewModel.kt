package com.gutcare.app.ui.records

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.gutcare.app.core.network.ApiResult
import com.gutcare.app.core.network.PatientRecordType
import com.gutcare.app.core.network.RecordImageAttachmentDto
import com.gutcare.app.core.network.RecordImageCandidateDecisionDto
import com.gutcare.app.core.network.RecordImageDisclosureAcknowledgeDto
import com.gutcare.app.core.network.RecordImageDisclosureDto
import com.gutcare.app.core.network.RecordImageRecognitionCandidateDto
import com.gutcare.app.core.network.RecordImageRecognitionCreateDto
import com.gutcare.app.core.network.RecordImageRecognitionRequestDto
import com.gutcare.app.core.network.RecordImageRules
import com.gutcare.app.core.network.RecordImagesRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.UUID

data class RecordImagesUiState(
    val type: PatientRecordType? = null,
    val recordId: String? = null,
    val recordVersion: Int = 0,
    val imageSetVersion: Int = 0,
    val images: List<RecordImageAttachmentDto> = emptyList(),
    val loading: Boolean = false,
    val uploading: Boolean = false,
    val deletingImageId: String? = null,
    val previewLoadingImageId: String? = null,
    val previewImageId: String? = null,
    /** Ephemeral image bytes only; never written to disk or preferences. */
    val previewBytes: ByteArray? = null,
    val message: String? = null,
    val isError: Boolean = false,
    val needsConsentSettings: Boolean = false,
    val recognitionDisclosure: RecordImageDisclosureDto? = null,
    val retryRequestId: String? = null,
    val recognition: RecordImageRecognitionRequestDto? = null,
    val recognitionBusy: Boolean = false,
    /** True only after this page successfully confirms a diet food name. */
    val dietFoodSaved: Boolean = false,
) {
    val canAdd: Boolean get() = type != null && recordId != null && RecordImageRules.nextPosition(type, images) != null && !uploading && !loading
}

interface RecordImagesGateway {
    suspend fun list(type: PatientRecordType, recordId: String): ApiResult<List<RecordImageAttachmentDto>>
    suspend fun latestStoolRecognition(recordId: String): ApiResult<RecordImageRecognitionRequestDto>
    suspend fun uploadAndAttach(type: PatientRecordType, recordId: String, recordVersion: Int, imageSetVersion: Int,
        idempotencyKey: String, fileName: String, contentType: String, bytes: ByteArray): ApiResult<RecordImageAttachmentDto>
    suspend fun delete(imageId: String, recordVersion: Int, imageSetVersion: Int): ApiResult<Unit>
    suspend fun preview(attachmentId: String): ApiResult<ByteArray>
    suspend fun disclosure(purpose: String): ApiResult<RecordImageDisclosureDto>
    suspend fun acknowledgeDisclosure(body: RecordImageDisclosureAcknowledgeDto): ApiResult<String>
    suspend fun createRecognition(type: PatientRecordType, recordId: String, key: String, body: RecordImageRecognitionCreateDto): ApiResult<RecordImageRecognitionRequestDto>
    suspend fun recognitionRequest(requestId: String): ApiResult<RecordImageRecognitionRequestDto>
    suspend fun retryRecognition(requestId: String, key: String, body: RecordImageRecognitionCreateDto): ApiResult<RecordImageRecognitionRequestDto>
    suspend fun decideCandidate(candidateId: String, key: String, body: RecordImageCandidateDecisionDto): ApiResult<Unit>
}

class RepositoryRecordImagesGateway(private val repository: RecordImagesRepository) : RecordImagesGateway {
    override suspend fun list(type: PatientRecordType, recordId: String) = repository.list(type, recordId)
    override suspend fun latestStoolRecognition(recordId: String) = repository.latestStoolRecognition(recordId)
    override suspend fun uploadAndAttach(type: PatientRecordType, recordId: String, recordVersion: Int, imageSetVersion: Int,
        idempotencyKey: String, fileName: String, contentType: String, bytes: ByteArray) = repository.uploadAndAttach(
        type, recordId, recordVersion, imageSetVersion, idempotencyKey, fileName, contentType,
        bytes.toRequestBody(contentType.toMediaType()), bytes.size.toLong(),
    )
    override suspend fun delete(imageId: String, recordVersion: Int, imageSetVersion: Int) = repository.delete(imageId, recordVersion, imageSetVersion)
    override suspend fun preview(attachmentId: String) = repository.downloadPreview(attachmentId)
    override suspend fun disclosure(purpose: String) = repository.recognitionDisclosure(purpose)
    override suspend fun acknowledgeDisclosure(body: RecordImageDisclosureAcknowledgeDto) =
        when (val result = repository.acknowledgeRecognitionDisclosure(body)) {
            is ApiResult.Success -> ApiResult.Success(result.value.disclosureToken)
            is ApiResult.Failure -> result
        }
    override suspend fun createRecognition(type: PatientRecordType, recordId: String, key: String, body: RecordImageRecognitionCreateDto) = repository.createRecognition(type, recordId, key, body)
    override suspend fun recognitionRequest(requestId: String) = repository.recognitionRequest(requestId)
    override suspend fun retryRecognition(requestId: String, key: String, body: RecordImageRecognitionCreateDto) = repository.retryRecognition(requestId, key, body)
    override suspend fun decideCandidate(candidateId: String, key: String, body: RecordImageCandidateDecisionDto) = repository.decideRecognitionCandidate(candidateId, key, body)
}

class RecordImagesViewModel(private val gateway: RecordImagesGateway) : ViewModel() {
    private val mutable = MutableStateFlow(RecordImagesUiState())
    val uiState: StateFlow<RecordImagesUiState> = mutable.asStateFlow()
    private var pollingJob: Job? = null

    fun load(type: PatientRecordType, recordId: String, recordVersion: Int, imageSetVersion: Int) = viewModelScope.launch {
        val previous = mutable.value
        if (previous.recordId != recordId || previous.type != type) {
            pollingJob?.cancel()
            pollingJob = null
        }
        mutable.value = previous.copy(type = type, recordId = recordId, recordVersion = recordVersion,
            imageSetVersion = imageSetVersion, loading = true, message = null, isError = false,
            previewImageId = null, previewBytes = null, previewLoadingImageId = null,
            recognition = if (type != PatientRecordType.STOOL && previous.recordId == recordId && previous.type == type) previous.recognition else null,
            recognitionDisclosure = null, retryRequestId = null, recognitionBusy = false)
        when (val result = gateway.list(type, recordId)) {
            is ApiResult.Success -> {
                val latest = result.value.maxByOrNull(RecordImageAttachmentDto::imageSetVersion)
                mutable.value = mutable.value.copy(loading = false, images = result.value,
                    recordVersion = latest?.recordVersion ?: recordVersion,
                    imageSetVersion = latest?.imageSetVersion ?: imageSetVersion)
                if (type == PatientRecordType.STOOL) restoreLatestStoolRecognition(recordId)
            }
            is ApiResult.Failure -> mutable.value = mutable.value.copy(loading = false, message = friendly(result), isError = true)
        }
    }

    fun upload(fileName: String, contentType: String, bytes: ByteArray) = viewModelScope.launch {
        val state = mutable.value
        val type = state.type ?: return@launch
        val id = state.recordId ?: return@launch
        val position = RecordImageRules.nextPosition(type, state.images)
        if (position == null) {
            mutable.value = state.copy(message = if (type == PatientRecordType.DIET) "饮食记录最多关联 10 张图片。" else "排便记录最多关联 1 张图片。", isError = true)
            return@launch
        }
        if (contentType !in setOf("image/jpeg", "image/png") || bytes.isEmpty() || bytes.size.toLong() > RecordImageRules.MAX_IMAGE_BYTES) {
            mutable.value = state.copy(message = "仅支持不超过 10 MiB 的 JPEG 或 PNG 图片。", isError = true)
            return@launch
        }
        mutable.value = state.copy(uploading = true, message = null, isError = false, needsConsentSettings = false)
        when (val result = gateway.uploadAndAttach(type, id, state.recordVersion, state.imageSetVersion,
            UUID.randomUUID().toString(), fileName.take(255), contentType, bytes)) {
            is ApiResult.Success -> mutable.value = mutable.value.copy(uploading = false,
                images = (mutable.value.images + result.value).sortedBy(RecordImageAttachmentDto::position),
                recordVersion = result.value.recordVersion, imageSetVersion = result.value.imageSetVersion,
                message = "图片已通过安全校验并关联到记录。", isError = false)
            is ApiResult.Failure -> mutable.value = mutable.value.copy(uploading = false, message = friendly(result), isError = true,
                needsConsentSettings = result.status == 409 && result.code.equals("CONSENT_REQUIRED", true))
        }
    }

    fun delete(image: RecordImageAttachmentDto) = viewModelScope.launch {
        val state = mutable.value
        mutable.value = state.copy(deletingImageId = image.id, message = null, isError = false)
        when (val result = gateway.delete(image.id, state.recordVersion, state.imageSetVersion)) {
            is ApiResult.Success -> mutable.value = mutable.value.copy(deletingImageId = null,
                images = mutable.value.images.filterNot { it.id == image.id },
                previewImageId = mutable.value.previewImageId.takeUnless { it == image.id },
                previewBytes = mutable.value.previewBytes.takeUnless { mutable.value.previewImageId == image.id },
                recordVersion = state.recordVersion + 1, imageSetVersion = state.imageSetVersion + 1,
                message = "图片已移除，服务端将按文件生命周期清理。", isError = false)
            is ApiResult.Failure -> mutable.value = mutable.value.copy(deletingImageId = null, message = friendly(result), isError = true)
        }
    }

    fun preview(image: RecordImageAttachmentDto) = viewModelScope.launch {
        if (image.fileStatus != "available") {
            mutable.value = mutable.value.copy(message = "该图片当前不可用，无法预览。", isError = true)
            return@launch
        }
        mutable.value = mutable.value.copy(previewLoadingImageId = image.id, previewImageId = null, previewBytes = null,
            message = null, isError = false)
        when (val result = gateway.preview(image.id)) {
            is ApiResult.Success -> mutable.value = mutable.value.copy(previewLoadingImageId = null, previewImageId = image.id,
                previewBytes = result.value, message = null, isError = false)
            is ApiResult.Failure -> mutable.value = mutable.value.copy(previewLoadingImageId = null,
                message = previewFailure(result), isError = true)
        }
    }

    fun requestRecognition(retryRequestId: String? = null) = viewModelScope.launch {
        val initial = mutable.value
        val type = initial.type ?: return@launch
        val recordId = initial.recordId ?: return@launch
        if (type != PatientRecordType.DIET && type != PatientRecordType.STOOL) return@launch
        mutable.value = initial.copy(recognitionBusy = true, recognitionDisclosure = null, retryRequestId = retryRequestId, message = null, isError = false, needsConsentSettings = false)
        if (!refreshImageSnapshot(type, recordId)) {
            mutable.value = mutable.value.copy(recognitionBusy = false, message = "暂时无法刷新图片状态，请稍后重试。", isError = true)
            return@launch
        }
        val state = mutable.value
        val purpose = if (type == PatientRecordType.DIET) "diet_image_recognition" else "stool_image_recognition"
        when (val result = gateway.disclosure(purpose)) {
            is ApiResult.Success -> mutable.value = mutable.value.copy(recognitionBusy = false, recognitionDisclosure = result.value,
                message = if (result.value.enabled) null else "当前环境未启用该用途的识别告知，无法发起识别。", isError = !result.value.enabled)
            is ApiResult.Failure -> mutable.value = mutable.value.copy(recognitionBusy = false, message = friendly(result), isError = true,
                needsConsentSettings = result.status == 409 && result.code.equals("CONSENT_REQUIRED", true))
        }
    }

    fun dismissRecognitionDisclosure() {
        mutable.value = mutable.value.copy(recognitionDisclosure = null, retryRequestId = null)
    }

    /** Called only after the patient has seen and explicitly accepted the displayed notice. */
    fun acknowledgeAndStartRecognition() = viewModelScope.launch {
        val state = mutable.value
        val type = state.type ?: return@launch
        val recordId = state.recordId ?: return@launch
        val notice = state.recognitionDisclosure?.takeIf { it.enabled && !it.policyVersion.isNullOrBlank() } ?: return@launch
        val purpose = if (type == PatientRecordType.DIET) "diet_image_recognition" else "stool_image_recognition"
        mutable.value = state.copy(recognitionBusy = true, recognitionDisclosure = null, message = null, isError = false)
        val acknowledgment = RecordImageDisclosureAcknowledgeDto(recordId, purpose, state.recordVersion, state.imageSetVersion, notice.policyVersion!!)
        when (val token = gateway.acknowledgeDisclosure(acknowledgment)) {
            is ApiResult.Failure -> {
                val stale = token.isRecordVersionConflict()
                if (stale) refreshImageSnapshot(type, recordId)
                mutable.value = mutable.value.copy(recognitionBusy = false,
                    message = if (stale) "图片仍已保留，记录状态已更新；请重新发起识别。" else friendly(token), isError = true)
            }
            is ApiResult.Success -> {
                val body = RecordImageRecognitionCreateDto(state.recordVersion, state.imageSetVersion, token.value)
                val result = state.retryRequestId?.let { gateway.retryRecognition(it, UUID.randomUUID().toString(), body) }
                    ?: gateway.createRecognition(type, recordId, UUID.randomUUID().toString(), body)
                when (result) {
                    is ApiResult.Success -> {
                        mutable.value = mutable.value.copy(recognitionBusy = false, retryRequestId = null, recognition = result.value,
                            recordVersion = result.value.decisionRecordVersion,
                            imageSetVersion = result.value.imageSetVersion,
                            message = if (type == PatientRecordType.STOOL) "已提交识别任务；完成后将展示 AI 辅助分类。"
                                else "已提交识别任务；候选需由你逐项确认。", isError = false)
                        pollRecognition(result.value.id)
                    }
                    is ApiResult.Failure -> {
                        val stale = result.isRecordVersionConflict()
                        if (stale) {
                            refreshImageSnapshot(type, recordId)
                            mutable.value = mutable.value.copy(recognitionBusy = false, retryRequestId = null,
                                message = "图片仍已保留，记录状态已更新；请重新阅读告知并发起识别。", isError = true)
                        } else if (type == PatientRecordType.STOOL && result.status == 409 &&
                            result.code.equals("RECORD_IMAGE_REQUEST_ACTIVE", true)) {
                            restoreLatestStoolRecognition(recordId)
                            mutable.value = mutable.value.copy(recognitionBusy = false, retryRequestId = null,
                                message = null, isError = false)
                        } else mutable.value = mutable.value.copy(recognitionBusy = false, retryRequestId = null, message = friendly(result), isError = true,
                            needsConsentSettings = result.status == 409 && result.code.equals("CONSENT_REQUIRED", true))
                    }
                }
            }
        }
    }

    private suspend fun refreshImageSnapshot(type: PatientRecordType, recordId: String): Boolean =
        when (val result = gateway.list(type, recordId)) {
            is ApiResult.Success -> {
                val latest = result.value.maxByOrNull(RecordImageAttachmentDto::imageSetVersion)
                val current = mutable.value
                if (current.type == type && current.recordId == recordId) {
                    mutable.value = current.copy(images = result.value,
                        recordVersion = latest?.recordVersion ?: current.recordVersion,
                        imageSetVersion = latest?.imageSetVersion ?: current.imageSetVersion)
                }
                true
            }
            is ApiResult.Failure -> false
        }

    private suspend fun restoreLatestStoolRecognition(recordId: String) {
        when (val result = gateway.latestStoolRecognition(recordId)) {
            is ApiResult.Success -> {
                val current = mutable.value
                if (current.type != PatientRecordType.STOOL || current.recordId != recordId) return
                mutable.value = current.copy(recognition = result.value)
                if (result.value.status in setOf("pending", "processing")) pollRecognition(result.value.id)
            }
            is ApiResult.Failure -> if (result.status != 404) {
                val current = mutable.value
                if (current.type == PatientRecordType.STOOL && current.recordId == recordId) {
                    mutable.value = current.copy(message = friendly(result), isError = true)
                }
            }
        }
    }

    fun refreshRecognition() {
        mutable.value.recognition?.id?.let { id -> viewModelScope.launch { fetchRecognition(id) } }
    }

    fun decideCandidate(candidate: RecordImageRecognitionCandidateDto, action: String, correctedValue: String? = null) = viewModelScope.launch {
        val state = mutable.value
        val type = state.type ?: return@launch
        if (!candidate.requiresPatientConfirmation) {
            mutable.value = state.copy(message = "这是 AI 辅助识别结果，不是已确认的患者事实；当前结果不支持确认或修改。", isError = true)
            return@launch
        }
        val request = state.recognition ?: return@launch
        val corrected: Any? = if (action == "edit" && type == PatientRecordType.STOOL) correctedValue?.toIntOrNull() else correctedValue
        val invalidBristolCorrection = action == "edit" && type == PatientRecordType.STOOL && (corrected !is Int || corrected !in 1..7)
        if (action == "edit" && (corrected == null || invalidBristolCorrection)) {
            mutable.value = state.copy(message = if (type == PatientRecordType.STOOL) "请输入 Bristol 1–7 的整数。" else "请输入修正后的候选值。", isError = true)
            return@launch
        }
        mutable.value = state.copy(recognitionBusy = true, message = null, isError = false)
        when (val result = gateway.decideCandidate(candidate.id, UUID.randomUUID().toString(), RecordImageCandidateDecisionDto(
            action, candidate.candidateVersion, request.decisionRecordVersion, request.imageSetVersion, corrected,
        ))) {
            is ApiResult.Success -> {
                mutable.value = mutable.value.copy(
                    dietFoodSaved = type == PatientRecordType.DIET && action in setOf("accept", "edit"),
                )
                fetchRecognition(request.id)
            }
            is ApiResult.Failure -> mutable.value = mutable.value.copy(recognitionBusy = false, message = friendly(result), isError = true)
        }
    }

    private suspend fun fetchRecognition(id: String) {
        when (val result = gateway.recognitionRequest(id)) {
            is ApiResult.Success -> {
                val latest = result.value
                mutable.value = mutable.value.copy(recognitionBusy = false, recognition = latest,
                    recordVersion = latest.decisionRecordVersion, imageSetVersion = latest.imageSetVersion,
                    message = if (latest.status == "candidates_ready") "候选仅供你确认；未确认内容不会写入记录。" else mutable.value.message,
                    isError = false)
                if (latest.status in setOf("pending", "processing")) pollRecognition(id)
            }
            is ApiResult.Failure -> mutable.value = mutable.value.copy(recognitionBusy = false, message = friendly(result), isError = true)
        }
    }

    private fun pollRecognition(id: String) {
        if (pollingJob?.isActive == true) return
        pollingJob = viewModelScope.launch {
            repeat(30) {
                delay(2_000)
                fetchRecognition(id)
                if (mutable.value.recognition?.status !in setOf("pending", "processing")) return@launch
            }
        }
    }

    fun clearPreview() { mutable.value = mutable.value.copy(previewImageId = null, previewBytes = null, previewLoadingImageId = null) }

    fun clear() { pollingJob?.cancel(); pollingJob = null; mutable.value = RecordImagesUiState() }

    private fun friendly(result: ApiResult.Failure): String = when {
        result.status == 401 -> "登录状态已失效，请重新登录。"
        result.status == 409 && result.code.equals("CONSENT_REQUIRED", true) -> "请先在授权设置中完成健康数据、敏感图片以及识别所需的第三方 AI 授权。"
        result.status == 409 && result.code.equals("candidate_dependency_unmet", true) -> "请先确认或修正同组的食物名称，再处理类别或份量候选。"
        result.status == 409 && result.code.equals("DISCLOSURE_REQUIRED", true) -> "用途告知已失效，请重新阅读并确认后再试。"
        result.status == 409 && result.code.equals("RECORD_IMAGE_REQUEST_ACTIVE", true) -> "该记录已有识别任务或结果，已为你恢复最新结果。"
        result.status == 409 -> "记录或图片集已变化，请刷新后重试。"
        result.status == 413 -> "图片超过服务端大小限制。"
        result.status == 415 -> "文件格式不受支持。"
        result.status == 422 && result.code.equals("MALWARE_DETECTED", true) -> "安全扫描未通过，图片已拒绝并且没有关联到记录。"
        result.status == 403 -> "当前授权不允许上传或关联图片。"
        result.status == 503 && result.code.equals("MALWARE_SCANNER_UNAVAILABLE", true) -> "图片安全扫描服务暂不可用，请稍后重试。"
        result.status == 503 && result.code.equals("DISCLOSURE_UNAVAILABLE", true) -> "当前环境未启用该用途的识别告知。"
        result.status == 503 -> "文件服务暂不可用，请稍后重试。"
        result.code.equals("FILE_NOT_AVAILABLE", true) -> "图片尚未通过安全扫描，未关联到记录。"
        else -> "图片操作暂时失败，请检查网络后重试。"
    }

    private fun ApiResult.Failure.isRecordVersionConflict(): Boolean =
        status == 409 && code.equals("RECORD_VERSION_CONFLICT", ignoreCase = true)

    private fun previewFailure(result: ApiResult.Failure): String = when {
        result.status == 401 -> "登录状态已失效，请重新登录。"
        result.status == 404 -> "图片已移除或当前不可用。"
        result.status == 413 -> "图片超过预览大小限制。"
        result.status == 415 -> "服务端返回了不支持的图片格式。"
        result.code == "UNSAFE_DOWNLOAD_URL" -> "图片预览地址未通过同源安全校验。"
        else -> "暂时无法预览图片，请稍后重试。"
    }
}

class RecordImagesViewModelFactory(private val gateway: RecordImagesGateway) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST") override fun <T : ViewModel> create(modelClass: Class<T>): T {
        require(modelClass.isAssignableFrom(RecordImagesViewModel::class.java))
        return RecordImagesViewModel(gateway) as T
    }
}
