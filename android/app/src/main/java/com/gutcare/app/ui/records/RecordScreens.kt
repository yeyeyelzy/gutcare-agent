package com.gutcare.app.ui.records

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.Image
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.gutcare.app.ui.design.GutCareDimensions
import com.gutcare.app.ui.design.GutCareLeafMark
import com.gutcare.app.ui.design.GutCarePage
import com.gutcare.app.ui.design.GutCarePrimaryButton
import com.gutcare.app.ui.design.WelcomeChecklistIllustration
import com.gutcare.app.ui.theme.GutCareBrandGreen
import com.gutcare.app.ui.theme.GutCareCanvas
import com.gutcare.app.ui.theme.GutCareDeepGreen
import com.gutcare.app.ui.theme.GutCareInk
import com.gutcare.app.ui.theme.GutCareLine
import com.gutcare.app.ui.theme.GutCareMuted
import com.gutcare.app.ui.theme.GutCareOrange
import com.gutcare.app.ui.theme.GutCareOrangeSoft
import com.gutcare.app.ui.theme.GutCarePurple
import com.gutcare.app.ui.theme.GutCarePurpleSoft
import com.gutcare.app.ui.theme.GutCareSage
import com.gutcare.app.R

/**
 * Pure UI contracts for the six records-related routes. Repository and navigation wiring belong
 * to a later layer; these composables neither access a service nor retain a patient record.
 */
enum class RecordCategory(val label: String) {
    Diet("饮食"),
    Bowel("排便"),
    Symptoms("症状"),
    Mood("心情"),
    Activity("运动"),
}

enum class MealType(val label: String) {
    Breakfast("早餐"),
    Lunch("午餐"),
    Dinner("晚餐"),
    Snack("加餐"),
    Other("其他"),
}

enum class PortionSize(val label: String) {
    Small("少量"),
    Normal("正常份量"),
    Large("较多"),
}

enum class CookingStyle(val label: String) {
    Light("清淡"),
    LessOil("少油"),
    Regular("常规"),
}

enum class BowelDiscomfort(val label: String) {
    None("无"),
    Pain("腹痛"),
    Bloating("腹胀"),
}

enum class SymptomChange(val label: String) {
    Better("有所减轻"),
    Same("差不多"),
    Worse("加重"),
}

data class TodayMedicationUiState(
    val completedCount: Int,
    val totalCount: Int,
    val nextLabel: String? = null,
)

data class TodayMealUiState(
    val label: String,
    val detail: String,
    val isRecorded: Boolean,
)

data class TodayUiState(
    val dateLabel: String = "今天",
    val displayName: String? = null,
    val weeklyRecordDays: Int? = null,
    val medication: TodayMedicationUiState? = null,
    val meals: List<TodayMealUiState> = emptyList(),
    val trendSummary: String? = null,
    val summaryMessage: String? = null,
    val riskSummary: String? = null,
    val recentRecordSummary: String? = null,
    val adviceSummary: String? = null,
    val unreadCount: Int? = null,
    val medicationUnavailable: Boolean = false,
    val recentRecordMessage: String? = null,
    val adviceMessage: String? = null,
)

data class TodayCallbacks(
    val onQuickRecord: (RecordCategory) -> Unit = {},
    val onQuickMedicationCheckin: () -> Unit = {},
    val onQuickActivityRecord: () -> Unit = {},
    val onOpenMedication: () -> Unit = {},
    val onOpenMeals: () -> Unit = {},
    val onOpenTrend: () -> Unit = {},
    val onOpenProfile: () -> Unit = {},
    val onOpenNotifications: () -> Unit = {},
)

data class DietDraftItemUiState(
    val label: String,
    val portionLabel: String? = null,
)

/** Candidate labels are deliberately displayed as candidates, never as confirmed food facts. */
data class DietCandidateUiState(
    val label: String,
    val statusLabel: String = "待确认",
)

data class DietRecordUiState(
    val mealType: MealType = MealType.Lunch,
    val occurredDate: String = "",
    val occurredTime: String = "",
    val draftItems: List<DietDraftItemUiState> = emptyList(),
    val candidates: List<DietCandidateUiState> = emptyList(),
    val portionSize: PortionSize? = null,
    val cookingStyle: CookingStyle? = null,
    val canSave: Boolean = true,
    val textDescription: String = "",
    val isSaving: Boolean = false,
    val feedbackMessage: String? = null,
    val isEditing: Boolean = false,
)

data class DietRecordCallbacks(
    val onBack: () -> Unit = {},
    val onSelectCategory: (RecordCategory) -> Unit = {},
    val onSelectMealType: (MealType) -> Unit = {},
    val onDateChange: (String) -> Unit = {},
    val onTimeChange: (String) -> Unit = {},
    val onDescriptionChange: (String) -> Unit = {},
    val onManageImages: () -> Unit = {},
    val onCreateForImageUpload: () -> Unit = {},
    val onAddFood: (String, String?) -> Unit = { _, _ -> },
    val onRemoveFood: (Int) -> Unit = {},
    val onReviewCandidate: (DietCandidateUiState) -> Unit = {},
    val onSelectPortionSize: (PortionSize) -> Unit = {},
    val onSelectCookingStyle: (CookingStyle) -> Unit = {},
    val onSave: () -> Unit = {},
)

data class HealthProfileUiState(
    val displayName: String? = null,
    val birthYear: Int? = null,
    val confirmedSummary: String? = null,
)

data class ArchiveReportUiState(
    val title: String,
    val dateLabel: String,
    val statusLabel: String,
)

data class HealthArchiveUiState(
    val profile: HealthProfileUiState? = null,
    val reports: List<ArchiveReportUiState> = emptyList(),
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
    val uploadEnabled: Boolean = true,
    val profileActionEnabled: Boolean = true,
    val retryEnabled: Boolean = true,
)

data class HealthArchiveCallbacks(
    val onBack: () -> Unit = {},
    val onEditProfile: () -> Unit = {},
    val onOpenReport: (ArchiveReportUiState) -> Unit = {},
    val onUploadReport: () -> Unit = {},
    val onRetry: () -> Unit = {},
)

data class BowelRecordUiState(
    val occurredDate: String = "",
    val occurredTime: String = "",
    val discomfort: BowelDiscomfort = BowelDiscomfort.None,
    val note: String = "",
    val canSave: Boolean = true,
    val isSaving: Boolean = false,
    val feedbackMessage: String? = null,
    val isEditing: Boolean = false,
)

data class BowelRecordCallbacks(
    val onBack: () -> Unit = {},
    val onSelectCategory: (RecordCategory) -> Unit = {},
    val onDateChange: (String) -> Unit = {},
    val onTimeChange: (String) -> Unit = {},
    val onManageImages: () -> Unit = {},
    val onSelectDiscomfort: (BowelDiscomfort) -> Unit = {},
    val onNoteChange: (String) -> Unit = {},
    val onSave: () -> Unit = {},
)

data class SymptomChoiceUiState(val code: String, val label: String)

data class SymptomRecordUiState(
    val choices: List<SymptomChoiceUiState> = defaultSymptomChoices,
    val selectedCode: String? = null,
    val severity: Int = 0,
    val startedTime: String = "",
    val durationMinutes: String = "",
    val change: SymptomChange? = null,
    val relatedRecordLabel: String? = null,
    val note: String = "",
    val canSave: Boolean = true,
    val isSaving: Boolean = false,
    val feedbackMessage: String? = null,
    val otherDescription: String = "",
    val isEditing: Boolean = false,
)

data class SymptomRecordCallbacks(
    val onBack: () -> Unit = {},
    val onSelectCategory: (RecordCategory) -> Unit = {},
    val onSelectSymptom: (SymptomChoiceUiState) -> Unit = {},
    val onOtherDescriptionChange: (String) -> Unit = {},
    val onSeverityChange: (Int) -> Unit = {},
    val onStartedTimeChange: (String) -> Unit = {},
    val onDurationChange: (String) -> Unit = {},
    val onSelectChange: (SymptomChange) -> Unit = {},
    val onSelectRelatedRecord: () -> Unit = {},
    val onNoteChange: (String) -> Unit = {},
    val onSave: () -> Unit = {},
)

data class MoodOptionUiState(val level: Int, val label: String, val emoji: String)

data class MoodRecordUiState(
    val selectedLevel: Int? = null,
    val occurredDate: String = "",
    val occurredTime: String = "",
    val note: String = "",
    val canSave: Boolean = true,
    val blockedMessage: String? = null,
    val isSaving: Boolean = false,
    val feedbackMessage: String? = null,
    val isEditing: Boolean = false,
)

data class MoodRecordCallbacks(
    val onBack: () -> Unit = {},
    val onSelectCategory: (RecordCategory) -> Unit = {},
    val onSelectMood: (MoodOptionUiState) -> Unit = {},
    val onDateChange: (String) -> Unit = {},
    val onTimeChange: (String) -> Unit = {},
    val onNoteChange: (String) -> Unit = {},
    val onSave: () -> Unit = {},
)

private val defaultSymptomChoices = listOf(
    SymptomChoiceUiState("abdominal_pain", "腹痛"),
    SymptomChoiceUiState("bloating", "腹胀"),
    SymptomChoiceUiState("diarrhea", "腹泻"),
    SymptomChoiceUiState("constipation", "便秘"),
    SymptomChoiceUiState("nausea", "恶心"),
    SymptomChoiceUiState("other", "其他"),
)

private val moodOptions = listOf(
    MoodOptionUiState(5, "愉快", "😄"),
    MoodOptionUiState(4, "平静", "😌"),
    MoodOptionUiState(3, "一般", "😐"),
    MoodOptionUiState(2, "低落", "😔"),
    MoodOptionUiState(1, "烦躁", "😣"),
)

@Composable
fun TodayScreen(
    uiState: TodayUiState,
    callbacks: TodayCallbacks,
    modifier: Modifier = Modifier,
) {
    RecordsPage(modifier, "today_screen", horizontalPadding = 16.dp, topPadding = 0.dp) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                GutCareLeafMark(Modifier.size(22.dp))
                Spacer(Modifier.width(6.dp))
                Text("GutCare", style = androidx.compose.material3.MaterialTheme.typography.titleMedium, color = GutCareInk)
                Spacer(Modifier.weight(1f))
                  OutlinedButton(
                      onClick = callbacks.onOpenNotifications,
                      modifier = Modifier.height(40.dp).testTag("today_notifications"),
                      contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 10.dp),
                  ) { Text(uiState.unreadCount?.let { if (it > 0) "通知 $it" else "通知" } ?: "通知") }
                OutlinedButton(
                    onClick = callbacks.onOpenProfile,
                    modifier = Modifier.size(44.dp).testTag("today_profile"),
                    shape = CircleShape,
                    border = androidx.compose.foundation.BorderStroke(1.dp, GutCareLine),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp),
                ) { PrototypeAvatar(32.dp) }
            }
        Spacer(Modifier.height(20.dp))
        Text(uiState.dateLabel, style = androidx.compose.material3.MaterialTheme.typography.bodyLarge, color = GutCareMuted)
        Text(
            text = if (uiState.displayName.isNullOrBlank()) "你好" else "早上好，${uiState.displayName}",
            fontSize = 32.sp,
            lineHeight = 40.sp,
            fontWeight = FontWeight.ExtraBold,
            color = GutCareInk,
        )
          uiState.summaryMessage?.let {
            Spacer(Modifier.height(16.dp))
            RecordCard { Text(it, style = androidx.compose.material3.MaterialTheme.typography.bodyLarge, color = GutCareMuted) }
        } ?: run {
            Spacer(Modifier.height(16.dp))
            DailyCareCard(uiState)
        }
          uiState.riskSummary?.let { summary -> Spacer(Modifier.height(12.dp)); RecordCard { Text(summary, color = GutCareInk, modifier = Modifier.testTag("today_risk_summary")) } }
          (uiState.recentRecordSummary ?: uiState.recentRecordMessage)?.let { summary -> Spacer(Modifier.height(8.dp)); Text(summary, color = GutCareMuted, modifier = Modifier.testTag("today_recent_record")) }
          (uiState.adviceSummary?.let { "最新建议：$it" } ?: uiState.adviceMessage)?.let { summary -> Spacer(Modifier.height(8.dp)); RecordCard { Text(summary, color = GutCareInk, modifier = Modifier.testTag("today_latest_advice")) } }
        Spacer(Modifier.height(20.dp))
        TodaySectionTitle("快捷记录")
        Spacer(Modifier.height(12.dp))
        QuickRecordRow(
            onQuickRecord = callbacks.onQuickRecord,
            onMedicationCheckin = callbacks.onQuickMedicationCheckin,
            onActivityRecord = callbacks.onQuickActivityRecord,
        )
        if (uiState.summaryMessage == null) {
            Spacer(Modifier.height(20.dp))
            SectionHeader(title = "今日用药", actionLabel = "查看计划", onAction = callbacks.onOpenMedication)
            Spacer(Modifier.height(12.dp))
              MedicationCard(uiState.medication, uiState.medicationUnavailable)
            Spacer(Modifier.height(20.dp))
            SectionHeader(title = "今天吃了什么", actionLabel = "查看全部", onAction = callbacks.onOpenMeals)
            Spacer(Modifier.height(12.dp))
            MealSummary(uiState.meals)
            Spacer(Modifier.height(20.dp))
            TrendCard(uiState.trendSummary, callbacks.onOpenTrend)
        }
    }
}

@Composable
fun DietRecordScreen(
    uiState: DietRecordUiState,
    callbacks: DietRecordCallbacks,
    modifier: Modifier = Modifier,
) {
    RecordsPage(modifier, "diet_record_screen") {
        RecordHeader("饮食记录", callbacks.onBack)
        Spacer(Modifier.height(14.dp))
        RecordCategoryTabs(RecordCategory.Diet, callbacks.onSelectCategory)
        Spacer(Modifier.height(12.dp))
        if (uiState.isEditing) {
            OutlinedButton(onClick = callbacks.onManageImages, modifier = Modifier.fillMaxWidth().testTag("diet_manage_images")) { Text("管理记录图片") }
        } else {
            GutCarePrimaryButton(
                label = "上传图片识别饮食",
                onClick = callbacks.onCreateForImageUpload,
                enabled = !uiState.isSaving,
                testTag = "diet_image_first_entry",
            )
            Spacer(Modifier.height(8.dp))
            Text("拍照或选择图片后即可识别，无需先手工填写饮食。", color = GutCareMuted, modifier = Modifier.testTag("diet_images_before_save"))
        }
        Spacer(Modifier.height(16.dp))
        PillRow(MealType.entries, uiState.mealType, { it.label }, callbacks.onSelectMealType, "diet_meal")
        Spacer(Modifier.height(18.dp))
        if (uiState.candidates.isNotEmpty()) {
            DietCandidateCard(uiState.candidates, callbacks.onReviewCandidate)
            Spacer(Modifier.height(16.dp))
        }
        DraftFoodCard(uiState.draftItems, callbacks.onAddFood, callbacks.onRemoveFood)
        Spacer(Modifier.height(16.dp))
        NoteField(
            value = uiState.textDescription,
            onValueChange = callbacks.onDescriptionChange,
            placeholder = "简单描述今天吃了什么（必填）",
            tag = "diet_description",
        )
        uiState.feedbackMessage?.let { OperationFeedback(it, uiState.isSaving, "diet_operation_feedback") }
        Spacer(Modifier.height(16.dp))
        RecordCard {
            DateTimeFields(
                date = uiState.occurredDate,
                time = uiState.occurredTime,
                onDateChange = callbacks.onDateChange,
                onTimeChange = callbacks.onTimeChange,
                dateTag = "diet_date",
                timeTag = "diet_time",
                timeLabel = "用餐时间",
            )
            Spacer(Modifier.height(18.dp))
            Text("用餐份量", style = androidx.compose.material3.MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(10.dp))
            PillRow(PortionSize.entries, uiState.portionSize, { it.label }, callbacks.onSelectPortionSize, "diet_portion")
            Spacer(Modifier.height(18.dp))
            Text("烹调方式", style = androidx.compose.material3.MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(10.dp))
            PillRow(CookingStyle.entries, uiState.cookingStyle, { it.label }, callbacks.onSelectCookingStyle, "diet_cooking")
        }
        Spacer(Modifier.height(20.dp))
        GutCarePrimaryButton(
            label = if (uiState.isEditing) "保存修改" else "确认并保存记录",
            onClick = callbacks.onSave,
            enabled = uiState.canSave && !uiState.isSaving,
            testTag = "diet_save",
        )
    }
}

@Composable
fun HealthArchiveScreen(
    uiState: HealthArchiveUiState,
    callbacks: HealthArchiveCallbacks,
    modifier: Modifier = Modifier,
) {
    RecordsPage(modifier, "health_archive_screen") {
        RecordHeader("健康档案", callbacks.onBack, actionLabel = "编辑", onAction = callbacks.onEditProfile, actionEnabled = uiState.profileActionEnabled)
        Spacer(Modifier.height(18.dp))
        uiState.profile?.let { ProfileCard(it) }
        if (!uiState.profileActionEnabled) {
            Text("当前版本暂不可用：资料编辑功能尚未接入。", color = GutCareMuted, modifier = Modifier.padding(top = 8.dp).testTag("archive_profile_edit_unavailable"))
        }
        if (uiState.profile != null) Spacer(Modifier.height(28.dp))
        SectionTitle("检查报告")
        Spacer(Modifier.height(12.dp))
        when {
            uiState.isLoading -> ArchiveMessageCard("正在加载你的档案…")
            uiState.errorMessage != null -> ArchiveErrorCard(uiState.errorMessage, callbacks.onRetry, uiState.retryEnabled)
            uiState.reports.isEmpty() -> ArchiveMessageCard("还没有可展示的检查报告。")
            else -> ArchiveReportsCard(uiState.reports, callbacks.onOpenReport)
        }
        Spacer(Modifier.height(20.dp))
        GutCarePrimaryButton(
            label = "上传新报告",
            onClick = callbacks.onUploadReport,
            enabled = uiState.uploadEnabled,
            testTag = "archive_upload",
        )
    }
}

@Composable
fun BowelRecordScreen(
    uiState: BowelRecordUiState,
    callbacks: BowelRecordCallbacks,
    modifier: Modifier = Modifier,
) {
    RecordsPage(modifier, "bowel_record_screen") {
        RecordHeader("排便记录", callbacks.onBack)
        Spacer(Modifier.height(14.dp))
        RecordCategoryTabs(RecordCategory.Bowel, callbacks.onSelectCategory)
        Spacer(Modifier.height(12.dp))
        RecordCard {
            DateTimeFields(
                date = uiState.occurredDate,
                time = uiState.occurredTime,
                onDateChange = callbacks.onDateChange,
                onTimeChange = callbacks.onTimeChange,
                dateTag = "bowel_date",
                timeTag = "bowel_time",
                timeLabel = "记录时间",
            )
            Spacer(Modifier.height(16.dp))
        }
        Text("先保存记录，再到详情页上传图片查看 AI 辅助 Bristol 分类。", color = GutCareMuted, modifier = Modifier.testTag("bowel_images_after_save"))
        if (uiState.isEditing) {
            Spacer(Modifier.height(8.dp))
            OutlinedButton(onClick = callbacks.onManageImages, modifier = Modifier.fillMaxWidth().testTag("bowel_manage_images")) { Text("查看与管理图片") }
        }
        Spacer(Modifier.height(22.dp))
        SectionTitle("伴随不适")
        Spacer(Modifier.height(12.dp))
        RecordCard(padding = 16.dp) {
            PillRow(BowelDiscomfort.entries, uiState.discomfort, { it.label }, callbacks.onSelectDiscomfort, "bowel_discomfort")
        }
        Spacer(Modifier.height(24.dp))
        SectionTitle("备注")
        Spacer(Modifier.height(12.dp))
        NoteField(
            value = uiState.note,
            onValueChange = callbacks.onNoteChange,
            placeholder = "颜色、饮食或其他情况（选填）",
            tag = "bowel_note",
        )
        uiState.feedbackMessage?.let { OperationFeedback(it, uiState.isSaving, "bowel_operation_feedback") }
        Spacer(Modifier.height(16.dp))
        SafetyNote("照片仅用于你的记录；如出现令你担心的异常情况，请及时寻求专业医疗帮助。")
        Spacer(Modifier.height(20.dp))
        GutCarePrimaryButton(
            label = if (uiState.isEditing) "保存修改" else "确认并保存记录",
            onClick = callbacks.onSave,
            enabled = uiState.canSave && !uiState.isSaving,
            testTag = "bowel_save",
        )
    }
}

@Composable
fun SymptomRecordScreen(
    uiState: SymptomRecordUiState,
    callbacks: SymptomRecordCallbacks,
    modifier: Modifier = Modifier,
) {
    RecordsPage(modifier, "symptom_record_screen") {
        RecordHeader("症状记录", callbacks.onBack)
        Spacer(Modifier.height(14.dp))
        RecordCategoryTabs(RecordCategory.Symptoms, callbacks.onSelectCategory)
        Spacer(Modifier.height(12.dp))
        RecordCard {
            Text("哪里不舒服？", style = androidx.compose.material3.MaterialTheme.typography.headlineMedium)
            Spacer(Modifier.height(14.dp))
            WrapPills(
                items = uiState.choices,
                selected = { it.code == uiState.selectedCode },
                label = { it.label },
                onSelect = callbacks.onSelectSymptom,
                testTagPrefix = "symptom_choice",
            )
            if (uiState.selectedCode == "other") {
                Spacer(Modifier.height(14.dp))
                NoteField(uiState.otherDescription, callbacks.onOtherDescriptionChange, "请描述其他症状（必填）", "symptom_other_description")
            }
        }
        Spacer(Modifier.height(16.dp))
        SeverityCard(uiState.severity, callbacks.onSeverityChange)
        Spacer(Modifier.height(16.dp))
        RecordCard {
            FieldRow("开始时间") {
                CompactTextField(
                    value = uiState.startedTime,
                    onValueChange = callbacks.onStartedTimeChange,
                    placeholder = "例如 14:00",
                    tag = "symptom_started_time",
                )
            }
            FormDivider()
            FieldRow("持续分钟") {
                CompactTextField(
                    value = uiState.durationMinutes,
                    onValueChange = callbacks.onDurationChange,
                    placeholder = "例如 30",
                    tag = "symptom_duration",
                )
            }
            FormDivider()
            Text("比之前", style = androidx.compose.material3.MaterialTheme.typography.bodyLarge)
            Spacer(Modifier.height(12.dp))
            PillRow(
                SymptomChange.entries, uiState.change, { it.label }, callbacks.onSelectChange, "symptom_change",
                enabled = { it != SymptomChange.Worse },
            )
            Text("当前版本暂不可用：症状状态仅支持‘仍持续’或‘已缓解’。", color = GutCareMuted, modifier = Modifier.testTag("symptom_worse_unavailable"))
            Spacer(Modifier.height(18.dp))
            FieldRow("关联记录") {
                OutlinedButton(
                    onClick = callbacks.onSelectRelatedRecord,
                    enabled = false,
                    modifier = Modifier.heightIn(min = 48.dp).testTag("symptom_related_record"),
                    border = androidx.compose.foundation.BorderStroke(1.dp, GutCareLine),
                ) { Text(uiState.relatedRecordLabel ?: "选择记录（可选）") }
                Text("当前版本暂不可用：关联记录选择尚未接入。", color = GutCareMuted, modifier = Modifier.testTag("symptom_related_unavailable"))
            }
        }
        Spacer(Modifier.height(24.dp))
        SectionTitle("其他补充")
        Spacer(Modifier.height(12.dp))
        NoteField(
            value = uiState.note,
            onValueChange = callbacks.onNoteChange,
            placeholder = "还有什么想记下的？（选填）",
            tag = "symptom_note",
        )
        uiState.feedbackMessage?.let { OperationFeedback(it, uiState.isSaving, "symptom_operation_feedback") }
        Spacer(Modifier.height(20.dp))
        GutCarePrimaryButton(
            label = if (uiState.isEditing) "保存修改" else "保存症状记录",
            onClick = callbacks.onSave,
            enabled = uiState.canSave && !uiState.isSaving,
            testTag = "symptom_save",
        )
    }
}

@Composable
fun MoodRecordScreen(
    uiState: MoodRecordUiState,
    callbacks: MoodRecordCallbacks,
    modifier: Modifier = Modifier,
) {
    RecordsPage(modifier, "mood_record_screen") {
        RecordHeader("心情记录", callbacks.onBack, actionLabel = "今天", onAction = {})
        Spacer(Modifier.height(14.dp))
        RecordCategoryTabs(RecordCategory.Mood, callbacks.onSelectCategory)
        Spacer(Modifier.height(12.dp))
        MoodSelector(uiState.selectedLevel, callbacks.onSelectMood)
        Spacer(Modifier.height(16.dp))
        RecordCard {
            DateTimeFields(
                date = uiState.occurredDate,
                time = uiState.occurredTime,
                onDateChange = callbacks.onDateChange,
                onTimeChange = callbacks.onTimeChange,
                dateTag = "mood_date",
                timeTag = "mood_time",
                timeLabel = "记录时间",
            )
        }
        Spacer(Modifier.height(16.dp))
        RecordCard {
            Text("想补充些什么？", style = androidx.compose.material3.MaterialTheme.typography.headlineMedium)
            Spacer(Modifier.height(14.dp))
            NoteField(
                value = uiState.note,
                onValueChange = callbacks.onNoteChange,
                placeholder = "发生了什么，或者此刻有什么感受？（选填）",
                tag = "mood_note",
            )
        }
        uiState.blockedMessage?.let {
            Spacer(Modifier.height(14.dp))
            SafetyNote(it)
        }
        uiState.feedbackMessage?.let { OperationFeedback(it, uiState.isSaving, "mood_operation_feedback") }
        Spacer(Modifier.height(20.dp))
        GutCarePrimaryButton(
            label = if (uiState.isEditing) "保存修改" else "保存心情记录",
            onClick = callbacks.onSave,
            enabled = uiState.canSave && !uiState.isSaving && uiState.blockedMessage == null,
            testTag = "mood_save",
        )
    }
}

@Composable
private fun RecordsPage(
    modifier: Modifier,
    testTag: String,
    horizontalPadding: androidx.compose.ui.unit.Dp = GutCareDimensions.pageGutter,
    topPadding: androidx.compose.ui.unit.Dp = 16.dp,
    content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit,
) {
    GutCarePage(
        modifier = modifier.statusBarsPadding().testTag(testTag),
        horizontalPadding = horizontalPadding,
    ) {
        Spacer(Modifier.height(topPadding))
        content()
        Spacer(Modifier.height(32.dp))
    }
}

@Composable
private fun OperationFeedback(message: String, isSaving: Boolean, testTag: String) {
    Text(
        text = if (isSaving) "正在保存…" else message,
        modifier = Modifier.fillMaxWidth().padding(top = 10.dp).testTag(testTag),
        color = if (!isSaving && (message.contains("冲突") || message.contains("失效") || message.contains("无法") || message.contains("网络")))
            androidx.compose.material3.MaterialTheme.colorScheme.error else GutCareMuted,
        style = androidx.compose.material3.MaterialTheme.typography.bodyMedium,
    )
}

@Composable
private fun RecordHeader(title: String, onBack: () -> Unit, actionLabel: String? = null, onAction: (() -> Unit)? = null, actionEnabled: Boolean = true) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        OutlinedButton(
            onClick = onBack,
            modifier = Modifier.sizeIn(minWidth = 48.dp, minHeight = 48.dp).testTag("${title}_back"),
            shape = RoundedCornerShape(16.dp),
            border = androidx.compose.foundation.BorderStroke(1.dp, GutCareLine),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp),
        ) { RecordLineIcon(RecordIcon.Back, GutCareInk, Modifier.size(22.dp)) }
        Spacer(Modifier.width(14.dp))
        Text(title, style = androidx.compose.material3.MaterialTheme.typography.headlineLarge, color = GutCareInk)
        Spacer(Modifier.weight(1f))
        if (actionLabel != null && onAction != null) {
            TextButton(onClick = onAction, enabled = actionEnabled, modifier = Modifier.testTag("${title}_action")) { Text(actionLabel) }
        }
    }
}

@Composable
private fun RecordCategoryTabs(selected: RecordCategory, onSelect: (RecordCategory) -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(GutCareSage, RoundedCornerShape(20.dp))
            .padding(5.dp),
        horizontalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        RecordCategory.entries.forEach { category ->
            Button(
                onClick = { onSelect(category) },
                modifier = Modifier
                    .weight(1f)
                    .heightIn(min = 48.dp)
                    .testTag("record_category_${category.name.lowercase()}"),
                shape = RoundedCornerShape(16.dp),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 2.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (category == selected) Color.White else Color.Transparent,
                    contentColor = if (category == selected) GutCareBrandGreen else GutCareMuted,
                    disabledContainerColor = Color.Transparent,
                ),
            ) {
                Text(category.label, maxLines = 1, style = androidx.compose.material3.MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun DailyCareCard(uiState: TodayUiState) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(Color(0xFFBCCCBF), RoundedCornerShape(GutCareDimensions.cardRadius))
            .padding(18.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text("YOUR DAILY CARE", fontSize = 12.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = 2.sp, color = GutCareDeepGreen)
            Spacer(Modifier.height(12.dp))
            Text("照顾身体，\n从记录今天开始。", style = androidx.compose.material3.MaterialTheme.typography.headlineMedium, color = GutCareInk)
            uiState.weeklyRecordDays?.let {
                Spacer(Modifier.height(10.dp))
                Text("本周已记录 $it 天", style = androidx.compose.material3.MaterialTheme.typography.bodyLarge, color = GutCareBrandGreen)
            }
        }
        WelcomeChecklistIllustration(Modifier.size(104.dp))
    }
}

@Composable
private fun QuickRecordRow(
    onQuickRecord: (RecordCategory) -> Unit,
    onMedicationCheckin: () -> Unit,
    onActivityRecord: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        QuickRecordCard(RecordCategory.Diet, GutCareOrangeSoft, GutCareOrange, onQuickRecord)
        QuickRecordCard(RecordCategory.Bowel, GutCareSage, GutCareBrandGreen, onQuickRecord)
        QuickRecordCard(RecordCategory.Symptoms, GutCarePurpleSoft, GutCarePurple, onQuickRecord)
        QuickRecordCard(RecordCategory.Mood, Color(0xFFE2ECF8), Color(0xFF4E75AE), onQuickRecord)
        QuickRecordActionCard(
            label = "服药打卡",
            icon = RecordIcon.Check,
            color = Color(0xFFF2E9D8),
            tint = Color(0xFF9A713A),
            testTag = "today_quick_medication_checkin",
            onClick = onMedicationCheckin,
        )
        QuickRecordActionCard(
            label = "运动记录",
            icon = RecordIcon.Activity,
            color = Color(0xFFDDEDE8),
            tint = Color(0xFF3D806F),
            testTag = "today_quick_activity",
            onClick = onActivityRecord,
        )
    }
}

@Composable
private fun QuickRecordActionCard(
    label: String,
    icon: RecordIcon,
    color: Color,
    tint: Color,
    testTag: String,
    onClick: () -> Unit,
) {
    Button(
        onClick = onClick,
        modifier = Modifier
            .width(110.dp)
            .height(116.dp)
            .testTag(testTag),
        shape = RoundedCornerShape(24.dp),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(14.dp),
        colors = ButtonDefaults.buttonColors(containerColor = color, contentColor = tint),
    ) {
        Column(modifier = Modifier.fillMaxWidth(), verticalArrangement = Arrangement.SpaceBetween) {
            RecordLineIcon(icon, tint, Modifier.size(27.dp))
            Text("$label ↗", fontSize = 16.sp, lineHeight = 20.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Start, maxLines = 1)
        }
    }
}

@Composable
private fun QuickRecordCard(category: RecordCategory, color: Color, tint: Color, onQuickRecord: (RecordCategory) -> Unit) {
    Button(
        onClick = { onQuickRecord(category) },
        modifier = Modifier
            .width(110.dp)
            .height(116.dp)
            .testTag("today_quick_${category.name.lowercase()}"),
        shape = RoundedCornerShape(24.dp),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(14.dp),
        colors = ButtonDefaults.buttonColors(containerColor = color, contentColor = tint),
    ) {
        Column(modifier = Modifier.fillMaxWidth(), verticalArrangement = Arrangement.SpaceBetween) {
            RecordLineIcon(category.icon, tint, Modifier.size(27.dp))
            Text("${category.label}记录 ↗", fontSize = 16.sp, lineHeight = 20.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Start)
        }
    }
}

@Composable
private fun MedicationCard(medication: TodayMedicationUiState?, unavailable: Boolean = false) {
    RecordCard {
        if (unavailable) {
            Text("今日用药数据暂不可用，请稍后重试。", style = androidx.compose.material3.MaterialTheme.typography.bodyLarge, color = GutCareMuted, modifier = Modifier.testTag("today_medication_unavailable"))
        } else if (medication == null) {
            Text("今日暂无用药打卡数据", style = androidx.compose.material3.MaterialTheme.typography.bodyLarge, color = GutCareMuted)
        } else {
            Row(verticalAlignment = Alignment.CenterVertically) {
                ProgressRing(medication.completedCount, medication.totalCount)
                Spacer(Modifier.width(16.dp))
                Column(modifier = Modifier.weight(1f)) {
                    val remaining = (medication.totalCount - medication.completedCount).coerceAtLeast(0)
                    Text(
                        if (remaining == 0) "今日打卡已完成" else "还有 $remaining 次待记录",
                        style = androidx.compose.material3.MaterialTheme.typography.titleLarge,
                    )
                    medication.nextLabel?.let { Text(it, style = androidx.compose.material3.MaterialTheme.typography.bodyLarge, color = GutCareMuted) }
                }
                RecordLineIcon(RecordIcon.Check, GutCareBrandGreen, Modifier.size(28.dp))
            }
        }
    }
}

@Composable
private fun ProgressRing(completed: Int, total: Int) {
    val safeTotal = total.coerceAtLeast(1)
    Box(contentAlignment = Alignment.Center) {
        Canvas(Modifier.size(76.dp)) {
            drawCircle(GutCareLine, style = Stroke(width = size.minDimension * .14f))
            drawArc(
                color = GutCareBrandGreen,
                startAngle = -90f,
                sweepAngle = 360f * completed.coerceIn(0, safeTotal) / safeTotal,
                useCenter = false,
                style = Stroke(width = size.minDimension * .14f, cap = StrokeCap.Round),
            )
        }
        Text("$completed/$total", style = androidx.compose.material3.MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun MealSummary(meals: List<TodayMealUiState>) {
    if (meals.isEmpty()) {
        RecordCard { Text("今天还没有饮食记录", style = androidx.compose.material3.MaterialTheme.typography.bodyLarge, color = GutCareMuted) }
        return
    }
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
        meals.take(2).forEach { meal ->
            Column(
                modifier = Modifier
                    .weight(1f)
                    .border(1.dp, GutCareLine, RoundedCornerShape(18.dp))
                    .clip(RoundedCornerShape(18.dp))
                    .background(Color.White),
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(96.dp)
                        .background(GutCareSage),
                    contentAlignment = Alignment.Center,
                ) { RecordLineIcon(RecordIcon.Food, GutCareBrandGreen, Modifier.size(42.dp)) }
                Row(Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(meal.label, style = androidx.compose.material3.MaterialTheme.typography.titleMedium)
                    Text(meal.detail, style = androidx.compose.material3.MaterialTheme.typography.bodyMedium, color = if (meal.isRecorded) GutCareMuted else GutCareOrange)
                }
            }
        }
    }
}

@Composable
private fun TrendCard(summary: String?, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth().heightIn(min = 112.dp).testTag("today_trend"),
        shape = RoundedCornerShape(GutCareDimensions.cardRadius),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(20.dp),
        colors = ButtonDefaults.buttonColors(containerColor = GutCarePurpleSoft, contentColor = GutCareInk),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f), horizontalAlignment = Alignment.Start) {
                Text("本周变化", style = androidx.compose.material3.MaterialTheme.typography.titleLarge)
                Text(summary ?: "查看趋势", style = androidx.compose.material3.MaterialTheme.typography.bodyLarge, color = GutCareBrandGreen)
            }
            TrendGlyph(Modifier.size(94.dp))
        }
    }
}

@Composable
private fun TrendGlyph(modifier: Modifier = Modifier) {
    Canvas(modifier) {
        val color = GutCarePurple
        val points = listOf(.05f to .66f, .28f to .43f, .48f to .58f, .72f to .24f, .96f to .36f)
        points.zipWithNext().forEach { (start, end) ->
            drawLine(color, Offset(size.width * start.first, size.height * start.second), Offset(size.width * end.first, size.height * end.second), strokeWidth = size.minDimension * .055f, cap = StrokeCap.Round)
        }
        drawLine(Color(0xFFD4CCEA), Offset(size.width * .05f, size.height * .78f), Offset(size.width * .96f, size.height * .78f), strokeWidth = size.minDimension * .025f)
    }
}

@Composable
private fun DietCandidateCard(candidates: List<DietCandidateUiState>, onReview: (DietCandidateUiState) -> Unit) {
    RecordCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("识别候选", style = androidx.compose.material3.MaterialTheme.typography.titleLarge)
            Spacer(Modifier.weight(1f))
            Text("需你逐项确认", style = androidx.compose.material3.MaterialTheme.typography.bodyMedium, color = GutCareOrange)
        }
        candidates.forEach { candidate ->
            TextButton(
                onClick = { onReview(candidate) },
                modifier = Modifier.fillMaxWidth().testTag("diet_candidate_${candidate.label}"),
            ) {
                Text(candidate.label, modifier = Modifier.weight(1f), textAlign = TextAlign.Start)
                Text(candidate.statusLabel, color = GutCareOrange)
            }
        }
    }
}

@Composable
private fun DraftFoodCard(items: List<DietDraftItemUiState>, onAddFood: (String, String?) -> Unit, onRemoveFood: (Int) -> Unit) {
    var showAdd by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }
    var amount by remember { mutableStateOf("") }
    RecordCard {
        Text("食物", style = androidx.compose.material3.MaterialTheme.typography.titleLarge)
        if (items.isEmpty()) {
            Text("还没有添加食物", modifier = Modifier.padding(top = 10.dp), style = androidx.compose.material3.MaterialTheme.typography.bodyMedium, color = GutCareMuted)
        } else {
            items.forEachIndexed { index, item ->
                Row(Modifier.fillMaxWidth().padding(top = 10.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(item.label, style = androidx.compose.material3.MaterialTheme.typography.bodyLarge)
                    item.portionLabel?.let { Text(it, style = androidx.compose.material3.MaterialTheme.typography.bodyMedium, color = GutCareMuted) }
                    TextButton(onClick = { onRemoveFood(index) }, modifier = Modifier.testTag("diet_remove_food_$index")) { Text("移除") }
                }
            }
        }
        TextButton(onClick = { showAdd = true }, modifier = Modifier.testTag("diet_add_food")) { Text("＋ 添加食物") }
    }
    if (showAdd) AlertDialog(
        onDismissRequest = { showAdd = false },
        title = { Text("添加食物") },
        text = {
            Column {
                OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("食物名称（必填）") }, modifier = Modifier.testTag("diet_food_name"))
                OutlinedTextField(value = amount, onValueChange = { amount = it }, label = { Text("份量（选填）") }, modifier = Modifier.testTag("diet_food_amount"))
            }
        },
        confirmButton = { TextButton(onClick = { if (name.isNotBlank()) { onAddFood(name, amount); name = ""; amount = ""; showAdd = false } }, enabled = name.isNotBlank(), modifier = Modifier.testTag("diet_food_add_confirm")) { Text("添加") } },
        dismissButton = { TextButton(onClick = { showAdd = false }) { Text("取消") } },
    )
}

@Composable
private fun PrototypeAvatar(size: androidx.compose.ui.unit.Dp) {
    Image(
        painter = painterResource(R.drawable.avatar_profile_prototype),
        contentDescription = null,
        modifier = Modifier
            .size(size)
            .clip(CircleShape)
            .border(2.dp, Color.White, CircleShape),
        contentScale = ContentScale.Crop,
    )
}

@Composable
private fun ProfileCard(profile: HealthProfileUiState) {
    Column {
        Row(
            modifier = Modifier.fillMaxWidth().background(GutCareSage, RoundedCornerShape(GutCareDimensions.cardRadius)).padding(20.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            PrototypeAvatar(58.dp)
            Spacer(Modifier.width(14.dp))
            Column {
                Text(profile.displayName ?: "我的健康档案", style = androidx.compose.material3.MaterialTheme.typography.titleLarge)
                profile.birthYear?.let { Text("出生年份 $it", style = androidx.compose.material3.MaterialTheme.typography.bodyLarge, color = GutCareMuted) }
            }
        }
        profile.confirmedSummary?.let { summary ->
            Spacer(Modifier.height(12.dp))
            RecordCard {
                Text("已确认健康信息", style = androidx.compose.material3.MaterialTheme.typography.titleMedium)
                Spacer(Modifier.height(8.dp))
                Text(summary, style = androidx.compose.material3.MaterialTheme.typography.bodyLarge, color = GutCareMuted)
            }
        }
    }
}

@Composable
private fun ArchiveReportsCard(reports: List<ArchiveReportUiState>, onOpenReport: (ArchiveReportUiState) -> Unit) {
    RecordCard(padding = 12.dp) {
        reports.forEachIndexed { index, report ->
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { onOpenReport(report) }
                    .padding(8.dp)
                    .testTag("archive_report_$index"),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(Modifier.size(44.dp).background(Color(0xFFE2ECF8), RoundedCornerShape(14.dp)), contentAlignment = Alignment.Center) {
                    RecordLineIcon(RecordIcon.Document, Color(0xFF4E75AE), Modifier.size(24.dp))
                }
                Spacer(Modifier.width(12.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(report.title, style = androidx.compose.material3.MaterialTheme.typography.titleMedium)
                    Text("${report.dateLabel} · ${report.statusLabel}", style = androidx.compose.material3.MaterialTheme.typography.bodyMedium, color = GutCareMuted)
                }
                RecordLineIcon(RecordIcon.Chevron, GutCareMuted, Modifier.size(20.dp))
            }
            if (index < reports.lastIndex) FormDivider()
        }
    }
}

@Composable
private fun ArchiveMessageCard(message: String) {
    RecordCard {
        Text(message, style = androidx.compose.material3.MaterialTheme.typography.bodyLarge, color = GutCareMuted)
    }
}

@Composable
private fun ArchiveErrorCard(message: String, onRetry: () -> Unit, retryEnabled: Boolean = true) {
    RecordCard {
        Text("暂时无法加载档案", style = androidx.compose.material3.MaterialTheme.typography.titleMedium)
        Text(message, modifier = Modifier.padding(top = 6.dp), style = androidx.compose.material3.MaterialTheme.typography.bodyMedium, color = GutCareMuted)
        if (retryEnabled) TextButton(onClick = onRetry, modifier = Modifier.testTag("archive_retry")) { Text("重试") }
    }
}

@Composable
private fun SeverityCard(severity: Int, onChange: (Int) -> Unit) {
    Column(
        modifier = Modifier.fillMaxWidth().background(GutCareSage, RoundedCornerShape(GutCareDimensions.cardRadius)).padding(20.dp),
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("自评程度", style = androidx.compose.material3.MaterialTheme.typography.titleLarge)
            Text("0—10分", style = androidx.compose.material3.MaterialTheme.typography.bodyLarge, color = GutCareBrandGreen)
        }
        Spacer(Modifier.height(18.dp))
        Text("$severity / 10", fontSize = 34.sp, color = GutCareBrandGreen)
        Slider(
            value = severity.coerceIn(0, 10).toFloat(),
            onValueChange = { onChange(it.toInt()) },
            valueRange = 0f..10f,
            steps = 9,
            modifier = Modifier.testTag("symptom_severity"),
        )
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("无不适", style = androidx.compose.material3.MaterialTheme.typography.bodyMedium, color = GutCareMuted)
            Text("明显不适", style = androidx.compose.material3.MaterialTheme.typography.bodyMedium, color = GutCareMuted)
        }
    }
}

@Composable
private fun MoodSelector(selectedLevel: Int?, onSelect: (MoodOptionUiState) -> Unit) {
    Column(
        modifier = Modifier.fillMaxWidth().background(GutCarePurpleSoft, RoundedCornerShape(GutCareDimensions.cardRadius)).padding(20.dp),
    ) {
        Text("现在的心情怎么样？", style = androidx.compose.material3.MaterialTheme.typography.headlineMedium)
        Spacer(Modifier.height(16.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            moodOptions.forEach { option ->
                Button(
                    onClick = { onSelect(option) },
                    modifier = Modifier.weight(1f).height(112.dp).testTag("mood_level_${option.level}"),
                    shape = RoundedCornerShape(20.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(4.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (option.level == selectedLevel) GutCarePurple else Color.White,
                        contentColor = if (option.level == selectedLevel) Color.White else GutCareMuted,
                    ),
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(option.emoji, fontSize = 30.sp)
                        Spacer(Modifier.height(6.dp))
                        Text(option.label, style = androidx.compose.material3.MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}

@Composable
private fun DateTimeFields(
    date: String,
    time: String,
    onDateChange: (String) -> Unit,
    onTimeChange: (String) -> Unit,
    dateTag: String,
    timeTag: String,
    timeLabel: String,
) {
    FieldRow("记录日期") {
        CompactTextField(date, onDateChange, "YYYY/MM/DD", dateTag)
    }
    FormDivider()
    FieldRow(timeLabel) {
        CompactTextField(time, onTimeChange, "HH:MM", timeTag)
    }
}

@Composable
private fun FieldRow(label: String, field: @Composable RowScope.() -> Unit) {
    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(label, modifier = Modifier.weight(.44f), style = androidx.compose.material3.MaterialTheme.typography.bodyLarge)
        Row(modifier = Modifier.weight(.56f), content = field)
    }
}

@Composable
private fun CompactTextField(value: String, onValueChange: (String) -> Unit, placeholder: String, tag: String) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = Modifier.fillMaxWidth().heightIn(min = 54.dp).testTag(tag),
        placeholder = { Text(placeholder) },
        trailingIcon = if (tag.contains("date")) {
            { Text("▣", color = GutCareMuted, fontSize = 14.sp) }
        } else if (tag.contains("time")) {
            { Text("◷", color = GutCareMuted, fontSize = 14.sp) }
        } else null,
        singleLine = true,
        shape = RoundedCornerShape(16.dp),
        colors = OutlinedTextFieldDefaults.colors(
            focusedContainerColor = GutCareCanvas,
            unfocusedContainerColor = GutCareCanvas,
            focusedBorderColor = GutCareBrandGreen,
            unfocusedBorderColor = Color.Transparent,
        ),
    )
}

@Composable
private fun NoteField(value: String, onValueChange: (String) -> Unit, placeholder: String, tag: String) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = Modifier.fillMaxWidth().heightIn(min = 122.dp).testTag(tag),
        placeholder = { Text(placeholder) },
        minLines = 3,
        shape = RoundedCornerShape(18.dp),
        colors = OutlinedTextFieldDefaults.colors(
            focusedContainerColor = GutCareCanvas,
            unfocusedContainerColor = GutCareCanvas,
            focusedBorderColor = GutCareBrandGreen,
            unfocusedBorderColor = GutCareLine,
        ),
    )
}

@Composable
private fun <T> PillRow(
    items: Iterable<T>,
    selected: T?,
    label: (T) -> String,
    onSelect: (T) -> Unit,
    testTagPrefix: String,
    enabled: (T) -> Boolean = { true },
) {
    Row(
        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        items.forEach { item ->
            val isSelected = item == selected
            Button(
                onClick = { onSelect(item) },
                enabled = enabled(item),
                modifier = Modifier.heightIn(min = 44.dp).testTag("${testTagPrefix}_${label(item)}"),
                shape = RoundedCornerShape(30.dp),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (isSelected) GutCareBrandGreen else Color.White,
                    contentColor = if (isSelected) Color.White else GutCareInk,
                ),
                border = if (isSelected) null else androidx.compose.foundation.BorderStroke(1.dp, GutCareLine),
            ) { Text(label(item), style = androidx.compose.material3.MaterialTheme.typography.bodyLarge) }
        }
    }
}

@Composable
private fun <T> WrapPills(
    items: List<T>,
    selected: (T) -> Boolean,
    label: (T) -> String,
    onSelect: (T) -> Unit,
    testTagPrefix: String,
) {
    // A horizontally scrollable chip line stays reachable on narrow screens without clipping.
    Row(
        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        items.forEach { item ->
            val active = selected(item)
            Button(
                onClick = { onSelect(item) },
                modifier = Modifier.heightIn(min = 44.dp).testTag("${testTagPrefix}_${label(item)}"),
                shape = RoundedCornerShape(30.dp),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (active) GutCareBrandGreen else Color.White,
                    contentColor = if (active) Color.White else GutCareInk,
                ),
                border = if (active) null else androidx.compose.foundation.BorderStroke(1.dp, GutCareLine),
            ) { Text(label(item), style = androidx.compose.material3.MaterialTheme.typography.bodyLarge) }
        }
    }
}

@Composable
private fun RecordCard(
    modifier: Modifier = Modifier,
    padding: androidx.compose.ui.unit.Dp = 20.dp,
    content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(Color.White, RoundedCornerShape(GutCareDimensions.cardRadius))
            .border(1.dp, GutCareLine, RoundedCornerShape(GutCareDimensions.cardRadius))
            .padding(padding),
        content = content,
    )
}

@Composable
private fun SafetyNote(message: String) {
    Row(
        modifier = Modifier.fillMaxWidth().background(GutCareSage, RoundedCornerShape(18.dp)).padding(16.dp),
        verticalAlignment = Alignment.Top,
    ) {
        RecordLineIcon(RecordIcon.Shield, GutCareMuted, Modifier.size(22.dp))
        Spacer(Modifier.width(10.dp))
        Text(message, style = androidx.compose.material3.MaterialTheme.typography.bodyMedium, color = GutCareMuted)
    }
}

@Composable
private fun SectionTitle(title: String) {
    Text(title, style = androidx.compose.material3.MaterialTheme.typography.headlineMedium, color = GutCareInk)
}

@Composable
private fun TodaySectionTitle(title: String) {
    Text(title, fontSize = 20.sp, lineHeight = 26.sp, fontWeight = FontWeight.Bold, color = GutCareInk)
}

@Composable
private fun SectionHeader(title: String, actionLabel: String, onAction: () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        TodaySectionTitle(title)
        Spacer(Modifier.weight(1f))
        TextButton(onClick = onAction) { Text("$actionLabel ›", style = androidx.compose.material3.MaterialTheme.typography.bodyLarge, color = GutCareBrandGreen) }
    }
}

@Composable
private fun FormDivider() {
    Spacer(Modifier.height(16.dp))
    Box(Modifier.fillMaxWidth().height(1.dp).background(GutCareLine))
    Spacer(Modifier.height(16.dp))
}

private enum class RecordIcon { Back, Person, Food, Bowel, Symptoms, Mood, Camera, Check, Document, Chevron, Shield, Activity }

private val RecordCategory.icon: RecordIcon
    get() = when (this) {
        RecordCategory.Diet -> RecordIcon.Food
        RecordCategory.Bowel -> RecordIcon.Bowel
        RecordCategory.Symptoms -> RecordIcon.Symptoms
        RecordCategory.Mood -> RecordIcon.Mood
        RecordCategory.Activity -> RecordIcon.Symptoms
    }

/** Small local vector glyphs keep the screens asset-free and work offline in tests. */
@Composable
private fun RecordLineIcon(icon: RecordIcon, tint: Color, modifier: Modifier = Modifier) {
    Canvas(modifier) {
        val w = size.width
        val h = size.height
        val stroke = Stroke(width = size.minDimension * .11f, cap = StrokeCap.Round)
        fun line(x1: Float, y1: Float, x2: Float, y2: Float) = drawLine(tint, Offset(w * x1, h * y1), Offset(w * x2, h * y2), strokeWidth = size.minDimension * .11f, cap = StrokeCap.Round)
        when (icon) {
            RecordIcon.Back -> { line(.68f, .16f, .30f, .50f); line(.30f, .50f, .68f, .84f) }
            RecordIcon.Chevron -> { line(.32f, .16f, .68f, .50f); line(.68f, .50f, .32f, .84f) }
            RecordIcon.Check -> { line(.18f, .52f, .42f, .76f); line(.42f, .76f, .84f, .26f) }
            RecordIcon.Person -> {
                drawCircle(tint, radius = size.minDimension * .18f, center = Offset(w * .5f, h * .30f), style = stroke)
                drawArc(tint, 195f, 150f, false, Offset(w * .18f, h * .43f), androidx.compose.ui.geometry.Size(w * .64f, h * .48f), style = stroke)
            }
            RecordIcon.Camera -> {
                drawRoundRect(tint, Offset(w * .12f, h * .30f), androidx.compose.ui.geometry.Size(w * .76f, h * .52f), CornerRadius(size.minDimension * .08f), style = stroke)
                drawCircle(tint, radius = size.minDimension * .17f, center = Offset(w * .5f, h * .56f), style = stroke)
                line(.31f, .30f, .42f, .18f); line(.42f, .18f, .58f, .18f); line(.58f, .18f, .69f, .30f)
            }
            RecordIcon.Document -> {
                drawRoundRect(tint, Offset(w * .19f, h * .10f), androidx.compose.ui.geometry.Size(w * .62f, h * .80f), CornerRadius(size.minDimension * .09f), style = stroke)
                line(.36f, .37f, .66f, .37f); line(.36f, .54f, .66f, .54f); line(.36f, .71f, .55f, .71f)
            }
            RecordIcon.Shield -> {
                val path = androidx.compose.ui.graphics.Path().apply {
                    moveTo(w * .50f, h * .10f); lineTo(w * .83f, h * .24f); lineTo(w * .76f, h * .67f); lineTo(w * .50f, h * .90f); lineTo(w * .24f, h * .67f); lineTo(w * .17f, h * .24f); close()
                }
                drawPath(path, tint, style = stroke)
                line(.35f, .50f, .47f, .62f); line(.47f, .62f, .68f, .39f)
            }
            RecordIcon.Activity -> {
                drawCircle(tint, radius = size.minDimension * .11f, center = Offset(w * .62f, h * .20f), style = stroke)
                line(.55f, .34f, .44f, .56f); line(.44f, .56f, .70f, .63f)
                line(.52f, .42f, .30f, .50f); line(.52f, .42f, .76f, .44f)
                line(.44f, .56f, .29f, .82f); line(.44f, .56f, .64f, .84f)
            }
            RecordIcon.Food -> { line(.25f, .12f, .25f, .88f); line(.12f, .12f, .12f, .42f); line(.25f, .12f, .25f, .42f); line(.38f, .12f, .38f, .42f); line(.12f, .42f, .38f, .42f); line(.70f, .12f, .70f, .88f); drawArc(tint, -90f, 180f, false, Offset(w * .51f, h * .12f), androidx.compose.ui.geometry.Size(w * .38f, h * .38f), style = stroke) }
            RecordIcon.Bowel -> { drawCircle(tint, radius = size.minDimension * .30f, center = Offset(w * .5f, h * .55f), style = stroke); line(.35f, .18f, .65f, .18f) }
            RecordIcon.Symptoms -> { line(.50f, .10f, .50f, .90f); line(.10f, .50f, .90f, .50f); line(.22f, .22f, .78f, .78f); line(.78f, .22f, .22f, .78f) }
            RecordIcon.Mood -> { drawCircle(tint, radius = size.minDimension * .34f, center = Offset(w * .5f, h * .5f), style = stroke); line(.31f, .61f, .42f, .70f); line(.42f, .70f, .58f, .70f); line(.58f, .70f, .69f, .61f); drawCircle(tint, radius = size.minDimension * .035f, center = Offset(w * .37f, h * .40f)); drawCircle(tint, radius = size.minDimension * .035f, center = Offset(w * .63f, h * .40f)) }
        }
    }
}
