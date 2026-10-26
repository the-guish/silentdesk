import Foundation
import SilentDeskCore
import Testing

@testable import SilentDeskAppModel

private let utc = TimeZone(identifier: "UTC")!
private let now = Format.parse("2026-10-25T15:00:00Z")!

@Test func serviceNamesReadAsTheServicesWriteThem() {
    #expect(Format.serviceName("github") == "GitHub")
    #expect(Format.serviceName("tasks") == "Google Tasks")
    #expect(Format.serviceName("linear") == "Linear")
}

@Test func datesParseWithOrWithoutFractionsAndOffsets() {
    #expect(Format.parse("2026-10-25T15:00:00Z") == now)
    #expect(Format.parse("2026-10-25T15:00:00.000Z") == now)
    #expect(Format.parse("2026-10-25T12:00:00-03:00") == now)
    #expect(Format.parse("yesterday") == nil)
    #expect(Format.parse(nil) == nil)
}

// The core writes milliseconds without their trailing zeros (RFC3339.format).
@Test(arguments: [("2026-10-25T15:00:00.1Z", 0.1), ("2026-10-25T15:00:00.12Z", 0.12), ("2026-10-25T15:00:00.123Z", 0.123)])
func datesParseFractionsOfAnyLength(_ text: String, _ seconds: Double) throws {
    let date = try #require(Format.parse(text))
    #expect(abs(date.timeIntervalSince(now) - seconds) < 0.0005)
}

@Test func agoCountsMinutesHoursThenDays() {
    #expect(Format.ago(nil, now: now) == "just now")
    #expect(Format.ago("2026-10-25T14:59:30Z", now: now) == "just now")
    #expect(Format.ago("2026-10-25T14:57:00Z", now: now) == "3 min ago")
    #expect(Format.ago("2026-10-25T13:00:00Z", now: now) == "2 h ago")
    #expect(Format.ago("2026-10-22T15:00:00Z", now: now) == "3 days ago")
}

@Test func shortDatesShowTheTimeTodayTheDayThisYearOrTheFullDate() {
    #expect(Format.shortDate("2026-10-25T09:05:00Z", now: now, timeZone: utc) == "09:05")
    #expect(Format.shortDate("2026-03-04T09:05:00Z", now: now, timeZone: utc) == "Mar 4")
    #expect(Format.shortDate("2025-12-31T09:05:00Z", now: now, timeZone: utc) == "Dec 31, 2025")
    #expect(Format.shortDate("", now: now, timeZone: utc) == "")
}

@Test func shortDatesUseTheLocalDay() {
    let saoPaulo = TimeZone(identifier: "America/Sao_Paulo")!
    // 02:30 UTC on the 25th, the day `now` is, is still the 24th in São Paulo.
    #expect(Format.shortDate("2026-10-25T02:30:00Z", now: now, timeZone: utc) == "02:30")
    #expect(Format.shortDate("2026-10-25T02:30:00Z", now: now, timeZone: saoPaulo) == "Oct 24")
}

@Test func itemLinesSayWhetherTheUserReceivedOrSentIt() {
    #expect(Format.itemLine(.inbound, "2026-10-25T09:12:00Z", now: now, timeZone: utc) == "Received · Today 09:12")
    #expect(Format.itemLine(.outbound, "2026-10-24T09:12:00Z", now: now, timeZone: utc) == "Sent · Oct 24, 09:12")
    #expect(Format.itemLine(nil, "2025-10-24T09:12:00Z", now: now, timeZone: utc) == "Oct 24, 2025, 09:12")
}

@Test func subtitlesNameWhoWroteLastOrThatItWaitsOnOthers() {
    let received = topic("a", items: [item("1", author: "Ana"), item("2", author: "Ben"), item("3", author: nil)])
    #expect(Format.subtitle(received) == "Gmail · Ben")
    let sent = topic("b", items: [item("1", author: "Ana"), item("2", .outbound, author: "Me")])
    #expect(Format.subtitle(sent) == "Gmail · Waiting on others")
    #expect(Format.subtitle(topic("c", service: "tasks", items: [item("1", nil)])) == "Google Tasks")
}

@Test func avatarsShowTheNewestAuthorsInitials() {
    #expect(Format.avatarName(topic("a", items: [item("1", author: "Ana López"), item("2")])) == "Ana López")
    #expect(Format.initials("Ana López") == "AL")
    #expect(Format.initials("Ana María López") == "AL")
    #expect(Format.initials("octocat") == "O")
    #expect(Format.initials("ana.lopez@example.com") == "AL")
    #expect(Format.initials("@marco") == "M")
    #expect(Format.initials("") == "")
}

@Test func avatarColorsAreStable() {
    #expect(Format.colorIndex("Ana López", count: 8) == Format.colorIndex("Ana López", count: 8))
    #expect((0..<8).contains(Format.colorIndex("Ben", count: 8)))
    #expect(Format.colorIndex("Ben", count: 0) == 0)
}

@Test func searchMatchesEveryWordInTitleServiceAuthorsAndKeys() {
    let found = topic("a", service: "jira", title: "Rotate certificates", items: [item("OPS-142", author: "Priya Shah")])
    #expect(Format.matches(found, "rotate"))
    #expect(Format.matches(found, "JIRA priya"))
    #expect(Format.matches(found, "ops-142"))
    #expect(!Format.matches(found, "rotate gmail"))
    #expect(Format.matches(found, "  "))
}

private struct Plain: Error {}

private struct Localized: LocalizedError {
    var errorDescription: String? { "Readable." }
}

@Test func errorsReadAsOneLine() {
    #expect(Format.describe(ConnectorError.auth("github", "Bad credentials.")) == "GitHub: Bad credentials.")
    #expect(Format.describe(ConnectorError.network(nil, "Offline.")) == "Offline.")
    #expect(Format.describe(StorageError("No key.")) == "No key.")
    #expect(Format.describe(Plain()) == "Plain()")
    #expect(Format.describe(Localized()) == "Readable.")
}

@Test func aChipNamesTheStatusOrShowsADash() {
    #expect(Format.chipLabel(TopicStatus(name: "Code Review", category: .inProgress)) == "Code Review")
    #expect(Format.chipLabel(nil) == "—")
}

@Test(arguments: [
    ([Double](), 800.0, 0.0),
    ([61, 88, 70], 800, 88),
    ([61, 88, 70], 200, 50),
    ([61, 88], 0, 88),
    ([300], 1000, 250),
] as [([Double], Double, Double)])
func everyChipTakesTheWidestOnesWidthUpToAQuarterOfTheQueue(_ widths: [Double], _ queueWidth: Double, _ expected: Double) {
    #expect(Format.chipWidth(widths, queueWidth: queueWidth) == expected)
}

@Test func searchMatchesAStatusName() {
    let topic = TopicView(
        id: "1", service: "jira", title: "Fix login", items: [], updatedAt: "2026-10-25T15:00:00Z", deletable: false,
        status: TopicStatus(name: "Code Review", category: .inProgress))
    #expect(Format.matches(topic, "review"))
    #expect(!Format.matches(TopicView(
        id: "2", service: "jira", title: "Fix login", items: [], updatedAt: "2026-10-25T15:00:00Z", deletable: false), "review"))
}

@Test func aTopicOpensAtItsNewestItemWithALink() {
    func topic(_ urls: [String?]) -> TopicView {
        TopicView(
            id: "1", service: "gmail", title: "T",
            items: urls.enumerated().map { index, url in
                Item(key: "\(index)", direction: .inbound, author: "Bo", url: url, date: "2026-10-25T15:00:00Z", deletable: false)
            },
            updatedAt: "2026-10-25T15:00:00Z", deletable: false)
    }
    #expect(Format.topicURL(topic(["https://a/1", "https://a/2"])) == "https://a/2")
    #expect(Format.topicURL(topic(["https://a/1", nil])) == "https://a/1")
    #expect(Format.topicURL(topic([nil])) == nil)
}
