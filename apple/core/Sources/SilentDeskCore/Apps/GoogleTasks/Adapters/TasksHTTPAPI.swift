/// The Google Tasks REST API, read-only, and Google's user info for the email.
final class TasksHTTPAPI: TasksAPI {
    /// Stop paging after this many pages of 100, per list.
    static let maxPages = 20
    /// Where a task came from, by assignmentInfo.surfaceType, then by link type.
    static let surfaces = ["DOCUMENT": "Docs", "SPACE": "Chat", "GMAIL": "Gmail"]
    static let links = ["email": "Gmail", "chat_message": "Chat"]

    private let http: any Http
    /// Such as https://tasks.googleapis.com/tasks/v1.
    private let apiBase: String
    private let userinfoURL: String
    private let service = TasksRules.service

    init(http: any Http, apiBase: String, userinfoURL: String) {
        self.http = http
        self.apiBase = apiBase
        self.userinfoURL = userinfoURL
    }

    private func get(_ url: String, token: String, params: [(String, String)] = []) async throws -> JSON {
        let response = try await http.request("GET", url, headers: ["Authorization": "Bearer \(token)"], params: params)
        let body = response.body.isEmpty ? nil : try? JSON.parse(response.body)
        if response.status == 401 {
            throw ConnectorError.auth(service, "Google rejected the access token.")
        }
        guard response.isSuccess else {
            let message = body?["error"]?["message"]?.string
            throw ConnectorError.remote(
                service, "Google Tasks answered \(response.status): \(message ?? "no details").", status: response.status)
        }
        guard let body, body.object != nil else { throw ConnectorError.network(service, "Google's answer could not be read.") }
        return body
    }

    private func all(_ url: String, token: String, params: [(String, String)]) async throws -> [JSON] {
        var items: [JSON] = []
        var pageToken: String?
        for _ in 0..<Self.maxPages {
            let page = try await get(url, token: token, params: params + (pageToken.map { [("pageToken", $0)] } ?? []))
            guard let found = (page["items"] ?? .array([])).array else {
                throw ConnectorError.network(service, "Google's answer could not be read.")
            }
            items += found
            pageToken = page["nextPageToken"]?.string
            if pageToken == nil {
                break
            }
        }
        return items
    }

    func email(token: String) async throws -> String {
        guard let email = try await get(userinfoURL, token: token)["email"]?.string else {
            throw ConnectorError.network(service, "Google did not say which account signed in.")
        }
        return email
    }

    func lists(token: String) async throws -> [TaskList] {
        try await all("\(apiBase)/users/@me/lists", token: token, params: [("maxResults", "100")]).compactMap { item in
            guard let id = item["id"]?.string else { return nil }
            return TaskList(listID: id, title: item["title"]?.string ?? "")
        }
    }

    func tasks(token: String, in list: TaskList) async throws -> [GoogleTask] {
        let found = try await all(
            "\(apiBase)/lists/\(URLQuery.encode(list.listID))/tasks", token: token,
            params: [
                ("maxResults", "100"), ("showCompleted", "false"), ("showHidden", "false"), ("showDeleted", "false"),
                ("showAssigned", "true"),
            ])
        return found.compactMap { item in
            guard let id = item["id"]?.string else { return nil }
            return task(item, id: id, in: list)
        }
    }

    private func task(_ item: JSON, id: String, in list: TaskList) -> GoogleTask {
        let surface = item["assignmentInfo"]?["surfaceType"]?.string
        let linkTypes = item["links"]?.array?.compactMap { $0["type"]?.string } ?? []
        let origin = surface.flatMap { Self.surfaces[$0] } ?? linkTypes.lazy.compactMap { Self.links[$0] }.first
        let due = item["due"]?.string
        let url = item["webViewLink"]?.string
        return GoogleTask(
            taskID: id,
            listID: list.listID,
            listTitle: list.title,
            title: item["title"]?.string ?? "",
            completed: item["status"]?.string == "completed",
            deleted: item["deleted"]?.bool == true,
            due: due.flatMap { $0.count >= 10 ? String($0.prefix(10)) : nil },
            origin: origin,
            url: url?.isEmpty == false ? url! : "https://tasks.google.com/",
            updated: item["updated"]?.string ?? "")
    }
}
