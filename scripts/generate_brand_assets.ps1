$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Drawing

$staticDirectory = Join-Path (Split-Path $PSScriptRoot -Parent) "static"
$pixelFormat = [System.Drawing.Imaging.PixelFormat]::Format32bppArgb
$pngFormat = [System.Drawing.Imaging.ImageFormat]::Png

function New-RoundedRectanglePath {
    param(
        [float]$X,
        [float]$Y,
        [float]$Width,
        [float]$Height,
        [float]$Radius
    )

    $diameter = $Radius * 2
    $path = [System.Drawing.Drawing2D.GraphicsPath]::new()
    $path.AddArc($X, $Y, $diameter, $diameter, 180, 90)
    $path.AddArc($X + $Width - $diameter, $Y, $diameter, $diameter, 270, 90)
    $path.AddArc($X + $Width - $diameter, $Y + $Height - $diameter, $diameter, $diameter, 0, 90)
    $path.AddArc($X, $Y + $Height - $diameter, $diameter, $diameter, 90, 90)
    $path.CloseFigure()
    return $path
}

function New-BrandIcon {
    param(
        [int]$Size,
        [string]$OutputPath
    )

    $bitmap = [System.Drawing.Bitmap]::new($Size, $Size, $pixelFormat)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    try {
        $graphics.Clear([System.Drawing.Color]::FromArgb(255, 8, 11, 24))
        $padding = [float]($Size * 0.055)
        $path = New-RoundedRectanglePath $padding $padding ($Size - 2 * $padding) ($Size - 2 * $padding) ($Size * 0.24)
        $gradient = [System.Drawing.Drawing2D.LinearGradientBrush]::new(
            [System.Drawing.PointF]::new(0, 0),
            [System.Drawing.PointF]::new($Size, $Size),
            [System.Drawing.Color]::FromArgb(255, 145, 233, 220),
            [System.Drawing.Color]::FromArgb(255, 185, 167, 255)
        )
        $graphics.FillPath($gradient, $path)

        $innerPadding = [float]($Size * 0.11)
        $innerPath = New-RoundedRectanglePath $innerPadding $innerPadding ($Size - 2 * $innerPadding) ($Size - 2 * $innerPadding) ($Size * 0.19)
        $innerBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255, 13, 18, 36))
        $graphics.FillPath($innerBrush, $innerPath)

        $glyphPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(255, 247, 245, 242), $Size * 0.105)
        $glyphPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $glyphPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $glyphPen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
        $graphics.DrawLine($glyphPen, $Size * 0.31, $Size * 0.25, $Size * 0.31, $Size * 0.75)
        $graphics.DrawLine($glyphPen, $Size * 0.33, $Size * 0.52, $Size * 0.69, $Size * 0.77)

        $penPath = [System.Drawing.Drawing2D.GraphicsPath]::new()
        $penPath.AddPolygon(@(
            [System.Drawing.PointF]::new($Size * 0.31, $Size * 0.57),
            [System.Drawing.PointF]::new($Size * 0.44, $Size * 0.38),
            [System.Drawing.PointF]::new($Size * 0.70, $Size * 0.12),
            [System.Drawing.PointF]::new($Size * 0.84, $Size * 0.26),
            [System.Drawing.PointF]::new($Size * 0.58, $Size * 0.52),
            [System.Drawing.PointF]::new($Size * 0.37, $Size * 0.64)
        ))
        $penGradient = [System.Drawing.Drawing2D.LinearGradientBrush]::new(
            [System.Drawing.PointF]::new($Size * 0.3, $Size * 0.6),
            [System.Drawing.PointF]::new($Size * 0.85, $Size * 0.1),
            [System.Drawing.Color]::FromArgb(255, 145, 233, 220),
            [System.Drawing.Color]::FromArgb(255, 185, 167, 255)
        )
        $penOutline = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(255, 13, 18, 36), $Size * 0.025)
        $penOutline.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
        $graphics.FillPath($penGradient, $penPath)
        $graphics.DrawPath($penOutline, $penPath)
        $capPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(255, 13, 18, 36), $Size * 0.035)
        $capPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $capPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $graphics.DrawLine($capPen, $Size * 0.70, $Size * 0.17, $Size * 0.79, $Size * 0.26)
        $bitmap.Save($OutputPath, $pngFormat)
    }
    finally {
        if ($capPen) { $capPen.Dispose() }
        if ($penOutline) { $penOutline.Dispose() }
        if ($penGradient) { $penGradient.Dispose() }
        if ($penPath) { $penPath.Dispose() }
        if ($glyphPen) { $glyphPen.Dispose() }
        if ($innerBrush) { $innerBrush.Dispose() }
        if ($innerPath) { $innerPath.Dispose() }
        if ($gradient) { $gradient.Dispose() }
        if ($path) { $path.Dispose() }
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

function New-SocialCard {
    param([string]$OutputPath)

    $width = 1200
    $height = 630
    $bitmap = [System.Drawing.Bitmap]::new($width, $height, $pixelFormat)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    try {
        $background = [System.Drawing.Drawing2D.LinearGradientBrush]::new(
            [System.Drawing.PointF]::new(0, 0),
            [System.Drawing.PointF]::new($width, $height),
            [System.Drawing.Color]::FromArgb(255, 7, 10, 23),
            [System.Drawing.Color]::FromArgb(255, 21, 19, 48)
        )
        $graphics.FillRectangle($background, 0, 0, $width, $height)

        $gridPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(18, 255, 255, 255), 1)
        for ($x = 0; $x -le $width; $x += 60) { $graphics.DrawLine($gridPen, $x, 0, $x, $height) }
        for ($y = 0; $y -le $height; $y += 60) { $graphics.DrawLine($gridPen, 0, $y, $width, $y) }

        $aura = [System.Drawing.Drawing2D.GraphicsPath]::new()
        $aura.AddEllipse(760, 40, 500, 500)
        $auraBrush = [System.Drawing.Drawing2D.PathGradientBrush]::new($aura)
        $auraBrush.CenterColor = [System.Drawing.Color]::FromArgb(90, 143, 168, 255)
        $auraBrush.SurroundColors = @([System.Drawing.Color]::FromArgb(0, 143, 168, 255))
        $graphics.FillPath($auraBrush, $aura)

        $markPath = New-RoundedRectanglePath 850 130 230 230 58
        $markGradient = [System.Drawing.Drawing2D.LinearGradientBrush]::new(
            [System.Drawing.PointF]::new(850, 130),
            [System.Drawing.PointF]::new(1080, 360),
            [System.Drawing.Color]::FromArgb(255, 143, 168, 255),
            [System.Drawing.Color]::FromArgb(255, 157, 118, 220)
        )
        $graphics.FillPath($markGradient, $markPath)

        $markFont = [System.Drawing.Font]::new("Arial", 132, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
        $markFormat = [System.Drawing.StringFormat]::new()
        $markFormat.Alignment = [System.Drawing.StringAlignment]::Center
        $markFormat.LineAlignment = [System.Drawing.StringAlignment]::Center
        $graphics.DrawString("K", $markFont, [System.Drawing.Brushes]::White, [System.Drawing.RectangleF]::new(850, 122, 230, 230), $markFormat)

        $labelFont = [System.Drawing.Font]::new("Consolas", 21, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
        $titleFont = [System.Drawing.Font]::new("Yu Gothic UI", 64, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
        $bodyFont = [System.Drawing.Font]::new("Yu Gothic UI", 25, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
        $brandFont = [System.Drawing.Font]::new("Arial", 28, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
        $mutedBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255, 145, 233, 220))
        $bodyBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255, 190, 197, 215))
        $graphics.DrawString("FONT INFRASTRUCTURE / V2", $labelFont, $mutedBrush, 72, 72)
        $headline = [System.Text.Encoding]::UTF8.GetString(
            [System.Convert]::FromBase64String("5b+F6KaB44Gq5paH5a2X44KS44CBCuW/heimgeOBquOBtuOCk+OBoOOBkeOAgg==")
        )
        $graphics.DrawString($headline, $titleFont, [System.Drawing.Brushes]::White, 66, 145)
        $graphics.DrawString("Deterministic, self-hosted WOFF2 subsets", $bodyFont, $bodyBrush, 72, 346)
        $graphics.DrawString("Klyph", $brandFont, [System.Drawing.Brushes]::White, 72, 520)

        $accentPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(255, 145, 233, 220), 4)
        $graphics.DrawLine($accentPen, 72, 492, 290, 492)
        $bitmap.Save($OutputPath, $pngFormat)
    }
    finally {
        foreach ($resource in @($accentPen, $bodyBrush, $mutedBrush, $brandFont, $bodyFont, $titleFont, $labelFont, $markFormat, $markFont, $markGradient, $markPath, $auraBrush, $aura, $gridPen, $background)) {
            if ($resource) { $resource.Dispose() }
        }
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

New-SocialCard (Join-Path $staticDirectory "og-image.png")
New-BrandIcon 192 (Join-Path $staticDirectory "icon-192.png")
New-BrandIcon 512 (Join-Path $staticDirectory "icon-512.png")
New-BrandIcon 180 (Join-Path $staticDirectory "apple-touch-icon.png")
