/// Pull requests and accounts, as far as SilentDesk needs them. Descriptions,
/// diffs and comments are never fetched.

/// Why a pull request is in the queue, strongest first.
enum GitHubReason: String, Sendable {
    case reviewRequested
    case assigned
    case authored
}

struct GitHubEndpoint: Sendable, Equatable {
    /// Such as https://api.github.com, or https://github.acme.com/api/v3.
    let apiBase: String
    /// Such as https://github.com.
    let webBase: String
}

struct PullRequest: Sendable, Equatable {
    let prID: Int
    /// owner/name
    let repo: String
    let number: Int
    let title: String
    let reason: GitHubReason
    /// The author's login.
    let author: String
    let draft: Bool
    let url: String
    /// RFC 3339: last updated.
    let updated: String
    var merged = false
    /// Closed, merged or not.
    var closed = false
    /// The checks on its last commit, as GitHub sums them up: SUCCESS,
    /// PENDING, FAILURE, ERROR or EXPECTED; nil when it has none.
    var checks: String? = nil
    /// GitHub's review decision: APPROVED, CHANGES_REQUESTED or
    /// REVIEW_REQUIRED; nil when the repository needs no review.
    var review: String? = nil
}

struct GitHubAccount: Sendable, Equatable {
    let login: String
    /// The display name, or the login when the user has none.
    let name: String
    let endpoint: GitHubEndpoint
}
