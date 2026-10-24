import Foundation
import SilentDeskCLI

let result = CLI.run(Array(CommandLine.arguments.dropFirst()))
FileHandle.standardOutput.write(result.output + Data("\n".utf8))
exit(result.exitCode)
