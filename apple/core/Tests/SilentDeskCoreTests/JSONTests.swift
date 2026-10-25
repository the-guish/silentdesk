import Foundation
@testable import SilentDeskCore
import Testing

@Test func parsesEveryKindOfValue() throws {
    let document = try JSON.parse(#"{"a": [1, 2.5, -3, 1e2, true, null, "x"], "b": {"c": ""}}"#)
    #expect(document["a"]?.array == [.int(1), .double(2.5), .int(-3), .double(100), .bool(true), .null, .string("x")])
    #expect(document["b"]?["c"]?.string == "")
    #expect(document["missing"] == nil)
    #expect(document["a"]?[1]?.int == nil, "a number with a fraction is not an integer")
}

@Test func parsesEscapesAndSurrogatePairs() throws {
    let document = try JSON.parse(#""a\"b\\c\/d\né😀""#)
    #expect(document.string == "a\"b\\c/d\né😀")
}

@Test func rejectsBrokenDocuments() {
    for text in ["", "{", "[1,]", "{\"a\" 1}", "01", "1 2", "\"unterminated", "tru", "{\"a\":1,}"] {
        #expect(throws: JSONError.self, "\(text) should not parse") { try JSON.parse(text) }
    }
}

@Test func serializesSortedCompactAndUTF8() {
    let document: JSON = ["b": .null, "a": [1, "ñ · €", true], "c": ["d": .double(1.5)]]
    #expect(document.serialized() == #"{"a":[1,"ñ · €",true],"b":null,"c":{"d":1.5}}"#)
    #expect(document.serialized(indent: 2) == """
        {
          "a": [
            1,
            "ñ · €",
            true
          ],
          "b": null,
          "c": {
            "d": 1.5
          }
        }
        """)
}

@Test func escapesControlCharactersAndQuotes() throws {
    let text = JSON.string("tab\t quote\" slash\\ nul\u{0} bell\u{07}").serialized()
    #expect(text == #""tab\t quote\" slash\\ nul\u0000 bell\u0007""#)
    #expect(try JSON.parse(text).string == "tab\t quote\" slash\\ nul\u{0} bell\u{07}")
}

@Test func roundTripsThroughData() throws {
    let document: JSON = ["raw": "AAEC", "threadId": "t1", "count": 3]
    #expect(try JSON.parse(document.data) == document)
}
