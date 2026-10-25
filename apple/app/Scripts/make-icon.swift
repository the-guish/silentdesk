// Draws SilentDesk's icon and saves it as an .icns: a tray on a blue
// rounded square, the shape macOS gives app icons.
//
//   swift Scripts/make-icon.swift OUTPUT.icns

import AppKit

let output = URL(fileURLWithPath: CommandLine.arguments.dropFirst().first ?? "AppIcon.icns")
let iconset = FileManager.default.temporaryDirectory.appendingPathComponent("SilentDesk-\(UUID().uuidString).iconset")
try FileManager.default.createDirectory(at: iconset, withIntermediateDirectories: true)

func draw(_ pixels: Int) -> Data {
    let size = CGFloat(pixels)
    let bitmap = NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels, bitsPerSample: 8, samplesPerPixel: 4,
        hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)

    // Apple's grid: an 824-point square on a 1024-point canvas.
    let inset = size * 100 / 1024
    let square = NSRect(x: inset, y: inset, width: size - 2 * inset, height: size - 2 * inset)
    let shape = NSBezierPath(roundedRect: square, xRadius: square.width * 0.225, yRadius: square.width * 0.225)
    let shadow = NSShadow()
    shadow.shadowColor = NSColor.black.withAlphaComponent(0.3)
    shadow.shadowOffset = NSSize(width: 0, height: -size * 0.01)
    shadow.shadowBlurRadius = size * 0.02
    NSGraphicsContext.saveGraphicsState()
    shadow.set()
    NSColor.black.setFill()
    shape.fill()
    NSGraphicsContext.restoreGraphicsState()
    NSGradient(
        starting: NSColor(calibratedRed: 0.35, green: 0.55, blue: 1.0, alpha: 1),
        ending: NSColor(calibratedRed: 0.22, green: 0.27, blue: 0.85, alpha: 1))!
        .draw(in: shape, angle: -90)

    let configuration = NSImage.SymbolConfiguration(pointSize: size * 0.42, weight: .medium)
        .applying(.init(paletteColors: [.white]))
    if let symbol = NSImage(systemSymbolName: "tray.full.fill", accessibilityDescription: nil)?
        .withSymbolConfiguration(configuration)
    {
        let box = symbol.size
        symbol.draw(in: NSRect(x: (size - box.width) / 2, y: (size - box.height) / 2, width: box.width, height: box.height))
    }

    NSGraphicsContext.restoreGraphicsState()
    return bitmap.representation(using: .png, properties: [:])!
}

for points in [16, 32, 128, 256, 512] {
    try draw(points).write(to: iconset.appendingPathComponent("icon_\(points)x\(points).png"))
    try draw(points * 2).write(to: iconset.appendingPathComponent("icon_\(points)x\(points)@2x.png"))
}

let iconutil = Process()
iconutil.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
iconutil.arguments = ["-c", "icns", iconset.path, "-o", output.path]
try iconutil.run()
iconutil.waitUntilExit()
try? FileManager.default.removeItem(at: iconset)
exit(iconutil.terminationStatus)
