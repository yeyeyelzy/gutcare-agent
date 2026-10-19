package com.gutcare.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable

private val GutCareColors = lightColorScheme()

@Composable
fun GutCareTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = GutCareColors,
        content = content,
    )
}
