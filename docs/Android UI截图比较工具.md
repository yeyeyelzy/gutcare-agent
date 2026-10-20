# Android UI 截图比较工具

`scripts/android_ui_compare.py` 对 Android Studio 模拟器截图与 `design-reference/android-ui-baseline/manifest.json` 中的静态基线进行确定性比较。运行环境需要 Python 3、Pillow 和 NumPy。工具不会操作设备或判断业务功能正确性。

## 运行

```powershell
python scripts/android_ui_compare.py `
  --manifest design-reference/android-ui-baseline/manifest.json `
  --actual-dir android/build/emulator-evidence/ui-visual-baseline-20261020-round2 `
  --segments design-reference/android-ui-baseline/segments-top.json `
  --profile android/build/emulator-evidence/ui-visual-baseline-20261020-round2/device-profile.json `
  --out android/build/emulator-evidence/ui-visual-compare-tooling-20261020/results
```

输出每页 `overlay.png`、`diff.png`、`heatmap.png`、`result.json` 和总览 `summary.json`。色差采用 sRGB D65 到 CIE Lab 的 ΔE76，`ΔE > 12` 计为差异像素，相似度为 `1 - 差异像素 / 有效像素`，默认目标 0.90。尺寸归一化只按宽度等比缩放基线，再比较显式指定的滚动段与实际视口；不拉伸，不自动平移。当前示例段落从页面顶部开始，长页面只比较当前可见视口，底部裁切像素会记录在结果里，不能据此宣称整页通过。

版本化段落映射位于 `design-reference/android-ui-baseline/segments-top.json`，逐页记录基线页、截图文件、参考图 y 坐标、实际截图 y 坐标和系统栏处理声明。系统状态栏/导航栏必须按设备 profile 与基线内容边界统一；本次既有六图配置标明系统栏保留，但边界尚未独立核实，因此只能作为探索性分数。ROI 结果目前报告完整可见视口；如增加重点区域，应把区域坐标写入该版本化 segment 配置，不能用 mask 排除产品布局、文案、按钮或安全区差异。输出包含输入 SHA-256、算法参数、缩放/裁切、ROI 结果及图片哈希，便于追溯。

可用 `--capture-evidence` 提供逐截图证据 JSON。每个截图记录都必须用该图片的 SHA-256 绑定，并记录捕获前、捕获后观察到的包名和完整 Activity，以及时间戳；两次观察必须都匹配 profile 中预期 Activity。示例结构：

```json
{
  "captures": {
    "page01_today.png": {
      "screenshot_sha256": "该截图文件的 SHA-256",
      "foreground_before": {"package": "com.gutcare.app", "activity": "com.gutcare.app/.VisualBaselineActivity"},
      "foreground_after": {"package": "com.gutcare.app", "activity": "com.gutcare.app/.VisualBaselineActivity"},
      "captured_at": "2026-10-20T12:00:00+08:00"
    }
  }
}
```

缺少记录、哈希不匹配、捕获前后 Activity 不符或缺少时间戳时，该图的 `capture_validation` 会失败关闭。此证据仅说明截图过程中观察到目标 Activity，不会改变视觉比较的范围标签：本工具当前只比较显式滚动段，示例只覆盖页面顶部；状态栏/导航栏与原型内容边界也尚未逐图核实。因此输出始终为 `exploratory_only`，永不将页面标记为最终验收通过。

## 六张既有截图试跑

运行输入使用 `ui-visual-baseline-20261020-round2` 下的六张图及对应 profile。该目录没有逐图捕获证据，因此每页的捕获校验均为 missing，接受状态全部为 `exploratory_only`。其长页面基线高 2693–3522 px，设备截图为 1080×2400；当前仅测顶部视口并对基线底部裁切，不代表完整滚动页面覆盖。现有系统栏保留声明也没有提供基线原图边界验证，因此分数不能用作最终 ≥90% 结论。
