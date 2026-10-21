package com.gutcare.app.ui.records

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.gutcare.app.ui.theme.GutCareTheme
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import androidx.test.ext.junit.runners.AndroidJUnit4

@RunWith(AndroidJUnit4::class)
class RecordScreensTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun todayQuickRecordIsVisibleAndDelegatesCategory() {
        var selected: RecordCategory? = null
        composeRule.setContent {
            GutCareTheme {
                TodayScreen(
                    uiState = TodayUiState(dateLabel = "10月19日"),
                    callbacks = TodayCallbacks(onQuickRecord = { selected = it }),
                )
            }
        }

        composeRule.onNodeWithTag("today_screen").assertIsDisplayed()
        composeRule.onNodeWithTag("today_quick_diet").performClick()
        check(selected == RecordCategory.Diet)
    }

    @Test
    fun dietControlsAndSaveDelegateToHoistedCallbacks() {
        var selectedMeal: MealType? = null
        var saved = false
        composeRule.setContent {
            var state by remember { mutableStateOf(DietRecordUiState()) }
            GutCareTheme {
                DietRecordScreen(
                    uiState = state,
                    callbacks = DietRecordCallbacks(
                        onSelectMealType = {
                            selectedMeal = it
                            state = state.copy(mealType = it)
                        },
                        onSave = { saved = true },
                    ),
                )
            }
        }

        composeRule.onNodeWithTag("diet_record_screen").assertIsDisplayed()
        composeRule.onNodeWithTag("diet_meal_早餐").performClick()
        composeRule.waitForIdle()
        composeRule.onNodeWithTag("diet_save").performScrollTo().performClick()
        composeRule.waitForIdle()
        composeRule.runOnIdle {
            check(selectedMeal == MealType.Breakfast)
            check(saved)
        }
    }

    @Test
    fun healthArchiveDisplaysReportsAndDelegatesRowAndUploadActions() {
        var opened = false
        var upload = false
        val report = ArchiveReportUiState("合成检查报告", "10月12日", "待确认")
        composeRule.setContent {
            GutCareTheme {
                HealthArchiveScreen(
                    uiState = HealthArchiveUiState(reports = listOf(report)),
                    callbacks = HealthArchiveCallbacks(
                        onOpenReport = { opened = it == report },
                        onUploadReport = { upload = true },
                    ),
                )
            }
        }

        composeRule.onNodeWithTag("health_archive_screen").assertIsDisplayed()
        composeRule.onNodeWithTag("archive_report_0").performClick()
        composeRule.onNodeWithTag("archive_upload").performClick()
        check(opened)
        check(upload)
    }

    @Test
    fun bowelRecordExposesItsCoreInputs() {
        var bristolType: Int? = null
        composeRule.setContent {
            GutCareTheme {
                BowelRecordScreen(
                    uiState = BowelRecordUiState(),
                    callbacks = BowelRecordCallbacks(onSelectBristolType = { bristolType = it }),
                )
            }
        }
        composeRule.onNodeWithTag("bowel_record_screen").assertIsDisplayed()
        composeRule.onNodeWithTag("bowel_bristol_4").performClick()
        composeRule.onNodeWithTag("bowel_save").performScrollTo().assertIsDisplayed()
        check(bristolType == 4)
    }

    @Test
    fun dietEditExposesImageManagementAndCreationExplainsSaveFirst() {
        var opened = false
        composeRule.setContent {
            GutCareTheme {
                DietRecordScreen(DietRecordUiState(isEditing = true), DietRecordCallbacks(onManageImages = { opened = true }))
            }
        }
        composeRule.onNodeWithTag("diet_manage_images").performScrollTo().performClick()
        composeRule.runOnIdle { check(opened) }
    }

    @Test
    fun dietCreationExplainsImagesAreAvailableAfterSave() {
        composeRule.setContent { GutCareTheme { DietRecordScreen(DietRecordUiState(), DietRecordCallbacks()) } }
        composeRule.onNodeWithTag("diet_images_after_save").assertIsDisplayed()
    }

    @Test
    fun bowelEditExposesImageManagementEntryPoint() {
        var opened = false
        composeRule.setContent {
            GutCareTheme { BowelRecordScreen(BowelRecordUiState(isEditing = true), BowelRecordCallbacks(onManageImages = { opened = true })) }
        }
        composeRule.onNodeWithTag("bowel_manage_images").performScrollTo().performClick()
        composeRule.runOnIdle { check(opened) }
    }

    @Test
    fun recordDetailExposesImageManagementAction() {
        var opened = false
        composeRule.setContent {
            GutCareTheme {
                RecordDetailScreen(
                    type = WorkspaceRecordType.DIET,
                    state = RecordsUiState(detailState = RecordDetailLoadState.Loaded(
                        RecordDetailModel("diet-1", 2, "2026-10-19T08:30:00+08:00", com.gutcare.app.core.network.RecordPayloadDto()),
                    )),
                    onBack = {}, onRetry = {}, onEdit = {}, onDelete = {}, onManageImages = { opened = true },
                )
            }
        }
        composeRule.onNodeWithTag("record_detail_images").performClick()
        composeRule.runOnIdle { check(opened) }
    }

    @Test
    fun symptomRecordExposesItsCoreInputs() {
        var symptomCode: String? = null
        composeRule.setContent {
            GutCareTheme {
                SymptomRecordScreen(
                    uiState = SymptomRecordUiState(),
                    callbacks = SymptomRecordCallbacks(onSelectSymptom = { symptomCode = it.code }),
                )
            }
        }
        composeRule.onNodeWithTag("symptom_record_screen").assertIsDisplayed()
        composeRule.onNodeWithTag("symptom_choice_腹痛").performClick()
        composeRule.onNodeWithTag("symptom_severity").assertIsDisplayed()
        composeRule.onNodeWithTag("symptom_save").performScrollTo().assertIsDisplayed()
        composeRule.onNodeWithTag("symptom_change_加重").assertIsNotEnabled()
        composeRule.onNodeWithTag("symptom_worse_unavailable").assertIsDisplayed()
        check(symptomCode == "abdominal_pain")
    }

    @Test
    fun moodDetailRendersPrivateNoteOnlyOnTheDetailSurface() {
        composeRule.setContent {
            GutCareTheme {
                RecordDetailScreen(
                    type = WorkspaceRecordType.MOOD,
                    state = RecordsUiState(detailState = RecordDetailLoadState.Loaded(
                        RecordDetailModel("mood-1", 2, "2026-10-19T08:30:00+08:00", com.gutcare.app.core.network.RecordPayloadDto(), moodLevel = 4, note = "我的心情备注"),
                    )),
                    onBack = {}, onRetry = {}, onEdit = {}, onDelete = {},
                )
            }
        }
        composeRule.onNodeWithTag("mood_detail_note").assertIsDisplayed()
    }

    @Test
    fun moodSelectionAndSaveRemainUiOnlyCallbacks() {
        var selectedLevel: Int? = null
        var saved = false
        composeRule.setContent {
            GutCareTheme {
                MoodRecordScreen(
                    uiState = MoodRecordUiState(),
                    callbacks = MoodRecordCallbacks(
                        onSelectMood = { selectedLevel = it.level },
                        onSave = { saved = true },
                    ),
                )
            }
        }

        composeRule.onNodeWithTag("mood_record_screen").assertIsDisplayed()
        composeRule.onNodeWithTag("mood_level_5").performClick()
        composeRule.onNodeWithTag("mood_save").performClick()
        check(selectedLevel == 5)
        check(saved)
    }

    @Test
    fun recordsHubExposesFrozenRecordDestinations() {
        var selected: WorkspaceRecordType? = null
        var archiveOpened = false
        composeRule.setContent {
            GutCareTheme {
                RecordsHubScreen(onOpenCategory = { selected = it }, onOpenArchive = { archiveOpened = true })
            }
        }
        composeRule.onNodeWithTag("records_hub_screen").assertIsDisplayed()
        composeRule.onNodeWithTag("records_open_mood").performClick()
        composeRule.onNodeWithTag("records_open_health_archive").performClick()
        check(selected == WorkspaceRecordType.MOOD)
        check(archiveOpened)
    }

    @Test
    fun recordListRendersLoadingEmptyAndRetryableErrorStates() {
        var retried = false
        composeRule.setContent {
            GutCareTheme {
                RecordListScreen(
                    type = WorkspaceRecordType.DIET,
                    state = RecordsUiState(loadState = RecordsLoadState.Error("网络暂不可用。")),
                    onBack = {}, onRetry = { retried = true }, onNew = {}, onOpen = {}, onLoadMore = {}, onDelete = {},
                )
            }
        }
        composeRule.onNodeWithTag("record_list_diet_screen").assertIsDisplayed()
        composeRule.onNodeWithTag("record_list_error").assertIsDisplayed()
        composeRule.onNodeWithTag("record_list_retry").performClick()
        check(retried)
    }
}
