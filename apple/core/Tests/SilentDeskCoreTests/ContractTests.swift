// The contract's values never show a secret when printed, as the Python
// core's dataclasses hide them from repr().
import Foundation
@testable import SilentDeskCore
import Testing

@Test func tokensAndClientsHideTheirSecretsWhenPrinted() {
    let tokens = Tokens(accessToken: "access-secret", refreshToken: "refresh-secret", scopes: ["a"], raw: ["access_token": "access-secret"])
    let printed = "\(tokens)"
    #expect(!printed.contains("secret"))
    #expect(printed.contains("scopes: [\"a\"]"))

    let client = OAuthClient(service: "gmail", authorizeURL: "https://a", tokenURL: "https://t", clientID: "cid", clientSecret: "client-secret")
    #expect(!"\(client)".contains("client-secret"))
    #expect("\(client)".contains("cid"))

    let response = Response(status: 200, headers: [:], body: Data("{\"access_token\": \"body-secret\"}".utf8))
    #expect(!"\(response)".contains("body-secret"))
    #expect("\(response)".contains("200"))
}
