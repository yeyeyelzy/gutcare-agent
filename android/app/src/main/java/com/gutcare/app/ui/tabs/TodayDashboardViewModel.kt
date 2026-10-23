package com.gutcare.app.ui.tabs

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.gutcare.app.core.network.AnalysisAdviceRepository
import com.gutcare.app.core.network.ApiResult
import com.gutcare.app.core.network.AdvicePageDto
import com.gutcare.app.core.network.HistoryPageDto
import com.gutcare.app.core.network.HistoryItemDto
import com.gutcare.app.core.network.MedicationCheckinDto
import com.gutcare.app.core.network.MedicationRepository
import com.gutcare.app.core.network.NotificationRepository
import com.gutcare.app.core.network.NotificationUnreadCountDto
import com.gutcare.app.core.network.RecordsRepository
import com.gutcare.app.core.network.RiskAlertDto
import com.gutcare.app.core.network.RiskAlertPageDto
import com.gutcare.app.ui.records.TodayMedicationUiState
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter

data class DashboardPart<out T>(val value: T? = null, val failed: Boolean = false)
data class TodayDashboardState(
    val dateLabel: String = "今天",
    val risks: DashboardPart<List<RiskAlertDto>> = DashboardPart(),
    val medication: DashboardPart<TodayMedicationUiState> = DashboardPart(),
    val recentRecord: DashboardPart<String> = DashboardPart(),
    val latestAdvice: DashboardPart<String> = DashboardPart(),
    val unreadCount: Int? = null,
    val loading: Boolean = false,
)

internal val RECENT_HEALTH_HISTORY_CATEGORIES = listOf("diet", "stool", "symptom", "mood", "medication_checkin", "activity")

interface TodayDashboardGateway {
    suspend fun risks(): ApiResult<RiskAlertPageDto>
    suspend fun medication(): ApiResult<List<MedicationCheckinDto>>
    suspend fun recentHealthHistory(): ApiResult<HistoryPageDto>
    suspend fun latestAdvice(): ApiResult<AdvicePageDto>
    suspend fun unreadCount(): ApiResult<NotificationUnreadCountDto>
}

private class RepositoryTodayDashboardGateway(
    private val records: RecordsRepository,
    private val medicationRepository: MedicationRepository,
    private val analysisAdvice: AnalysisAdviceRepository,
    private val notifications: NotificationRepository,
) : TodayDashboardGateway {
    override suspend fun risks() = records.listRiskAlerts(limit = 3, unreadOnly = true)
    override suspend fun medication() = medicationRepository.todayCheckins()
    override suspend fun recentHealthHistory() = records.history(
        limit = 5,
        categories = RECENT_HEALTH_HISTORY_CATEGORIES,
    )
    override suspend fun latestAdvice() = analysisAdvice.adviceList()
    override suspend fun unreadCount() = notifications.unreadCount()
}

/** Loads independent home cards concurrently; each endpoint may degrade without blanking the others. */
class TodayDashboardViewModel(
    private val gateway: TodayDashboardGateway,
) : ViewModel() {
    private val mutable = MutableStateFlow(TodayDashboardState())
    val state = mutable.asStateFlow()

    private var refreshGeneration = 0L
    private var refreshJob: Job? = null

    constructor(
        records: RecordsRepository,
        medication: MedicationRepository,
        analysisAdvice: AnalysisAdviceRepository,
        notifications: NotificationRepository,
    ) : this(RepositoryTodayDashboardGateway(records, medication, analysisAdvice, notifications))

    fun refresh(timeZone: String?) {
        val generation = ++refreshGeneration
        refreshJob?.cancel()
        refreshJob = viewModelScope.launch {
            val zone = runCatching { ZoneId.of(timeZone ?: "UTC") }.getOrDefault(ZoneId.of("UTC"))
            val localDate = LocalDate.now(zone)
            val dateText = runCatching { localDate.format(DateTimeFormatter.ofPattern("M月d日 EEEE", java.util.Locale.CHINA)) }.getOrDefault("今天")
            mutable.value = mutable.value.copy(loading = true, dateLabel = dateText)
            coroutineScope {
                val risk = async { gateway.risks() }
                val checkins = async { gateway.medication() }
                val history = async { gateway.recentHealthHistory() }
                val advice = async { gateway.latestAdvice() }
                val unread = async { gateway.unreadCount() }
                val riskResult = risk.await()
                val checkinsResult = checkins.await()
                val historyResult = history.await()
                val adviceResult = advice.await()
                val unreadResult = unread.await()
                if (generation != refreshGeneration) return@coroutineScope
                val next = mutable.value.copy(loading = false, dateLabel = dateText)
                mutable.value = next.copy(
                    risks = when (val r = riskResult) { is ApiResult.Success -> DashboardPart(r.value.items); is ApiResult.Failure -> DashboardPart(failed = true) },
                    medication = when (val r = checkinsResult) {
                        is ApiResult.Success -> DashboardPart(r.value.toTodayMedication())
                        is ApiResult.Failure -> DashboardPart(failed = true)
                    },
                    recentRecord = when (val r = historyResult) {
                        is ApiResult.Success -> DashboardPart(r.value.items.firstOrNull { it.type in RECENT_HEALTH_HISTORY_CATEGORIES }?.let(::recentRecordLabel))
                        is ApiResult.Failure -> DashboardPart(failed = true)
                    },
                    latestAdvice = when (val r = adviceResult) {
                        is ApiResult.Success -> DashboardPart(r.value.items.firstOrNull()?.title)
                        is ApiResult.Failure -> DashboardPart(failed = true)
                    },
                    unreadCount = (unreadResult as? ApiResult.Success)?.value?.count,
                )
            }
        }
    }

    fun clearForLogout() {
        refreshGeneration++
        refreshJob?.cancel()
        refreshJob = null
        mutable.value = TodayDashboardState()
    }

    private fun List<MedicationCheckinDto>.toTodayMedication(): TodayMedicationUiState {
        val complete = count { it.status == "taken" }
        return TodayMedicationUiState(completedCount = complete, totalCount = size, nextLabel = firstOrNull { it.status == "pending" }?.scheduledFor)
    }

    private fun recentRecordLabel(item: HistoryItemDto): String = when (item.type) {
        "diet" -> "最近记录：饮食"
        "stool" -> "最近记录：排便"
        "symptom" -> "最近记录：症状"
        "mood" -> "最近记录：心情"
        "medication_checkin" -> "最近记录：用药打卡"
        "activity" -> "最近记录：活动"
        "advice" -> "最近记录：建议"
        else -> "最近有一条健康记录"
    }
}

class TodayDashboardViewModelFactory(
    private val records: RecordsRepository,
    private val medication: MedicationRepository,
    private val analysisAdvice: AnalysisAdviceRepository,
    private val notifications: NotificationRepository,
) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST") override fun <T : ViewModel> create(modelClass: Class<T>): T {
        require(modelClass.isAssignableFrom(TodayDashboardViewModel::class.java))
        return TodayDashboardViewModel(records, medication, analysisAdvice, notifications) as T
    }
}
