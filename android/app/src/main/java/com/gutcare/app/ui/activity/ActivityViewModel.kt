package com.gutcare.app.ui.activity

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.gutcare.app.core.network.ActivityPageDto
import com.gutcare.app.core.network.ActivityPatchDto
import com.gutcare.app.core.network.ActivityRecordDto
import com.gutcare.app.core.network.ActivityRecordsRepository
import com.gutcare.app.core.network.ActivityWriteDto
import com.gutcare.app.core.network.ApiResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

interface ActivityFeatureGateway {
    suspend fun list(cursor: String? = null, limit: Int = 50): ApiResult<ActivityPageDto>
    suspend fun create(body: ActivityWriteDto): ApiResult<ActivityRecordDto>
    suspend fun detail(id: String): ApiResult<ActivityRecordDto>
    suspend fun update(id: String, body: ActivityPatchDto): ApiResult<ActivityRecordDto>
    suspend fun delete(id: String, version: Int): ApiResult<Unit>
}

class RepositoryActivityFeatureGateway(private val repository: ActivityRecordsRepository) : ActivityFeatureGateway {
    override suspend fun list(cursor: String?, limit: Int) = repository.list(cursor, limit)
    override suspend fun create(body: ActivityWriteDto) = repository.create(body)
    override suspend fun detail(id: String) = repository.detail(id)
    override suspend fun update(id: String, body: ActivityPatchDto) = repository.update(id, body)
    override suspend fun delete(id: String, version: Int) = repository.delete(id, version)
}

class ActivityViewModelFactory(private val gateway: ActivityFeatureGateway) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        require(modelClass.isAssignableFrom(ActivityViewModel::class.java))
        return ActivityViewModel(gateway) as T
    }
}

data class ActivityDraft(
    val activityType: String = "walking",
    val description: String = "",
    val intensity: String = "moderate",
    val subjectiveFeeling: String = "same",
    val duration: String = "30",
    val occurredAt: String = OffsetDateTime.now().withSecond(0).withNano(0).format(DateTimeFormatter.ISO_OFFSET_DATE_TIME),
)

data class ActivityUiState(
    val items: List<ActivityRecordDto> = emptyList(),
    val nextCursor: String? = null,
    val loading: Boolean = false,
    val loadingMore: Boolean = false,
    val saving: Boolean = false,
    val deletingId: String? = null,
    val error: String? = null,
    val message: String? = null,
    val sessionExpired: Boolean = false,
    val formOpen: Boolean = false,
    val editingId: String? = null,
    val editingVersion: Int? = null,
    val draft: ActivityDraft = ActivityDraft(),
    val conflictLatest: ActivityRecordDto? = null,
    val detailRequestedId: String? = null,
    val detail: ActivityRecordDto? = null,
    val detailLoading: Boolean = false,
    val detailError: String? = null,
)

class ActivityViewModel(private val gateway: ActivityFeatureGateway) : ViewModel() {
    private val mutableState = MutableStateFlow(ActivityUiState())
    val uiState: StateFlow<ActivityUiState> = mutableState.asStateFlow()
    private var epoch = 0L
    private var detailEpoch = 0L

    fun openDetail(id: String) {
        val requestEpoch = ++detailEpoch
        mutableState.value = mutableState.value.copy(detailRequestedId = id, detail = null, detailLoading = true, detailError = null)
        viewModelScope.launch {
            when (val result = gateway.detail(id)) {
                is ApiResult.Success -> if (requestEpoch == detailEpoch && mutableState.value.detailRequestedId == id) {
                    mutableState.value = mutableState.value.copy(detail = result.value, detailLoading = false, detailError = null)
                }
                is ApiResult.Failure -> if (requestEpoch == detailEpoch && mutableState.value.detailRequestedId == id) {
                    mutableState.value = mutableState.value.copy(detailLoading = false, detailError = result.message(), sessionExpired = result.status == 401)
                }
            }
        }
    }

    fun retryDetail() { mutableState.value.detailRequestedId?.let(::openDetail) }
    fun closeDetail() {
        detailEpoch++
        mutableState.value = mutableState.value.copy(detailRequestedId = null, detail = null, detailLoading = false, detailError = null)
    }

    fun load() {
        val currentEpoch = ++epoch
        mutableState.value = mutableState.value.copy(loading = true, error = null)
        viewModelScope.launch {
            when (val result = gateway.list()) {
                is ApiResult.Success -> if (currentEpoch == epoch) mutableState.value = mutableState.value.copy(
                    items = result.value.items, nextCursor = result.value.nextCursor, loading = false, error = null,
                )
                is ApiResult.Failure -> if (currentEpoch == epoch) mutableState.value = mutableState.value.copy(
                    loading = false, error = result.message(), sessionExpired = result.status == 401,
                )
            }
        }
    }

    fun loadMore() {
        val cursor = mutableState.value.nextCursor ?: return
        if (mutableState.value.loadingMore || mutableState.value.saving) return
        mutableState.value = mutableState.value.copy(loadingMore = true, error = null)
        viewModelScope.launch {
            when (val result = gateway.list(cursor)) {
                is ApiResult.Success -> mutableState.value = mutableState.value.copy(
                    items = (mutableState.value.items + result.value.items).distinctBy(ActivityRecordDto::id),
                    nextCursor = result.value.nextCursor, loadingMore = false,
                )
                is ApiResult.Failure -> mutableState.value = mutableState.value.copy(loadingMore = false, error = result.message(), sessionExpired = result.status == 401)
            }
        }
    }

    fun beginCreate() { mutableState.value = mutableState.value.copy(formOpen = true, editingId = null, editingVersion = null, draft = ActivityDraft(), message = null, error = null) }
    fun beginEdit(record: ActivityRecordDto) {
        detailEpoch++
        mutableState.value = mutableState.value.copy(
            formOpen = true, editingId = record.id, editingVersion = record.recordVersion, draft = record.toDraft(),
            message = null, error = null, detailRequestedId = null, detail = null, detailLoading = false, detailError = null,
        )
    }
    fun closeForm() { if (!mutableState.value.saving) mutableState.value = mutableState.value.copy(formOpen = false, conflictLatest = null) }
    fun updateDraft(draft: ActivityDraft) { mutableState.value = mutableState.value.copy(draft = draft, error = null) }

    fun save() {
        val state = mutableState.value
        if (state.saving) return
        val body = state.draft.toWriteOrNull()
        if (body == null) { mutableState.value = state.copy(error = state.draft.validationMessage()); return }
        mutableState.value = state.copy(saving = true, error = null, message = null)
        viewModelScope.launch {
            val result = if (state.editingId == null) gateway.create(body) else gateway.update(
                state.editingId, ActivityPatchDto(
                    recordVersion = state.editingVersion ?: return@launch,
                    activityType = body.activityType, description = body.description, intensity = body.intensity,
                    subjectiveFeeling = body.subjectiveFeeling, durationMinutes = body.durationMinutes, occurredAt = body.occurredAt,
                ),
            )
            when (result) {
                is ApiResult.Success -> {
                    mutableState.value = mutableState.value.copy(
                        items = if (state.editingId == null) listOf(result.value) + mutableState.value.items else mutableState.value.items.map { if (it.id == result.value.id) result.value else it },
                        formOpen = false, saving = false, editingId = null, editingVersion = null, conflictLatest = null,
                        message = if (state.editingId == null) "活动记录已保存。" else "活动记录已更新。",
                    )
                }
                is ApiResult.Failure -> {
                    val latest = if (result.status == 409 && state.editingId != null) (gateway.detail(state.editingId) as? ApiResult.Success)?.value else null
                    mutableState.value = mutableState.value.copy(saving = false, error = if (result.status == 409) "记录已在其他位置修改，请比较后选择如何继续。" else result.message(), sessionExpired = result.status == 401, conflictLatest = latest)
                }
            }
        }
    }

    fun keepDraftWithLatestVersion() {
        val latest = mutableState.value.conflictLatest ?: return
        mutableState.value = mutableState.value.copy(editingVersion = latest.recordVersion, conflictLatest = null, error = "草稿已保留，请检查后再次手动保存。")
    }

    fun discardDraftAndLoadLatest() {
        val latest = mutableState.value.conflictLatest ?: return
        mutableState.value = mutableState.value.copy(draft = latest.toDraft(), editingVersion = latest.recordVersion, conflictLatest = null, error = null)
    }

    fun delete(record: ActivityRecordDto) {
        if (mutableState.value.saving || mutableState.value.deletingId != null) return
        mutableState.value = mutableState.value.copy(deletingId = record.id, error = null, message = null)
        viewModelScope.launch {
            when (val result = gateway.delete(record.id, record.recordVersion)) {
                is ApiResult.Success -> mutableState.value = mutableState.value.copy(
                    items = mutableState.value.items.filterNot { it.id == record.id }, deletingId = null, message = "活动记录已删除。",
                    detailRequestedId = mutableState.value.detailRequestedId?.takeUnless { it == record.id },
                    detail = mutableState.value.detail?.takeUnless { it.id == record.id },
                )
                is ApiResult.Failure -> {
                    val latest = if (result.status == 409) (gateway.detail(record.id) as? ApiResult.Success)?.value else null
                    mutableState.value = mutableState.value.copy(deletingId = null, error = if (result.status == 409) "记录已被修改，刷新后再删除。" else result.message(), sessionExpired = result.status == 401)
                    if (latest != null) mutableState.value = mutableState.value.copy(
                        items = mutableState.value.items.map { if (it.id == latest.id) latest else it },
                        detail = mutableState.value.detail?.let { if (it.id == latest.id) latest else it },
                    )
                }
            }
        }
    }
}

private fun ActivityRecordDto.toDraft() = ActivityDraft(
    activityType = activityType, description = description.orEmpty(), intensity = intensity,
    subjectiveFeeling = subjectiveFeeling, duration = durationMinutes.toString(), occurredAt = occurredAt,
)

private fun ActivityDraft.toWriteOrNull(): ActivityWriteDto? {
    val minutes = duration.toIntOrNull() ?: return null
    val instant = runCatching { OffsetDateTime.parse(occurredAt).format(DateTimeFormatter.ISO_OFFSET_DATE_TIME) }.getOrNull() ?: return null
    val boundedDescription = description.trim()
    if (activityType !in setOf("walking", "jogging", "cycling", "other") || intensity !in setOf("low", "moderate", "high") || subjectiveFeeling !in setOf("better", "same", "worse") || minutes !in 1..1440) return null
    if ((activityType == "other" && boundedDescription.length !in 1..160) || (activityType != "other" && boundedDescription.isNotEmpty())) return null
    return ActivityWriteDto(activityType, boundedDescription.takeIf { activityType == "other" }, intensity, subjectiveFeeling, minutes, instant)
}

private fun ActivityDraft.validationMessage(): String = when {
    duration.toIntOrNull()?.let { it !in 1..1440 } != false -> "时长需为 1–1440 分钟。"
    runCatching { OffsetDateTime.parse(occurredAt) }.isFailure -> "日期时间需要包含有效时区。"
    activityType == "other" && description.trim().length !in 1..160 -> "请为“其他”填写 1–160 字描述。"
    activityType != "other" && description.isNotBlank() -> "描述仅适用于“其他”活动。"
    else -> "请检查活动类型、强度和感受。"
}

private fun ApiResult.Failure.message(): String = when (status) {
    401 -> "登录已失效，请重新登录。"
    409 -> "记录已被修改，请检查后重试。"
    null -> "网络暂不可用，请检查连接后重试。"
    else -> "暂时无法完成操作，请稍后重试。"
}
