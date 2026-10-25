/// The few Slack Web API calls SilentDesk makes, all read-only.
final class SlackHTTPAPI: SlackAPI {
    static let tokenErrors = ["invalid_auth", "not_authed", "token_revoked", "token_expired", "account_inactive"]

    private let http: any Http
    /// Such as https://slack.com/api.
    private let base: String
    private let service = SlackRules.service

    init(http: any Http, baseURL: String) {
        self.http = http
        base = baseURL
    }

    private func call(_ method: String, token: String, params: [(String, String)] = []) async throws -> JSON {
        let response = try await http.request(
            "GET", "\(base)/\(method)", headers: ["Authorization": "Bearer \(token)"], params: params)
        if response.status == 429 {
            let wait = response.headers["retry-after"] ?? "a few"
            throw ConnectorError.remote(service, "Slack is rate limiting SilentDesk. Try again in \(wait) seconds.", status: 429)
        }
        guard let body = try? JSON.parse(response.body), body.object != nil else {
            throw ConnectorError.network(service, "Slack's answer could not be read.")
        }
        guard body["ok"]?.bool == true else {
            let error = body["error"]?.string ?? "unknown_error"
            if Self.tokenErrors.contains(error) {
                throw ConnectorError.auth(service, "Slack rejected the token.")
            }
            if error == "missing_scope" {
                throw ConnectorError.auth(service, "Slack did not grant this. Disconnect Slack and connect it again.")
            }
            throw ConnectorError.remote(service, "Slack answered \(error).", status: response.status)
        }
        return body
    }

    func identity(token: String) async throws -> SlackAccount {
        let body = try await call("auth.test", token: token)
        guard let userID = body["user_id"]?.string, let user = body["user"]?.string, let teamID = body["team_id"]?.string,
            let team = body["team"]?.string
        else { throw ConnectorError.network(service, "Slack did not say who signed in.") }
        return SlackAccount(userID: userID, userName: user, teamID: teamID, teamName: team)
    }

    func search(token: String, query: String, count: Int) async throws -> [SlackMatch] {
        let params = [("query", query), ("sort", "timestamp"), ("sort_dir", "desc"), ("count", String(count))]
        let found = try await call("search.messages", token: token, params: params)["messages"]
        return (found?["matches"]?.array ?? []).compactMap { match in
            guard match.object != nil, let ts = match["ts"]?.string else { return nil }
            return Self.match(match, ts: ts)
        }
    }

    func history(token: String, channelID: String, count: Int) async throws -> [SlackHistoryEntry] {
        let found = try await call("conversations.history", token: token, params: [("channel", channelID), ("limit", String(count))])
        return (found["messages"]?.array ?? []).compactMap { message in
            guard message.object != nil, let ts = message["ts"]?.string else { return nil }
            return SlackHistoryEntry(
                user: message["user"]?.string,
                username: message["username"]?.string,
                text: message["text"]?.string ?? "",
                ts: ts,
                subtype: message["subtype"]?.string)
        }
    }

    func userName(token: String, userID: String) async throws -> String {
        let user: JSON?
        do {
            user = try await call("users.info", token: token, params: [("user", userID)])["user"]
        } catch let error as ConnectorError where error.kind == .remote || error.kind == .network {
            return ""
        }
        let profile = user?["profile"]
        let candidates = [profile?["display_name"], profile?["real_name"], user?["real_name"], user?["name"]]
        return candidates.lazy.compactMap { $0?.string }.first { !$0.trimmingCharacters(in: .whitespaces).isEmpty } ?? ""
    }

    private static func match(_ value: JSON, ts: String) -> SlackMatch {
        let channel = value["channel"]?.object != nil ? value["channel"] : nil
        return SlackMatch(
            channelID: channel?["id"]?.string ?? "",
            channelName: channel?["name"]?.string ?? "",
            isIM: value["type"]?.string == "im" || channel?["is_im"]?.bool == true,
            isMPIM: channel?["is_mpim"]?.bool == true,
            user: value["user"]?.string,
            username: value["username"]?.string,
            text: value["text"]?.string ?? "",
            ts: ts,
            permalink: value["permalink"]?.string ?? "")
    }
}
