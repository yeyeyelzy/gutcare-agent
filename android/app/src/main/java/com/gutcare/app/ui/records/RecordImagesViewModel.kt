package com.gutcare.app.ui.records

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.gutcare.app.core.network.ApiResult
import com.gutcare.app.core.network.PatientRecordType
import com.gutcare.app.core.network.RecordImageAttachmentDto
import com.gutcare.app.core.network.RecordImageRules
import com.gutcare.app.core.network.RecordImagesRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
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
) {
    val canAdd: Boolean get() = type != null && recordId != null && RecordImageRules.nextPosition(type, images) != null && !uploading && !loading
}

interface RecordImagesGateway {
    suspend fun list(type: PatientRecordType, recordId: String): ApiResult<List<RecordImageAttachmentDto>>
    suspend fun uploadAndAttach(type: PatientRecordType, recordId: String, recordVersion: Int, imageSetVersion: Int,
        idempotencyKey: String, fileName: String, contentType: String, bytes: ByteArray): ApiResult<RecordImageAttachmentDto>
    suspend fun delete(imageId: String, recordVersion: Int, imageSetVersion: Int): ApiResult<Unit>
    suspend fun preview(attachmentId: String): ApiResult<ByteArray>
}

class RepositoryRecordImagesGateway(private val repository: RecordImagesRepository) : RecordImagesGateway {
    override suspend fun list(type: PatientRecordType, recordId: String) = repository.list(type, recordId)
    override suspend fun uploadAndAttach(type: PatientRecordType, recordId: String, recordVersion: Int, imageSetVersion: Int,
        idempotencyKey: String, fileName: String, contentType: String, bytes: ByteArray) = repository.uploadAndAttach(
        type, recordId, recordVersion, imageSetVersion, idempotencyKey, fileName, contentType,
        bytes.toRequestBody(contentType.toMediaType()), bytes.size.toLong(),
    )
    override suspend fun delete(imageId: String, recordVersion: Int, imageSetVersion: Int) = repository.delete(imageId, recordVersion, imageSetVersion)
    override suspend fun preview(attachmentId: String) = repository.downloadPreview(attachmentId)
}

class RecordImagesViewModel(private val gateway: RecordImagesGateway) : ViewModel() {
    private val mutable = MutableStateFlow(RecordImagesUiState())
    val uiState: StateFlow<RecordImagesUiState> = mutable.asStateFlow()

    fun load(type: PatientRecordType, recordId: String, recordVersion: Int, imageSetVersion: Int) = viewModelScope.launch {
        mutable.value = mutable.value.copy(type = type, recordId = recordId, recordVersion = recordVersion,
            imageSetVersion = imageSetVersion, loading = true, message = null, isError = false,
            previewImageId = null, previewBytes = null, previewLoadingImageId = null)
        when (val result = gateway.list(type, recordId)) {
            is ApiResult.Success -> {
                val latest = result.value.maxByOrNull(RecordImageAttachmentDto::imageSetVersion)
                mutable.value = mutable.value.copy(loading = false, images = result.value,
                    recordVersion = latest?.recordVersion ?: recordVersion,
                    imageSetVersion = latest?.imageSetVersion ?: imageSetVersion)
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
        mutable.value = state.copy(uploading = true, message = null, isError = false)
        when (val result = gateway.uploadAndAttach(type, id, state.recordVersion, state.imageSetVersion,
            UUID.randomUUID().toString(), fileName.take(255), contentType, bytes)) {
            is ApiResult.Success -> mutable.value = mutable.value.copy(uploading = false,
                images = (mutable.value.images + result.value).sortedBy(RecordImageAttachmentDto::position),
                recordVersion = result.value.recordVersion, imageSetVersion = result.value.imageSetVersion,
                message = "图片已通过安全校验并关联到记录。", isError = false)
            is ApiResult.Failure -> mutable.value = mutable.value.copy(uploading = false, message = friendly(result), isError = true)
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

    fun clearPreview() { mutable.value = mutable.value.copy(previewImageId = null, previewBytes = null, previewLoadingImageId = null) }

    fun clear() { mutable.value = RecordImagesUiState() }

    private fun friendly(result: ApiResult.Failure): String = when {
        result.status == 401 -> "登录状态已失效，请重新登录。"
        result.status == 409 && result.code.equals("CONSENT_REQUIRED", true) -> "请先在授权设置中同意健康数据处理和敏感图片处理。"
        result.status == 409 -> "记录或图片集已变化，请刷新后重试。"
        result.status == 413 -> "图片超过服务端大小限制。"
        result.status == 415 -> "文件格式不受支持。"
        result.status == 422 && result.code.equals("MALWARE_DETECTED", true) -> "安全扫描未通过，图片已拒绝并且没有关联到记录。"
        result.status == 403 -> "当前授权不允许上传或关联图片。"
        result.status == 503 && result.code.equals("MALWARE_SCANNER_UNAVAILABLE", true) -> "图片安全扫描服务暂不可用，请稍后重试。"
        result.status == 503 -> "文件服务暂不可用，请稍后重试。"
        result.code.equals("FILE_NOT_AVAILABLE", true) -> "图片尚未通过安全扫描，未关联到记录。"
        else -> "图片操作暂时失败，请检查网络后重试。"
    }

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
