package com.gutcare.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/**
 * The colour and type foundation is deliberately local to the UI layer.  It is derived from the
 * frozen 430dp prototype tokens, not from any of the non-production reference images.
 */
val GutCareBrandGreen = Color(0xFF285F4C)
val GutCareDeepGreen = Color(0xFF214B3E)
val GutCareCanvas = Color(0xFFF7F8F5)
val GutCareInk = Color(0xFF24382F)
val GutCareMuted = Color(0xFF747F78)
val GutCareLine = Color(0xFFE8ECE6)
val GutCareSage = Color(0xFFE9EFEA)
val GutCareOrange = Color(0xFFE28560)
val GutCareOrangeSoft = Color(0xFFF9E4D9)
val GutCarePurple = Color(0xFF77689F)
val GutCarePurpleSoft = Color(0xFFEAE5F3)
val GutCareDanger = Color(0xFFBB4C4A)

private val GutCareColors = lightColorScheme(
    primary = GutCareBrandGreen,
    onPrimary = Color.White,
    primaryContainer = GutCareSage,
    onPrimaryContainer = GutCareDeepGreen,
    secondary = GutCarePurple,
    background = GutCareCanvas,
    onBackground = GutCareInk,
    surface = Color.White,
    onSurface = GutCareInk,
    surfaceVariant = GutCareSage,
    onSurfaceVariant = GutCareMuted,
    outline = GutCareLine,
    error = GutCareDanger,
    onError = Color.White,
)

private val GutCareTypography = Typography(
    displayLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.ExtraBold,
        fontSize = 42.sp,
        lineHeight = 50.sp,
    ),
    headlineLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.ExtraBold,
        fontSize = 32.sp,
        lineHeight = 40.sp,
    ),
    headlineMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 26.sp,
        lineHeight = 34.sp,
    ),
    titleLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 22.sp,
        lineHeight = 29.sp,
    ),
    titleMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 18.sp,
        lineHeight = 25.sp,
    ),
    bodyLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 17.sp,
        lineHeight = 26.sp,
    ),
    bodyMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 15.sp,
        lineHeight = 22.sp,
    ),
    labelLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 17.sp,
        lineHeight = 22.sp,
    ),
)

@Composable
fun GutCareTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = GutCareColors,
        typography = GutCareTypography,
        content = content,
    )
}
