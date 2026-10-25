/// Jira issues, sites and accounts, as far as SilentDesk needs them.
/// Descriptions and comments are never fetched.

enum JiraFlavor: String, Sendable {
    /// Jira Cloud: email and API token (HTTP Basic), REST API v3.
    case cloud
    /// Jira Data Center: personal access token (Bearer), REST API v2.
    case dataCenter
}

/// With an email, a Jira Cloud API token; without, a Data Center personal
/// access token.
struct JiraCredential: Sendable, Equatable {
    let email: String?
    let token: String

    var flavor: JiraFlavor {
        email?.isEmpty == false ? .cloud : .dataCenter
    }
}

struct JiraEndpoint: Sendable, Equatable {
    /// Such as https://acme.atlassian.net: issues open from here.
    let site: String
    /// Where the REST API is: the site, or Atlassian's gateway for scoped tokens.
    let apiBase: String
    let flavor: JiraFlavor
}

struct JiraAccount: Sendable, Equatable {
    /// The Cloud account ID, or the Data Center user key.
    let userID: String
    let userName: String
    let endpoint: JiraEndpoint
}

struct JiraUser: Sendable, Equatable {
    let id: String?
    let name: String
}

struct JiraIssue: Sendable, Equatable {
    let issueID: String
    /// Such as PAY-412.
    let key: String
    let summary: String
    let status: String
    let project: String
    let assignee: JiraUser?
    let reporter: JiraUser?
    /// As Jira writes it, such as 2026-10-23T10:00:00.000+0200; nil when absent.
    let updated: String?
}

extension JiraCredential: CustomStringConvertible {
    var description: String { "JiraCredential(email: \(email ?? "none"), token hidden)" }
}
