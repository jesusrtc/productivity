// Opt-in prototype: align one real browser popup with a rectangle in Lab.
// Retained Accessibility references identify only the two explicitly marked windows.
import AppKit
import ApplicationServices

struct Input: Decodable {
    var operation: String
    var parentMarker: String?
    var childMarker: String?
    var slot: [Double]?
    var visible: Bool?
}
struct Output: Encodable {
    var ok = true
    var trusted = true
    var active = false
    var detail = ""
    var parent: [Double]?
    var popup: [Double]?
    var target: [Double]?
}
let args = CommandLine.arguments
guard args.count == 5 else { exit(2) }
let requestURL = URL(fileURLWithPath: args[1])
let responseURL = URL(fileURLWithPath: args[2])
let controlURL = URL(fileURLWithPath: args[3])
let stateURL = URL(fileURLWithPath: args[4])
func read(_ url: URL) -> Input? {
    guard let data = try? Data(contentsOf: url) else { return nil }
    return try? JSONDecoder().decode(Input.self, from: data)
}
func write(_ value: Output, _ url: URL) {
    if let data = try? JSONEncoder().encode(value) { try? data.write(to: url, options: .atomic) }
}
func attr(_ element: AXUIElement, _ name: String) -> CFTypeRef? {
    AXUIElementSetMessagingTimeout(element, 0.15)
    var value: CFTypeRef?
    return AXUIElementCopyAttributeValue(element, name as CFString, &value) == .success ? value : nil
}
func frame(_ element: AXUIElement) -> CGRect? {
    guard let p = attr(element, kAXPositionAttribute), let s = attr(element, kAXSizeAttribute),
          CFGetTypeID(p) == AXValueGetTypeID(), CFGetTypeID(s) == AXValueGetTypeID() else { return nil }
    var point = CGPoint.zero, size = CGSize.zero
    guard AXValueGetValue(p as! AXValue, .cgPoint, &point), AXValueGetValue(s as! AXValue, .cgSize, &size) else { return nil }
    return CGRect(origin: point, size: size)
}
func values(_ rect: CGRect) -> [Double] { [rect.minX, rect.minY, rect.width, rect.height] }
func same(_ a: AXUIElement?, _ b: AXUIElement?) -> Bool {
    guard let a = a, let b = b else { return false }; return CFEqual(a, b)
}
func ax(_ value: CFTypeRef?) -> AXUIElement? {
    guard let value = value, CFGetTypeID(value) == AXUIElementGetTypeID() else { return nil }
    return (value as! AXUIElement)
}
struct Match { var window: AXUIElement; var web: AXUIElement; var pid: pid_t }
func find(_ marker: String, until: Date) -> [Match] {
    var matches: [Match] = []
    for app in NSWorkspace.shared.runningApplications {
        let bundle = app.bundleIdentifier ?? ""
        guard bundle == "com.google.Chrome" || bundle.hasPrefix("com.google.Chrome.") else { continue }
        let windows = attr(AXUIElementCreateApplication(app.processIdentifier), kAXWindowsAttribute) as? [AXUIElement] ?? []
        for window in windows {
            var queue = [window], seen = 0
            while !queue.isEmpty && seen < 160 && Date() < until {
                let el = queue.removeFirst(); seen += 1
                let title = attr(el, kAXTitleAttribute) as? String ?? ""
                if (attr(el, kAXRoleAttribute) as? String) == "AXWebArea", title.contains(marker) {
                    matches.append(Match(window: window, web: el, pid: app.processIdentifier)); break
                }
                queue.append(contentsOf: attr(el, kAXChildrenAttribute) as? [AXUIElement] ?? [])
            }
        }
    }
    return matches
}
func minimized(_ el: AXUIElement) -> Bool { (attr(el, kAXMinimizedAttribute) as? Bool) == true }
func minimize(_ el: AXUIElement, _ value: Bool) {
    AXUIElementSetAttributeValue(el, kAXMinimizedAttribute as CFString, value ? kCFBooleanTrue : kCFBooleanFalse)
}
func position(_ el: AXUIElement, _ rect: CGRect) -> Bool {
    var point = rect.origin, size = rect.size
    guard let p = AXValueCreate(.cgPoint, &point), let s = AXValueCreate(.cgSize, &size) else { return false }
    let resized = AXUIElementSetAttributeValue(el, kAXSizeAttribute as CFString, s)
    let moved = AXUIElementSetAttributeValue(el, kAXPositionAttribute as CFString, p)
    return resized == .success && moved == .success
}

guard let input = read(requestURL) else { exit(2) }
let trusted = input.operation == "permission"
    ? AXIsProcessTrustedWithOptions([kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary)
    : AXIsProcessTrusted()
if input.operation == "status" || input.operation == "permission" || !trusted {
    let result = Output(ok: trusted, trusted: trusted, detail: trusted ? "Ready to dock a Chrome window." : "Enable Lab Window Dock in System Settings → Privacy & Security → Accessibility, then check again.")
    write(result, responseURL)
    if input.operation == "permission" && !trusted {
        NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!)
    }
    exit(0)
}
guard input.operation == "attach", let parentMarker = input.parentMarker, let childMarker = input.childMarker else {
    write(Output(ok: false, detail: "Missing dock window identity."), responseURL); exit(1)
}
let registrationDeadline = Date().addingTimeInterval(3)
let parents = find(parentMarker, until: registrationDeadline)
let children = find(childMarker, until: registrationDeadline)
guard parents.count == 1, children.count == 1, let parent = parents.first, let child = children.first,
      !same(parent.window, child.window), frame(parent.web) != nil, frame(child.window) != nil else {
    write(Output(ok: false, detail: "Could not uniquely identify the two Chrome windows. Keep Lab visible, then try Dock again."), responseURL)
    exit(1)
}
var current = input
var lastCommand = Date()
var lastModification: Date?
var running = true
var hiddenByHelper = false
var previousFocus: AXUIElement?
var lastTarget: CGRect?
var lastState = Date.distantPast
var result = Output(active: true, detail: "Docked — move or resize Lab to try it.")
func finish(_ detail: String, close: Bool = false) {
    if hiddenByHelper { minimize(child.window, false) }
    if close, let button = ax(attr(child.window, kAXCloseButtonAttribute)) {
        if AXUIElementPerformAction(button, kAXPressAction as CFString) != .success {
            result.ok = false; result.detail = "Detached; Chrome did not accept Close. Close the popup normally."
        } else { result.detail = detail }
    } else { result.detail = detail }
    result.active = false; running = false; write(result, stateURL)
}
func tick() {
    if let stamp = try? controlURL.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate,
       stamp != lastModification, let command = read(controlURL) {
        lastModification = stamp; lastCommand = Date()
        if command.operation == "detach" || command.operation == "close" {
            finish("Detached. The popup is independent again.", close: command.operation == "close"); return
        }
        current = command
    }
    // A closed/reloaded Lab page or stopped backend must never leave a controller running.
    if Date().timeIntervalSince(lastCommand) > 12 { finish("Detached after Lab stopped responding."); return }
    guard let parentFrame = frame(parent.window), let webFrame = frame(parent.web), frame(child.window) != nil else {
        finish("Detached because one of the windows closed or changed."); return
    }
    let shouldHide = current.visible == false || minimized(parent.window)
    if shouldHide {
        if !minimized(child.window) { minimize(child.window, true); hiddenByHelper = true }
        previousFocus = nil
    } else {
        if hiddenByHelper { minimize(child.window, false); hiddenByHelper = false; lastTarget = nil }
        if let s = current.slot, s.count == 4 {
            // Browser supplies normalized viewport coordinates; AX supplies screen coordinates.
            let viewport = webFrame.intersection(parentFrame)
            let target = CGRect(x: viewport.minX + s[0] * viewport.width,
                                y: viewport.minY + s[1] * viewport.height,
                                width: s[2] * viewport.width, height: s[3] * viewport.height).integral
            if target.width < 320 || target.height < 180 {
                finish("Panel too small. Enlarge Lab and try Dock again."); return
            }
            let actual = frame(child.window)
            if lastTarget != target || actual.map({ abs($0.minX - target.minX) > 2 || abs($0.minY - target.minY) > 2 || abs($0.width - target.width) > 2 || abs($0.height - target.height) > 2 }) == true {
                guard position(child.window, target) else { finish("Chrome could not move or resize this popup."); return }
                lastTarget = target
            }
            result.target = values(target)
        }
        // Raise only on a transition into the owning Lab window. Never activate an app,
        // repeatedly steal focus, or raise over an unrelated Chrome window/another app.
        if NSWorkspace.shared.frontmostApplication?.processIdentifier == parent.pid {
            let focused = ax(attr(AXUIElementCreateApplication(parent.pid), kAXFocusedWindowAttribute))
            if same(focused, parent.window) && !same(previousFocus, parent.window) {
                AXUIElementPerformAction(child.window, kAXRaiseAction as CFString)
            }
            previousFocus = focused
        } else { previousFocus = nil }
    }
    result.parent = values(parentFrame)
    result.popup = frame(child.window).map(values)
    if Date().timeIntervalSince(lastState) > 0.75 { write(result, stateURL); lastState = Date() }
}
tick()
write(result, responseURL)
let timer = Timer(timeInterval: 0.10, repeats: true) { _ in tick() }
RunLoop.current.add(timer, forMode: .common)
while running { RunLoop.current.run(until: Date().addingTimeInterval(0.10)) }
timer.invalidate()
