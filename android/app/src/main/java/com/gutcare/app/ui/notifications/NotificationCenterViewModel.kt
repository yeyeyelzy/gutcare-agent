package com.gutcare.app.ui.notifications

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.gutcare.app.core.network.ApiResult
import com.gutcare.app.core.network.NotificationPreferenceDto
import com.gutcare.app.core.network.NotificationRepository
import com.gutcare.app.core.network.PatientNotificationDto
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.util.UUID

enum class NotificationCategoryFilter(val wire: String?, val label: String) {
    ALL(null, "全部"), ANALYSIS("analysis", "分析"), ADVICE("advice", "建议"), RISK("risk", "风险"), MEDICATION("medication_reminder", "用药提醒"),
}

data class NotificationCenterState(
    val loading: Boolean = false,
    val items: List<PatientNotificationDto> = emptyList(),
    val nextCursor: String? = null,
    val unreadCount: Int? = null,
    val unreadOnly: Boolean = false,
    val category: NotificationCategoryFilter = NotificationCategoryFilter.ALL,
    val selectedIds: Set<String> = emptySet(),
    val detail: PatientNotificationDto? = null,
    val preferences: NotificationPreferenceDto? = null,
    val ordinaryEnabled: Boolean = true,
    val quietStart: String = "",
    val quietEnd: String = "",
    val timezone: String = "UTC",
    val busy: Boolean = false,
    val message: String? = null,
    val error: Boolean = false,
)

sealed interface SafeNotificationTarget {
    data class Risk(val id: String) : SafeNotificationTarget
    data class Medication(val id: String) : SafeNotificationTarget
    data class Analysis(val id: String) : SafeNotificationTarget
    data class Advice(val id: String) : SafeNotificationTarget
}

/** IDs are accepted only for the target types explicitly frozen by the OpenAPI contract. */
fun safeNotificationTarget(item: PatientNotificationDto): SafeNotificationTarget? {
    val target = item.target ?: return null
    if (item.targetUnavailable || runCatching { UUID.fromString(target.id) }.isFailure) return null
    return when (target.type) {
        "risk_alert" -> SafeNotificationTarget.Risk(target.id)
        "medication_checkin" -> SafeNotificationTarget.Medication(target.id)
        "analysis_task" -> SafeNotificationTarget.Analysis(target.id)
        "advice" -> SafeNotificationTarget.Advice(target.id)
        else -> null
    }
}

class NotificationCenterViewModel(private val repository: NotificationRepository) : ViewModel() {
    private val mutable = MutableStateFlow(NotificationCenterState())
    val state = mutable.asStateFlow()
    private var lifecycleGeneration = 0L
    private var detailRequestGeneration = 0L
    private var listRequestGeneration = 0L

    fun load(reset: Boolean = true): kotlinx.coroutines.Job {
        val generation = lifecycleGeneration
        val requestGeneration = ++listRequestGeneration
        return viewModelScope.launch {
            if (generation != lifecycleGeneration || requestGeneration != listRequestGeneration) return@launch
            val before = mutable.value
            mutable.value = before.copy(loading = true, message = null, error = false, selectedIds = if (reset) emptySet() else before.selectedIds)
            val cursor = if (reset) null else before.nextCursor
            val result = repository.list(cursor, before.category.wire, before.unreadOnly)
            if (generation != lifecycleGeneration || requestGeneration != listRequestGeneration) return@launch
            when (result) {
                is ApiResult.Success -> mutable.value = mutable.value.copy(loading = false, items = if (reset) result.value.items else before.items + result.value.items, nextCursor = result.value.nextCursor)
                is ApiResult.Failure -> fail(result.status)
            }
            if (generation == lifecycleGeneration) refreshCount()
        }
    }
    fun refreshCount(): kotlinx.coroutines.Job {
        val generation = lifecycleGeneration
        return viewModelScope.launch {
            if (generation != lifecycleGeneration) return@launch
            when (val result = repository.unreadCount()) {
                is ApiResult.Success -> if (generation == lifecycleGeneration) mutable.value = mutable.value.copy(unreadCount = result.value.count)
                is ApiResult.Failure -> if (generation == lifecycleGeneration && mutable.value.unreadCount == null) mutable.value = mutable.value.copy(unreadCount = null)
            }
        }
    }
    fun setCategory(value: NotificationCategoryFilter) { mutable.value = mutable.value.copy(category = value); load() }
    fun setUnreadOnly(value: Boolean) { mutable.value = mutable.value.copy(unreadOnly = value); load() }
    fun toggleSelection(id: String) { mutable.value = mutable.value.copy(selectedIds = mutable.value.selectedIds.let { if (id in it) it - id else it + id }) }
    fun openDetail(id: String): kotlinx.coroutines.Job {
        val generation = lifecycleGeneration
        val requestGeneration = ++detailRequestGeneration
        return viewModelScope.launch {
            if (generation != lifecycleGeneration || requestGeneration != detailRequestGeneration) return@launch
            mutable.value = mutable.value.copy(busy = true, detail = null, message = null, error = false)
            when (val result = repository.detail(id)) {
                is ApiResult.Success -> if (generation == lifecycleGeneration && requestGeneration == detailRequestGeneration && result.value.id == id) mutable.value = mutable.value.copy(busy = false, detail = result.value) else if (generation == lifecycleGeneration && requestGeneration == detailRequestGeneration) fail(null)
                is ApiResult.Failure -> if (generation == lifecycleGeneration && requestGeneration == detailRequestGeneration) fail(result.status)
            }
        }
    }
    fun markRead(id: String): kotlinx.coroutines.Job {
        val generation = lifecycleGeneration
        return viewModelScope.launch {
            if (generation != lifecycleGeneration) return@launch
            mutable.value = mutable.value.copy(busy = true, message = null, error = false)
            when (val result = repository.markRead(id)) {
                is ApiResult.Success -> {
                    if (generation != lifecycleGeneration) return@launch
                    val current = mutable.value
                    mutable.value = current.copy(
                        busy = false,
                        detail = current.detail?.takeIf { it.id == id }?.let { result.value },
                        items = current.items.map { if (it.id == id) result.value else it },
                    )
                    refreshCount()
                }
                is ApiResult.Failure -> if (generation == lifecycleGeneration) fail(result.status)
            }
        }
    }
    fun markSelectedRead(): kotlinx.coroutines.Job {
        val generation = lifecycleGeneration
        val ids = mutable.value.selectedIds.toList()
        if (ids.isEmpty()) return viewModelScope.launch { }
        return viewModelScope.launch {
            if (generation != lifecycleGeneration) return@launch
            mutable.value = mutable.value.copy(busy = true, message = null, error = false)
            when (val result = repository.markReadBatch(ids)) {
                is ApiResult.Success -> {
                    if (generation != lifecycleGeneration) return@launch
                    val updates = result.value.items.associateBy { it.id }
                    mutable.value = mutable.value.copy(busy = false, items = mutable.value.items.map { updates[it.id] ?: it }, selectedIds = emptySet(), message = "已将所选通知标为已读。")
                    refreshCount()
                }
                is ApiResult.Failure -> if (generation == lifecycleGeneration) fail(result.status)
            }
        }
    }
    fun loadPreferences(): kotlinx.coroutines.Job {
        val generation = lifecycleGeneration
        return viewModelScope.launch {
            if (generation != lifecycleGeneration) return@launch
            mutable.value = mutable.value.copy(busy = true, message = null, error = false)
            when (val result = repository.preferences()) {
                is ApiResult.Success -> if (generation == lifecycleGeneration) mutable.value = mutable.value.copy(busy = false, preferences = result.value, ordinaryEnabled = result.value.ordinaryInAppEnabled, quietStart = result.value.quietStart.orEmpty(), quietEnd = result.value.quietEnd.orEmpty(), timezone = result.value.timezone)
                is ApiResult.Failure -> if (generation == lifecycleGeneration) fail(result.status)
            }
        }
    }
    fun editPreferences(enabled: Boolean = mutable.value.ordinaryEnabled, start: String = mutable.value.quietStart, end: String = mutable.value.quietEnd) {
        mutable.value = mutable.value.copy(ordinaryEnabled = enabled, quietStart = start, quietEnd = end)
    }
    fun savePreferences(): kotlinx.coroutines.Job {
        val generation = lifecycleGeneration
        val current = mutable.value
        if ((current.quietStart.isBlank()) != (current.quietEnd.isBlank())) {
            mutable.value = current.copy(message = "静默时段需同时填写开始和结束时间，或同时留空。", error = true); return viewModelScope.launch { }
        }
        if (current.quietStart.isNotBlank() && (!current.quietStart.matches(Regex("(?:[01]\\d|2[0-3]):[0-5]\\d(?::[0-5]\\d)?")) || !current.quietEnd.matches(Regex("(?:[01]\\d|2[0-3]):[0-5]\\d(?::[0-5]\\d)?")))) {
            mutable.value = current.copy(message = "请使用 HH:mm 格式填写静默时间。", error = true); return viewModelScope.launch { }
        }
        return viewModelScope.launch {
            if (generation != lifecycleGeneration) return@launch
            mutable.value = current.copy(busy = true, message = null, error = false)
            val body = NotificationPreferenceDto(current.ordinaryEnabled, current.quietStart.ifBlank { null }, current.quietEnd.ifBlank { null }, current.timezone)
            when (val result = repository.updatePreferences(body)) {
                is ApiResult.Success -> if (generation == lifecycleGeneration) mutable.value = mutable.value.copy(busy = false, preferences = result.value, ordinaryEnabled = result.value.ordinaryInAppEnabled, quietStart = result.value.quietStart.orEmpty(), quietEnd = result.value.quietEnd.orEmpty(), timezone = result.value.timezone, message = "偏好已保存。")
                is ApiResult.Failure -> if (generation == lifecycleGeneration) fail(result.status)
            }
        }
    }
    fun clearForLogout() {
        lifecycleGeneration++
        detailRequestGeneration++
        listRequestGeneration++
        mutable.value = NotificationCenterState()
    }
    private fun fail(status: Int?) { mutable.value = mutable.value.copy(loading = false, busy = false, error = true, message = when (status) { 401 -> "登录状态已失效，请重新登录。"; 404 -> "通知已不可用或已被清理。"; 409 -> "通知状态已变化，请刷新后重试。"; else -> "暂时无法加载，请检查网络后重试。" }) }
}

class NotificationCenterViewModelFactory(private val repository: NotificationRepository) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST") override fun <T : ViewModel> create(modelClass: Class<T>): T {
        require(modelClass.isAssignableFrom(NotificationCenterViewModel::class.java))
        return NotificationCenterViewModel(repository) as T
    }
}

private fun ApiResult.Failure.statusForNotification() = status
