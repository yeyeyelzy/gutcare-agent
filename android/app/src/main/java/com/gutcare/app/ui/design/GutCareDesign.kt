package com.gutcare.app.ui.design

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.toggleableState
import androidx.compose.ui.state.ToggleableState
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.gutcare.app.ui.theme.GutCareBrandGreen
import com.gutcare.app.ui.theme.GutCareCanvas
import com.gutcare.app.ui.theme.GutCareDeepGreen
import com.gutcare.app.ui.theme.GutCareLine
import com.gutcare.app.ui.theme.GutCareMuted
import com.gutcare.app.ui.theme.GutCareOrange
import com.gutcare.app.ui.theme.GutCareOrangeSoft
import com.gutcare.app.ui.theme.GutCarePurple
import com.gutcare.app.ui.theme.GutCarePurpleSoft
import com.gutcare.app.ui.theme.GutCareSage

/** Design tokens distilled from the 430dp visual baseline. */
object GutCareDimensions {
    val pageMaxWidth = 430.dp
    val pageGutter = 24.dp
    val controlHeight = 56.dp
    val touchTarget = 44.dp
    val cardRadius = 22.dp
    val controlRadius = 18.dp
    val pillRadius = 30.dp
}

@Composable
fun GutCarePage(
    modifier: Modifier = Modifier,
    scrollable: Boolean = true,
    content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit,
) {
    Box(
        modifier = modifier
            .fillMaxSize()
            .background(GutCareCanvas),
        contentAlignment = Alignment.TopCenter,
    ) {
        val pageModifier = Modifier
            .fillMaxWidth()
            .widthIn(max = GutCareDimensions.pageMaxWidth)
            .imePadding()
            .navigationBarsPadding()
            .padding(horizontal = GutCareDimensions.pageGutter)
        Column(
            modifier = if (scrollable) pageModifier.verticalScroll(rememberScrollState()) else pageModifier,
            content = content,
        )
    }
}

@Composable
fun GutCareBrand(modifier: Modifier = Modifier, center: Boolean = false) {
    Row(
        modifier = modifier,
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = if (center) Arrangement.Center else Arrangement.Start,
    ) {
        GutCareLeafMark(modifier = Modifier.size(34.dp))
        Text(
            text = "GutCare",
            modifier = Modifier.padding(start = 8.dp),
            style = MaterialTheme.typography.headlineMedium,
            color = GutCareInkColor,
        )
    }
}

@Composable
fun GutCareLeafMark(modifier: Modifier = Modifier) {
    Canvas(
        modifier = modifier.semantics { contentDescription = "GutCare 标志" },
    ) {
        val leaf = Path().apply {
            moveTo(size.width * .14f, size.height * .63f)
            cubicTo(size.width * .24f, size.height * .20f, size.width * .58f, size.height * .09f, size.width * .89f, size.height * .12f)
            cubicTo(size.width * .84f, size.height * .49f, size.width * .61f, size.height * .75f, size.width * .22f, size.height * .81f)
        }
        drawPath(leaf, GutCareBrandGreen, style = Stroke(width = size.minDimension * .1f, cap = StrokeCap.Round, join = StrokeJoin.Round))
        drawLine(
            color = GutCareBrandGreen,
            start = Offset(size.width * .05f, size.height * .91f),
            end = Offset(size.width * .72f, size.height * .31f),
            strokeWidth = size.minDimension * .1f,
            cap = StrokeCap.Round,
        )
    }
}

@Composable
fun GutCarePrimaryButton(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    loading: Boolean = false,
    showTrailingArrow: Boolean = false,
    testTag: String? = null,
) {
    Button(
        onClick = onClick,
        enabled = enabled && !loading,
        modifier = modifier
            .fillMaxWidth()
            .heightIn(min = GutCareDimensions.controlHeight)
            .then(if (testTag != null) Modifier.testTag(testTag) else Modifier)
            .semantics { contentDescription = label },
        shape = RoundedCornerShape(GutCareDimensions.controlRadius),
        colors = ButtonDefaults.buttonColors(
            containerColor = GutCareBrandGreen,
            disabledContainerColor = GutCareSage,
            disabledContentColor = GutCareMuted,
        ),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = if (loading) "处理中…" else label,
                style = MaterialTheme.typography.labelLarge,
            )
            if (showTrailingArrow && !loading) {
                Spacer(Modifier.size(8.dp))
                Text(
                    text = "›",
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Normal,
                )
            }
        }
    }
}

@Composable
fun GutCareSecondaryButton(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier
            .fillMaxWidth()
            .heightIn(min = GutCareDimensions.controlHeight)
            .semantics { contentDescription = label },
        shape = RoundedCornerShape(GutCareDimensions.controlRadius),
        colors = ButtonDefaults.buttonColors(
            containerColor = GutCareSage,
            contentColor = GutCareBrandGreen,
            disabledContainerColor = GutCareSage,
            disabledContentColor = GutCareMuted,
        ),
    ) {
        Text(text = label, style = MaterialTheme.typography.labelLarge)
    }
}

@Composable
fun GutCareTextField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    supportingText: String? = null,
    isError: Boolean = false,
    enabled: Boolean = true,
    password: Boolean = false,
    passwordVisible: Boolean = false,
    onPasswordVisibilityChange: (() -> Unit)? = null,
    testTag: String? = null,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = modifier
            .fillMaxWidth()
            .defaultMinSize(minHeight = GutCareDimensions.controlHeight)
            .then(if (testTag != null) Modifier.testTag(testTag) else Modifier)
            .semantics { contentDescription = label },
        label = { Text(label) },
        singleLine = true,
        enabled = enabled,
        isError = isError,
        visualTransformation = if (password && !passwordVisible) PasswordVisualTransformation() else VisualTransformation.None,
        trailingIcon = if (password && onPasswordVisibilityChange != null) {
            {
                TextButton(
                    onClick = onPasswordVisibilityChange,
                    modifier = Modifier
                        .sizeIn(minWidth = GutCareDimensions.touchTarget, minHeight = GutCareDimensions.touchTarget)
                        .semantics { contentDescription = if (passwordVisible) "隐藏密码" else "显示密码" },
                ) {
                    Text(if (passwordVisible) "隐藏" else "显示", style = MaterialTheme.typography.bodyMedium)
                }
            }
        } else {
            null
        },
        supportingText = supportingText?.let { { Text(it) } },
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = GutCareBrandGreen,
            unfocusedBorderColor = GutCareLine,
            disabledBorderColor = GutCareLine,
            focusedLabelColor = GutCareBrandGreen,
            unfocusedLabelColor = GutCareMuted,
        ),
        shape = RoundedCornerShape(GutCareDimensions.controlRadius),
    )
}

@Composable
fun GutCareConsentRow(
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    description: String,
    modifier: Modifier = Modifier,
    testTag: String? = null,
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .heightIn(min = GutCareDimensions.touchTarget)
            .clickable(role = Role.Checkbox) { onCheckedChange(!checked) }
            .semantics {
                contentDescription = description
                role = Role.Checkbox
                toggleableState = if (checked) ToggleableState.On else ToggleableState.Off
                stateDescription = if (checked) "已同意" else "未同意"
            }
            .then(if (testTag != null) Modifier.testTag(testTag) else Modifier),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Checkbox(
            checked = checked,
            onCheckedChange = null,
            modifier = Modifier.clearAndSetSemantics {},
            colors = CheckboxDefaults.colors(checkedColor = GutCareBrandGreen),
        )
        Text(
            text = description,
            modifier = Modifier.padding(start = 8.dp),
            style = MaterialTheme.typography.bodyMedium,
            color = GutCareInkColor,
        )
    }
}

@Composable
fun GutCareCard(
    modifier: Modifier = Modifier,
    padding: Dp = 20.dp,
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
fun FeatureRow(
    tint: Color,
    glyph: FeatureGlyph,
    title: String,
    detail: String,
) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier
                .size(46.dp)
                .background(tint, RoundedCornerShape(15.dp)),
            contentAlignment = Alignment.Center,
        ) {
            FeatureIcon(glyph = glyph, modifier = Modifier.size(27.dp))
        }
        Column(modifier = Modifier.padding(start = 16.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, color = GutCareInkColor)
            Text(
                detail,
                modifier = Modifier.padding(top = 3.dp),
                style = MaterialTheme.typography.bodyMedium,
                color = GutCareMuted,
            )
        }
    }
}

enum class FeatureGlyph { Archive, Note, Trend, Calendar }

@Composable
fun FeatureIcon(glyph: FeatureGlyph, modifier: Modifier = Modifier) {
    Canvas(modifier = modifier.semantics { contentDescription = glyph.name }) {
        val color = when (glyph) {
            FeatureGlyph.Archive, FeatureGlyph.Calendar -> GutCareBrandGreen
            FeatureGlyph.Note -> GutCareOrange
            FeatureGlyph.Trend -> GutCarePurple
        }
        when (glyph) {
            FeatureGlyph.Archive -> drawArchive(color)
            FeatureGlyph.Note -> drawNote(color)
            FeatureGlyph.Trend -> drawTrend(color)
            FeatureGlyph.Calendar -> drawCalendar(color)
        }
    }
}

@Composable
fun WelcomeChecklistIllustration(modifier: Modifier = Modifier) {
    Canvas(
        modifier = modifier.semantics { contentDescription = "日常记录插图" },
    ) {
        drawCircle(color = Color(0xFFDDE8DE), radius = size.minDimension * .43f, center = Offset(size.width * .53f, size.height * .49f))
        drawCircle(color = Color(0xFFE7EEE7), radius = size.minDimension * .33f, center = Offset(size.width * .76f, size.height * .54f))
        drawLeafCluster()
        rotate(degrees = 8f, pivot = Offset(size.width * .5f, size.height * .51f)) {
            val sheet = Rect(size.width * .28f, size.height * .18f, size.width * .70f, size.height * .84f)
            drawRoundRect(
                color = Color(0xFFFFFEFA),
                topLeft = sheet.topLeft,
                size = sheet.size,
                cornerRadius = androidx.compose.ui.geometry.CornerRadius(size.width * .045f),
                style = Stroke(width = size.minDimension * .025f),
            )
            repeat(3) { index ->
                val y = size.height * (.37f + index * .15f)
                drawLine(GutCareBrandGreen, Offset(size.width * .37f, y), Offset(size.width * .40f, y + size.height * .03f), strokeWidth = size.minDimension * .018f, cap = StrokeCap.Round)
                drawLine(GutCareBrandGreen, Offset(size.width * .40f, y + size.height * .03f), Offset(size.width * .45f, y - size.height * .035f), strokeWidth = size.minDimension * .018f, cap = StrokeCap.Round)
                drawLine(Color(0xFFB8C8BC), Offset(size.width * .50f, y), Offset(size.width * .63f, y), strokeWidth = size.minDimension * .025f, cap = StrokeCap.Round)
            }
        }
        drawWelcomePerson()
        drawCircle(GutCareOrange, radius = size.minDimension * .035f, center = Offset(size.width * .22f, size.height * .23f))
        drawCircle(Color(0xFFF4D88D), radius = size.minDimension * .082f, center = Offset(size.width * .82f, size.height * .19f))
        drawLine(Color(0xFF9FB4A4), Offset(size.width * .06f, size.height * .91f), Offset(size.width * .94f, size.height * .91f), strokeWidth = size.minDimension * .01f)
    }
}

/** Code-drawn companion: no non-production raster reference is shipped in the APK. */
private fun DrawScope.drawWelcomePerson() {
    val skin = Color(0xFFF0AC81)
    val shirt = Color(0xFFE28560)
    val hair = Color(0xFF214B3E)
    val trousers = Color(0xFF77689F)
    val unit = size.minDimension

    drawCircle(skin, radius = unit * .062f, center = Offset(size.width * .73f, size.height * .45f))
    drawOval(
        hair,
        topLeft = Offset(size.width * .675f, size.height * .365f),
        size = androidx.compose.ui.geometry.Size(size.width * .12f, size.height * .11f),
    )
    drawPath(Path().apply {
        moveTo(size.width * .675f, size.height * .54f)
        lineTo(size.width * .775f, size.height * .54f)
        lineTo(size.width * .79f, size.height * .73f)
        lineTo(size.width * .665f, size.height * .73f)
        close()
    }, shirt)
    drawLine(
        skin,
        Offset(size.width * .68f, size.height * .58f),
        Offset(size.width * .59f, size.height * .69f),
        strokeWidth = unit * .05f,
        cap = StrokeCap.Round,
    )
    drawLine(
        skin,
        Offset(size.width * .77f, size.height * .58f),
        Offset(size.width * .85f, size.height * .52f),
        strokeWidth = unit * .05f,
        cap = StrokeCap.Round,
    )
    drawPath(Path().apply {
        moveTo(size.width * .68f, size.height * .72f)
        lineTo(size.width * .73f, size.height * .72f)
        lineTo(size.width * .70f, size.height * .89f)
        lineTo(size.width * .64f, size.height * .89f)
        close()
    }, trousers)
    drawPath(Path().apply {
        moveTo(size.width * .73f, size.height * .72f)
        lineTo(size.width * .78f, size.height * .72f)
        lineTo(size.width * .84f, size.height * .89f)
        lineTo(size.width * .78f, size.height * .89f)
        close()
    }, trousers)
}

private fun DrawScope.drawLeafCluster() {
    val stem = GutCareBrandGreen
    drawLine(stem, Offset(size.width * .20f, size.height * .89f), Offset(size.width * .17f, size.height * .40f), strokeWidth = size.minDimension * .02f, cap = StrokeCap.Round)
    drawOval(Color(0xFF86A78F), topLeft = Offset(size.width * .04f, size.height * .52f), size = androidx.compose.ui.geometry.Size(size.width * .20f, size.height * .20f))
    drawOval(Color(0xFF86A78F), topLeft = Offset(size.width * .19f, size.height * .42f), size = androidx.compose.ui.geometry.Size(size.width * .20f, size.height * .15f))
    drawLine(stem, Offset(size.width * .75f, size.height * .90f), Offset(size.width * .82f, size.height * .50f), strokeWidth = size.minDimension * .02f, cap = StrokeCap.Round)
    drawOval(Color(0xFF285F4C), topLeft = Offset(size.width * .75f, size.height * .61f), size = androidx.compose.ui.geometry.Size(size.width * .12f, size.height * .24f))
}

private fun DrawScope.drawArchive(color: Color) {
    drawPath(Path().apply {
        moveTo(size.width * .14f, size.height * .22f)
        lineTo(size.width * .45f, size.height * .22f)
        lineTo(size.width * .57f, size.height * .36f)
        lineTo(size.width * .86f, size.height * .36f)
        lineTo(size.width * .86f, size.height * .80f)
        lineTo(size.width * .14f, size.height * .80f)
        close()
    }, color, style = Stroke(width = size.minDimension * .09f, join = StrokeJoin.Round))
}

private fun DrawScope.drawNote(color: Color) {
    drawRoundRect(color, topLeft = Offset(size.width * .22f, size.height * .12f), size = androidx.compose.ui.geometry.Size(size.width * .56f, size.height * .76f), cornerRadius = androidx.compose.ui.geometry.CornerRadius(size.minDimension * .13f), style = Stroke(width = size.minDimension * .09f))
    repeat(3) { index ->
        val y = size.height * (.35f + index * .16f)
        drawLine(color, Offset(size.width * .36f, y), Offset(size.width * .66f, y), strokeWidth = size.minDimension * .07f, cap = StrokeCap.Round)
    }
}

private fun DrawScope.drawTrend(color: Color) {
    drawLine(color, Offset(size.width * .18f, size.height * .14f), Offset(size.width * .18f, size.height * .83f), strokeWidth = size.minDimension * .08f, cap = StrokeCap.Round)
    drawLine(color, Offset(size.width * .18f, size.height * .83f), Offset(size.width * .86f, size.height * .83f), strokeWidth = size.minDimension * .08f, cap = StrokeCap.Round)
    val path = Path().apply {
        moveTo(size.width * .30f, size.height * .64f)
        lineTo(size.width * .50f, size.height * .48f)
        lineTo(size.width * .64f, size.height * .58f)
        lineTo(size.width * .84f, size.height * .29f)
    }
    drawPath(path, color, style = Stroke(width = size.minDimension * .08f, cap = StrokeCap.Round, join = StrokeJoin.Round))
}

private fun DrawScope.drawCalendar(color: Color) {
    drawRoundRect(color, topLeft = Offset(size.width * .17f, size.height * .22f), size = androidx.compose.ui.geometry.Size(size.width * .66f, size.height * .60f), cornerRadius = androidx.compose.ui.geometry.CornerRadius(size.minDimension * .12f), style = Stroke(width = size.minDimension * .08f))
    drawLine(color, Offset(size.width * .17f, size.height * .40f), Offset(size.width * .83f, size.height * .40f), strokeWidth = size.minDimension * .08f)
    drawLine(color, Offset(size.width * .36f, size.height * .13f), Offset(size.width * .36f, size.height * .32f), strokeWidth = size.minDimension * .08f, cap = StrokeCap.Round)
    drawLine(color, Offset(size.width * .64f, size.height * .13f), Offset(size.width * .64f, size.height * .32f), strokeWidth = size.minDimension * .08f, cap = StrokeCap.Round)
}

val GutCareInkColor: Color
    @Composable get() = MaterialTheme.colorScheme.onBackground

@Composable
fun ScreenStatus(text: String, modifier: Modifier = Modifier) {
    Text(
        text = text,
        modifier = modifier.fillMaxWidth(),
        style = MaterialTheme.typography.bodyMedium,
        textAlign = TextAlign.Center,
        color = GutCareMuted,
    )
}

