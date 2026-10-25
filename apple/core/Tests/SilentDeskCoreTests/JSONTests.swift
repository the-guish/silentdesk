import Foundation
@testable import SilentDeskCore
import Testing

@Test func parsesEveryKindOfValue() throws {
    let document = try JSON.parse(#"{"a": [1, 2.5, -3, true, null, "x"], "b": {"c": ""}}"#)
    #expect(document["a"]?.array == [.int(1), .double(2.5), .int(-3), .bool(true), .null, .string("x")])
    #expect(document["b"]?["c"]?.string == "")
    #expect(document["missing"] == nil)
    #expect(document["a"]?[1]?.int == nil, "a number with a fraction is not an integer")
    #expect(document["a"]?[3]?.int == nil, "true is not 1")
}

@Test func wholeNumbersAreIntegersHoweverWritten() throws {
    // The coder reads 1.0 as 1; the contract leaves number formatting open.
    #expect(try JSON.parse("[1.0, 2.5, 3599]").array == [.int(1), .double(2.5), .int(3599)])
}

@Test func parsesEscapesAndSurrogatePairs() throws {
    let document = try JSON.parse(#"["a\"b\\c\/d\n\u00e9\ud83d\ude00"]"#)
    #expect(document[0]?.string == "a\"b\\c/d\né😀")
}

@Test func rejectsBrokenDocuments() {
    // Foundation's decoder forgives a trailing comma, as in [1,]; everything else it refuses.
    for text in ["", "{", "{\"a\" 1}", "[01]", "[1] 2", "[\"unterminated", "[tru]", "[1 2]"] {
        #expect(throws: JSONError.self, "\(text) should not parse") { try JSON.parse(text) }
    }
}

@Test func serializesSortedCompactAndUTF8() throws {
    let document: JSON = ["b": .null, "a": [1, "ñ · €", true], "c": ["d": .double(1.5), "e": "a/b"]]
    #expect(document.serialized() == #"{"a":[1,"ñ · €",true],"b":null,"c":{"d":1.5,"e":"a/b"}}"#)
    let pretty = document.serialized(pretty: true)
    #expect(pretty.contains("\n  "))
    #expect(try JSON.parse(pretty) == document)
}

@Test func escapesControlCharactersAndQuotes() throws {
    let original = "tab\t quote\" slash\\ nul\u{0} bell\u{07}"
    let text = JSON.array([.string(original)]).serialized()
    #expect(!text.unicodeScalars.contains { $0.value < 0x20 }, "control characters are escaped")
    #expect(text.contains(#"\""#) && text.contains(#"\\"#))
    #expect(try JSON.parse(text)[0]?.string == original)
}

@Test func nonFiniteNumbersBecomeNull() {
    #expect(JSON.array([.double(.infinity), .double(.nan)]).serialized() == "[null,null]")
}

@Test func roundTripsThroughData() throws {
    let document: JSON = ["raw": "AAEC", "threadId": "t1", "count": 3]
    #expect(try JSON.parse(document.data) == document)
}
