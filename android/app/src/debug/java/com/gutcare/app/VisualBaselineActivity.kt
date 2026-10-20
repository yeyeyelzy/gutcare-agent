package com.gutcare.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.Composable
import com.gutcare.app.navigation.RootTab
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
                bristolType = 4,
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
        else -> TodayScreen(TodayUiState(summaryMessage = "未指定视觉夹具页面。"), TodayCallbacks())
    }
}
