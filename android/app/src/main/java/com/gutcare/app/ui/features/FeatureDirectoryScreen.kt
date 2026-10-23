package com.gutcare.app.ui.features

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.gutcare.app.ui.design.GutCareBackButton
import com.gutcare.app.ui.design.GutCarePage

/** Secondary feature index reachable from the protected My tab. */
@Composable
fun FeatureDirectoryScreen(
    onBack: () -> Unit,
    onMedication: () -> Unit,
    onRisks: () -> Unit,
    onTrends: () -> Unit,
    onHistory: () -> Unit,
    onPrivacy: () -> Unit,
    onNotifications: () -> Unit,
    onActivity: () -> Unit,
) {
    GutCarePage(
        modifier = Modifier
            .statusBarsPadding()
            .testTag("feature_directory"),
    ) {
        GutCareBackButton(onBack, text = "‹ 返回", testTag = "features_back")
        Text("健康功能", fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(12.dp))
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            FeatureEntry("用药计划与打卡", "管理本人用药计划、日程和打卡。", "features_medication", onMedication)
            FeatureEntry("风险提示", "查看业务服务生成的风险状态。", "features_risks", onRisks)
            FeatureEntry("健康趋势", "查看服务端按本人数据汇总的趋势。", "features_trends", onTrends)
            FeatureEntry("历史记录", "按时间查看本人业务记录。", "features_history", onHistory)
            FeatureEntry("运动记录", "记录活动类型、时长和主观感受。", "features_activity", onActivity)
            FeatureEntry("隐私与授权", "管理数据处理授权、导出与注销。", "features_privacy", onPrivacy)
            FeatureEntry("站内通知", "查看通知并管理普通提醒偏好。", "features_notifications", onNotifications)
        }
    }
}

@Composable
private fun FeatureEntry(title: String, description: String, tag: String, onClick: () -> Unit) {
    androidx.compose.material3.Card(modifier = Modifier.fillMaxWidth().testTag(tag), onClick = onClick) {
        Column(Modifier.fillMaxWidth().height(78.dp).padding(horizontal = 16.dp), verticalArrangement = Arrangement.Center) {
            Text(title, fontWeight = FontWeight.Medium)
            Text(description, style = androidx.compose.material3.MaterialTheme.typography.bodySmall)
        }
    }
}
