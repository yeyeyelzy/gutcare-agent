package com.gutcare.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.navigation.compose.rememberNavController
import com.gutcare.app.core.network.AndroidAuthComposition
import com.gutcare.app.core.network.AuthWorkflowResult
import com.gutcare.app.navigation.AppSessionState
import com.gutcare.app.navigation.GutCareNavHost
import com.gutcare.app.ui.theme.GutCareTheme

class MainActivity : ComponentActivity() {
    private val auth by lazy { AndroidAuthComposition(applicationContext) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            GutCareTheme {
                Surface(
                    modifier = Modifier,
                    color = MaterialTheme.colorScheme.background,
                ) {
                    val scope = rememberCoroutineScope()
                    var bootstrapped by remember { mutableStateOf(false) }
                    var sessionState by remember { mutableStateOf<AppSessionState>(AppSessionState.Public) }
                    var startupError by remember { mutableStateOf<String?>(null) }
                    val navController = rememberNavController()
                    val workflow = remember(scope) {
                        auth.workflow(
                            scope,
                            {
                                sessionState = AppSessionState.Authenticated
                                startupError = null
                            },
                            {
                                sessionState = AppSessionState.Public
                                startupError = null
                            },
                        )
                    }
                    LaunchedEffect(Unit) {
                        val restored = runCatching { auth.restore() }
                            .getOrElse { AuthWorkflowResult.Failure(null, "NETWORK_ERROR") }
                        sessionState = when (restored) {
                            is AuthWorkflowResult.Success -> AppSessionState.Authenticated
                            else -> AppSessionState.Public
                        }
                        if (restored is AuthWorkflowResult.Failure && restored.code != "SESSION_UNAVAILABLE") {
                            startupError = listOfNotNull(
                                "会话恢复失败，请重新登录或联系支持。",
                                restored.code,
                                restored.requestId?.let { "request_id: $it" },
                            ).joinToString(" · ")
                        }
                        bootstrapped = true
                    }
                    if (bootstrapped) {
                        Box(Modifier.fillMaxSize()) {
                            GutCareNavHost(
                                navController = navController,
                                sessionState = sessionState,
                                authWorkflow = workflow,
                                onLogout = { onResult -> workflow.logout(onResult) },
                                registrationNoticeSummaries = auth.notices.summaries(),
                            )
                            startupError?.let {
                                Text(
                                    text = it,
                                    modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(16.dp),
                                    color = MaterialTheme.colorScheme.error,
                                    style = MaterialTheme.typography.bodyMedium,
                                )
                            }
                        }
                    } else {
                        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                    }
                }
            }
        }
    }
}
