package com.gutcare.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.Composable
import com.gutcare.app.navigation.RootTab
import com.gutcare.app.core.network.MedicationCheckinDto
import com.gutcare.app.core.network.MedicationPlanDto
import com.gutcare.app.core.network.MedicationScheduleDto
import com.gutcare.app.core.network.MoodTrendBucketDto
import com.gutcare.app.core.network.MoodTrendDto
import com.gutcare.app.core.network.RiskAlertDto
import com.gutcare.app.core.network.TrendResponseDto
import com.gutcare.app.core.network.TrendSeriesDto
import com.gutcare.app.core.network.TrendSeriesItemDto
import com.gutcare.app.ui.medication.MedicationScreen
import com.gutcare.app.ui.medication.MedicationSection
import com.gutcare.app.ui.medication.MedicationUiState
import com.gutcare.app.ui.risktrend.HealthTrendsScreen
import com.gutcare.app.ui.risktrend.RiskAlertDetailScreen
import com.gutcare.app.ui.risktrend.RiskTrendUiState
import com.gutcare.app.ui.risktrend.TrendState
import com.gutcare.app.ui.records.ArchiveReportUiState
import com.gutcare.app.ui.records.BowelDiscomfort
import com.gutcare.app.ui.records.BowelRecordScreen
import com.gutcare.app.ui.records.BowelRecordUiState
import com.gutcare.app.ui.records.DietDraftItemUiState
import com.gutcare.app.ui.records.DietRecordScreen
import com.gutcare.app.ui.records.DietRecordUiState
import com.gutcare.app.ui.records.HealthArchiveScreen
import com.gutcare.app.ui.records.HealthArchiveUiState
import com.gutcare.app.ui.records.HealthProfileUiState
import com.gutcare.app.ui.records.MealType
import com.gutcare.app.ui.records.MoodRecordScreen
import com.gutcare.app.ui.records.MoodRecordUiState
import com.gutcare.app.ui.records.SymptomChange
import com.gutcare.app.ui.records.SymptomRecordScreen
import com.gutcare.app.ui.records.SymptomRecordUiState
import com.gutcare.app.ui.records.TodayCallbacks
import com.gutcare.app.ui.records.TodayMealUiState
import com.gutcare.app.ui.records.TodayMedicationUiState
import com.gutcare.app.ui.records.TodayScreen
import com.gutcare.app.ui.records.TodayUiState
import com.gutcare.app.ui.tabs.ProtectedTabShell
import com.gutcare.app.ui.theme.GutCareTheme

/**
 * Deterministic, debug-only rendering fixture used by the visual-evidence script.
 * It deliberately has no launcher intent, API client, credentials, or release manifest entry.
 */
class VisualBaselineActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val page = intent.getStringExtra(EXTRA_PAGE).orEmpty()
        setContent {
            GutCareTheme { VisualBaselinePage(page) }
        }
    }

    companion object {
        const val EXTRA_PAGE = "page"
    }
}

@Composable
private fun VisualBaselinePage(page: String) {
    when (page) {
        "today" -> ProtectedTabShell(selectedTab = RootTab.Today, onSelectTab = {}) {
            TodayScreen(
                uiState = TodayUiState(
                    dateLabel = "10月19日 星期日",
                    displayName = "小安",
                    weeklyRecordDays = 5,
                    medication = TodayMedicationUiState(1, 2, "晚餐后 20:00"),
                    meals = listOf(
                        TodayMealUiState("早餐", "燕麦、香蕉", true),
                        TodayMealUiState("午餐", "还未记录", false),
                    ),
                    trendSummary = "本周已记录 5 天",
                ),
                callbacks = TodayCallbacks(),
            )
        }
        "diet" -> DietRecordScreen(
            DietRecordUiState(
                mealType = MealType.Lunch,
                occurredDate = "2026-10-19",
                occurredTime = "12:30",
                draftItems = listOf(DietDraftItemUiState("杂粮饭", "一碗")),
                textDescription = "杂粮饭、青菜和鸡蛋",
            ),
            callbacks = com.gutcare.app.ui.records.DietRecordCallbacks(),
        )
        "archive" -> HealthArchiveScreen(
            HealthArchiveUiState(
                profile = HealthProfileUiState("小安", 1996, "基础资料已完善"),
                reports = listOf(ArchiveReportUiState("合成检查报告", "10月12日", "待确认")),
            ),
            callbacks = com.gutcare.app.ui.records.HealthArchiveCallbacks(),
        )
        "bowel" -> BowelRecordScreen(
            BowelRecordUiState(
                occurredDate = "2026-10-19",
                occurredTime = "08:10",
                discomfort = BowelDiscomfort.None,
            ),
            callbacks = com.gutcare.app.ui.records.BowelRecordCallbacks(),
        )
        "symptoms" -> SymptomRecordScreen(
            SymptomRecordUiState(
                selectedCode = "abdominal_pain",
                severity = 2,
                startedTime = "14:00",
                durationMinutes = "30",
                change = SymptomChange.Better,
            ),
            callbacks = com.gutcare.app.ui.records.SymptomRecordCallbacks(),
        )
        "mood" -> MoodRecordScreen(
            MoodRecordUiState(
                selectedLevel = 4,
                occurredDate = "2026-10-19",
                occurredTime = "20:00",
                note = "今天状态平静。",
            ),
            callbacks = com.gutcare.app.ui.records.MoodRecordCallbacks(),
        )
        "medication" -> MedicationVisualFixture()
        "trends" -> HealthTrendsScreen(
            state = RiskTrendUiState(trends = TrendState.Ready(visualTrendResponse())),
            onLoad = {},
            timeZoneId = "Asia/Shanghai",
        )
        "risk-detail" -> RiskAlertDetailScreen(
            state = RiskTrendUiState(detail = RiskAlertDto(
                id = "visual-risk", environment = "test_only", severity = "seek_care",
                message = "演示记录触发了需要关注的症状。", recommendedAction = "请结合实际情况及时寻求专业医疗帮助。",
                status = "unread", triggeredAt = "2026-10-20T10:32:00+08:00",
            )),
            alertId = "visual-risk", onLoad = {}, onMarkRead = {}, onReevaluate = {}, onBack = {},
        )
        else -> TodayScreen(TodayUiState(summaryMessage = "未指定视觉夹具页面。"), TodayCallbacks())
    }
}

@Composable
private fun MedicationVisualFixture() {
    val date = "2026-10-20"
    val plan = MedicationPlanDto(
        id = "visual-plan", patientId = "visual-patient", medicationName = "肠胃调理药物",
        dosageText = "按医嘱服用", routeCode = "oral", sourceType = "patient_reported",
        sourceDeleted = false, confirmationStatus = "confirmed", planStatus = "active", recordVersion = 1,
    )
    val scheduleRows = listOf("08:00", "12:00", "20:00").mapIndexed { index, time ->
        MedicationScheduleDto("visual-schedule-$index", plan.id, "$time:00", "Asia/Shanghai", "FREQ=DAILY", date, null, true, 1)
    }
    val checkins = listOf("taken", "taken", "pending").mapIndexed { index, status ->
        MedicationCheckinDto("visual-checkin-$index", scheduleRows[index].id, date, "${date}T${scheduleRows[index].localTime}+08:00", status, recordVersion = 1)
    }
    MedicationScreen(
        state = MedicationUiState(
            section = MedicationSection.TODAY, plans = listOf(plan), schedules = mapOf(plan.id to scheduleRows), today = checkins,
        ),
        onBack = {}, onRefresh = {}, onSection = {}, onSelectPlan = {}, onHistoryRange = { _, _ -> },
        onCreatePlan = { _, _, _, _, _ -> }, onTransition = { _, _ -> }, onCreateSchedule = { _, _, _, _, _ -> },
        onToggleSchedule = {}, onRemoveSchedule = {}, onUpdateCheckin = { _, _ -> },
    )
}

private fun visualTrendResponse(): TrendResponseDto {
    val buckets = listOf("14", "15", "16", "17", "18", "19", "20")
    val stool = buckets.mapIndexed { index, day -> TrendSeriesItemDto("10.$day", count = listOf(1, 2, 3, 2, 1, 2, 2)[index], bristolConfirmedCount = listOf(1, 2, 3, 2, 1, 2, 2)[index], bristolUnknownCount = 0) }
    val moodBuckets = buckets.mapIndexed { index, day ->
        val count = listOf(1, 1, 2, 2, 1, 3, 2)[index]
        MoodTrendBucketDto("2026-10-$day", "2026-10-${(day.toInt() + 1).toString().padStart(2, '0')}", true, count, mapOf("1" to 0, "2" to 1, "3" to count, "4" to 0, "5" to 0))
    }
    return TrendResponseDto(
        timezone = "Asia/Shanghai", from = "2026-10-14T00:00:00+08:00", to = "2026-10-21T00:00:00+08:00", bucket = "day",
        activity = TrendSeriesDto(true, buckets.map { TrendSeriesItemDto(it, count = 1, durationMinutes = 20) }),
        stool = TrendSeriesDto(true, stool),
        symptom = TrendSeriesDto(true, buckets.map { TrendSeriesItemDto(it, count = 1, meanSeverity = 2.0) }),
        dietConfirmedCategories = TrendSeriesDto(true, buckets.map { TrendSeriesItemDto(it, count = 1, category = "vegetable") }),
        medicationCheckins = TrendSeriesDto(true, buckets.map { TrendSeriesItemDto(it, count = 1, status = "taken") }),
        mood = MoodTrendDto("available", moodBuckets),
    )
}
