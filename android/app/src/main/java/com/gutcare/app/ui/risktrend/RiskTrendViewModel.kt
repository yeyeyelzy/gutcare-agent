package com.gutcare.app.ui.risktrend

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.gutcare.app.core.network.ApiResult
import com.gutcare.app.core.network.HistoryItemDto
import com.gutcare.app.core.network.HistoryPageDto
import com.gutcare.app.core.network.MoodTrendDto
import com.gutcare.app.core.network.RecordsRepository
import com.gutcare.app.core.network.RiskAlertDto
import com.gutcare.app.core.network.RiskAlertPageDto
import com.gutcare.app.core.network.TrendResponseDto
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

interface RiskTrendGateway {
    suspend fun risks(cursor: String?): ApiResult<RiskAlertPageDto>
    suspend fun risk(id: String): ApiResult<RiskAlertDto>
    suspend fun readRisk(id: String): ApiResult<RiskAlertDto>
    suspend fun reevaluateRisk(id: String): ApiResult<RiskAlertDto>
    suspend fun trends(from: String, to: String, bucket: String): ApiResult<TrendResponseDto>
    suspend fun history(cursor: String?): ApiResult<HistoryPageDto>
}

class RepositoryRiskTrendGateway(private val repository: RecordsRepository) : RiskTrendGateway {
    override suspend fun risks(cursor: String?) = repository.listRiskAlerts(cursor, 20, null)
    override suspend fun risk(id: String) = repository.riskAlert(id)
    override suspend fun readRisk(id: String) = repository.markRiskAlertRead(id)
    override suspend fun reevaluateRisk(id: String) = repository.reevaluateRiskAlert(id)
    override suspend fun trends(from: String, to: String, bucket: String) = repository.trends(from, to, bucket)
    override suspend fun history(cursor: String?) = repository.history(cursor, 30)
}

class RiskTrendViewModelFactory(private val gateway: RiskTrendGateway) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        require(modelClass.isAssignableFrom(RiskTrendViewModel::class.java))
        return RiskTrendViewModel(gateway) as T
    }
}

sealed interface RiskListState {
    data object Loading : RiskListState
    data object Empty : RiskListState
    data class Ready(val items: List<RiskAlertDto>) : RiskListState
    data class Error(val message: String) : RiskListState
}
sealed interface TrendState {
    data object Idle : TrendState
    data object Loading : TrendState
    data object Empty : TrendState
    data class Ready(val response: TrendResponseDto) : TrendState
    data class ConsentRequired(val mood: MoodTrendDto) : TrendState
    data class Error(val message: String) : TrendState
}
sealed interface HistoryState {
    data object Loading : HistoryState
    data object Empty : HistoryState
    data class Ready(val items: List<HistoryItemDto>, val nextCursor: String?) : HistoryState
    data class Error(val message: String) : HistoryState
}
data class RiskTrendUiState(
    val risks: RiskListState = RiskListState.Loading,
    val riskCursor: String? = null,
    val riskLoadingMore: Boolean = false,
    val detail: RiskAlertDto? = null,
    val detailLoading: Boolean = false,
    val actionBusy: Boolean = false,
    val actionMessage: String? = null,
    val trends: TrendState = TrendState.Idle,
    val history: HistoryState = HistoryState.Loading,
    val historyLoadingMore: Boolean = false,
    val historyMoreError: String? = null,
)

class RiskTrendViewModel(private val gateway: RiskTrendGateway) : ViewModel() {
    private val mutable = MutableStateFlow(RiskTrendUiState())
    val uiState: StateFlow<RiskTrendUiState> = mutable.asStateFlow()

    fun clear() { mutable.value = RiskTrendUiState() }

    fun loadRisks() = viewModelScope.launch {
        mutable.value = mutable.value.copy(risks = RiskListState.Loading, riskCursor = null)
        when (val result = gateway.risks(null)) {
            is ApiResult.Success -> mutable.value = mutable.value.copy(
                risks = result.value.items.takeIf { it.isNotEmpty() }?.let(RiskListState::Ready) ?: RiskListState.Empty,
                riskCursor = result.value.nextCursor,
            )
            is ApiResult.Failure -> mutable.value = mutable.value.copy(risks = RiskListState.Error(friendly(result)))
        }
    }
    fun loadMoreRisks() = viewModelScope.launch {
        val cursor = mutable.value.riskCursor ?: return@launch
        val existing = (mutable.value.risks as? RiskListState.Ready)?.items.orEmpty()
        mutable.value = mutable.value.copy(riskLoadingMore = true)
        when (val result = gateway.risks(cursor)) {
            is ApiResult.Success -> mutable.value = mutable.value.copy(
                risks = RiskListState.Ready(existing + result.value.items), riskCursor = result.value.nextCursor, riskLoadingMore = false,
            )
            is ApiResult.Failure -> mutable.value = mutable.value.copy(riskLoadingMore = false, actionMessage = friendly(result))
        }
    }
    fun openRisk(id: String) = viewModelScope.launch {
        mutable.value = mutable.value.copy(detailLoading = true, detail = null, actionMessage = null)
        when (val result = gateway.risk(id)) {
            is ApiResult.Success -> mutable.value = mutable.value.copy(detailLoading = false, detail = result.value)
            is ApiResult.Failure -> mutable.value = mutable.value.copy(detailLoading = false, actionMessage = friendly(result))
        }
    }
    fun markRead() = riskAction(gatewayCall = { gateway.readRisk(it) }, success = "已标记查看。")
    fun reevaluate() = riskAction(gatewayCall = { gateway.reevaluateRisk(it) }, success = "已提交重新评估状态。此状态不代表风险解除。")
    private fun riskAction(gatewayCall: suspend (String) -> ApiResult<RiskAlertDto>, success: String) = viewModelScope.launch {
        val id = mutable.value.detail?.id ?: return@launch
        mutable.value = mutable.value.copy(actionBusy = true, actionMessage = null)
        when (val result = gatewayCall(id)) {
            is ApiResult.Success -> mutable.value = mutable.value.copy(detail = result.value, actionBusy = false, actionMessage = success)
            is ApiResult.Failure -> mutable.value = mutable.value.copy(actionBusy = false, actionMessage = friendly(result))
        }
    }
    fun loadTrends(from: String, to: String, bucket: String = "day") = viewModelScope.launch {
        mutable.value = mutable.value.copy(trends = TrendState.Loading)
        when (val result = gateway.trends(from, to, bucket)) {
            is ApiResult.Success -> {
                val response = result.value
                val anyData = response.activity.hasData || response.stool.hasData || response.symptom.hasData ||
                    response.dietConfirmedCategories.hasData || response.medicationCheckins.hasData ||
                    (response.mood.availability == "available" && response.mood.buckets.isNotEmpty())
                mutable.value = mutable.value.copy(trends = if (anyData) TrendState.Ready(response) else if (response.mood.availability == "consent_required") TrendState.ConsentRequired(response.mood) else TrendState.Empty)
            }
            is ApiResult.Failure -> mutable.value = mutable.value.copy(trends = TrendState.Error(friendly(result)))
        }
    }
    fun loadHistory() = viewModelScope.launch {
        mutable.value = mutable.value.copy(history = HistoryState.Loading)
        when (val result = gateway.history(null)) {
            is ApiResult.Success -> mutable.value = mutable.value.copy(history = result.value.toState(), historyMoreError = null)
            is ApiResult.Failure -> mutable.value = mutable.value.copy(history = HistoryState.Error(friendly(result)))
        }
    }
    fun loadMoreHistory() = viewModelScope.launch {
        val current = mutable.value.history as? HistoryState.Ready ?: return@launch
        val cursor = current.nextCursor ?: return@launch
        mutable.value = mutable.value.copy(historyLoadingMore = true, historyMoreError = null)
        when (val result = gateway.history(cursor)) {
            is ApiResult.Success -> mutable.value = mutable.value.copy(history = HistoryState.Ready(current.items + result.value.items, result.value.nextCursor), historyLoadingMore = false)
            is ApiResult.Failure -> mutable.value = mutable.value.copy(historyLoadingMore = false, historyMoreError = friendly(result))
        }
    }
    private fun HistoryPageDto.toState(): HistoryState = if (items.isEmpty()) HistoryState.Empty else HistoryState.Ready(items, nextCursor)
    private fun friendly(result: ApiResult.Failure): String = when (result.code) {
        "NETWORK_ERROR" -> "网络暂时不可用，请检查连接后重试。"
        "CONSENT_REQUIRED" -> "当前授权状态不满足此项数据处理。"
        "INVALID_CURSOR" -> "历史位置已失效，请重新加载。"
        "HTTP_ERROR" -> "服务暂时无法处理请求，请稍后重试。"
        else -> "暂时无法加载，请稍后重试。"
    }
}
