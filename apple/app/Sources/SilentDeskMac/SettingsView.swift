/// The settings window (⌘,), with the Services pane: every service,
/// connected or not, with its connect form or its Disconnect button.

import SilentDeskAppModel
import SilentDeskCore
import SwiftUI

struct SettingsView: View {
    let services: ServicesModel

    var body: some View {
        TabView {
            ServicesView(model: services)
                .tabItem { Label("Services", systemImage: "link") }
        }
        .frame(width: 560, height: 520)
    }
}

struct ServicesView: View {
    let model: ServicesModel

    var body: some View {
        Form {
            Section {
                ForEach(model.statuses, id: \.service) { status in
                    ServiceRow(status: status, model: model)
                }
            } footer: {
                Text("SilentDesk reads each service with your own account, and keeps your sign-in in the Keychain.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .overlay(alignment: .bottom) { NoticeView(notices: model.notices) }
        .task { await model.load() }
    }
}

struct ServiceRow: View {
    let status: ServiceStatus
    let model: ServicesModel
    @State private var expanded = false
    @State private var confirmingDisconnect = false

    init(status: ServiceStatus, model: ServicesModel) {
        self.status = status
        self.model = model
    }

    private var name: String { Format.serviceName(status.service) }
    private var busy: Bool { model.busy == status.service }
    private var fields: [Services.Field] { Services.fields(status.service) }

    var body: some View {
        if !status.configured {
            LabeledContent {
                EmptyView()
            } label: {
                title
            }
            .disabled(true)
        } else if status.connected {
            LabeledContent {
                Button(busy ? "Disconnecting…" : "Disconnect", role: .destructive) {
                    confirmingDisconnect = true
                }
                .disabled(model.busy != nil)
            } label: {
                title
            }
            .confirmationDialog(
                "Disconnect \(name)?", isPresented: $confirmingDisconnect, titleVisibility: .visible
            ) {
                Button("Disconnect", role: .destructive) {
                    Task { await model.disconnect(status.service) }
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text(Services.disconnectWarning(status.service))
            }
        } else if fields.isEmpty {
            LabeledContent {
                connectButton("Sign In with the Browser")
            } label: {
                title
            }
        } else {
            DisclosureGroup(isExpanded: $expanded) {
                ForEach(fields) { field in
                    let text = Binding(
                        get: { model.value(status.service, field.name) },
                        set: { model.set(status.service, field.name, $0) })
                    if field.secret {
                        SecureField(field.title, text: text)
                    } else {
                        TextField(field.title, text: text)
                    }
                }
                HStack {
                    Spacer()
                    connectButton("Connect")
                }
            } label: {
                title
            }
        }
    }

    private var title: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(name)
            Text(Services.describe(status))
                .font(.caption)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
        }
    }

    private func connectButton(_ label: String) -> some View {
        Button(busy ? "Connecting…" : label) {
            Task { await model.connect(status.service) }
        }
        .buttonStyle(.borderedProminent)
        .disabled(model.busy != nil)
    }
}
