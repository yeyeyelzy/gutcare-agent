package com.gutcare.app.ui.medication

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.gutcare.app.core.network.ApiResult
import com.gutcare.app.core.network.MedicationCheckinDto
import com.gutcare.app.core.network.MedicationCheckinUpdateDto
import com.gutcare.app.core.network.MedicationPlanCreateDto
import com.gutcare.app.core.network.MedicationPlanDto
import com.gutcare.app.core.network.MedicationPlanTransitionDto
import com.gutcare.app.core.network.MedicationRepository
import com.gutcare.app.core.network.MedicationScheduleDto
import com.gutcare.app.core.network.MedicationScheduleWriteDto
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.util.UUID
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** Thin feature boundary: all business state comes from the authenticated API repository. */
interface MedicationFeatureGateway {
    suspend fun plans(): ApiResult<List<MedicationPlanDto>>
    suspend fun createPlan(key: String, body: MedicationPlanCreateDto): ApiResult<MedicationPlanDto>
    suspend fun transitionPlan(id: String, key: String, body: MedicationPlanTransitionDto): ApiResult<MedicationPlanDto>
    suspend fun schedules(planId: String): ApiResult<List<MedicationScheduleDto>>
    suspend fun createSchedule(planId: String, key: String, body: MedicationScheduleWriteDto): ApiResult<MedicationScheduleDto>
    suspend fun updateSchedule(id: String, body: MedicationScheduleWriteDto): ApiResult<MedicationScheduleDto>
    suspend fun deleteSchedule(id: String, version: Int): ApiResult<Unit>
    suspend fun today(): ApiResult<List<MedicationCheckinDto>>
    suspend fun history(start: String, end: String): ApiResult<List<MedicationCheckinDto>>
    suspend fun updateCheckin(id: String, body: MedicationCheckinUpdateDto): ApiResult<MedicationCheckinDto>
}

class RepositoryMedicationFeatureGateway(private val repository: MedicationRepository) : MedicationFeatureGateway {
    override suspend fun plans() = repository.listPlans()
    override suspend fun createPlan(key: String, body: MedicationPlanCreateDto) = repository.createPlan(key, body)
    override suspend fun transitionPlan(id: String, key: String, body: MedicationPlanTransitionDto) = repository.transitionPlan(id, key, body)
    override suspend fun schedules(planId: String) = repository.listSchedules(planId)
    override suspend fun createSchedule(planId: String, key: String, body: MedicationScheduleWriteDto) = repository.createSchedule(planId, key, body)
    override suspend fun updateSchedule(id: String, body: MedicationScheduleWriteDto) = repository.patchSchedule(id, body)
    override suspend fun deleteSchedule(id: String, version: Int) = repository.deleteSchedule(id, version)
    override suspend fun today() = repository.todayCheckins()
    override suspend fun history(start: String, end: String) = repository.listCheckins(start, end)
    override suspend fun updateCheckin(id: String, body: MedicationCheckinUpdateDto) = repository.updateCheckin(id, body)
}

class MedicationViewModelFactory(private val gateway: MedicationFeatureGateway) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        require(modelClass.isAssignableFrom(MedicationViewModel::class.java))
        return MedicationViewModel(gateway) as T
    }
}

enum class MedicationSection(val label: String) { TODAY("今日打卡"), PLANS("用药计划"), HISTORY("服药历史") }

data class MedicationUiState(
    val section: MedicationSection = MedicationSection.TODAY,
    val loading: Boolean = false,
    val plans: List<MedicationPlanDto> = emptyList(),
    val schedules: Map<String, List<MedicationScheduleDto>> = emptyMap(),
    val today: List<MedicationCheckinDto> = emptyList(),
    val history: List<MedicationCheckinDto> = emptyList(),
    val selectedPlanId: String? = null,
    val error: String? = null,
    val operationMessage: String? = null,
    val conflict: Boolean = false,
    val saving: Boolean = false,
    val historyStart: String = LocalDate.now().minusDays(29).toString(),
    val historyEnd: String = LocalDate.now().toString(),
)

class MedicationViewModel(private val gateway: MedicationFeatureGateway) : ViewModel() {
    private val mutableState = MutableStateFlow(MedicationUiState())
    val uiState: StateFlow<MedicationUiState> = mutableState.asStateFlow()
    private var epoch = 0L

    fun load(section: MedicationSection = mutableState.value.section) {
        val requestEpoch = epoch
        mutableState.value = mutableState.value.copy(section = section, loading = true, error = null)
        viewModelScope.launch {
            val plansResult = gateway.plans()
            if (requestEpoch != epoch) return@launch
            when (plansResult) {
                is ApiResult.Failure -> mutableState.value = mutableState.value.copy(loading = false, error = plansResult.toMessage())
                is ApiResult.Success -> {
                    val plans = plansResult.value
                    val schedulePairs = plans.map { plan -> async { plan.id to gateway.schedules(plan.id) } }.awaitAll()
                    if (requestEpoch != epoch) return@launch
                    val scheduleFailure = schedulePairs.firstNotNullOfOrNull { (_, result) -> (result as? ApiResult.Failure)?.toMessage() }
                    val schedules = schedulePairs.mapNotNull { (id, result) -> (result as? ApiResult.Success)?.let { id to it.value } }.toMap()
                    val checkinsResult = if (section == MedicationSection.HISTORY) gateway.history(mutableState.value.historyStart, mutableState.value.historyEnd) else gateway.today()
                    if (requestEpoch != epoch) return@launch
                    when (checkinsResult) {
                        is ApiResult.Failure -> mutableState.value = mutableState.value.copy(
                            plans = plans, schedules = schedules, loading = false,
                            error = checkinsResult.toMessage(),
                        )
                        is ApiResult.Success -> mutableState.value = mutableState.value.copy(
                            plans = plans, schedules = schedules,
                            today = if (section == MedicationSection.TODAY) checkinsResult.value else mutableState.value.today,
                            history = if (section == MedicationSection.HISTORY) checkinsResult.value else mutableState.value.history,
                            loading = false,
                            error = scheduleFailure,
                            selectedPlanId = mutableState.value.selectedPlanId?.takeIf { selected -> plans.any { it.id == selected } } ?: plans.firstOrNull()?.id,
                        )
                    }
                }
            }
        }
    }

    fun selectSection(section: MedicationSection) = load(section)

    fun setHistoryRange(start: String, end: String) {
        mutableState.value = mutableState.value.copy(historyStart = start, historyEnd = end)
        load(MedicationSection.HISTORY)
    }

    fun selectPlan(id: String) { mutableState.value = mutableState.value.copy(selectedPlanId = id) }

    fun createPlan(name: String, dosage: String, route: String, startDate: String, endDate: String) {
        if (name.isBlank()) return message("请填写药品名称。")
        val body = MedicationPlanCreateDto(
            medicationName = name.trim(), dosageText = dosage.trim().ifBlank { null },
            routeCode = route.trim().ifBlank { null }, startDate = startDate.trim().ifBlank { null },
            endDate = endDate.trim().ifBlank { null }, sourceType = "manual",
        )
        perform("用药计划已保存，待确认。") { gateway.createPlan(UUID.randomUUID().toString(), body) }
    }

    fun transition(plan: MedicationPlanDto, action: String) {
        perform("计划状态已更新。") {
            gateway.transitionPlan(plan.id, UUID.randomUUID().toString(), MedicationPlanTransitionDto(plan.recordVersion, action))
        }
    }

    fun createSchedule(planId: String, localTime: String, timezone: String, validFrom: String, rrule: String) {
        if (localTime.isBlank() || timezone.isBlank() || validFrom.isBlank()) return message("请填写服药时间、时区和开始日期。")
        val body = MedicationScheduleWriteDto(localTime, timezone, rrule.trim().ifBlank { null }, validFrom, enabled = true)
        perform("服药日程已添加。") { gateway.createSchedule(planId, UUID.randomUUID().toString(), body) }
    }

    fun toggleSchedule(schedule: MedicationScheduleDto) {
        val update = MedicationScheduleWriteDto(
            localTime = schedule.localTime, timezone = schedule.timezone, rrule = schedule.rrule,
            validFrom = schedule.validFrom, validTo = schedule.validTo, enabled = !schedule.enabled,
            recordVersion = schedule.recordVersion,
        )
        perform(if (update.enabled) "日程已启用。" else "日程已暂停。") { gateway.updateSchedule(schedule.id, update) }
    }

    fun removeSchedule(schedule: MedicationScheduleDto) = perform("日程已停用，历史打卡会保留。") {
        gateway.deleteSchedule(schedule.id, schedule.recordVersion)
    }

    fun updateCheckin(checkin: MedicationCheckinDto, status: String) {
        val takenAt = if (status == "taken") OffsetDateTime.ofInstant(Instant.now(), ZoneId.of("UTC")).toString() else null
        perform("打卡已更新。") { gateway.updateCheckin(checkin.id, MedicationCheckinUpdateDto(checkin.recordVersion, status, takenAt)) }
    }

    fun clearForLogout() {
        epoch++
        mutableState.value = MedicationUiState()
    }

    private fun <T> perform(success: String, action: suspend () -> ApiResult<T>) {
        if (mutableState.value.saving) return
        val requestEpoch = epoch
        mutableState.value = mutableState.value.copy(saving = true, operationMessage = null, conflict = false, error = null)
        viewModelScope.launch {
            when (val result = action()) {
                is ApiResult.Failure -> if (requestEpoch == epoch) mutableState.value = mutableState.value.copy(
                    saving = false, conflict = result.status == 409, operationMessage = result.toMessage(),
                )
                is ApiResult.Success -> if (requestEpoch == epoch) {
                    mutableState.value = mutableState.value.copy(saving = false, operationMessage = success, conflict = false)
                    load(mutableState.value.section)
                }
            }
        }
    }

    private fun message(value: String) { mutableState.value = mutableState.value.copy(operationMessage = value, conflict = false) }
}

private fun ApiResult.Failure.toMessage(): String = when {
    status == 401 -> "登录状态已失效，请重新登录。"
    status == 409 -> "数据版本已变化，请刷新后重试。"
    status == 422 -> "输入内容不符合要求，请检查后重试。"
    code == "NETWORK_ERROR" -> "网络暂不可用，请检查连接后重试。"
    else -> "暂时无法加载或保存，请稍后重试。"
}
