package com.gutcare.app.ui.records

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.gutcare.app.core.network.ApiResult
import com.gutcare.app.core.network.MoodDetailDto
import com.gutcare.app.core.network.ExplicitNullableString
import com.gutcare.app.core.network.MoodPageDto
import com.gutcare.app.core.network.MoodPatchDto
import com.gutcare.app.core.network.MoodWriteDto
import com.gutcare.app.core.network.PatientRecordType
import com.gutcare.app.core.network.RecordDto
import com.gutcare.app.core.network.RecordItemDto
import com.gutcare.app.core.network.RecordPageDto
import com.gutcare.app.core.network.RecordPatchDto
import com.gutcare.app.core.network.RecordPayloadDto
import com.gutcare.app.core.network.RecordWriteDto
import com.gutcare.app.core.network.RecordsRepository
import com.gutcare.app.core.network.SymptomStatusEventDto
import com.gutcare.app.core.network.SymptomStatusHistoryDto
import java.time.OffsetDateTime
import java.time.ZoneId
import java.util.UUID
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** Small boundary that keeps orchestration tests independent from Retrofit and Android. */
interface RecordsGateway {
    suspend fun list(type: WorkspaceRecordType, cursor: String?): ApiResult<RecordPageDto>
    suspend fun detail(type: WorkspaceRecordType, id: String): ApiResult<RecordDetailModel>
    suspend fun create(type: WorkspaceRecordType, idempotencyKey: String, body: RecordWriteDto): ApiResult<RecordDetailModel>
    suspend fun update(type: WorkspaceRecordType, id: String, body: RecordPatchDto): ApiResult<RecordDetailModel>
    suspend fun delete(type: WorkspaceRecordType, id: String, version: Int): ApiResult<Unit>
    suspend fun symptomStatusHistory(id: String): ApiResult<SymptomStatusHistoryDto>
    suspend fun listMood(cursor: String?): ApiResult<MoodPageDto>
    suspend fun detailMood(id: String): ApiResult<MoodDetailDto>
    suspend fun createMood(idempotencyKey: String, body: MoodWriteDto): ApiResult<MoodDetailDto>
    suspend fun updateMood(id: String, body: MoodPatchDto): ApiResult<MoodDetailDto>
    suspend fun deleteMood(id: String, version: Int): ApiResult<Unit>
}

class RecordsViewModelFactory(private val gateway: RecordsGateway) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        require(modelClass.isAssignableFrom(RecordsViewModel::class.java))
        return RecordsViewModel(gateway) as T
    }
}

class UnavailableRecordsGateway : RecordsGateway {
    private fun <T> unavailable(): ApiResult<T> = ApiResult.Failure(null, "SERVICE_UNAVAILABLE")
    override suspend fun list(type: WorkspaceRecordType, cursor: String?) = unavailable<RecordPageDto>()
    override suspend fun detail(type: WorkspaceRecordType, id: String) = unavailable<RecordDetailModel>()
    override suspend fun create(type: WorkspaceRecordType, idempotencyKey: String, body: RecordWriteDto) = unavailable<RecordDetailModel>()
    override suspend fun update(type: WorkspaceRecordType, id: String, body: RecordPatchDto) = unavailable<RecordDetailModel>()
    override suspend fun delete(type: WorkspaceRecordType, id: String, version: Int) = unavailable<Unit>()
    override suspend fun symptomStatusHistory(id: String) = unavailable<SymptomStatusHistoryDto>()
    override suspend fun listMood(cursor: String?) = unavailable<MoodPageDto>()
    override suspend fun detailMood(id: String) = unavailable<MoodDetailDto>()
    override suspend fun createMood(idempotencyKey: String, body: MoodWriteDto) = unavailable<MoodDetailDto>()
    override suspend fun updateMood(id: String, body: MoodPatchDto) = unavailable<MoodDetailDto>()
    override suspend fun deleteMood(id: String, version: Int) = unavailable<Unit>()
}

class RepositoryRecordsGateway(private val repository: RecordsRepository) : RecordsGateway {
    override suspend fun list(type: WorkspaceRecordType, cursor: String?) =
        if (type == WorkspaceRecordType.MOOD) repository.listMood(cursor = cursor, limit = 30).mapMoodPage()
        else repository.list(type.apiType(), cursor = cursor, limit = 30)

    override suspend fun detail(type: WorkspaceRecordType, id: String): ApiResult<RecordDetailModel> =
        if (type == WorkspaceRecordType.MOOD) when (val result = repository.moodDetail(id)) {
            is ApiResult.Failure -> result
            is ApiResult.Success -> ApiResult.Success(result.value.toRecordDetail())
        } else when (val result = repository.detail(type.apiType(), id)) {
            is ApiResult.Failure -> result
            is ApiResult.Success -> ApiResult.Success(result.value.toRecordDetail(type))
        }

    override suspend fun create(type: WorkspaceRecordType, idempotencyKey: String, body: RecordWriteDto): ApiResult<RecordDetailModel> =
        when (val result = repository.create(type.apiType(), idempotencyKey, body)) {
            is ApiResult.Failure -> result
            is ApiResult.Success -> ApiResult.Success(result.value.toRecordDetail(type))
        }

    override suspend fun update(type: WorkspaceRecordType, id: String, body: RecordPatchDto): ApiResult<RecordDetailModel> =
        when (val result = repository.update(type.apiType(), id, body)) {
            is ApiResult.Failure -> result
            is ApiResult.Success -> ApiResult.Success(result.value.toRecordDetail(type))
        }

    override suspend fun delete(type: WorkspaceRecordType, id: String, version: Int) = repository.delete(type.apiType(), id, version)
    override suspend fun symptomStatusHistory(id: String) = repository.symptomStatusHistory(id)
    override suspend fun listMood(cursor: String?) = repository.listMood(cursor = cursor, limit = 30)
    override suspend fun detailMood(id: String) = repository.moodDetail(id)
    override suspend fun createMood(idempotencyKey: String, body: MoodWriteDto) = repository.createMood(idempotencyKey, body)
    override suspend fun updateMood(id: String, body: MoodPatchDto) = repository.updateMood(id, body)
    override suspend fun deleteMood(id: String, version: Int) = repository.deleteMood(id, version)
}

data class RecordRow(val id: String, val version: Int, val label: String, val occurredAt: String)
data class RecordDetailModel(
    val id: String,
    val recordVersion: Int,
    val occurredAt: String,
    val payload: RecordPayloadDto,
    val moodLevel: Int? = null,
    val emotionTags: List<String> = emptyList(),
    val note: String? = null,
    val statusHistory: List<SymptomStatusEventDto> = emptyList(),
    val statusHistoryError: String? = null,
    val imageSetVersion: Int = 0,
)
sealed interface RecordsLoadState {
    data object Idle : RecordsLoadState
    data object Loading : RecordsLoadState
    data object Empty : RecordsLoadState
    data class Loaded(val records: List<RecordRow>) : RecordsLoadState
    data class Error(val message: String) : RecordsLoadState
}
sealed interface RecordDetailLoadState {
    data object Idle : RecordDetailLoadState
    data object Loading : RecordDetailLoadState
    data class Loaded(val detail: RecordDetailModel) : RecordDetailLoadState
    data class Error(val message: String) : RecordDetailLoadState
}
data class RecordOperationState(
    val saving: Boolean = false,
    val feedback: String? = null,
    val conflict: Boolean = false,
    val savedRecordId: String? = null,
)
data class RecordDraft(
    val date: String = "",
    val time: String = "",
    val mealType: String = "lunch",
    val description: String = "",
    val portionNote: String? = null,
    val cookingMethod: String? = null,
    val subjectiveNote: String? = null,
    val dietItems: List<RecordItemDto> = emptyList(),
    val bristolType: Int? = null,
    val bowelNote: String = "",
    val discomfort: String? = null,
    val bowelAmount: String? = null,
    val colorCode: String? = null,
    val bloodReported: Boolean? = null,
    val urgencyLevel: Int? = null,
    val symptomCode: String? = null,
    val otherDescription: String = "",
    val bodyLocation: String? = null,
    val severity: Int = 0,
    val duration: String = "",
    val symptomStatus: String = "ongoing",
    val symptomNote: String = "",
    val companionSigns: List<String> = emptyList(),
    val moodLevel: Int? = null,
    val moodTags: List<String> = emptyList(),
    val moodNote: String = "",
)
enum class WorkspaceRecordType(val title: String, val routeKey: String) {
    DIET("饮食", "diet"), STOOL("排便", "stool"), SYMPTOM("症状", "symptoms"), MOOD("心情", "mood"),
}
data class RecordsUiState(
    val listType: WorkspaceRecordType? = null,
    val loadState: RecordsLoadState = RecordsLoadState.Idle,
    val nextCursor: String? = null,
    val loadingMore: Boolean = false,
    val loadMoreError: String? = null,
    val detailState: RecordDetailLoadState = RecordDetailLoadState.Idle,
    val operation: RecordOperationState = RecordOperationState(),
    val draft: RecordDraft = RecordDraft(),
    val editingRecordId: String? = null,
    val editingRecordVersion: Int? = null,
)

class RecordsViewModel(private val gateway: RecordsGateway) : ViewModel() {
    private var timeZoneId: String? = null
    private var sessionEpoch = 0L
    private var listRequest = 0L
    private var detailRequest = 0L
    private var draftEdited = false
    private val mutableState = MutableStateFlow(RecordsUiState(draft = defaultDraft()))
    val uiState: StateFlow<RecordsUiState> = mutableState.asStateFlow()

    fun setTimeZone(value: String?) {
        val resolved = value?.takeIf { it.isNotBlank() }?.let { runCatching { ZoneId.of(it).id }.getOrNull() }
        if (timeZoneId != resolved) {
            timeZoneId = resolved
            if (!draftEdited) mutableState.value = mutableState.value.copy(draft = defaultDraft())
        }
    }

    fun load(type: WorkspaceRecordType, cursor: String? = null) {
        val append = cursor != null
        val epoch = sessionEpoch
        val request = ++listRequest
        mutableState.value = mutableState.value.copy(
            listType = type,
            loadState = if (append) mutableState.value.loadState else RecordsLoadState.Loading,
            nextCursor = if (append) mutableState.value.nextCursor else null,
            loadingMore = append,
            loadMoreError = null,
        )
        viewModelScope.launch {
            val result = gateway.list(type, cursor)
            if (epoch != sessionEpoch || request != listRequest) return@launch
            when (result) {
                is ApiResult.Failure -> mutableState.value = if (append) mutableState.value.copy(
                    loadingMore = false, loadMoreError = result.errorText(),
                ) else mutableState.value.copy(loadState = result.toLoadError(), loadingMore = false)
                is ApiResult.Success -> {
                    val incoming = result.value.items.map { it.toRow(type) }
                    val combined = if (append) (mutableState.value.loadState as? RecordsLoadState.Loaded)?.records.orEmpty() + incoming else incoming
                    val records = combined.distinctBy(RecordRow::id)
                    mutableState.value = mutableState.value.copy(
                        loadState = if (records.isEmpty()) RecordsLoadState.Empty else RecordsLoadState.Loaded(records),
                        nextCursor = result.value.nextCursor,
                        loadingMore = false,
                        loadMoreError = null,
                    )
                }
            }
        }
    }

    fun loadMore() {
        val state = mutableState.value
        val cursor = state.nextCursor ?: return
        if (!state.loadingMore) load(state.listType ?: return, cursor)
    }

    fun loadDetail(type: WorkspaceRecordType, id: String) {
        val epoch = sessionEpoch
        val request = ++detailRequest
        mutableState.value = mutableState.value.copy(detailState = RecordDetailLoadState.Loading)
        viewModelScope.launch {
            when (val result = gateway.detail(type, id)) {
                is ApiResult.Failure -> if (epoch == sessionEpoch && request == detailRequest) {
                    mutableState.value = mutableState.value.copy(detailState = RecordDetailLoadState.Error(result.errorText()))
                }
                is ApiResult.Success -> {
                    var detail = result.value
                    if (type == WorkspaceRecordType.SYMPTOM) {
                        detail = when (val history = gateway.symptomStatusHistory(id)) {
                            is ApiResult.Success -> detail.copy(statusHistory = history.value.events)
                            is ApiResult.Failure -> detail.copy(statusHistoryError = history.errorText())
                        }
                    }
                    if (epoch == sessionEpoch && request == detailRequest) {
                        mutableState.value = mutableState.value.copy(detailState = RecordDetailLoadState.Loaded(detail))
                    }
                }
            }
        }
    }

    fun refreshDetail(type: WorkspaceRecordType, id: String) = loadDetail(type, id)

    fun beginEdit(type: WorkspaceRecordType) {
        val detail = (mutableState.value.detailState as? RecordDetailLoadState.Loaded)?.detail ?: return
        val local = runCatching { OffsetDateTime.parse(detail.occurredAt).atZoneSameInstant(ZoneId.of(timeZoneId ?: ZoneId.systemDefault().id)) }.getOrNull()
        val payload = detail.payload
        val draft = when (type) {
            WorkspaceRecordType.DIET -> RecordDraft(
                date = local?.toLocalDate()?.toString().orEmpty(), time = local?.toLocalTime()?.withSecond(0)?.withNano(0)?.toString().orEmpty(),
                mealType = payload.mealType ?: "lunch", description = payload.textDescription.orEmpty(),
                portionNote = payload.portionNote, cookingMethod = payload.cookingMethod, subjectiveNote = payload.subjectiveNote,
                dietItems = payload.items.orEmpty(),
            )
            WorkspaceRecordType.STOOL -> RecordDraft(
                date = local?.toLocalDate()?.toString().orEmpty(), time = local?.toLocalTime()?.withSecond(0)?.withNano(0)?.toString().orEmpty(),
                bristolType = payload.bristolType, bowelNote = payload.notes.orEmpty(), discomfort = payload.processSensation?.firstOrNull(),
                bowelAmount = payload.bowelAmount, colorCode = payload.colorCode, bloodReported = payload.bloodReported,
                urgencyLevel = payload.urgencyLevel,
            )
            WorkspaceRecordType.SYMPTOM -> {
                val item = payload.items.orEmpty().firstOrNull()
                RecordDraft(
                    date = local?.toLocalDate()?.toString().orEmpty(), time = local?.toLocalTime()?.withSecond(0)?.withNano(0)?.toString().orEmpty(),
                    symptomCode = item?.symptomCode, otherDescription = item?.otherDescription.orEmpty(), bodyLocation = item?.bodyLocation,
                    severity = item?.severity ?: 0, duration = payload.durationMinutes?.toString().orEmpty(), symptomStatus = payload.symptomStatus ?: "ongoing",
                    symptomNote = payload.notes.orEmpty(), companionSigns = payload.companionSigns.orEmpty(),
                )
            }
            WorkspaceRecordType.MOOD -> RecordDraft(
                date = local?.toLocalDate()?.toString().orEmpty(), time = local?.toLocalTime()?.withSecond(0)?.withNano(0)?.toString().orEmpty(),
                moodLevel = detail.moodLevel, moodTags = detail.emotionTags, moodNote = detail.note.orEmpty(),
            )
        }
        draftEdited = true
        mutableState.value = mutableState.value.copy(draft = draft, editingRecordId = detail.id, editingRecordVersion = detail.recordVersion, operation = RecordOperationState())
    }

    fun updateDraft(transform: (RecordDraft) -> RecordDraft) {
        draftEdited = true
        mutableState.value = mutableState.value.copy(draft = transform(mutableState.value.draft))
    }

    fun addDietItem(name: String, amount: String? = null) {
        if (name.isBlank()) return
        updateDraft { it.copy(dietItems = it.dietItems + RecordItemDto(name = name.trim(), amountText = amount?.trim()?.ifEmpty { null })) }
    }

    fun removeDietItem(index: Int) = updateDraft { it.copy(dietItems = it.dietItems.filterIndexed { i, _ -> i != index }) }

    fun save(type: WorkspaceRecordType) {
        val current = mutableState.value
        val draft = current.draft
        if (current.operation.saving) return
        when {
            type == WorkspaceRecordType.DIET && draft.description.isBlank() && draft.dietItems.isEmpty() -> return message("请填写饮食描述或添加食物。")
            type == WorkspaceRecordType.SYMPTOM && draft.symptomCode == null -> return message("请选择一项症状。")
            type == WorkspaceRecordType.SYMPTOM && draft.symptomCode == "other" && draft.otherDescription.isBlank() -> return message("请填写“其他”症状描述。")
            type == WorkspaceRecordType.SYMPTOM && draft.otherDescription.length > 160 -> return message("“其他”症状描述最多 160 字。")
            type == WorkspaceRecordType.MOOD && draft.moodLevel == null -> return message("请选择此刻的心情等级。")
            type == WorkspaceRecordType.MOOD && draft.moodNote.length > 500 -> return message("备注最多 500 字。")
        }
        val zone = timeZoneId ?: return message("正在读取本人时区，请稍后重试。")
        val occurredAt = parseOccurredAt(draft.date, draft.time, zone) ?: return message("请输入有效的日期和时间。")
        val duration = draft.duration.trim().ifEmpty { null }?.toIntOrNull()
        if (type == WorkspaceRecordType.SYMPTOM && draft.duration.isNotBlank() && (duration == null || duration !in 0..10080)) return message("持续时间需为 0 至 10080 分钟。")
        val editingId = current.editingRecordId
        val version = current.editingRecordVersion
        mutableState.value = current.copy(operation = RecordOperationState(saving = true))
        val epoch = sessionEpoch
        viewModelScope.launch {
            val key = UUID.randomUUID().toString()
            val result: ApiResult<RecordDetailModel> = if (type == WorkspaceRecordType.MOOD) {
                when {
                    editingId != null && version != null -> when (val updated = gateway.updateMood(editingId, MoodPatchDto(
                        recordVersion = version, occurredAt = occurredAt, moodLevel = draft.moodLevel,
                        emotionTags = draft.moodTags.distinct().take(5), note = ExplicitNullableString(draft.moodNote.trim().ifEmpty { null }),
                    ))) {
                        is ApiResult.Failure -> updated
                        is ApiResult.Success -> ApiResult.Success(updated.value.toRecordDetail())
                    }
                    else -> when (val created = gateway.createMood(key, MoodWriteDto(
                        occurredAt, draft.moodLevel!!, draft.moodTags.distinct().take(5), draft.moodNote.trim().ifEmpty { null },
                    ))) {
                        is ApiResult.Failure -> created
                        is ApiResult.Success -> ApiResult.Success(created.value.toRecordDetail())
                    }
                }
            } else {
                val payload = draft.toPayload(type, duration)
                if (editingId != null && version != null) gateway.update(type, editingId, RecordPatchDto(version, occurredAt, payload))
                else gateway.create(type, key, RecordWriteDto(occurredAt, payload))
            }
            if (epoch != sessionEpoch) return@launch
            when (result) {
                is ApiResult.Failure -> mutableState.value = mutableState.value.copy(operation = result.toOperationError())
                is ApiResult.Success -> mutableState.value = mutableState.value.copy(
                    operation = RecordOperationState(feedback = if (editingId == null) "记录已保存。" else "修改已保存。", savedRecordId = result.value.id),
                    detailState = RecordDetailLoadState.Loaded(result.value),
                )
            }
        }
    }

    fun delete(type: WorkspaceRecordType, row: RecordRow) = delete(type, row.id, row.version)

    fun deleteDetail(type: WorkspaceRecordType) {
        val detail = (mutableState.value.detailState as? RecordDetailLoadState.Loaded)?.detail ?: return
        delete(type, detail.id, detail.recordVersion)
    }

    private fun delete(type: WorkspaceRecordType, id: String, version: Int) {
        mutableState.value = mutableState.value.copy(operation = RecordOperationState(saving = true))
        val epoch = sessionEpoch
        viewModelScope.launch {
            val result = if (type == WorkspaceRecordType.MOOD) gateway.deleteMood(id, version) else gateway.delete(type, id, version)
            if (epoch != sessionEpoch) return@launch
            mutableState.value = mutableState.value.copy(operation = when (result) {
                is ApiResult.Success -> RecordOperationState(feedback = "记录已删除。", savedRecordId = id)
                is ApiResult.Failure -> result.toOperationError()
            })
            if (result is ApiResult.Success) load(type)
        }
    }

    fun clearDraft() {
        draftEdited = false
        mutableState.value = mutableState.value.copy(draft = defaultDraft(), operation = RecordOperationState(), editingRecordId = null, editingRecordVersion = null)
    }

    fun clearDetail() {
        detailRequest += 1
        mutableState.value = mutableState.value.copy(detailState = RecordDetailLoadState.Idle)
    }

    fun clearForLogout() {
        sessionEpoch += 1
        listRequest += 1
        detailRequest += 1
        draftEdited = false
        timeZoneId = null
        mutableState.value = RecordsUiState(draft = defaultDraft())
    }

    private fun defaultDraft(): RecordDraft {
        val now = OffsetDateTime.now(ZoneId.of(timeZoneId ?: ZoneId.systemDefault().id))
        return RecordDraft(date = now.toLocalDate().toString(), time = now.toLocalTime().withSecond(0).withNano(0).toString())
    }

    private fun message(text: String) { mutableState.value = mutableState.value.copy(operation = RecordOperationState(feedback = text)) }
}

private fun RecordDraft.toPayload(type: WorkspaceRecordType, duration: Int?): RecordPayloadDto = when (type) {
    WorkspaceRecordType.DIET -> RecordPayloadDto(
        mealType = mealType, textDescription = description.trim().ifEmpty { null }, items = dietItems.takeIf { it.isNotEmpty() },
        portionNote = portionNote, cookingMethod = cookingMethod, subjectiveNote = subjectiveNote,
    )
    WorkspaceRecordType.STOOL -> RecordPayloadDto(
        bristolType = bristolType, colorCode = colorCode, bloodReported = bloodReported, urgencyLevel = urgencyLevel,
        bowelAmount = bowelAmount, processSensation = discomfort?.let(::listOf) ?: emptyList(), notes = bowelNote.trim().ifEmpty { null },
    )
    WorkspaceRecordType.SYMPTOM -> RecordPayloadDto(
        items = listOf(RecordItemDto(symptomCode = symptomCode, otherDescription = otherDescription.trim().ifEmpty { null }, severity = severity, bodyLocation = bodyLocation)),
        symptomStatus = symptomStatus, durationMinutes = duration, notes = symptomNote.trim().ifEmpty { null }, companionSigns = companionSigns,
    )
    WorkspaceRecordType.MOOD -> error("Mood records use their dedicated API")
}

private fun WorkspaceRecordType.apiType() = when (this) {
    WorkspaceRecordType.DIET -> PatientRecordType.DIET
    WorkspaceRecordType.STOOL -> PatientRecordType.STOOL
    WorkspaceRecordType.SYMPTOM -> PatientRecordType.SYMPTOM
    WorkspaceRecordType.MOOD -> error("Mood records use their dedicated API")
}

private fun ApiResult<MoodPageDto>.mapMoodPage(): ApiResult<RecordPageDto> = when (this) {
    is ApiResult.Failure -> this
    is ApiResult.Success -> ApiResult.Success(RecordPageDto(value.items.map { summary ->
        RecordDto(summary.id, summary.recordVersion, summary.occurredAt,
            RecordPayloadDto(textDescription = "心情等级 ${summary.moodLevel}"), summary.createdAt, summary.updatedAt, 0)
    }, value.nextCursor))
}

private fun RecordDto.toRecordDetail(type: WorkspaceRecordType) = RecordDetailModel(
    id, recordVersion, occurredAt, payload,
    statusHistory = emptyList(),
    imageSetVersion = imageSetVersion,
)
private fun MoodDetailDto.toRecordDetail() = RecordDetailModel(
    id, recordVersion, occurredAt, RecordPayloadDto(textDescription = "心情等级 $moodLevel"), moodLevel, emotionTags, note,
)
private fun RecordDto.toRow(type: WorkspaceRecordType) = RecordRow(
    id, recordVersion,
    if (type == WorkspaceRecordType.MOOD) payload.textDescription ?: "心情记录" else payload.textDescription ?: payload.notes ?: payload.items?.joinToString { it.name ?: it.otherDescription ?: it.symptomCode.orEmpty() } ?: "本人记录",
    occurredAt,
)

private fun parseOccurredAt(date: String, time: String, timeZoneId: String): String? = runCatching {
    java.time.LocalDateTime.of(java.time.LocalDate.parse(date.replace('/', '-')), java.time.LocalTime.parse(time))
        .atZone(ZoneId.of(timeZoneId)).toOffsetDateTime().toString()
}.getOrNull()

private fun ApiResult.Failure.toLoadError() = RecordsLoadState.Error(errorText())
private fun ApiResult.Failure.toOperationError() = RecordOperationState(feedback = errorText(), conflict = status == 409)
private fun ApiResult.Failure.errorText(): String = when {
    code == "SERVICE_UNAVAILABLE" -> "当前版本尚未连接记录服务。"
    code == "CONSENT_REQUIRED" -> "请先完成心情记录所需授权后重试。"
    status == 409 -> "记录版本冲突：请重新读取详情后再修改或删除。"
    status == 401 -> "登录状态已失效，请重新登录。"
    status == 404 -> "记录不存在或已被删除。"
    status == null -> "网络暂不可用，请检查连接后重试。"
    else -> "暂时无法完成请求（${code ?: "REQUEST_FAILED"}）。"
}
