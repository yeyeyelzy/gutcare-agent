package com.gutcare.app.ui.medication

import android.app.Activity
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.core.view.WindowInsetsControllerCompat
import com.gutcare.app.core.network.MedicationCheckinDto
import com.gutcare.app.core.network.MedicationPlanDto
import com.gutcare.app.core.network.MedicationRepository
import com.gutcare.app.core.network.MedicationScheduleDto
import com.gutcare.app.ui.design.GutCarePage
import com.gutcare.app.ui.design.GutCareBackButton
import com.gutcare.app.ui.design.GutCarePrimaryButton
import com.gutcare.app.ui.theme.GutCareCanvas
import com.gutcare.app.ui.theme.GutCareBrandGreen
import com.gutcare.app.ui.theme.GutCareMuted
import java.time.LocalDate

/** Route to add to the host when F06 is enabled. */
const val MEDICATION_ROUTE = "medication"

@Composable
private fun MedicationLightSystemBars() {
    val view = LocalView.current
    val window = (view.context as? Activity)?.window ?: return
    val controller = remember(window, view) { WindowInsetsControllerCompat(window, view) }
    val status = remember(window) { window.statusBarColor }
    val navigation = remember(window) { window.navigationBarColor }
    val lightStatus = remember(window, controller) { controller.isAppearanceLightStatusBars }
    val lightNavigation = remember(window, controller) { controller.isAppearanceLightNavigationBars }
    SideEffect {
        window.statusBarColor = GutCareCanvas.toArgb()
        window.navigationBarColor = GutCareCanvas.toArgb()
        controller.isAppearanceLightStatusBars = true
        controller.isAppearanceLightNavigationBars = true
    }
    DisposableEffect(window, controller) {
        onDispose {
            window.statusBarColor = status
            window.navigationBarColor = navigation
            controller.isAppearanceLightStatusBars = lightStatus
            controller.isAppearanceLightNavigationBars = lightNavigation
        }
    }
}

/** Standalone entry point for navigation integration; no top-level graph edits are required. */
@Composable
fun MedicationFeatureEntry(gateway: MedicationFeatureGateway, onBack: () -> Unit = {}) {
    val model: MedicationViewModel = viewModel(factory = remember(gateway) { MedicationViewModelFactory(gateway) })
    val state by model.uiState.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { model.load() }
    MedicationScreen(
        state = state, onBack = onBack, onRefresh = { model.load() }, onSection = model::selectSection,
        onSelectPlan = model::selectPlan, onHistoryRange = model::setHistoryRange,
        onCreatePlan = model::createPlan, onTransition = model::transition,
        onCreateSchedule = model::createSchedule, onToggleSchedule = model::toggleSchedule,
        onRemoveSchedule = model::removeSchedule, onUpdateCheckin = model::updateCheckin,
    )
}

@Composable
fun MedicationFeatureEntry(repository: MedicationRepository, onBack: () -> Unit = {}) =
    MedicationFeatureEntry(remember(repository) { RepositoryMedicationFeatureGateway(repository) }, onBack)

@Composable
fun MedicationScreen(
    state: MedicationUiState,
    onBack: () -> Unit,
    onRefresh: () -> Unit,
    onSection: (MedicationSection) -> Unit,
    onSelectPlan: (String) -> Unit,
    onHistoryRange: (String, String) -> Unit,
    onCreatePlan: (String, String, String, String, String) -> Unit,
    onTransition: (MedicationPlanDto, String) -> Unit,
    onCreateSchedule: (String, String, String, String, String) -> Unit,
    onToggleSchedule: (MedicationScheduleDto) -> Unit,
    onRemoveSchedule: (MedicationScheduleDto) -> Unit,
    onUpdateCheckin: (MedicationCheckinDto, String) -> Unit,
) {
    var name by remember { mutableStateOf("") }
    var dosage by remember { mutableStateOf("") }
    var route by remember { mutableStateOf("") }
    var planStart by remember { mutableStateOf(LocalDate.now().toString()) }
    var planEnd by remember { mutableStateOf("") }
    var localTime by remember { mutableStateOf("08:00:00") }
    var timezone by remember { mutableStateOf(java.time.ZoneId.systemDefault().id) }
    var validFrom by remember { mutableStateOf(LocalDate.now().toString()) }
    var rrule by remember { mutableStateOf("FREQ=DAILY") }
    var removeCandidate by remember { mutableStateOf<MedicationScheduleDto?>(null) }

    MedicationLightSystemBars()
    GutCarePage(modifier = Modifier.statusBarsPadding().testTag("medication_screen")) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            GutCareBackButton(onBack, text = "‹", testTag = "medication_back", modifier = Modifier.padding(end = 12.dp))
            Column(Modifier.weight(1f)) {
                Text("用药计划", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            }
            androidx.compose.material3.Surface(onClick = onRefresh, enabled = !state.loading, modifier = Modifier.testTag("medication_refresh"), shape = RoundedCornerShape(22.dp), color = GutCareCanvas) {
                androidx.compose.foundation.layout.Box(Modifier.padding(horizontal = 18.dp, vertical = 9.dp), contentAlignment = Alignment.Center) { Text("今天", color = GutCareBrandGreen, style = MaterialTheme.typography.labelLarge) }
            }
        }
        Text(LocalDate.now().format(java.time.format.DateTimeFormatter.ofPattern("M月d日，EEEE", java.util.Locale.SIMPLIFIED_CHINESE)), color = GutCareMuted, modifier = Modifier.padding(start = 8.dp, bottom = 16.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            MedicationSection.entries.forEach { section ->
                if (section == state.section) GutCarePrimaryButton(section.label, { onSection(section) }, modifier = Modifier.weight(1f), testTag = "medication_tab_${section.name.lowercase()}")
                else OutlinedButton(onClick = { onSection(section) }, modifier = Modifier.weight(1f).height(52.dp).testTag("medication_tab_${section.name.lowercase()}")) { Text(section.label) }
            }
        }
        Spacer(Modifier.height(12.dp))
        if (state.loading) Text("正在加载用药信息…", color = GutCareMuted, modifier = Modifier.testTag("medication_loading"))
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("medication_error")) }
        state.operationMessage?.let { Text(it, color = if (state.conflict) MaterialTheme.colorScheme.error else GutCareMuted, modifier = Modifier.testTag("medication_feedback")) }
        when (state.section) {
            MedicationSection.TODAY -> TodayContent(state, onUpdateCheckin)
            MedicationSection.PLANS -> PlansContent(
                state, name, { name = it }, dosage, { dosage = it }, route, { route = it }, planStart, { planStart = it }, planEnd, { planEnd = it },
                localTime, { localTime = it }, timezone, { timezone = it }, validFrom, { validFrom = it }, rrule, { rrule = it },
                onCreatePlan, onSelectPlan, onTransition, onCreateSchedule, onToggleSchedule, { removeCandidate = it }, state.saving,
            )
            MedicationSection.HISTORY -> HistoryContent(state, onHistoryRange)
        }
        Spacer(Modifier.height(20.dp))
    }
    removeCandidate?.let { schedule ->
        AlertDialog(
            onDismissRequest = { removeCandidate = null },
            title = { Text("停用这条服药日程？") },
            text = { Text("已有的打卡历史会保留。") },
            confirmButton = { TextButton(onClick = { removeCandidate = null; onRemoveSchedule(schedule) }, modifier = Modifier.testTag("medication_schedule_delete_confirm")) { Text("确认停用") } },
            dismissButton = { TextButton(onClick = { removeCandidate = null }) { Text("取消") } },
        )
    }
}

@Composable
private fun TodayContent(state: MedicationUiState, onUpdate: (MedicationCheckinDto, String) -> Unit) {
    val completed = state.today.count { it.status != "pending" }
    Card(Modifier.fillMaxWidth().padding(bottom = 18.dp), shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 20.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("◉", color = com.gutcare.app.ui.theme.GutCareBrandGreen, style = MaterialTheme.typography.headlineMedium, modifier = Modifier.padding(end = 16.dp))
            Column(Modifier.weight(1f)) {
                Text("今日服药打卡", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                Text("按已确认的用药计划记录", color = GutCareMuted)
            }
            Text("$completed/${state.today.size}", style = MaterialTheme.typography.headlineMedium, color = com.gutcare.app.ui.theme.GutCareBrandGreen, fontWeight = FontWeight.Bold)
        }
    }
    SectionTitle("今日安排", "未回应的计划保持待确认，不会自动记为未服用。")
    if (state.today.isEmpty() && !state.loading) Text("今天还没有生成服药日程。", color = GutCareMuted, modifier = Modifier.testTag("medication_today_empty"))
    state.today.sortedBy { it.scheduledFor }.forEach { item ->
        val schedule = state.schedules.values.flatten().firstOrNull { it.id == item.scheduleId }
        val plan = state.plans.firstOrNull { it.id == schedule?.planId }
        val pending = item.status == "pending"
        val time = schedule?.localTime?.take(5) ?: item.scheduledFor.take(16)
        Row(Modifier.fillMaxWidth().padding(bottom = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.padding(end = 10.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Text(time, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Text(if (pending) "待记录" else "已记录", color = if (pending) com.gutcare.app.ui.theme.GutCareOrange else GutCareMuted, style = MaterialTheme.typography.bodySmall)
            }
            Card(Modifier.weight(1f).testTag("medication_checkin_${item.id}"), shape = RoundedCornerShape(topStart = 0.dp, bottomStart = 0.dp, topEnd = 22.dp, bottomEnd = 22.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
                Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(plan?.medicationName ?: "用药记录", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    Text(if (pending) "按已确认的用药计划" else statusLabel(item.status), color = GutCareMuted, modifier = Modifier.testTag("medication_checkin_status_${item.id}"))
                    if (pending) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        OutlinedButton(
                            onClick = { onUpdate(item, "taken") },
                            modifier = Modifier.weight(1f).heightIn(min = 48.dp).testTag("medication_checkin_taken_${item.id}"),
                            contentPadding = PaddingValues(horizontal = 4.dp, vertical = 6.dp),
                        ) { Text("已服用", maxLines = 1, style = MaterialTheme.typography.labelSmall) }
                        OutlinedButton(
                            onClick = { onUpdate(item, "not_taken") },
                            modifier = Modifier.weight(1f).heightIn(min = 48.dp).testTag("medication_checkin_not_taken_${item.id}"),
                            contentPadding = PaddingValues(horizontal = 4.dp, vertical = 6.dp),
                        ) { Text("未服用", maxLines = 1, style = MaterialTheme.typography.labelSmall) }
                        OutlinedButton(
                            onClick = { onUpdate(item, "skipped") },
                            modifier = Modifier.weight(1f).heightIn(min = 48.dp).testTag("medication_checkin_skipped_${item.id}"),
                            contentPadding = PaddingValues(horizontal = 4.dp, vertical = 6.dp),
                        ) { Text("跳过", maxLines = 1, style = MaterialTheme.typography.labelSmall) }
                    }
                }
            }
        }
    }
}

@Composable
private fun PlansContent(
    state: MedicationUiState,
    name: String, setName: (String) -> Unit, dosage: String, setDosage: (String) -> Unit,
    route: String, setRoute: (String) -> Unit, start: String, setStart: (String) -> Unit,
    end: String, setEnd: (String) -> Unit, localTime: String, setLocalTime: (String) -> Unit,
    timezone: String, setTimezone: (String) -> Unit, validFrom: String, setValidFrom: (String) -> Unit,
    rrule: String, setRrule: (String) -> Unit, onCreate: (String, String, String, String, String) -> Unit,
    onSelectPlan: (String) -> Unit, onTransition: (MedicationPlanDto, String) -> Unit,
    onCreateSchedule: (String, String, String, String, String) -> Unit, onToggleSchedule: (MedicationScheduleDto) -> Unit,
    onRemoveSchedule: (MedicationScheduleDto) -> Unit, saving: Boolean,
) {
    SectionTitle("用药计划", "来源可手动填写；待确认、已确认和计划状态分开显示。")
    if (state.plans.isEmpty() && !state.loading) Text("还没有用药计划。", color = GutCareMuted, modifier = Modifier.testTag("medication_plans_empty"))
    state.plans.forEach { plan ->
        MedicationCard {
            Text(plan.medicationName, style = MaterialTheme.typography.titleMedium)
            Text("${plan.dosageText ?: "剂量未填写"}${plan.routeCode?.let { " · $it" } ?: ""}")
            Text("确认：${confirmationLabel(plan.confirmationStatus)}　计划：${planStatusLabel(plan.planStatus)}${if (plan.sourceDeleted) "　来源已删除" else ""}", color = GutCareMuted, modifier = Modifier.testTag("medication_plan_status_${plan.id}"))
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                when {
                    plan.confirmationStatus != "confirmed" -> OutlinedButton(onClick = { onTransition(plan, "confirm") }, enabled = !saving, modifier = Modifier.testTag("medication_plan_confirm_${plan.id}")) { Text("确认来源") }
                    plan.confirmationStatus == "confirmed" && plan.planStatus != "active" -> OutlinedButton(onClick = { onTransition(plan, "activate") }, enabled = !saving, modifier = Modifier.testTag("medication_plan_activate_${plan.id}")) { Text("开始计划") }
                }
                if (plan.planStatus == "active") {
                    OutlinedButton(onClick = { onTransition(plan, "end") }, enabled = !saving) { Text("结束") }
                    OutlinedButton(onClick = { onTransition(plan, "discontinue") }, enabled = !saving) { Text("停用") }
                }
                if (plan.confirmationStatus == "confirmed") OutlinedButton(onClick = { onTransition(plan, "review") }, enabled = !saving) { Text("需复核") }
            }
            TextButton(onClick = { onSelectPlan(plan.id) }, modifier = Modifier.testTag("medication_schedule_select_${plan.id}")) { Text(if (state.selectedPlanId == plan.id) "正在为此计划添加日程" else "为此计划管理日程") }
            state.schedules[plan.id].orEmpty().forEach { schedule ->
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.weight(1f)) {
                        Text("${schedule.localTime.take(5)} · ${schedule.timezone}")
                        Text(if (schedule.enabled) "已启用 · ${schedule.rrule ?: "单次"}" else "已暂停", color = GutCareMuted)
                    }
                    TextButton(onClick = { onToggleSchedule(schedule) }, enabled = !saving, modifier = Modifier.testTag("medication_schedule_toggle_${schedule.id}")) { Text(if (schedule.enabled) "暂停" else "启用") }
                    TextButton(onClick = { onRemoveSchedule(schedule) }, enabled = !saving, modifier = Modifier.testTag("medication_schedule_remove_${schedule.id}")) { Text("停用") }
                }
            }
        }
        Spacer(Modifier.height(8.dp))
    }
    SectionTitle("新增计划")
    MedicationField("药品名称", name, setName, "medication_plan_name")
    MedicationField("剂量原文（可选）", dosage, setDosage, "medication_plan_dosage")
    MedicationField("给药途径（可选）", route, setRoute, "medication_plan_route")
    MedicationField("开始日期 YYYY-MM-DD（可选）", start, setStart, "medication_plan_start")
    MedicationField("结束日期 YYYY-MM-DD（可选）", end, setEnd, "medication_plan_end")
    GutCarePrimaryButton("保存待确认计划", { onCreate(name, dosage, route, start, end) }, enabled = !saving, testTag = "medication_plan_create")
    SectionTitle("新增服药日程", "选择一个计划；日期、当地时间及 IANA 时区按服务端规则解析。")
    val schedulablePlans = state.plans.filter { it.confirmationStatus == "confirmed" && it.planStatus == "active" }
    if (schedulablePlans.isNotEmpty()) {
        Text("当前计划：${schedulablePlans.firstOrNull { it.id == state.selectedPlanId }?.medicationName ?: schedulablePlans.first().medicationName}", color = GutCareMuted)
        schedulablePlans.forEach { plan -> TextButton(onClick = { onSelectPlan(plan.id) }, modifier = Modifier.testTag("medication_schedule_plan_${plan.id}")) { Text(if (state.selectedPlanId == plan.id) "✓ ${plan.medicationName}" else plan.medicationName) } }
        MedicationField("当地时间 HH:mm:ss", localTime, setLocalTime, "medication_schedule_time")
        MedicationField("时区（IANA）", timezone, setTimezone, "medication_schedule_timezone")
        MedicationField("生效日期 YYYY-MM-DD", validFrom, setValidFrom, "medication_schedule_valid_from")
        MedicationField("重复规则（可选）", rrule, setRrule, "medication_schedule_rrule")
        GutCarePrimaryButton("添加日程", { (state.selectedPlanId?.takeIf { id -> schedulablePlans.any { it.id == id } } ?: schedulablePlans.firstOrNull()?.id)?.let { onCreateSchedule(it, localTime, timezone, validFrom, rrule) } }, enabled = !saving, testTag = "medication_schedule_create")
    } else Text("请先确认并开始一个用药计划，再添加日程。", color = GutCareMuted)
}

@Composable
private fun HistoryContent(state: MedicationUiState, onRange: (String, String) -> Unit) {
    SectionTitle("服药历史", "最多查询连续 93 天；历史状态由本人确认记录。")
    var start by remember(state.historyStart) { mutableStateOf(state.historyStart) }
    var end by remember(state.historyEnd) { mutableStateOf(state.historyEnd) }
    MedicationField("开始日期 YYYY-MM-DD", start, { start = it }, "medication_history_start")
    MedicationField("结束日期 YYYY-MM-DD", end, { end = it }, "medication_history_end")
    GutCarePrimaryButton("查询历史", { onRange(start, end) }, enabled = !state.loading, testTag = "medication_history_query")
    if (state.history.isEmpty() && !state.loading) Text("所选日期内没有服药打卡。", color = GutCareMuted, modifier = Modifier.testTag("medication_history_empty"))
    state.history.forEach { item ->
        val schedule = state.schedules.values.flatten().firstOrNull { it.id == item.scheduleId }
        val plan = state.plans.firstOrNull { it.id == schedule?.planId }
        MedicationCard {
            Text(plan?.medicationName ?: "用药记录", style = MaterialTheme.typography.titleMedium)
            Text("${item.localDate} · ${schedule?.localTime?.take(5) ?: item.scheduledFor.take(16)} · ${statusLabel(item.status)}")
        }
    }
}

@Composable
private fun SectionTitle(title: String, subtitle: String? = null) {
    Text(title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
    subtitle?.let { Text(it, color = GutCareMuted, style = MaterialTheme.typography.bodyMedium) }
    Spacer(Modifier.height(10.dp))
}

@Composable
private fun MedicationCard(content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(vertical = 5.dp),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp), content = content) }
}

@Composable
private fun MedicationField(label: String, value: String, onValue: (String) -> Unit, tag: String) {
    OutlinedTextField(value, onValue, label = { Text(label) }, modifier = Modifier.fillMaxWidth().testTag(tag), singleLine = true)
}

private fun statusLabel(status: String) = when (status) {
    "taken" -> "已服用"
    "not_taken" -> "未服用"
    "skipped" -> "已跳过"
    else -> "待确认"
}
private fun confirmationLabel(status: String) = when (status) { "confirmed" -> "已确认"; "needs_review" -> "需复核"; else -> "待确认" }
private fun planStatusLabel(status: String) = when (status) { "active" -> "进行中"; "ended" -> "已结束"; else -> "已停用" }
