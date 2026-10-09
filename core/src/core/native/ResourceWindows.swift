// Lab's local macOS window helper. No browser Apple events or URL navigation.
import AppKit
import ApplicationServices

struct WindowRef: Codable, Equatable {
    var pid: Int32
    var id: UInt32
    var started: Double
}
struct Resource: Codable {
    var url: String
    var window: WindowRef
}
struct Group: Codable {
    var parent: WindowRef?
    var resources: [Resource] = []
}
struct Input: Decodable {
    var operation: String
    var marker: String?
    var parentBounds: [Double]?
    var bounds: [Double]?
    var url: String?
    var group: Group
}
struct Output: Encodable {
    var ok = true
    var trusted = true
    var detail: String?
    var reused = false
    var group: Group
}

let deadline = Date().addingTimeInterval(4)
func attribute(_ element: AXUIElement, _ name: String) -> CFTypeRef? {
    AXUIElementSetMessagingTimeout(element, 0.5)
    var value: CFTypeRef?
    return AXUIElementCopyAttributeValue(element, name as CFString, &value) == .success ? value : nil
}
func frame(_ element: AXUIElement) -> CGRect? {
    guard let position = attribute(element, kAXPositionAttribute),
          let size = attribute(element, kAXSizeAttribute),
          CFGetTypeID(position) == AXValueGetTypeID(), CFGetTypeID(size) == AXValueGetTypeID() else { return nil }
    var point = CGPoint.zero, dimensions = CGSize.zero
    guard AXValueGetValue(position as! AXValue, .cgPoint, &point),
          AXValueGetValue(size as! AXValue, .cgSize, &dimensions) else { return nil }
    return CGRect(origin: point, size: dimensions)
}
func near(_ a: CGRect, _ b: CGRect) -> Bool {
    abs(a.minX - b.minX) < 3 && abs(a.minY - b.minY) < 3
        && abs(a.width - b.width) < 3 && abs(a.height - b.height) < 3
}
func rectangle(_ values: [Double]?) -> CGRect? {
    guard let v = values, v.count == 4 else { return nil }
    return CGRect(x: v[0], y: v[1], width: v[2], height: v[3])
}
func browser(_ app: NSRunningApplication) -> Bool {
    let id = app.bundleIdentifier ?? ""
    return ["com.google.Chrome", "com.microsoft.edgemac", "com.brave.Browser", "org.chromium.Chromium"]
        .contains { id == $0 || id.hasPrefix($0 + ".") }
}
struct NativeWindow {
    var ref: WindowRef
    var frame: CGRect
    var onscreen: Bool
}
func nativeWindows() -> [NativeWindow] {
    let values = CGWindowListCopyWindowInfo([.excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []
    return values.compactMap { value in
        guard (value[kCGWindowLayer as String] as? Int) == 0,
              let pid = value[kCGWindowOwnerPID as String] as? Int32,
              let app = NSRunningApplication(processIdentifier: pid),
              let id = value[kCGWindowNumber as String] as? UInt32,
              let bounds = value[kCGWindowBounds as String] as? NSDictionary,
              let rect = CGRect(dictionaryRepresentation: bounds), rect.width > 100, rect.height > 100 else { return nil }
        return NativeWindow(ref: WindowRef(pid: pid, id: id, started: app.launchDate?.timeIntervalSince1970 ?? 0),
                            frame: rect, onscreen: value[kCGWindowIsOnscreen as String] as? Bool ?? false)
    }
}
func axWindows(_ pid: Int32) -> [AXUIElement] {
    attribute(AXUIElementCreateApplication(pid), kAXWindowsAttribute) as? [AXUIElement] ?? []
}
func containsMarker(_ window: AXUIElement, _ marker: String) -> Bool {
    // Installed Chrome apps may keep a fixed native title such as Cerebro.
    // The blank page's accessible WebArea still carries its document title.
    var queue = [window], inspected = 0
    while !queue.isEmpty && inspected < 80 && Date() < deadline {
        let element = queue.removeFirst(); inspected += 1
        if (attribute(element, kAXTitleAttribute) as? String)?.contains(marker) == true
            || (attribute(element, kAXDescriptionAttribute) as? String)?.contains(marker) == true { return true }
        queue.append(contentsOf: attribute(element, kAXChildrenAttribute) as? [AXUIElement] ?? [])
    }
    return false
}
func axWindow(_ window: NativeWindow) -> AXUIElement? {
    let matches = axWindows(window.ref.pid).filter {
        Date() < deadline && (frame($0).map { near($0, window.frame) } ?? false)
    }
    // Do not act on a guessed window when overlapping frames are ambiguous.
    return matches.count == 1 ? matches[0] : nil
}
func raise(_ window: NativeWindow, activate: Bool) -> Bool {
    guard let element = axWindow(window) else { return false }
    AXUIElementSetAttributeValue(element, kAXMinimizedAttribute as CFString, kCFBooleanFalse)
    if activate { NSRunningApplication(processIdentifier: window.ref.pid)?.activate(options: [.activateIgnoringOtherApps]) }
    return AXUIElementPerformAction(element, kAXRaiseAction as CFString) == .success
}
func perform(_ input: Input) -> Output {
    var output = Output(group: input.group)
    if input.operation == "permission" {
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
        output.trusted = AXIsProcessTrustedWithOptions(options)
        if !output.trusted {
            NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!)
        }
        return output
    }
    guard AXIsProcessTrusted() else {
        output.ok = false; output.trusted = false
        output.detail = "Enable Lab Resource Windows in macOS Accessibility to bring these windows forward automatically."
        return output
    }
    let windows = nativeWindows()
    output.group.resources.removeAll { resource in !windows.contains { $0.ref == resource.window } }
    if input.operation == "register" {
        guard let marker = input.marker, let parentBounds = rectangle(input.parentBounds) else {
            output.ok = false; output.detail = "Missing resource window identity."; return output
        }
        var candidates: [(NativeWindow, AXUIElement)] = []
        for app in NSWorkspace.shared.runningApplications where browser(app) && Date() < deadline {
            for element in axWindows(app.processIdentifier) where Date() < deadline {
                guard let rect = frame(element), containsMarker(element, marker) else { continue }
                let matches = windows.filter { $0.ref.pid == app.processIdentifier && near($0.frame, rect) }
                if matches.count == 1 { candidates.append((matches[0], element)) }
            }
        }
        guard candidates.count == 1, let url = input.url else {
            output.ok = false; output.detail = "Could not identify this resource window on the local Mac."; return output
        }
        let (child, element) = candidates[0]
        if output.group.parent == nil || !windows.contains(where: { $0.ref == output.group.parent }) {
            let parents = windows.filter {
                $0.ref != child.ref && near($0.frame, parentBounds)
                    && NSRunningApplication(processIdentifier: $0.ref.pid).map(browser) == true
            }
            guard parents.count == 1 else {
                output.ok = false; output.detail = "Could not identify the owning Lab window."; return output
            }
            output.group.parent = parents[0].ref
        }
        if let rect = rectangle(input.bounds) {
            var point = rect.origin, size = rect.size
            if let value = AXValueCreate(.cgSize, &size) {
                AXUIElementSetAttributeValue(element, kAXSizeAttribute as CFString, value)
            }
            if let value = AXValueCreate(.cgPoint, &point) {
                AXUIElementSetAttributeValue(element, kAXPositionAttribute as CFString, value)
            }
        }
        output.group.resources.removeAll { $0.url == url }
        output.group.resources.append(Resource(url: url, window: child.ref))
    } else if input.operation == "focus" || input.operation == "close" {
        guard let resource = output.group.resources.first(where: { $0.url == input.url }),
              let window = windows.first(where: { $0.ref == resource.window }) else { return output }
        if input.operation == "focus" {
            output.reused = raise(window, activate: true)
            if !output.reused { output.ok = false; output.detail = "Could not activate the resource window. Try again from Lab." }
        } else {
            guard let element = axWindow(window), let button = attribute(element, kAXCloseButtonAttribute),
                  CFGetTypeID(button) == AXUIElementGetTypeID(),
                  AXUIElementPerformAction(button as! AXUIElement, kAXPressAction as CFString) == .success else {
                output.ok = false; output.detail = "Could not close the resource window."; return output
            }
            output.group.resources.removeAll { $0.url == resource.url }
        }
    } else if input.operation == "raise" {
        // A delayed focus request must never steal focus back from Slack.
        guard let parent = output.group.parent,
              windows.first(where: { $0.onscreen })?.ref == parent else { return output }
        for resource in output.group.resources where Date() < deadline {
            if let child = windows.first(where: { $0.ref == resource.window }), !raise(child, activate: false) {
                output.ok = false; output.detail = "Could not bring all resource windows forward."
            }
        }
    }
    return output
}

if CommandLine.arguments.count == 3 {
    do {
        let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
        let input = try JSONDecoder().decode(Input.self, from: data)
        let dataOut = try JSONEncoder().encode(perform(input))
        try dataOut.write(to: URL(fileURLWithPath: CommandLine.arguments[2]), options: .atomic)
    } catch {
        let failure = Output(ok: false, detail: "Could not control the resource windows.", group: Group())
        if let data = try? JSONEncoder().encode(failure) {
            try? data.write(to: URL(fileURLWithPath: CommandLine.arguments[2]), options: .atomic)
        }
    }
}
