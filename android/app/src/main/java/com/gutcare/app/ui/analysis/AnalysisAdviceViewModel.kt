package com.gutcare.app.ui.analysis

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.gutcare.app.core.network.*
import java.time.Instant
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

interface AnalysisAdviceGateway {
    suspend fun tasks(cursor: String? = null): ApiResult<AnalysisTaskPageDto>
    suspend fun preview(type: String, from: String? = null, to: String? = null): ApiResult<AnalysisTaskPreviewDto>
    suspend fun create(type: String, from: String? = null, to: String? = null): ApiResult<AnalysisTaskDto>
    suspend fun task(id: String): ApiResult<AnalysisTaskDto>
    suspend fun cancel(id: String): ApiResult<AnalysisTaskDto>
    suspend fun retry(id: String): ApiResult<AnalysisTaskDto>
    suspend fun adviceList(cursor: String? = null): ApiResult<AdvicePageDto>
    suspend fun advice(id: String): ApiResult<AdviceDto>
    suspend fun markRead(id: String): ApiResult<AdviceDto>
    suspend fun archive(id: String): ApiResult<AdviceDto>
    suspend fun feedback(id: String, value: String, version: Int): ApiResult<AdviceFeedbackDto>
}

class RepositoryAnalysisAdviceGateway(private val repository: AnalysisAdviceRepository) : AnalysisAdviceGateway {
    override suspend fun tasks(cursor: String?) = repository.tasks(cursor)
    override suspend fun preview(type: String, from: String?, to: String?) = repository.preview(type, from, to)
    override suspend fun create(type: String, from: String?, to: String?) = repository.create(type, from, to)
    override suspend fun task(id: String) = repository.task(id)
    override suspend fun cancel(id: String) = repository.cancel(id)
    override suspend fun retry(id: String) = repository.retry(id)
    override suspend fun adviceList(cursor: String?) = repository.adviceList(cursor)
    override suspend fun advice(id: String) = repository.advice(id)
    override suspend fun markRead(id: String) = repository.markRead(id)
    override suspend fun archive(id: String) = repository.archive(id)
    override suspend fun feedback(id: String, value: String, version: Int) = repository.feedback(id, value, version)
}

data class AnalysisAdviceUiState(
    val tasks: List<AnalysisTaskDto> = emptyList(), val advice: List<AdviceDto> = emptyList(),
    val taskCursor: String? = null, val adviceCursor: String? = null,
    val preview: AnalysisTaskPreviewDto? = null, val selectedTask: AnalysisTaskDto? = null,
    val selectedAdvice: AdviceDto? = null, val busy: Boolean = false,
    val taskPolling: Boolean = false, val taskPollingTimedOut: Boolean = false,
    val error: String? = null, val notice: String? = null,
    val analysisType: String = "comprehensive_health_analysis", val from: String = "", val to: String = "",
)

class AnalysisAdviceViewModel(private val gateway: AnalysisAdviceGateway) : ViewModel() {
    private val mutableState = MutableStateFlow(AnalysisAdviceUiState())
    val state: StateFlow<AnalysisAdviceUiState> = mutableState.asStateFlow()
    private var taskPollJob: Job? = null
    private var pollingTaskId: String? = null

    private companion object {
        const val TASK_POLL_INTERVAL_MS = 2_000L
        const val MAX_TASK_POLL_ATTEMPTS = 15
        val terminalTaskStatuses = setOf("succeeded", "partial", "failed", "cancelled")
    }

    fun load() { loadTasks(); loadAdvice() }
    fun chooseType(value: String) { mutableState.value = mutableState.value.copy(analysisType = value) }
    fun setRange(from: String, to: String) { mutableState.value = mutableState.value.copy(from = from, to = to) }
    fun loadTasks(cursor: String? = null) = gatewayCall({ gateway.tasks(cursor) }) { page ->
        mutableState.value = mutableState.value.copy(tasks = if (cursor == null) page.items else mutableState.value.tasks + page.items, taskCursor = page.nextCursor)
    }
    fun loadAdvice(cursor: String? = null) = gatewayCall({ gateway.adviceList(cursor) }) { page ->
        mutableState.value = mutableState.value.copy(advice = if (cursor == null) page.items else mutableState.value.advice + page.items, adviceCursor = page.nextCursor)
    }
    fun preview() {
        val s = mutableState.value
        if (!validRange(s)) return fail("请填写有效的开始和结束时间（ISO 8601）；仅综合分析可以不设范围。")
        gatewayCall({ gateway.preview(s.analysisType, s.from.ifBlank { null }, s.to.ifBlank { null }) }) {
            mutableState.value = mutableState.value.copy(preview = it, notice = "这是创建前预览，任务创建时服务端会重新校验并冻结实际输入。")
        }
    }
    fun create() {
        val s = mutableState.value
        if (s.preview == null) return fail("请先预览分析范围。")
        gatewayCall({ gateway.create(s.analysisType, s.from.ifBlank { null }, s.to.ifBlank { null }) }) {
            mutableState.value = mutableState.value.copy(selectedTask = it, notice = "任务已创建；此客户端不会执行智能体分析。")
            pollTaskUntilTerminal(it)
            loadTasks()
        }
    }
    fun openTask(id: String) {
        stopTaskPolling()
        gatewayCall({ gateway.task(id) }) {
            mutableState.value = mutableState.value.copy(selectedTask = it, taskPollingTimedOut = false)
            pollTaskUntilTerminal(it)
        }
    }
    fun refreshTask(id: String) = openTask(id)
    fun stopTaskPolling(expectedId: String? = null) {
        if (expectedId != null && pollingTaskId != expectedId) return
        taskPollJob?.cancel()
        taskPollJob = null
        pollingTaskId = null
        mutableState.value = mutableState.value.copy(taskPolling = false)
    }
    fun cancelTask(id: String) = gatewayCall({ gateway.cancel(id) }) {
        stopTaskPolling(id)
        mutableState.value = mutableState.value.copy(selectedTask = it, notice = "任务已取消。"); loadTasks()
    }
    fun retryTask(id: String) = gatewayCall({ gateway.retry(id) }) {
        stopTaskPolling(id)
        mutableState.value = mutableState.value.copy(selectedTask = it, notice = "已按原冻结快照创建新尝试。", taskPollingTimedOut = false)
        pollTaskUntilTerminal(it); loadTasks()
    }
    fun openAdvice(id: String) = gatewayCall({ gateway.advice(id) }) { item ->
        mutableState.value = mutableState.value.copy(selectedAdvice = item)
        if (item.status == "new") gatewayCall({ gateway.markRead(id) }) { updated ->
            mutableState.value = mutableState.value.copy(selectedAdvice = updated); loadAdvice()
        }
    }
    fun archiveAdvice(id: String) = gatewayCall({ gateway.archive(id) }) {
        mutableState.value = mutableState.value.copy(selectedAdvice = it, notice = "建议已归档。"); loadAdvice()
    }
    fun feedback(id: String, value: String) {
        val version = mutableState.value.selectedAdvice?.feedback?.version ?: 0
        gatewayCall({ gateway.feedback(id, value, version) }) {
            loadAdvice(); openAdvice(id); mutableState.value = mutableState.value.copy(notice = "反馈已保存。")
        }
    }
    fun backToList() { stopTaskPolling(); mutableState.value = mutableState.value.copy(selectedTask = null, selectedAdvice = null, taskPollingTimedOut = false) }
    fun clear() { stopTaskPolling(); mutableState.value = AnalysisAdviceUiState() }

    private fun pollTaskUntilTerminal(task: AnalysisTaskDto) {
        stopTaskPolling()
        if (task.status in terminalTaskStatuses) return
        pollingTaskId = task.id
        mutableState.value = mutableState.value.copy(taskPolling = true, taskPollingTimedOut = false)
        taskPollJob = viewModelScope.launch {
            repeat(MAX_TASK_POLL_ATTEMPTS) {
                delay(TASK_POLL_INTERVAL_MS)
                if (pollingTaskId != task.id) return@launch
                when (val result = gateway.task(task.id)) {
                    is ApiResult.Success -> {
                        val current = mutableState.value
                        if (current.selectedTask?.id != task.id) return@launch
                        mutableState.value = current.copy(selectedTask = result.value, error = null)
                        if (result.value.status in terminalTaskStatuses) {
                            pollingTaskId = null
                            taskPollJob = null
                            mutableState.value = mutableState.value.copy(taskPolling = false)
                            loadTasks()
                            return@launch
                        }
                    }
                    is ApiResult.Failure -> {
                        val status = result.status?.let { "（$it）" }.orEmpty()
                        mutableState.value = mutableState.value.copy(
                            taskPolling = false,
                            error = "刷新分析任务失败$status：${result.code ?: "NETWORK_ERROR"}",
                        )
                        pollingTaskId = null
                        taskPollJob = null
                        return@launch
                    }
                }
            }
            pollingTaskId = null
            taskPollJob = null
            mutableState.value = mutableState.value.copy(taskPolling = false, taskPollingTimedOut = true)
        }
    }

    private fun validRange(s: AnalysisAdviceUiState): Boolean {
        if (s.from.isBlank() && s.to.isBlank() && s.analysisType == "comprehensive_health_analysis") return true
        if (s.from.isBlank() || s.to.isBlank()) return false
        return runCatching { Instant.parse(s.from).isBefore(Instant.parse(s.to)) }.getOrDefault(false)
    }
    private fun fail(message: String) { mutableState.value = mutableState.value.copy(error = message) }
    private fun <T> gatewayCall(request: suspend () -> ApiResult<T>, onSuccess: (T) -> Unit) {
        viewModelScope.launch {
            mutableState.value = mutableState.value.copy(busy = true, error = null)
            when (val result = request()) {
                is ApiResult.Success -> onSuccess(result.value)
                is ApiResult.Failure -> {
                    val status = result.status?.let { "（$it）" }.orEmpty()
                    val requestId = result.requestId?.let { " · request_id $it" }.orEmpty()
                    mutableState.value = mutableState.value.copy(error = "请求失败$status：${result.code ?: "NETWORK_ERROR"}$requestId")
                }
            }
            mutableState.value = mutableState.value.copy(busy = false)
        }
    }
}

class AnalysisAdviceViewModelFactory(private val gateway: AnalysisAdviceGateway) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T = AnalysisAdviceViewModel(gateway) as T
}
