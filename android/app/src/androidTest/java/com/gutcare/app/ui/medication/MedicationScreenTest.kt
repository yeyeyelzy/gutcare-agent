package com.gutcare.app.ui.medication

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performClick
import com.gutcare.app.core.network.MedicationCheckinDto
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import androidx.test.ext.junit.runners.AndroidJUnit4

@RunWith(AndroidJUnit4::class)
class MedicationScreenTest {
    @get:Rule val compose = createComposeRule()

    @Test fun pendingTodayDoseShowsExplicitPatientActions() {
        var chosenStatus: String? = null
        val dose = MedicationCheckinDto("dose-1", "schedule-1", "2026-10-20", "2026-10-20T08:00:00+08:00", "pending", null, null, 2)
        compose.setContent {
            MedicationScreen(
                state = MedicationUiState(section = MedicationSection.TODAY, today = listOf(dose)),
                onBack = {}, onRefresh = {}, onSection = {}, onSelectPlan = {}, onHistoryRange = { _, _ -> },
                onCreatePlan = { _, _, _, _, _ -> }, onTransition = { _, _ -> }, onCreateSchedule = { _, _, _, _, _ -> },
                onToggleSchedule = {}, onRemoveSchedule = {}, onUpdateCheckin = { _, status -> chosenStatus = status },
            )
        }
        compose.onNodeWithTag("medication_checkin_status_dose-1").assertIsDisplayed()
        compose.onNodeWithTag("medication_checkin_taken_dose-1").assertIsDisplayed().performClick()
        compose.runOnIdle { assertEquals("taken", chosenStatus) }
        compose.onNodeWithTag("medication_checkin_not_taken_dose-1").assertIsDisplayed()
        compose.onNodeWithTag("medication_checkin_skipped_dose-1").performScrollTo().assertIsDisplayed()
    }
}
