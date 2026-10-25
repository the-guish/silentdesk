/// Wires the app's own adapters into its application.
enum DeskWiring {
    static func create(connectors: [any Connector], settings: any Settings, database: any Database) -> any Desk {
        let clock: any Clock = settings.now.map { FixedClock($0) } ?? SystemClock()
        return DeskService(connectors: connectors, store: SqlcipherTopicStore(database: database), clock: clock)
    }
}
