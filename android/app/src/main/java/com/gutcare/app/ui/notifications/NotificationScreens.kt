package com.gutcare.app.ui.notifications

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.gutcare.app.core.network.PatientNotificationDto
import com.gutcare.app.ui.design.GutCarePage
import com.gutcare.app.ui.theme.GutCareMuted

@Composable
fun NotificationCenterScreen(
    state: NotificationCenterState,
    model: NotificationCenterViewModel,
    onBack: () -> Unit,
    onPreferences: () -> Unit,
    onOpenDetail: (String) -> Unit,
    onOpenTarget: (SafeNotificationTarget) -> Unit,
    modifier: Modifier = Modifier,
) {
    GutCarePage(modifier = modifier.testTag("notification_center")) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = onBack, modifier = Modifier.testTag("notifications_back")) { Text("‹ 返回") }
                Text("站内通知", fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                TextButton(onClick = onPreferences, modifier = Modifier.testTag("notifications_preferences")) { Text("提醒偏好") }
            }
            Text(state.unreadCount?.let { "未读 $it 条" } ?: "未读数量暂不可用", color = GutCareMuted, modifier = Modifier.testTag("notifications_unread_count"))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(state.unreadOnly, { model.setUnreadOnly(it) }, modifier = Modifier.testTag("notifications_unread_filter"))
                Text("只看未读")
                Spacer(Modifier.width(8.dp))
                TextButton(onClick = { model.load() }, modifier = Modifier.testTag("notifications_refresh")) { Text("刷新") }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                NotificationCategoryFilter.entries.forEach { filter ->
                    TextButton(onClick = { model.setCategory(filter) }, modifier = Modifier.testTag("notifications_filter_${filter.name.lowercase()}")) {
                        Text(if (state.category == filter) "• ${filter.label}" else filter.label)
                    }
                }
            }
            state.message?.let { Text(it, color = if (state.error) androidx.compose.material3.MaterialTheme.colorScheme.error else GutCareMuted, modifier = Modifier.testTag("notifications_feedback")) }
            if (state.loading && state.items.isEmpty()) Text("正在加载通知…", modifier = Modifier.testTag("notifications_loading"))
            if (!state.loading && state.items.isEmpty() && !state.error) Text("暂无通知。", color = GutCareMuted, modifier = Modifier.testTag("notifications_empty"))
            state.items.forEach { item ->
                NotificationRow(item, item.id in state.selectedIds, onSelect = { model.toggleSelection(item.id) }, onClick = { onOpenDetail(item.id) })
            }
            if (state.selectedIds.isNotEmpty()) Button(onClick = model::markSelectedRead, enabled = !state.busy, modifier = Modifier.testTag("notifications_mark_selected_read")) { Text("将所选标为已读") }
            if (state.nextCursor != null) TextButton(onClick = { model.load(reset = false) }, enabled = !state.loading, modifier = Modifier.testTag("notifications_load_more")) { Text("加载更多") }
        }
    }
}

@Composable
private fun NotificationRow(item: PatientNotificationDto, selected: Boolean, onSelect: () -> Unit, onClick: () -> Unit) {
    Column(Modifier.fillMaxWidth().clickable(onClick = onClick).testTag("notification_row_${item.id}").padding(vertical = 6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(selected, { onSelect() }, modifier = Modifier.testTag("notification_select_${item.id}"))
            Column(Modifier.weight(1f)) {
                Text(notificationTitle(item), fontWeight = if (item.readAt == null) FontWeight.Bold else FontWeight.Normal)
                Text(if (item.priority == "risk") "风险优先提醒" else "普通提醒", color = GutCareMuted)
                Text(item.occurredAt, color = GutCareMuted, style = androidx.compose.material3.MaterialTheme.typography.bodySmall)
            }
            Text(if (item.readAt == null) "未读" else "已读", color = GutCareMuted)
        }
    }
}

@Composable
fun NotificationDetailScreen(
    state: NotificationCenterState,
    model: NotificationCenterViewModel,
    onBack: () -> Unit,
    onOpenTarget: (SafeNotificationTarget) -> Unit,
    modifier: Modifier = Modifier,
) {
    GutCarePage(modifier = modifier.testTag("notification_detail")) {
        Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            TextButton(onClick = onBack, modifier = Modifier.testTag("notification_detail_back")) { Text("‹ 返回通知") }
            val item = state.detail
            if (item == null) {
                Text(if (state.busy) "正在加载…" else state.message ?: "通知不可用", modifier = Modifier.testTag("notification_detail_state"))
            } else {
                Text(notificationTitle(item), style = androidx.compose.material3.MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                Text(if (item.priority == "risk") "风险提醒始终显示，不受普通提醒偏好影响。" else "普通站内提醒", color = GutCareMuted)
                Text("发生时间：${item.occurredAt}")
                Text(if (item.readAt == null) "尚未查看" else "已查看")
                state.message?.let { Text(it, color = GutCareMuted, modifier = Modifier.testTag("notification_detail_feedback")) }
                if (item.readAt == null) Button(onClick = { model.markRead(item.id) }, enabled = !state.busy, modifier = Modifier.testTag("notification_mark_read")) { Text("标记为已读") }
                val target = safeNotificationTarget(item)
                if (target != null) Button(onClick = { onOpenTarget(target) }, modifier = Modifier.testTag("notification_open_target")) { Text(targetLabel(target)) }
                else Text(if (item.targetUnavailable) "关联内容已不可用。" else "此通知没有可打开的关联内容。", color = GutCareMuted)
            }
        }
    }
}

@Composable
fun NotificationPreferencesScreen(state: NotificationCenterState, model: NotificationCenterViewModel, onBack: () -> Unit, modifier: Modifier = Modifier) {
    GutCarePage(modifier = modifier.testTag("notification_preferences_screen")) {
        Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            TextButton(onClick = onBack, modifier = Modifier.testTag("notification_preferences_back")) { Text("‹ 返回通知") }
            Text("提醒偏好", style = androidx.compose.material3.MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            if (state.preferences == null && state.busy) Text("正在读取偏好…")
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("普通站内提醒", modifier = Modifier.weight(1f))
                Switch(checked = state.ordinaryEnabled, onCheckedChange = { model.editPreferences(enabled = it) }, modifier = Modifier.testTag("notifications_ordinary_toggle"))
            }
            Text("风险通知不会被此开关或静默时段屏蔽。", color = GutCareMuted)
            OutlinedTextField(value = state.quietStart, onValueChange = { model.editPreferences(start = it) }, label = { Text("静默开始（HH:mm，可留空）") }, modifier = Modifier.fillMaxWidth().testTag("notifications_quiet_start"))
            OutlinedTextField(value = state.quietEnd, onValueChange = { model.editPreferences(end = it) }, label = { Text("静默结束（HH:mm，可留空）") }, modifier = Modifier.fillMaxWidth().testTag("notifications_quiet_end"))
            Text("时区：${state.timezone}", color = GutCareMuted)
            state.message?.let { Text(it, color = if (state.error) androidx.compose.material3.MaterialTheme.colorScheme.error else GutCareMuted, modifier = Modifier.testTag("notifications_preferences_feedback")) }
            Button(onClick = model::savePreferences, enabled = !state.busy, modifier = Modifier.testTag("notifications_save_preferences")) { Text("保存偏好") }
        }
    }
}

private fun notificationTitle(item: PatientNotificationDto) = when (item.eventType) {
    "analysis_completed" -> "分析任务状态更新"
    "advice_created" -> "有一条新建议"
    "risk_alert_created" -> "新的风险提示"
    "checkin_reminder" -> "用药打卡提醒"
    else -> "健康服务通知"
}

private fun targetLabel(target: SafeNotificationTarget) = when (target) {
    is SafeNotificationTarget.Risk -> "查看风险提示"
    is SafeNotificationTarget.Medication -> "查看用药打卡"
    is SafeNotificationTarget.Analysis -> "查看分析任务"
    is SafeNotificationTarget.Advice -> "查看建议"
}
