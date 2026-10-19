package com.gutcare.app.ui.tabs

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.gutcare.app.navigation.RootTab
import com.gutcare.app.ui.design.GutCarePage
import com.gutcare.app.ui.design.GutCarePrimaryButton
import com.gutcare.app.ui.theme.GutCareBrandGreen
import com.gutcare.app.ui.theme.GutCareMuted
import com.gutcare.app.ui.theme.GutCareSage

sealed interface TabContentState {
    data object Empty : TabContentState
    data object Loading : TabContentState
    data class Error(val message: String) : TabContentState
    data object Disabled : TabContentState
}

@Composable
fun ProtectedTabShell(
    selectedTab: RootTab,
    onSelectTab: (RootTab) -> Unit,
    onLogout: () -> Unit = {},
    modifier: Modifier = Modifier,
    contentState: TabContentState = TabContentState.Empty,
) {
    Column(modifier = modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        GutCarePage(modifier = Modifier.weight(1f), scrollable = false) {
            Spacer(Modifier.height(34.dp))
            Text("GutCare", style = MaterialTheme.typography.titleMedium, color = GutCareBrandGreen)
            Spacer(Modifier.height(34.dp))
            Text(
                text = selectedTab.title,
                modifier = Modifier.testTag("protected_tab_content_title"),
                style = MaterialTheme.typography.displayLarge,
            )
            Spacer(Modifier.height(10.dp))
            Text(selectedTab.subtitle, style = MaterialTheme.typography.bodyLarge, color = GutCareMuted)
            if (selectedTab == RootTab.Me) {
                Spacer(Modifier.height(18.dp))
                GutCarePrimaryButton(label = "退出登录", onClick = onLogout, testTag = "logout")
            }
            Spacer(Modifier.height(38.dp))
            TabStatePanel(tab = selectedTab, state = contentState)
        }
        NavigationBar(
            modifier = Modifier.navigationBarsPadding().testTag("protected_tab_bar"),
            containerColor = Color.White,
        ) {
            RootTab.entries.forEach { tab ->
                NavigationBarItem(
                    selected = selectedTab == tab,
                    onClick = { onSelectTab(tab) },
                    icon = {
                        Box(
                            modifier = Modifier
                                .size(28.dp)
                                .background(if (selectedTab == tab) GutCareSage else Color.Transparent, CircleShape),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(tab.glyph, style = MaterialTheme.typography.labelLarge)
                        }
                    },
                    label = { Text(tab.title, style = MaterialTheme.typography.bodyMedium) },
                    modifier = Modifier
                        .semantics { contentDescription = "切换到${tab.title}" }
                        .testTag("tab_${tab.name.lowercase()}"),
                )
            }
        }
    }
}

@Composable
private fun TabStatePanel(tab: RootTab, state: TabContentState) {
    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Box(
            modifier = Modifier
                .size(64.dp)
                .background(GutCareSage, CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Text(tab.glyph, style = MaterialTheme.typography.headlineMedium, color = GutCareBrandGreen)
        }
        Spacer(Modifier.height(18.dp))
        when (state) {
            TabContentState.Empty -> {
                Text("暂时没有可展示的内容", style = MaterialTheme.typography.titleMedium)
                Text(
                    "连接业务服务后，这里只会显示你的本人数据。",
                    modifier = Modifier.padding(top = 6.dp),
                    style = MaterialTheme.typography.bodyMedium,
                    color = GutCareMuted,
                    textAlign = TextAlign.Center,
                )
            }
            TabContentState.Loading -> {
                Text("正在加载", style = MaterialTheme.typography.titleMedium)
                Text("请稍候。", style = MaterialTheme.typography.bodyMedium, color = GutCareMuted)
            }
            is TabContentState.Error -> {
                Text("暂时无法加载", style = MaterialTheme.typography.titleMedium)
                Text(state.message, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.error)
                Spacer(Modifier.height(16.dp))
                GutCarePrimaryButton(label = "重试", onClick = {}, enabled = false)
            }
            TabContentState.Disabled -> {
                Text("此功能暂不可用", style = MaterialTheme.typography.titleMedium)
                Text("请稍后再试。", style = MaterialTheme.typography.bodyMedium, color = GutCareMuted)
            }
        }
    }
}

