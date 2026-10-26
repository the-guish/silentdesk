/// The Services settings: every service, connected or not, with its connect
/// form or its Disconnect button. As the GTK app's services_dialog.py.

import Foundation
import Observation
import SilentDeskCore

@MainActor
@Observable
public final class ServicesModel {
    public let desk: any Desk
    public let notices: Notices
    /// What the queue does after a service connects or disconnects.
    public var changed: @MainActor (_ service: String, _ connected: Bool) async -> Void = { _, _ in }

    public private(set) var statuses: [ServiceStatus] = []
    /// The service connecting or disconnecting now. One at a time.
    public private(set) var busy: String?
    /// What was typed in each service's form, by field name. It survives a
    /// failed connect.
    public var values: [String: [String: String]] = [:]

    public init(desk: any Desk, notices: Notices = Notices()) {
        self.desk = desk
        self.notices = notices
    }

    public func load() async {
        do {
            statuses = try await desk.services()
        } catch {
            notices.fail(error)
        }
    }

    public func value(_ service: String, _ field: String) -> String {
        values[service]?[field] ?? ""
    }

    public func set(_ service: String, _ field: String, _ value: String) {
        values[service, default: [:]][field] = value
    }

    /// Connects with the form's values; browser sign-ins have none.
    public func connect(_ service: String) async {
        guard busy == nil else { return }
        let typed = values[service] ?? [:]
        let empty = Services.missing(service, typed)
        guard empty.isEmpty else {
            notices.post("Fill in: \(empty.joined(separator: ", ")).", seconds: 6)
            return
        }
        busy = service
        do {
            _ = try await desk.connect(service, params: Services.connectParams(service, typed))
        } catch {
            busy = nil
            notices.fail(error)
            return
        }
        busy = nil
        // The form is done with, secrets included.
        values[service] = nil
        notices.post("Connected \(Format.serviceName(service))")
        await load()
        await changed(service, true)
    }

    /// Disconnects a service. The window asks first.
    public func disconnect(_ service: String) async {
        guard busy == nil else { return }
        busy = service
        do {
            _ = try await desk.disconnect(service)
        } catch {
            busy = nil
            notices.fail(error)
            return
        }
        busy = nil
        await load()
        await changed(service, false)
    }
}
