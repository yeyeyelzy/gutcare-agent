package com.gutcare.app.ui.risktrend

import android.app.Activity
import androidx.compose.foundation.clickable
import androidx.compose.foundation.background
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.Alignment
import androidx.compose.material3.Surface
import androidx.core.view.WindowInsetsControllerCompat
import com.gutcare.app.core.network.HistoryItemDto
import com.gutcare.app.core.network.RiskAlertDto
import com.gutcare.app.core.network.TrendResponseDto
import com.gutcare.app.ui.design.GutCarePage
import com.gutcare.app.ui.theme.GutCareBrandGreen
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter

@Composable
private fun RiskTrendLightSystemBars() {
    val view = LocalView.current
    val window = (view.context as? Activity)?.window ?: return
    val controller = remember(window, view) { WindowInsetsControllerCompat(window, view) }
    val status = remember(window) { window.statusBarColor }
    val navigation = remember(window) { window.navigationBarColor }
    val lightStatus = remember(window, controller) { controller.isAppearanceLightStatusBars }
    val lightNavigation = remember(window, controller) { controller.isAppearanceLightNavigationBars }
    SideEffect {
        window.statusBarColor = com.gutcare.app.ui.theme.GutCareCanvas.toArgb()
        window.navigationBarColor = com.gutcare.app.ui.theme.GutCareCanvas.toArgb()
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

@Composable
fun RiskAlertListScreen(state: RiskTrendUiState, onLoad: () -> Unit, onLoadMore: () -> Unit, onOpen: (String) -> Unit) {
    GutCarePage(modifier = Modifier.statusBarsPadding()) {
        Text("风险提示", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 24.dp, bottom = 16.dp))
        when (val list = state.risks) {
            RiskListState.Loading -> FeedbackCard("正在加载风险提示…", "risk_loading")
            RiskListState.Empty -> Column { FeedbackCard("目前没有风险提示。", "risk_empty"); TextButton(onClick = onLoad) { Text("刷新") } }
            is RiskListState.Error -> Column { FeedbackCard(list.message, "risk_error"); TextButton(onClick = onLoad) { Text("重试") } }
            is RiskListState.Ready -> {
                list.items.forEach { alert -> RiskAlertCard(alert) { onOpen(alert.id) } }
                if (state.riskCursor != null) TextButton(onClick = onLoadMore, enabled = !state.riskLoadingMore, modifier = Modifier.fillMaxWidth().testTag("risk_load_more")) {
                    Text(if (state.riskLoadingMore) "正在加载…" else "加载更多")
                }
            }
        }
        state.actionMessage?.let { FeedbackCard(it, "risk_feedback") }
    }
}

@Composable
fun RiskAlertDetailScreen(state: RiskTrendUiState, alertId: String, onLoad: (String) -> Unit, onMarkRead: () -> Unit, onReevaluate: () -> Unit, onBack: () -> Unit) {
    LaunchedEffect(alertId) { onLoad(alertId) }
    RiskTrendLightSystemBars()
    GutCarePage(modifier = Modifier.statusBarsPadding()) {
        Row(Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Surface(onClick = onBack, modifier = Modifier.padding(end = 12.dp).size(48.dp).testTag("risk_detail_back"), shape = RoundedCornerShape(16.dp), color = Color.White, shadowElevation = 1.dp) {
                Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) { Text("‹", style = MaterialTheme.typography.headlineMedium, color = GutCareBrandGreen) }
            }
            Text("风险提示", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold, color = com.gutcare.app.ui.theme.GutCareInk)
        }
        val alert = state.detail
        when {
            state.detailLoading -> FeedbackCard("正在加载详情…", "risk_detail_loading")
            alert == null -> Column { FeedbackCard(state.actionMessage ?: "无法获取此提示。", "risk_detail_error"); TextButton(onClick = { onLoad(alertId) }) { Text("重试") } }
            else -> {
                Text("${formatTime(alert.triggeredAt)} 更新", style = MaterialTheme.typography.bodyMedium, color = com.gutcare.app.ui.theme.GutCareMuted, modifier = Modifier.padding(top = 12.dp, bottom = 16.dp))
                RiskDetailHeroCard(alert)
                Text("相关记录", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 18.dp, bottom = 8.dp))
                Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
                    Column(Modifier.fillMaxWidth().padding(18.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text("提示时间", color = com.gutcare.app.ui.theme.GutCareMuted)
                            Text(formatTime(alert.triggeredAt), color = com.gutcare.app.ui.theme.GutCareInk)
                        }
                        androidx.compose.material3.HorizontalDivider(Modifier.padding(vertical = 12.dp), color = com.gutcare.app.ui.theme.GutCareLine)
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text("处理状态", color = com.gutcare.app.ui.theme.GutCareMuted)
                            Text(statusLabel(alert.status), color = com.gutcare.app.ui.theme.GutCareInk)
                        }
                        Text("查看风险提示", style = MaterialTheme.typography.bodyMedium, color = GutCareBrandGreen, modifier = Modifier.padding(top = 14.dp))
                    }
                }
                Text("处理记录", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 18.dp, bottom = 8.dp))
                Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
                    Column(Modifier.fillMaxWidth().padding(18.dp)) {
                        Text("${formatTime(alert.triggeredAt)} · 风险提示已生成", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                        Text("${statusLabel(alert.status)} · 由业务规则生成", style = MaterialTheme.typography.bodySmall, color = com.gutcare.app.ui.theme.GutCareMuted, modifier = Modifier.padding(top = 8.dp))
                        if (alert.status == "unread") TextButton(onClick = onMarkRead, enabled = !state.actionBusy, modifier = Modifier.fillMaxWidth().padding(top = 12.dp).testTag("risk_mark_read")) { Text("我已知晓") }
                    }
                }
                TextButton(onClick = onReevaluate, enabled = !state.actionBusy, modifier = Modifier.fillMaxWidth().testTag("risk_reevaluate")) { Text("重新评估") }
                Text("查看状态不代表风险已解除；提示由业务规则生成。", style = MaterialTheme.typography.bodySmall, color = GutCareBrandGreen, modifier = Modifier.padding(vertical = 12.dp))
                state.actionMessage?.let { FeedbackCard(it, "risk_action_feedback") }
            }
        }
    }
}

@Composable
private fun RiskDetailHeroCard(alert: RiskAlertDto) {
    val urgent = alert.severity in setOf("emergency", "seek_care")
    val accent = if (urgent) Color(0xFFBE4F4C) else GutCareBrandGreen
    Card(Modifier.fillMaxWidth().padding(top = 4.dp), shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = Color.White), border = androidx.compose.foundation.BorderStroke(1.dp, com.gutcare.app.ui.theme.GutCareLine)) {
        Column(Modifier.fillMaxWidth().background(Color.White)) {
            Box(Modifier.fillMaxWidth().height(4.dp).background(accent))
            Column(Modifier.fillMaxWidth().padding(18.dp)) {
            riskEnvironmentDisclosure(alert.environment)?.let {
                Text(it, modifier = Modifier.padding(bottom = 10.dp).clip(RoundedCornerShape(10.dp)).background(Color(0xFFFFE7BF)).padding(horizontal = 10.dp, vertical = 7.dp).testTag("risk_environment_disclosure"), color = Color(0xFF7A3E00), style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
            }
            Box(Modifier.padding(top = 8.dp).clip(RoundedCornerShape(18.dp)).background(accent.copy(alpha = .12f)).padding(14.dp)) { Text(if (urgent) "⚠" else "i", color = accent, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold) }
            Text(if (alert.severity == "emergency") "建议立即就医评估" else if (alert.severity == "seek_care") "建议就医评估" else "健康提示", color = accent, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 16.dp))
            Text(alert.message, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(top = 10.dp))
            Text(alert.recommendedAction, style = MaterialTheme.typography.bodyLarge, color = com.gutcare.app.ui.theme.GutCareMuted, modifier = Modifier.padding(top = 14.dp))
            Text(statusLabel(alert.status), style = MaterialTheme.typography.labelLarge, color = accent, modifier = Modifier.padding(top = 12.dp).testTag("risk_detail_status"))
            }
        }
    }
}

@Composable
fun HealthTrendsScreen(
    state: RiskTrendUiState,
    onLoad: () -> Unit,
    timeZoneId: String = java.time.ZoneId.systemDefault().id,
    onLoadRange: ((String, String, String) -> Unit)? = null,
    onBack: () -> Unit = {},
) {
    var rangeMode by remember(timeZoneId) { mutableStateOf(TrendRangeMode.WEEK) }
    val range = remember(timeZoneId, rangeMode) { trendRange(timeZoneId, rangeMode) }
    LaunchedEffect(range) { onLoadRange?.invoke(range.first, range.second, rangeMode.bucket) }
    RiskTrendLightSystemBars()
    GutCarePage(modifier = Modifier.statusBarsPadding()) {
        Row(Modifier.fillMaxWidth().padding(top = 20.dp, bottom = 14.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack, modifier = Modifier.padding(end = 8.dp).testTag("trends_back")) { Text("‹", style = MaterialTheme.typography.headlineMedium, color = GutCareBrandGreen) }
            Text("健康趋势", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        }
        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(Color(0xFFE9EFEA)).padding(4.dp)) {
            TrendRangeMode.entries.forEach { mode ->
                val selected = mode == rangeMode
                Surface(onClick = { rangeMode = mode; if (onLoadRange == null) onLoad() }, modifier = Modifier.weight(1f).height(42.dp).testTag("trends_range_${mode.name.lowercase()}"), shape = RoundedCornerShape(22.dp), color = if (selected) Color.White else Color.Transparent) {
                    Box(contentAlignment = Alignment.Center) { Text(mode.label, color = if (selected) GutCareBrandGreen else com.gutcare.app.ui.theme.GutCareMuted, fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal) }
                }
            }
        }
        Spacer(Modifier.height(16.dp))
        when (val trends = state.trends) {
            TrendState.Idle, TrendState.Loading -> FeedbackCard("正在加载趋势…", "trends_loading")
            TrendState.Empty -> Column { FeedbackCard("所选时间范围内暂无可展示的数据。", "trends_empty"); TextButton(onClick = { onLoadRange?.invoke(range.first, range.second, rangeMode.bucket) ?: onLoad() }) { Text("刷新") } }
            is TrendState.Error -> Column { FeedbackCard(trends.message, "trends_error"); TextButton(onClick = { onLoadRange?.invoke(range.first, range.second, rangeMode.bucket) ?: onLoad() }) { Text("重试") } }
            is TrendState.ConsentRequired -> Column {
                FeedbackCard("心情趋势暂不可用。请先在授权设置中确认健康数据处理与心情数据处理授权。", "trends_consent_required")
                trends.mood.missingConsents.forEach { Text(consentLabel(it), style = MaterialTheme.typography.bodySmall) }
                TextButton(onClick = { onLoadRange?.invoke(range.first, range.second, rangeMode.bucket) ?: onLoad() }) { Text("重新检查") }
            }
            is TrendState.Ready -> TrendContent(trends.response)
        }
    }
}

private enum class TrendRangeMode(val label: String, val bucket: String) { WEEK("本周", "day"), MONTH("本月", "week") }

private fun trendRange(timeZoneId: String, mode: TrendRangeMode): Pair<String, String> {
    val zone = runCatching { java.time.ZoneId.of(timeZoneId) }.getOrDefault(java.time.ZoneId.systemDefault())
    val today = java.time.LocalDate.now(zone)
    val start = when (mode) {
        TrendRangeMode.WEEK -> today.minusDays(6)
        TrendRangeMode.MONTH -> today.withDayOfMonth(1)
    }
    return start.atStartOfDay(zone).toOffsetDateTime().toString() to today.plusDays(1).atStartOfDay(zone).toOffsetDateTime().toString()
}

private enum class TrendMetric(val label: String) { STOOL("排便次数"), SYMPTOM("症状"), MOOD("心情"), ACTIVITY("运动"), MEDICATION("服药") }

@Composable
private fun TrendContent(data: TrendResponseDto) {
    var metric by remember { mutableStateOf(TrendMetric.STOOL) }
    val points = when (metric) {
        TrendMetric.STOOL -> data.stool.items.map { it.bucket to (it.count ?: 0) }
        TrendMetric.SYMPTOM -> data.symptom.items.map { it.bucket to (it.count ?: 0) }
        TrendMetric.MOOD -> if (data.mood.availability == "available") data.mood.buckets.map { it.periodStart to it.recordCount } else emptyList()
        TrendMetric.ACTIVITY -> data.activity.items.map { it.bucket to (it.count ?: 0) }
        TrendMetric.MEDICATION -> data.medicationCheckins.items.groupBy { it.bucket }.map { (bucket, rows) -> bucket to rows.sumOf { it.count ?: 0 } }.sortedBy { it.first }
    }
    val hasData = when (metric) {
        TrendMetric.STOOL -> data.stool.hasData
        TrendMetric.SYMPTOM -> data.symptom.hasData
        TrendMetric.MOOD -> data.mood.availability == "available" && data.mood.buckets.isNotEmpty()
        TrendMetric.ACTIVITY -> data.activity.hasData
        TrendMetric.MEDICATION -> data.medicationCheckins.hasData
    }
    Text("${data.from.take(10)} — ${data.to.take(10)} · ${data.timezone}", style = MaterialTheme.typography.bodySmall, color = com.gutcare.app.ui.theme.GutCareMuted)
    Row(horizontalArrangement = Arrangement.spacedBy(5.dp), modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp)) {
        TrendMetric.entries.forEach { item ->
            val selected = item == metric
            Surface(onClick = { metric = item }, modifier = Modifier.weight(1f).height(40.dp).testTag("trends_metric_${item.name.lowercase()}"), shape = RoundedCornerShape(22.dp), color = if (selected) GutCareBrandGreen else Color.White) {
                Box(contentAlignment = Alignment.Center) { Text(item.label, style = MaterialTheme.typography.labelSmall, color = if (selected) Color.White else GutCareBrandGreen, maxLines = 1) }
            }
        }
    }
    TrendChartCard(metric.label, points, hasData)
    val total = points.sumOf { it.second }
    val activeBucket = points.maxByOrNull { it.second }?.first?.takeLast(5) ?: "—"
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth().padding(bottom = 18.dp)) {
        TrendStatCard("本期记录", "$total 次", Modifier.weight(1f), Color(0xFFF9E4D9))
        TrendStatCard("最高记录日", activeBucket, Modifier.weight(1f), Color(0xFFEAE5F3))
    }
    Text("${metric.label}分时段记录", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, modifier = Modifier.padding(bottom = 8.dp))
    TrendSeriesCard("记录明细", points.map { "${it.first} · ${it.second} 次" }, hasData)
    if (metric == TrendMetric.STOOL && data.stool.hasData) {
        val confirmed = data.stool.items.sumOf { it.bristolConfirmedCount ?: 0 }
        val unknown = data.stool.items.sumOf { it.bristolUnknownCount ?: 0 }
        TrendBristolSummary(confirmed, unknown)
    }
    Text("趋势用于观察记录变化，不用于判断疾病或因果关系。", style = MaterialTheme.typography.bodySmall, color = com.gutcare.app.ui.theme.GutCareMuted, modifier = Modifier.padding(vertical = 14.dp))
    if (data.mood.availability == "consent_required") FeedbackCard("心情趋势授权不足，未显示为零。", "trends_mood_consent")
    if (data.mood.availability == "available" && data.mood.buckets.isEmpty()) FeedbackCard("所选范围内没有心情记录。", "trends_mood_empty")
}

@Composable
private fun TrendBristolSummary(confirmed: Int, unknown: Int) {
    val maxValue = maxOf(confirmed, unknown, 1)
    Card(Modifier.fillMaxWidth().padding(bottom = 12.dp), shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("Bristol 记录状态", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            listOf("已确认" to confirmed, "未知" to unknown).forEach { (label, count) ->
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(label, modifier = Modifier.weight(.22f), style = MaterialTheme.typography.bodySmall, color = com.gutcare.app.ui.theme.GutCareMuted)
                    Box(Modifier.weight(.68f).height(12.dp).clip(RoundedCornerShape(8.dp)).background(Color(0xFFF0F3EF))) {
                        Box(Modifier.fillMaxWidth(count.toFloat() / maxValue).height(12.dp).clip(RoundedCornerShape(8.dp)).background(if (label == "已确认") GutCareBrandGreen else Color(0xFFB8C9BE)))
                    }
                    Text(count.toString(), modifier = Modifier.weight(.1f), style = MaterialTheme.typography.bodySmall, color = GutCareBrandGreen)
                }
            }
        }
    }
}

@Composable
private fun TrendChartCard(title: String, points: List<Pair<String, Int>>, hasData: Boolean) {
    Card(Modifier.fillMaxWidth().padding(bottom = 12.dp), shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(16.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Text("${points.firstOrNull()?.first?.takeLast(5).orEmpty()} — ${points.lastOrNull()?.first?.takeLast(5).orEmpty()}", style = MaterialTheme.typography.labelSmall, color = com.gutcare.app.ui.theme.GutCareMuted)
            }
            if (!hasData || points.isEmpty()) Text("暂无数据", color = com.gutcare.app.ui.theme.GutCareMuted, modifier = Modifier.padding(vertical = 38.dp).testTag("trends_chart_empty"))
            else {
                val visible = points.takeLast(7)
                val maxValue = (visible.maxOfOrNull { it.second } ?: 0).coerceAtLeast(1)
                Canvas(Modifier.fillMaxWidth().height(190.dp).padding(top = 8.dp).testTag("trends_chart")) {
                    val top = 12.dp.toPx(); val bottom = size.height - 28.dp.toPx(); val height = bottom - top
                    repeat(3) { idx -> val y = top + height * (idx + 1) / 3f; drawLine(Color(0xFFE8ECE6), Offset(0f, y), Offset(size.width, y), strokeWidth = 1.dp.toPx()) }
                    val slot = size.width / visible.size; val barWidth = (slot * .48f).coerceAtMost(30.dp.toPx())
                    visible.forEachIndexed { idx, point ->
                        val barHeight = height * point.second / maxValue.toFloat(); val left = slot * idx + (slot - barWidth) / 2
                        drawRoundRect(if (idx == visible.lastIndex) GutCareBrandGreen else Color(0xFFB8C9BE), Offset(left, bottom - barHeight), androidx.compose.ui.geometry.Size(barWidth, barHeight.coerceAtLeast(3.dp.toPx())), CornerRadius(8.dp.toPx(), 8.dp.toPx()))
                    }
                    drawLine(Color(0xFFE1E6E1), Offset(0f, bottom), Offset(size.width, bottom), strokeWidth = 1.dp.toPx())
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { visible.forEach { Text(it.first.takeLast(2), style = MaterialTheme.typography.labelSmall, color = com.gutcare.app.ui.theme.GutCareMuted) } }
            }
        }
    }
}

@Composable
private fun TrendStatCard(title: String, value: String, modifier: Modifier, color: Color) {
    Card(modifier, shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = color)) {
        Column(Modifier.padding(14.dp)) { Text(title, style = MaterialTheme.typography.bodySmall, color = com.gutcare.app.ui.theme.GutCareMuted); Text(value, style = MaterialTheme.typography.titleLarge, color = com.gutcare.app.ui.theme.GutCareInk) }
    }
}

@Composable
fun HistoryTimelineScreen(state: RiskTrendUiState, onLoad: () -> Unit, onLoadMore: () -> Unit, onOpenTarget: (String, String) -> Unit) {
    GutCarePage {
        Text("历史记录", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 24.dp, bottom = 16.dp))
        when (val history = state.history) {
            HistoryState.Loading -> FeedbackCard("正在加载历史…", "history_loading")
            HistoryState.Empty -> Column { FeedbackCard("暂无历史记录。", "history_empty"); TextButton(onClick = onLoad) { Text("刷新") } }
            is HistoryState.Error -> Column { FeedbackCard(history.message, "history_error"); TextButton(onClick = onLoad) { Text("重试") } }
            is HistoryState.Ready -> {
                history.items.forEach { item -> HistoryCard(item) { onOpenTarget(item.target.type, item.target.id) } }
                if (history.nextCursor != null) TextButton(onClick = onLoadMore, enabled = !state.historyLoadingMore, modifier = Modifier.fillMaxWidth().testTag("history_load_more")) {
                    Text(if (state.historyLoadingMore) "正在加载…" else "加载更多")
                }
                if (state.historyLoadingMore) FeedbackCard("正在加载下一页…", "history_loading_more")
                state.historyMoreError?.let { FeedbackCard(it, "history_more_error"); TextButton(onClick = onLoadMore) { Text("重试加载") } }
            }
        }
    }
}

@Composable
private fun RiskAlertCard(alert: RiskAlertDto, onClick: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(bottom = 10.dp).clickable(onClick = onClick).testTag("risk_${alert.id}"),
        shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Column(Modifier.padding(18.dp)) {
            riskEnvironmentDisclosure(alert.environment)?.let { disclosure ->
                Text(
                    disclosure,
                    modifier = Modifier.padding(bottom = 8.dp).clip(RoundedCornerShape(10.dp)).background(Color(0xFFFFE7BF)).padding(horizontal = 10.dp, vertical = 7.dp).testTag("risk_environment_disclosure"),
                    color = Color(0xFF7A3E00), style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold,
                )
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(severityLabel(alert.severity), fontWeight = FontWeight.Bold, color = GutCareBrandGreen)
                Text(statusLabel(alert.status), style = MaterialTheme.typography.labelMedium)
            }
            Text(alert.message, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(top = 8.dp))
            Text(formatTime(alert.triggeredAt), style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 8.dp))
        }
    }
}

@Composable
private fun TrendSeriesCard(title: String, items: List<String>, hasData: Boolean) {
    Card(Modifier.fillMaxWidth().padding(bottom = 12.dp), shape = RoundedCornerShape(20.dp)) {
        Column(Modifier.padding(16.dp)) {
            Text(title, fontWeight = FontWeight.SemiBold)
            if (!hasData || items.isEmpty()) Text("暂无数据", style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 8.dp))
            else items.take(8).forEach { Text(it, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 8.dp)) }
        }
    }
}

@Composable
private fun HistoryCard(item: HistoryItemDto, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().padding(bottom = 8.dp).clickable(onClick = onClick).testTag("history_${item.id}"), shape = RoundedCornerShape(18.dp)) {
        Row(Modifier.padding(16.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(historyType(item.type), fontWeight = FontWeight.Medium)
            Text(formatTime(item.occurredAt), style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun FeedbackCard(text: String, tag: String) {
    Card(Modifier.fillMaxWidth().padding(bottom = 12.dp).testTag(tag), shape = RoundedCornerShape(18.dp)) {
        Text(text, modifier = Modifier.padding(16.dp), style = MaterialTheme.typography.bodyMedium)
    }
}

private fun severityLabel(value: String) = when (value) { "emergency" -> "紧急关注"; "seek_care" -> "建议及时就医"; else -> "健康提醒" }
private fun riskEnvironmentDisclosure(value: String): String? = when (value) {
    "production" -> null
    "test_only" -> "演示测试规则（非临床）"
    else -> "规则环境未知，请勿据此判断健康风险"
}
private fun statusLabel(value: String) = when (value) { "unread" -> "未读"; "reevaluated" -> "已重新评估"; else -> "已查看" }
private fun historyType(value: String) = when (value) { "diet" -> "饮食"; "stool" -> "排便"; "symptom" -> "症状"; "mood" -> "心情"; "medication_checkin" -> "用药打卡"; "activity" -> "活动"; "advice" -> "建议"; else -> "健康记录" }
private fun consentLabel(value: String) = when (value) { "health_data_processing" -> "健康数据处理授权"; "mood_data_processing" -> "心情数据处理授权"; else -> "相关授权" }
private fun formatTime(value: String): String = runCatching { OffsetDateTime.parse(value).format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")) }.getOrDefault(value)

/** Integration surface for a parent NavHost; navigation ownership remains with the caller. */
@Composable
fun RiskTrendDestination(
    viewModel: RiskTrendViewModel,
    destination: RiskTrendDestinationKind,
    alertId: String? = null,
    patientTimeZone: String = java.time.ZoneId.systemDefault().id,
    onNavigate: (RiskTrendDestinationKind, String?) -> Unit,
    onOpenHistoryTarget: (String, String) -> Unit = { _, _ -> },
) {
    val state by viewModel.uiState.collectAsState()
    when (destination) {
        RiskTrendDestinationKind.RISKS -> {
            LaunchedEffect(Unit) { viewModel.loadRisks() }
            RiskAlertListScreen(state, viewModel::loadRisks, viewModel::loadMoreRisks) { id -> onNavigate(RiskTrendDestinationKind.RISK_DETAIL, id) }
        }
        RiskTrendDestinationKind.RISK_DETAIL -> RiskAlertDetailScreen(state, alertId.orEmpty(), viewModel::openRisk, viewModel::markRead, viewModel::reevaluate) {
            onNavigate(RiskTrendDestinationKind.RISKS, null)
        }
        RiskTrendDestinationKind.TRENDS -> {
            HealthTrendsScreen(
                state = state,
                onLoad = { val range = trendRange(patientTimeZone, TrendRangeMode.WEEK); viewModel.loadTrends(range.first, range.second) },
                timeZoneId = patientTimeZone,
                onLoadRange = { from, to, bucket -> viewModel.loadTrends(from, to, bucket) },
                onBack = { onNavigate(RiskTrendDestinationKind.TRENDS, null) },
            )
        }
        RiskTrendDestinationKind.HISTORY -> {
            LaunchedEffect(Unit) { viewModel.loadHistory() }
            HistoryTimelineScreen(state, viewModel::loadHistory, viewModel::loadMoreHistory, onOpenHistoryTarget)
        }
    }
}

enum class RiskTrendDestinationKind { RISKS, RISK_DETAIL, TRENDS, HISTORY }
